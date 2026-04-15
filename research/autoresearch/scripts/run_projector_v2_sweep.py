"""Sweep runner for the projector-v2 lane.

Executes the walk-forward backtest once per variant on a shared set of
slices, with a synthetic-data fallback when the canonical parquets are
not present in the worktree (e.g. CI runs without the data submodule).

The runner is intentionally self-contained: it does NOT modify the
public backtester. Each variant is injected by monkey-patching
``the_similarity.api.project`` to call the variant module's
``project`` function for the duration of one backtest, then
restoring the original.

Walk-forward invariant (MANDATORY):
    The variant's ``project`` signature is identical to the baseline
    (same positional + keyword args), so the backtester keeps its
    "no look-ahead" guarantee — only the lookback slice is ever
    handed to the variant. Variants must not peek at any data beyond
    what they are passed.

Artifacts written (relative to repo root):
    progress/autoresearch/reports/projector-v2-v1.md
    progress/autoresearch/reports/projector-v2-<variant>-<slice>.json
    progress/autoresearch/experiments.jsonl   (append-only)
"""

from __future__ import annotations

import argparse
import importlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

from the_similarity import backtest
from the_similarity import api as _api_module
from the_similarity.config import Config


# ---------------------------------------------------------------------------
# Path and catalogue constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports"
LEDGER_PATH = REPO_ROOT / "progress" / "autoresearch" / "experiments.jsonl"
REPORT_MARKDOWN = REPORT_DIR / "projector-v2-v1.md"


# Canonical slices mirror research/autoresearch/benchmarks/projector-v2-core-v1.yaml.
# If a parquet is absent the runner generates a deterministic synthetic
# series so the sweep is still runnable in minimal environments.
CANONICAL_SLICES: list[dict[str, Any]] = [
    {
        "id": "spy-1d",
        "dataset_path": "the-similarity-data/data/stocks/spy/1d.parquet",
        "synthetic_seed": 101,
        "synthetic_bars": 2500,
    },
    {
        "id": "btc-1d",
        "dataset_path": "the-similarity-data/data/crypto/btc_usdt/1d.parquet",
        "synthetic_seed": 202,
        "synthetic_bars": 2500,
    },
]


# Variant registry. Each entry names a module exposing a
# ``project(matches, history, forward_bars, percentiles, config, **kwargs)``
# function; the ``extra`` dict is forwarded as keyword arguments.
VARIANT_REGISTRY: dict[str, dict[str, Any]] = {
    "baseline": {
        "module": "the_similarity.core.projector",
        "extra": {},
        "description": "Bar-wise weighted-quantile cone (reference).",
    },
    "adaptive_conformal": {
        "module": "the_similarity.core.projector_adaptive_conformal",
        "extra": {"mode": "adaptive", "alpha_target": 0.20, "lr": 0.05},
        "description": "Gibbs-Candès adaptive conformal recalibration.",
    },
    "change_aware_conformal": {
        "module": "the_similarity.core.projector_adaptive_conformal",
        "extra": {"mode": "change_aware", "alpha_target": 0.20, "lr": 0.05},
        "description": "Adaptive conformal with variance-jump down-weighting.",
    },
    "regime_aware_widening": {
        "module": "the_similarity.core.projector_regime_aware",
        "extra": {},
        "description": "Per-regime multiplicative cone widening.",
    },
    "joint_path": {
        "module": "the_similarity.core.projector_joint_path",
        "extra": {"n_paths": 500, "noise_fraction": 0.25},
        "description": "Correlated joint-path sampler.",
    },
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SliceReport:
    """Per-variant, per-slice scorecard."""

    slice_id: str
    variant: str
    dataset_path: str
    synthetic: bool
    n_valid_trials: int
    n_skipped_trials: int
    hit_rate: float
    mean_error: float
    crps: float
    calibration_error_p10_p90: float
    calibration_error_over_time_p10_p90: float
    joint_path_crps: float
    runtime_seconds: float


@dataclass
class VariantAggregate:
    """Aggregate scorecard across slices for one variant."""

    variant: str
    slices_evaluated: int
    hit_rate: float
    mean_error: float
    crps: float
    calibration_error_p10_p90: float
    calibration_error_over_time_p10_p90: float
    joint_path_crps: float
    runtime_seconds: float


# ---------------------------------------------------------------------------
# Data loading (with synthetic fallback)
# ---------------------------------------------------------------------------


def _load_series(slice_spec: dict[str, Any]) -> tuple[np.ndarray, bool]:
    """Return (prices, synthetic_flag). Real parquet takes precedence."""
    path = REPO_ROOT / slice_spec["dataset_path"]
    if path.exists() and path.is_file() and path.stat().st_size > 0:
        from the_similarity import load

        series = load(str(path))
        return series.values.astype(np.float64), False

    # Synthetic fallback: geometric Brownian motion with regime shifts.
    # Deterministic per-slice via ``synthetic_seed`` so sweep runs are
    # reproducible across machines without the data submodule.
    rng = np.random.default_rng(int(slice_spec["synthetic_seed"]))
    n = int(slice_spec["synthetic_bars"])
    # Two-regime GBM: first half low-vol drift, second half high-vol choppy.
    ret1 = rng.normal(0.0003, 0.01, size=n // 2)
    ret2 = rng.normal(-0.0001, 0.025, size=n - n // 2)
    log_returns = np.concatenate([ret1, ret2])
    prices = 100.0 * np.exp(np.cumsum(log_returns))
    return prices, True


# ---------------------------------------------------------------------------
# Variant injection
# ---------------------------------------------------------------------------


def _make_patched_project(variant_module: str, extras: dict[str, Any]) -> Callable:
    """Return a ``project`` replacement for the duration of one backtest.

    The backtester's ``_run_single_trial`` does
    ``from the_similarity.api import search, project`` inside the worker,
    so we monkey-patch ``_api_module.project`` with a wrapper that calls
    the variant module's ``project`` with the supplied ``extras``.
    """
    variant = importlib.import_module(variant_module)

    def _wrapped(
        matches,
        history,
        forward_bars: int = 50,
        percentiles=None,
        query=None,
        config=None,
    ):
        from the_similarity.api import SearchResults
        from the_similarity.io.loader import TimeSeries

        # Normalise callers the same way api.project does — keep behaviour
        # identical for the backtester.
        if isinstance(matches, SearchResults):
            matches_list = matches.matches
            query = matches.query if query is None else query
        else:
            matches_list = matches

        h_values = (
            history.values
            if isinstance(history, TimeSeries)
            else np.asarray(history, dtype=np.float64)
        )

        forecast = variant.project(
            matches=matches_list,
            history=h_values,
            forward_bars=forward_bars,
            percentiles=percentiles,
            config=config,
            **extras,
        )
        return forecast

    return _wrapped


# ---------------------------------------------------------------------------
# Scorecard computation
# ---------------------------------------------------------------------------


def _score_report(report, slice_id: str, variant: str, dataset_path: str, synthetic: bool, runtime: float) -> SliceReport:
    from the_similarity.core.metrics import (
        calibration_error_over_time,
        joint_path_crps,
    )

    cal = {int(k): float(v) for k, v in report.calibration.items()}
    # calibration_error_p10_p90 is the same metric used in projector-v1 so
    # the two lanes are directly comparable.
    deltas: list[float] = []
    for pct in (10, 90):
        if pct in cal:
            deltas.append(abs(cal[pct] - pct / 100.0))
    cal_err = float(np.mean(deltas)) if deltas else 0.0

    over_time = calibration_error_over_time(report.valid_trials, percentiles=[10, 90])
    over_time_mean = float(
        np.mean([v for v in over_time.values() if np.isfinite(v)]) if over_time else 0.0
    )
    jp_crps = float(joint_path_crps(report.valid_trials))

    return SliceReport(
        slice_id=slice_id,
        variant=variant,
        dataset_path=dataset_path,
        synthetic=synthetic,
        n_valid_trials=int(report.n_valid_trials),
        n_skipped_trials=int(report.n_skipped_trials),
        hit_rate=float(report.hit_rate),
        mean_error=float(report.mean_error),
        crps=float(report.crps),
        calibration_error_p10_p90=cal_err,
        calibration_error_over_time_p10_p90=over_time_mean,
        joint_path_crps=jp_crps,
        runtime_seconds=float(runtime),
    )


def _aggregate(reports: list[SliceReport]) -> VariantAggregate:
    """Mean-aggregate per-slice reports for one variant."""
    if not reports:
        raise ValueError("Cannot aggregate zero reports")
    n = len(reports)
    variant = reports[0].variant
    runtime_total = sum(r.runtime_seconds for r in reports)

    def _mean(attr: str) -> float:
        values = [getattr(r, attr) for r in reports if np.isfinite(getattr(r, attr))]
        return float(np.mean(values)) if values else float("nan")

    return VariantAggregate(
        variant=variant,
        slices_evaluated=n,
        hit_rate=_mean("hit_rate"),
        mean_error=_mean("mean_error"),
        crps=_mean("crps"),
        calibration_error_p10_p90=_mean("calibration_error_p10_p90"),
        calibration_error_over_time_p10_p90=_mean("calibration_error_over_time_p10_p90"),
        joint_path_crps=_mean("joint_path_crps"),
        runtime_seconds=runtime_total,
    )


# ---------------------------------------------------------------------------
# Sweep driver
# ---------------------------------------------------------------------------


def _run_variant_on_slice(
    *,
    variant_name: str,
    variant_spec: dict[str, Any],
    slice_spec: dict[str, Any],
    window_size: int,
    forward_bars: int,
    n_trials: int,
    seed: int,
    top_k: int,
    config: Config,
) -> SliceReport:
    """Execute one (variant, slice) combination."""
    prices, synthetic = _load_series(slice_spec)

    # Patch api.project — the backtester imports lazily inside each worker,
    # so we need to keep the patch in place for the duration of the run.
    original = _api_module.project
    try:
        if variant_name == "baseline":
            # Baseline = leave api.project untouched (calls projector.project).
            patched = None
        else:
            patched = _make_patched_project(variant_spec["module"], variant_spec["extra"])
            _api_module.project = patched  # type: ignore[assignment]

        started = time.perf_counter()
        report = backtest(
            prices,
            window_size=window_size,
            forward_bars=forward_bars,
            n_trials=n_trials,
            seed=seed,
            n_workers=1,  # deterministic runtime; sequential for comparability
            config=config,
            top_k=top_k,
        )
        runtime = time.perf_counter() - started
    finally:
        if patched is not None:
            _api_module.project = original  # type: ignore[assignment]

    return _score_report(
        report,
        slice_id=slice_spec["id"],
        variant=variant_name,
        dataset_path=slice_spec["dataset_path"],
        synthetic=synthetic,
        runtime=runtime,
    )


# ---------------------------------------------------------------------------
# Decision logic per variant (playbook rules)
# ---------------------------------------------------------------------------


def _decide_keep_discard(
    variant_agg: VariantAggregate,
    baseline_agg: VariantAggregate,
    *,
    min_cal_improvement: float = 0.005,
    max_crps_regression: float = 0.10,
) -> dict[str, Any]:
    """Apply the playbook's keep/discard rule to one variant."""
    crps_delta = variant_agg.crps - baseline_agg.crps
    cal_delta = (
        variant_agg.calibration_error_p10_p90 - baseline_agg.calibration_error_p10_p90
    )
    jp_delta = variant_agg.joint_path_crps - baseline_agg.joint_path_crps
    over_time_delta = (
        variant_agg.calibration_error_over_time_p10_p90
        - baseline_agg.calibration_error_over_time_p10_p90
    )
    hr_delta = variant_agg.hit_rate - baseline_agg.hit_rate
    rt_ratio = (
        variant_agg.runtime_seconds / baseline_agg.runtime_seconds
        if baseline_agg.runtime_seconds > 0
        else 1.0
    )

    crps_rel = crps_delta / baseline_agg.crps if baseline_agg.crps > 0 else 0.0

    hard_regression = False
    if crps_rel > max_crps_regression:
        hard_regression = True
    if variant_agg.hit_rate < 0.45:
        hard_regression = True

    crps_improved = crps_delta < 0
    cal_improved = cal_delta < -min_cal_improvement

    if hard_regression:
        decision = "discard"
    elif crps_improved or cal_improved:
        decision = "keep"
    else:
        decision = "discard"

    return {
        "crps_delta": crps_delta,
        "crps_relative": crps_rel,
        "calibration_error_delta": cal_delta,
        "joint_path_crps_delta": jp_delta,
        "calibration_over_time_delta": over_time_delta,
        "hit_rate_delta": hr_delta,
        "runtime_ratio": rt_ratio,
        "hard_regression": hard_regression,
        "decision": decision,
    }


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------


def _write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markdown_report(
    *,
    timestamp: str,
    per_variant: dict[str, VariantAggregate],
    per_slice: dict[str, list[SliceReport]],
    decisions: dict[str, dict[str, Any]],
) -> None:
    """Summarise the sweep in a keep/discard-per-variant markdown report."""
    lines: list[str] = []
    lines.append("# Projector v2 sweep — v1")
    lines.append("")
    lines.append(f"Generated: {timestamp}")
    lines.append("")
    lines.append("## Aggregate scorecard")
    lines.append("")
    lines.append(
        "| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Decision |"
    )
    lines.append(
        "|---------|------|------------------|--------------------|-----------|----------|-------------|----------|"
    )
    for name, agg in per_variant.items():
        dec = decisions.get(name, {})
        decision_str = dec.get("decision", "baseline")
        lines.append(
            f"| `{name}` | {agg.crps:.5f} | {agg.calibration_error_p10_p90:.4f} | "
            f"{agg.calibration_error_over_time_p10_p90:.4f} | {agg.joint_path_crps:.5f} | "
            f"{agg.hit_rate:.1%} | {agg.runtime_seconds:.1f} | {decision_str} |"
        )
    lines.append("")
    lines.append("## Per-slice breakdown")
    for slice_id, slice_reports in per_slice.items():
        lines.append("")
        lines.append(f"### {slice_id}")
        lines.append("")
        lines.append(
            "| Variant | CRPS | Cal. err P10/P90 | Cal. err over time | Joint CRPS | Hit rate | Runtime (s) | Synthetic |"
        )
        lines.append(
            "|---------|------|------------------|--------------------|-----------|----------|-------------|-----------|"
        )
        for sr in slice_reports:
            lines.append(
                f"| `{sr.variant}` | {sr.crps:.5f} | {sr.calibration_error_p10_p90:.4f} | "
                f"{sr.calibration_error_over_time_p10_p90:.4f} | {sr.joint_path_crps:.5f} | "
                f"{sr.hit_rate:.1%} | {sr.runtime_seconds:.1f} | {sr.synthetic} |"
            )
    lines.append("")
    lines.append("## Keep / discard notes")
    for name, dec in decisions.items():
        lines.append("")
        lines.append(f"- **`{name}`** — {dec.get('decision', 'baseline')}")
        lines.append(
            f"  - CRPS Δ: {dec.get('crps_delta', 0):.5f} "
            f"(rel {dec.get('crps_relative', 0):+.1%})"
        )
        lines.append(
            f"  - Calibration P10/P90 Δ: {dec.get('calibration_error_delta', 0):+.4f}"
        )
        lines.append(
            f"  - Joint CRPS Δ: {dec.get('joint_path_crps_delta', 0):+.5f}"
        )
        lines.append(
            f"  - Over-time calibration Δ: {dec.get('calibration_over_time_delta', 0):+.4f}"
        )
        lines.append(
            f"  - Hit rate Δ: {dec.get('hit_rate_delta', 0):+.1%}, runtime ×{dec.get('runtime_ratio', 1):.2f}"
        )
    REPORT_MARKDOWN.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MARKDOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_ledger_entry(
    *,
    variant: str,
    baseline_agg: VariantAggregate,
    variant_agg: VariantAggregate,
    decision_info: dict[str, Any],
    timestamp: str,
    branch: str,
) -> None:
    """Append one ledger entry per variant (baseline records decision=baseline)."""
    entry = {
        "run_id": f"projector-v2-{variant}-{timestamp}",
        "timestamp": timestamp,
        "benchmark_id": "projector-v2-core-v1",
        "lane_id": "projector-v2-lane-v1",
        "branch": branch,
        "commit_before": None,
        "commit_after": None,
        "status": "ok",
        "decision": decision_info.get("decision", "baseline"),
        "summary": (
            f"projector-v2 variant '{variant}': "
            f"CRPS {variant_agg.crps:.5f} (Δ {decision_info.get('crps_delta', 0):+.5f}), "
            f"cal_err {variant_agg.calibration_error_p10_p90:.4f}, "
            f"joint_crps {variant_agg.joint_path_crps:.5f}"
        ),
        "slices": [slice_spec["id"] for slice_spec in CANONICAL_SLICES],
        "artifacts": [f"progress/autoresearch/reports/projector-v2-v1.md"],
        "metrics_before": {
            "crps": baseline_agg.crps,
            "calibration_error_p10_p90": baseline_agg.calibration_error_p10_p90,
            "joint_path_crps": baseline_agg.joint_path_crps,
            "hit_rate": baseline_agg.hit_rate,
            "runtime_seconds": baseline_agg.runtime_seconds,
        },
        "metrics_after": {
            "crps": variant_agg.crps,
            "calibration_error_p10_p90": variant_agg.calibration_error_p10_p90,
            "joint_path_crps": variant_agg.joint_path_crps,
            "hit_rate": variant_agg.hit_rate,
            "runtime_seconds": variant_agg.runtime_seconds,
        },
        "regressions": [],
        "notes": json.dumps({"variant": variant}),
    }

    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the projector-v2 lane sweep.")
    parser.add_argument("--window-size", type=int, default=60)
    parser.add_argument("--forward-bars", type=int, default=30)
    parser.add_argument("--n-trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--variants",
        nargs="+",
        default=list(VARIANT_REGISTRY.keys()),
        help="Which variants to run. Defaults to all (including baseline).",
    )
    parser.add_argument(
        "--append-ledger",
        action="store_true",
        help="Append one ledger entry per variant to experiments.jsonl.",
    )
    parser.add_argument(
        "--branch",
        default="feat/projector-v2-lane",
        help="Branch name to record in ledger entries.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Baseline must always run first so decisions compare against it.
    variants = list(args.variants)
    if "baseline" in variants:
        variants.remove("baseline")
    variants = ["baseline", *variants]

    config = Config()

    per_variant_aggregates: dict[str, VariantAggregate] = {}
    per_slice: dict[str, list[SliceReport]] = {s["id"]: [] for s in CANONICAL_SLICES}

    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for variant_name in variants:
        variant_spec = VARIANT_REGISTRY[variant_name]
        variant_reports: list[SliceReport] = []
        for slice_spec in CANONICAL_SLICES:
            slice_report = _run_variant_on_slice(
                variant_name=variant_name,
                variant_spec=variant_spec,
                slice_spec=slice_spec,
                window_size=args.window_size,
                forward_bars=args.forward_bars,
                n_trials=args.n_trials,
                seed=args.seed,
                top_k=args.top_k,
                config=config,
            )
            variant_reports.append(slice_report)
            per_slice[slice_spec["id"]].append(slice_report)

            # Per-(variant, slice) JSON report for reproducibility.
            report_path = REPORT_DIR / f"projector-v2-{variant_name}-{slice_spec['id']}.json"
            _write_json_report(report_path, asdict(slice_report))

        per_variant_aggregates[variant_name] = _aggregate(variant_reports)

    # Decisions (baseline itself has no comparison).
    decisions: dict[str, dict[str, Any]] = {"baseline": {"decision": "baseline"}}
    baseline_agg = per_variant_aggregates["baseline"]
    for name in variants:
        if name == "baseline":
            continue
        decisions[name] = _decide_keep_discard(per_variant_aggregates[name], baseline_agg)

    _write_markdown_report(
        timestamp=timestamp,
        per_variant=per_variant_aggregates,
        per_slice=per_slice,
        decisions=decisions,
    )

    if args.append_ledger:
        for name in variants:
            _append_ledger_entry(
                variant=name,
                baseline_agg=baseline_agg,
                variant_agg=per_variant_aggregates[name],
                decision_info=decisions.get(name, {}),
                timestamp=timestamp,
                branch=args.branch,
            )

    # Console summary
    print("=" * 70)
    print(f"Projector v2 sweep — {timestamp}")
    print("=" * 70)
    for name in variants:
        agg = per_variant_aggregates[name]
        dec = decisions.get(name, {})
        print(
            f"  {name:<26} CRPS={agg.crps:.5f}  cal_err={agg.calibration_error_p10_p90:.4f}  "
            f"jpCRPS={agg.joint_path_crps:.5f}  hr={agg.hit_rate:.1%}  "
            f"runtime={agg.runtime_seconds:.1f}s  decision={dec.get('decision', 'baseline')}"
        )
    print(f"\nReport: {REPORT_MARKDOWN.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
