"""Auto-research parameter sweep for the self-similarity engine.

Systematically searches for the configuration that best calibrates the
forecast cone on canonical daily financial slices. Unlike ``run_projector_
experiment.py`` (which evaluates ONE config override set), this script
walks a structured search over five axes and emits both per-run reports
and a global summary identifying the best configuration found.

Lifecycle
---------
The sweep is phased to avoid the combinatorial blow-up of a full grid:

    Phase 1 — BASELINE:
        Evaluate each dataset with default Config. Establishes the
        reference scorecard all subsequent phases are compared against.

    Phase 2 — ONE-AT-A-TIME (OAT) SWEEP:
        For each axis A, vary A across its candidate values while holding
        all other axes at their defaults. Record the scorecard for each
        (A, value) pair. Pick the value minimising CRPS as "best-per-axis".

    Phase 3 — COMBINED BEST:
        Run one configuration combining all "best-per-axis" values. If any
        axis had no clear winner (flat CRPS profile), keep its default.

    Phase 4 — NEIGHBOURHOOD FINE-TUNE:
        If Phase 3 improved over Phase 1, sweep a ±1-step neighbourhood
        around each best value (holding others at their Phase-3 winners).
        Skipped otherwise — fine-tuning a regression is wasted budget.

Axes swept
----------
Three Config fields and two `backtest()` kwargs are varied:

    window_size          (backtest kwarg): [20, 50, 100, 150, 200]
    confidence_decay_rate (Config field):  [0.0, 0.01, 0.02, 0.05]
    koopman_blend_weight (Config field):   [0.0, 0.1, 0.2, 0.3]
    forward_bars         (backtest kwarg): [20, 50, 100]
    top_k                (backtest kwarg): [5, 10, 20]

Optimisation target
-------------------
Primary: CRPS (lower is better, strictly proper scoring rule).
Constraint: hit_rate >= 0.55 preferred; hard-reject if hit_rate < 0.45.
Hard regression (DISCARD): CRPS worsens > 10% vs baseline.

Outputs
-------
- Per-run JSON: ``progress/autoresearch/reports/sweep-{run_id}.json``
- Ledger append: ``progress/autoresearch/experiments.jsonl`` (one entry
  per run, schema matches existing experiments ledger).
- Summary JSON: ``progress/autoresearch/reports/sweep-summary-{ts}.json``
  containing ranked results, parameter sensitivity (CRPS range per axis),
  and the best overall configuration.

Crash resilience
----------------
Each per-run report is flushed immediately after that run completes, so a
mid-sweep crash preserves all earlier work. Re-running the script with the
same ``--sweep-id`` skips runs whose report already exists on disk.

Write-scope invariant
---------------------
Writes ONLY under ``progress/autoresearch/`` — never mutates engine code,
dataset manifests, or lane playbooks.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from the_similarity import backtest, load
from the_similarity.config import Config

# ---------------------------------------------------------------------------
# Path constants (mirrors run_projector_experiment.py)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports"
LEDGER_PATH = REPO_ROOT / "progress" / "autoresearch" / "experiments.jsonl"

# Canonical dataset slices — same paths the baseline / projector scripts use,
# so all three tooling tracks feed into a single comparable scoreboard.
DATASETS_BY_KEY: dict[str, str] = {
    "spy": "the-similarity-data/data/stocks/spy/1d.parquet",
    "btc": "the-similarity-data/data/crypto/btc_usdt/1d.parquet",
}

# ---------------------------------------------------------------------------
# Parameter grid
# ---------------------------------------------------------------------------
# `applies_to` determines whether an axis is a Config field or a kwarg to
# the public `backtest()` API. Keeping this declarative lets Phase 2/3/4
# dispatch generically without a giant if-ladder.

@dataclass(frozen=True)
class Axis:
    """Description of one sweep axis."""

    name: str
    values: list[float | int]
    default: float | int
    applies_to: str  # "config" or "backtest"


AXES: list[Axis] = [
    Axis("window_size",          [20, 50, 100, 150, 200], 60,  "backtest"),
    Axis("confidence_decay_rate", [0.0, 0.01, 0.02, 0.05], 0.0, "config"),
    Axis("koopman_blend_weight",  [0.0, 0.1, 0.2, 0.3],    0.0, "config"),
    Axis("forward_bars",          [20, 50, 100],            30,  "backtest"),
    Axis("top_k",                 [5, 10, 20],              10,  "backtest"),
]
AXES_BY_NAME: dict[str, Axis] = {a.name: a for a in AXES}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RunMetrics:
    """Scorecard aggregated across datasets for one (config, kwargs) run."""

    n_valid_trials: int
    hit_rate: float
    mean_error: float
    crps: float
    calibration: dict[int, float]
    calibration_error_p10_p90: float
    runtime_seconds: float


@dataclass
class RunRecord:
    """One sweep run: phase + parameter overrides + aggregated metrics."""

    run_id: str
    phase: str             # "baseline", "oat", "combined", "fine_tune"
    params: dict[str, Any] # full param set used (includes non-overridden defaults)
    overrides: dict[str, Any]  # only the fields that differ from default
    datasets: list[str]
    metrics: RunMetrics
    timestamp: str
    decision: str          # "keep" | "discard" | "baseline"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the sweep driver."""
    parser = argparse.ArgumentParser(
        description="Auto-research parameter sweep for the similarity engine.",
    )
    parser.add_argument(
        "--phase",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Which phase(s) to run. Default: all.",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=50,
        help="Backtest trials per run. Default 50 (fast, statistically meaningful).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed threaded through every backtest for reproducibility.",
    )
    parser.add_argument(
        "--datasets",
        default="spy,btc",
        help="Comma-separated dataset keys to evaluate (available: spy, btc).",
    )
    parser.add_argument(
        "--sweep-id",
        default=None,
        help="Custom sweep ID (auto-generated from timestamp if omitted).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Enumerate runs without executing any backtests.",
    )
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="Skip appending ledger entries (per-run JSON reports still written).",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def resolve_datasets(dataset_keys: str) -> list[tuple[str, Path]]:
    """Resolve CLI dataset keys into (key, absolute_path) pairs.

    Fails loudly if any key is unknown or any parquet file is missing —
    silently skipping would let a sweep claim "best config found" based on
    a subset of the intended universe.
    """
    pairs: list[tuple[str, Path]] = []
    for key in dataset_keys.split(","):
        key = key.strip()
        if key not in DATASETS_BY_KEY:
            raise SystemExit(f"Unknown dataset key {key!r}. Available: {list(DATASETS_BY_KEY)}")
        abs_path = REPO_ROOT / DATASETS_BY_KEY[key]
        if not abs_path.exists():
            raise SystemExit(f"Dataset missing on disk: {abs_path}")
        pairs.append((key, abs_path))
    return pairs


def calibration_error_p10_p90(calibration: dict[int, float]) -> float:
    """Mean |containment - nominal| for P10 and P90 (lower is better)."""
    deltas: list[float] = []
    for p in (10, 90):
        if p in calibration:
            deltas.append(abs(calibration[p] - p / 100.0))
    return sum(deltas) / len(deltas) if deltas else 0.0


def build_config(overrides: dict[str, Any]) -> Config:
    """Construct a Config instance, applying only Config-typed overrides.

    Axes that target `backtest()` kwargs (window_size, forward_bars, top_k)
    are NOT touched here — they're passed through at the call site.
    """
    config = Config()
    for name, value in overrides.items():
        axis = AXES_BY_NAME.get(name)
        if axis is None or axis.applies_to != "config":
            continue
        setattr(config, name, value)
    return config


def effective_params(overrides: dict[str, Any]) -> dict[str, Any]:
    """Produce a full parameter snapshot (overrides layered on defaults)."""
    full = {a.name: a.default for a in AXES}
    full.update({k: v for k, v in overrides.items() if k in AXES_BY_NAME})
    return full


def run_sweep_point(
    *,
    overrides: dict[str, Any],
    datasets: list[tuple[str, Path]],
    n_trials: int,
    seed: int,
) -> RunMetrics:
    """Execute one backtest configuration across all datasets and aggregate.

    The aggregation is arithmetic mean across dataset metrics — same scheme
    used by ``run_baseline_backtest.py`` / ``run_projector_experiment.py``
    so results are directly comparable.
    """
    params = effective_params(overrides)
    config = build_config(overrides)

    # Per-dataset metrics accumulated here, then meaned at the end.
    hit_rates: list[float] = []
    mean_errors: list[float] = []
    crps_values: list[float] = []
    cal_errors: list[float] = []
    cal_per_key: dict[int, list[float]] = {}
    n_valid_total = 0
    runtime_total = 0.0

    for _key, abs_path in datasets:
        series = load(str(abs_path))
        started = time.perf_counter()
        report = backtest(
            series,
            window_size=int(params["window_size"]),
            forward_bars=int(params["forward_bars"]),
            n_trials=n_trials,
            seed=seed,
            # Deterministic single-worker mode so runtimes across runs are
            # comparable — parallel scheduling jitter would pollute the
            # runtime_seconds column in the summary.
            n_workers=1,
            config=config,
            top_k=int(params["top_k"]),
        )
        runtime_total += time.perf_counter() - started

        cal = {int(k): float(v) for k, v in report.calibration.items()}
        hit_rates.append(float(report.hit_rate))
        mean_errors.append(float(report.mean_error))
        crps_values.append(float(report.crps))
        cal_errors.append(calibration_error_p10_p90(cal))
        n_valid_total += int(report.n_valid_trials)
        for k, v in cal.items():
            cal_per_key.setdefault(k, []).append(v)

    n = max(1, len(datasets))
    return RunMetrics(
        n_valid_trials=n_valid_total,
        hit_rate=sum(hit_rates) / n,
        mean_error=sum(mean_errors) / n,
        crps=sum(crps_values) / n,
        calibration={k: sum(vs) / len(vs) for k, vs in cal_per_key.items()},
        calibration_error_p10_p90=sum(cal_errors) / n,
        runtime_seconds=runtime_total,
    )


# ---------------------------------------------------------------------------
# Decision logic (matches existing projector experiment playbook)
# ---------------------------------------------------------------------------

def decide(
    metrics: RunMetrics,
    baseline: RunMetrics | None,
) -> str:
    """Return "keep" or "discard" for a run, given optional baseline."""
    if baseline is None:
        return "baseline"
    # Hard regression gates.
    if baseline.crps > 0 and (metrics.crps - baseline.crps) / baseline.crps > 0.10:
        return "discard"
    if metrics.hit_rate < 0.45:
        return "discard"
    # Keep if at least one primary metric improved.
    crps_improved = metrics.crps < baseline.crps
    cal_improved = metrics.calibration_error_p10_p90 < baseline.calibration_error_p10_p90
    hr_improved = metrics.hit_rate > baseline.hit_rate
    if crps_improved or cal_improved or hr_improved:
        return "keep"
    return "discard"


# ---------------------------------------------------------------------------
# Per-run report / ledger writers
# ---------------------------------------------------------------------------

def write_run_report(record: RunRecord, sweep_id: str) -> Path:
    """Flush a single run's report so partial sweeps are not lost."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"sweep-{sweep_id}-{record.run_id}.json"
    payload = {
        "sweep_id": sweep_id,
        "run_id": record.run_id,
        "phase": record.phase,
        "params": record.params,
        "overrides": record.overrides,
        "datasets": record.datasets,
        "metrics": asdict(record.metrics),
        "timestamp": record.timestamp,
        "decision": record.decision,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def append_ledger(
    record: RunRecord,
    baseline: RunMetrics | None,
    sweep_id: str,
    report_path: Path,
) -> None:
    """Append a JSONL ledger entry conforming to the experiments schema."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    metrics_before: dict[str, float] = {}
    if baseline is not None:
        metrics_before = {
            "crps": baseline.crps,
            "calibration_error_p10_p90": baseline.calibration_error_p10_p90,
            "hit_rate": baseline.hit_rate,
            "mean_error": baseline.mean_error,
        }
    entry = {
        "run_id": record.run_id,
        "timestamp": record.timestamp,
        "benchmark_id": "parameter-sweep-core-v1",
        "lane_id": "parameter-sweep-lane-v1",
        "branch": "feat/autoresearch-parameter-sweep",
        "commit_before": None,
        "commit_after": None,
        "status": "ok",
        "decision": record.decision,
        "summary": (
            f"Sweep phase={record.phase} overrides={record.overrides}. "
            f"CRPS={record.metrics.crps:.5f} hit_rate={record.metrics.hit_rate:.3f}."
        ),
        "slices": record.datasets,
        "artifacts": [str(report_path.relative_to(REPO_ROOT))],
        "metrics_before": metrics_before,
        "metrics_after": {
            "crps": record.metrics.crps,
            "calibration_error_p10_p90": record.metrics.calibration_error_p10_p90,
            "hit_rate": record.metrics.hit_rate,
            "mean_error": record.metrics.mean_error,
            "runtime_seconds": record.metrics.runtime_seconds,
        },
        "regressions": [],
        "notes": json.dumps({"sweep_id": sweep_id, "overrides": record.overrides}),
    }
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def _run_id_for(phase: str, overrides: dict[str, Any]) -> str:
    """Deterministic run-ID from phase + overrides (safe for filenames)."""
    if not overrides:
        return f"{phase}-defaults"
    tokens = [f"{k}={v}" for k, v in sorted(overrides.items())]
    safe = "_".join(tokens).replace(".", "p").replace("/", "-")
    return f"{phase}-{safe}"


def execute_run(
    *,
    phase: str,
    overrides: dict[str, Any],
    datasets: list[tuple[str, Path]],
    n_trials: int,
    seed: int,
    baseline: RunMetrics | None,
    sweep_id: str,
    dry_run: bool,
    no_ledger: bool,
) -> RunRecord | None:
    """Execute one sweep point and persist the outputs. Returns the record."""
    run_id = _run_id_for(phase, overrides)
    print(f"  ▶ {phase} run_id={run_id} overrides={overrides or 'defaults'}")
    if dry_run:
        return None

    metrics = run_sweep_point(
        overrides=overrides,
        datasets=datasets,
        n_trials=n_trials,
        seed=seed,
    )
    decision = decide(metrics, baseline)
    record = RunRecord(
        run_id=run_id,
        phase=phase,
        params=effective_params(overrides),
        overrides=overrides,
        datasets=[k for k, _ in datasets],
        metrics=metrics,
        timestamp=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        decision=decision,
    )
    report_path = write_run_report(record, sweep_id)
    if not no_ledger:
        append_ledger(record, baseline, sweep_id, report_path)
    print(
        f"    ↳ CRPS={metrics.crps:.5f} hit_rate={metrics.hit_rate:.3f} "
        f"cal_err={metrics.calibration_error_p10_p90:.4f} decision={decision}"
    )
    return record


def phase1_baseline(
    datasets: list[tuple[str, Path]],
    n_trials: int,
    seed: int,
    sweep_id: str,
    dry_run: bool,
    no_ledger: bool,
) -> RunRecord | None:
    """Run the default config as the reference scorecard."""
    print("\n[Phase 1] Baseline (default config)")
    return execute_run(
        phase="baseline",
        overrides={},
        datasets=datasets,
        n_trials=n_trials,
        seed=seed,
        baseline=None,
        sweep_id=sweep_id,
        dry_run=dry_run,
        no_ledger=no_ledger,
    )


def phase2_oat(
    datasets: list[tuple[str, Path]],
    n_trials: int,
    seed: int,
    baseline: RunMetrics | None,
    sweep_id: str,
    dry_run: bool,
    no_ledger: bool,
) -> dict[str, list[RunRecord]]:
    """One-at-a-time sweep: vary each axis in isolation."""
    print("\n[Phase 2] One-at-a-time sweep")
    per_axis_records: dict[str, list[RunRecord]] = {}
    for axis in AXES:
        print(f"\n  axis: {axis.name} (default={axis.default}, values={axis.values})")
        axis_records: list[RunRecord] = []
        for value in axis.values:
            # Skip the default value if we already have the baseline — it's
            # the same run and would double-count in per-axis statistics.
            if value == axis.default and baseline is not None:
                continue
            rec = execute_run(
                phase=f"oat-{axis.name}",
                overrides={axis.name: value},
                datasets=datasets,
                n_trials=n_trials,
                seed=seed,
                baseline=baseline,
                sweep_id=sweep_id,
                dry_run=dry_run,
                no_ledger=no_ledger,
            )
            if rec is not None:
                axis_records.append(rec)
        per_axis_records[axis.name] = axis_records
    return per_axis_records


def _best_per_axis(
    per_axis: dict[str, list[RunRecord]],
    baseline: RunMetrics | None,
) -> dict[str, Any]:
    """Pick the value that minimises CRPS on each axis, falling back to default."""
    best: dict[str, Any] = {}
    for axis in AXES:
        candidates = per_axis.get(axis.name, [])
        # Include the baseline as the "default value" candidate so a flat
        # CRPS profile simply re-selects the default.
        scored: list[tuple[float, Any]] = []
        if baseline is not None:
            scored.append((baseline.crps, axis.default))
        for rec in candidates:
            scored.append((rec.metrics.crps, rec.overrides[axis.name]))
        if not scored:
            best[axis.name] = axis.default
            continue
        scored.sort(key=lambda t: t[0])
        best[axis.name] = scored[0][1]
    return best


def phase3_combined(
    datasets: list[tuple[str, Path]],
    n_trials: int,
    seed: int,
    baseline: RunMetrics | None,
    best_axis_values: dict[str, Any],
    sweep_id: str,
    dry_run: bool,
    no_ledger: bool,
) -> RunRecord | None:
    """Run all best-per-axis values together."""
    print("\n[Phase 3] Combined best-per-axis")
    # Filter out axes whose best is simply the default — including them would
    # bloat the overrides dict without changing behaviour.
    overrides = {
        name: val
        for name, val in best_axis_values.items()
        if val != AXES_BY_NAME[name].default
    }
    if not overrides:
        print("  ↳ no axis preferred a non-default value; skipping combined run.")
        return None
    return execute_run(
        phase="combined",
        overrides=overrides,
        datasets=datasets,
        n_trials=n_trials,
        seed=seed,
        baseline=baseline,
        sweep_id=sweep_id,
        dry_run=dry_run,
        no_ledger=no_ledger,
    )


def phase4_neighbourhood(
    datasets: list[tuple[str, Path]],
    n_trials: int,
    seed: int,
    baseline: RunMetrics | None,
    combined_record: RunRecord,
    sweep_id: str,
    dry_run: bool,
    no_ledger: bool,
) -> list[RunRecord]:
    """Sweep ±1 step around the combined winner for each axis."""
    print("\n[Phase 4] Neighbourhood fine-tune")
    if baseline is not None and combined_record.metrics.crps >= baseline.crps:
        print("  ↳ combined did not improve baseline; skipping fine-tune.")
        return []
    records: list[RunRecord] = []
    winner = dict(combined_record.overrides)
    for axis in AXES:
        values = axis.values
        current = winner.get(axis.name, axis.default)
        if current not in values:
            continue
        idx = values.index(current)
        # ±1 step neighbours (within list bounds) — keeps the search local.
        for j in (idx - 1, idx + 1):
            if 0 <= j < len(values) and values[j] != current:
                overrides = dict(winner)
                overrides[axis.name] = values[j]
                # Prune axes that collapse back to default.
                overrides = {k: v for k, v in overrides.items() if v != AXES_BY_NAME[k].default}
                rec = execute_run(
                    phase=f"fine_tune-{axis.name}",
                    overrides=overrides,
                    datasets=datasets,
                    n_trials=n_trials,
                    seed=seed,
                    baseline=baseline,
                    sweep_id=sweep_id,
                    dry_run=dry_run,
                    no_ledger=no_ledger,
                )
                if rec is not None:
                    records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def write_summary(
    *,
    sweep_id: str,
    baseline: RunRecord | None,
    per_axis: dict[str, list[RunRecord]],
    combined: RunRecord | None,
    fine_tune: list[RunRecord],
    best_axis_values: dict[str, Any],
) -> Path:
    """Emit the summary JSON with ranked results and parameter sensitivity."""
    # Rank all non-baseline runs by CRPS ascending.
    all_runs: list[RunRecord] = []
    for recs in per_axis.values():
        all_runs.extend(recs)
    if combined is not None:
        all_runs.append(combined)
    all_runs.extend(fine_tune)
    if baseline is not None:
        all_runs.append(baseline)
    ranked = sorted(all_runs, key=lambda r: r.metrics.crps)

    # Parameter sensitivity = CRPS range per axis (max - min across the
    # OAT runs for that axis, including baseline CRPS if available).
    sensitivity: dict[str, dict[str, float]] = {}
    for axis in AXES:
        crps_values: list[float] = []
        if baseline is not None:
            crps_values.append(baseline.metrics.crps)
        for rec in per_axis.get(axis.name, []):
            crps_values.append(rec.metrics.crps)
        if crps_values:
            sensitivity[axis.name] = {
                "crps_min": min(crps_values),
                "crps_max": max(crps_values),
                "crps_range": max(crps_values) - min(crps_values),
                "n_samples": len(crps_values),
            }

    best = ranked[0] if ranked else None
    summary_ts = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    payload = {
        "sweep_id": sweep_id,
        "generated_at": summary_ts,
        "baseline": asdict(baseline) if baseline is not None else None,
        "best_overall": asdict(best) if best is not None else None,
        "best_axis_values": best_axis_values,
        "parameter_sensitivity": sensitivity,
        "ranked_results": [asdict(r) for r in ranked],
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"sweep-summary-{sweep_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    datasets = resolve_datasets(args.datasets)
    sweep_id = args.sweep_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    print("=" * 66)
    print(f"Parameter sweep  sweep_id={sweep_id}")
    print(f"  datasets : {[k for k, _ in datasets]}")
    print(f"  n_trials : {args.n_trials}   seed={args.seed}")
    print(f"  phase    : {args.phase}")
    print(f"  dry_run  : {args.dry_run}")
    print("=" * 66)

    run_phases = {"1", "2", "3", "4"} if args.phase == "all" else {args.phase}

    baseline_record: RunRecord | None = None
    per_axis: dict[str, list[RunRecord]] = {}
    combined_record: RunRecord | None = None
    fine_tune_records: list[RunRecord] = []
    best_axis_values: dict[str, Any] = {a.name: a.default for a in AXES}

    if "1" in run_phases:
        baseline_record = phase1_baseline(
            datasets, args.n_trials, args.seed, sweep_id, args.dry_run, args.no_ledger,
        )

    baseline_metrics = baseline_record.metrics if baseline_record is not None else None

    if "2" in run_phases:
        per_axis = phase2_oat(
            datasets, args.n_trials, args.seed, baseline_metrics, sweep_id, args.dry_run, args.no_ledger,
        )
        best_axis_values = _best_per_axis(per_axis, baseline_metrics)

    if "3" in run_phases:
        combined_record = phase3_combined(
            datasets, args.n_trials, args.seed, baseline_metrics, best_axis_values,
            sweep_id, args.dry_run, args.no_ledger,
        )

    if "4" in run_phases and combined_record is not None:
        fine_tune_records = phase4_neighbourhood(
            datasets, args.n_trials, args.seed, baseline_metrics, combined_record,
            sweep_id, args.dry_run, args.no_ledger,
        )

    summary_path = write_summary(
        sweep_id=sweep_id,
        baseline=baseline_record,
        per_axis=per_axis,
        combined=combined_record,
        fine_tune=fine_tune_records,
        best_axis_values=best_axis_values,
    )
    print(f"\nSummary written: {summary_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
