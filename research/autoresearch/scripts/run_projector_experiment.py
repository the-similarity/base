"""Run a single projector-calibration experiment and log results.

This script is the operational backbone of the projector-calibration lane.
It takes Config overrides as CLI arguments, runs the walk-forward backtest
through the public API, compares metrics against a baseline (if provided),
and appends a structured ledger entry.

Lifecycle:
1. Parse CLI overrides for projector-related Config fields.
2. Resolve dataset paths from repo root.
3. Run the public backtest API with the overridden Config.
4. Compute scorecard metrics including calibration_error_p10_p90.
5. Compare against a baseline report (optional) and decide keep/discard.
6. Write a JSON report under ``progress/autoresearch/reports/``.
7. Optionally append a JSONL ledger entry.

Write scope invariant:
- Writes ONLY under ``progress/autoresearch/`` and ``research/autoresearch/``.
- Never mutates engine code, benchmark manifests, or ``pyproject.toml``.
- Exits on missing datasets rather than guessing.
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
# Path constants
# ---------------------------------------------------------------------------
# Repo root is three directories up from this script:
#   research/autoresearch/scripts/run_projector_experiment.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Default datasets — same slices used by the baseline runner so that
# metrics are directly comparable.
DEFAULT_DATASETS = [
    "the-similarity-data/data/stocks/spy/1d.parquet",
    "the-similarity-data/data/crypto/btc_usdt/1d.parquet",
]

DEFAULT_REPORT_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports"
DEFAULT_LEDGER_PATH = REPO_ROOT / "progress" / "autoresearch" / "experiments.jsonl"


# ---------------------------------------------------------------------------
# Dataclasses for structured reporting
# ---------------------------------------------------------------------------

@dataclass
class DatasetReport:
    """Per-dataset scorecard for one experiment run."""

    dataset_path: str
    series_name: str
    n_valid_trials: int
    n_skipped_trials: int
    hit_rate: float
    mean_error: float
    crps: float
    calibration: dict[int, float]
    calibration_error_p10_p90: float
    runtime_seconds: float


@dataclass
class AggregateReport:
    """Mean aggregation across dataset reports."""

    datasets_evaluated: int
    hit_rate: float
    mean_error: float
    crps: float
    calibration_error_p10_p90: float
    runtime_seconds: float


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for projector experiment configuration.

    Projector-specific overrides (confidence_decay_rate, koopman_blend_weight,
    cone_width_scale) map directly to Config fields or to post-processing
    parameters in the experiment harness.
    """
    parser = argparse.ArgumentParser(
        description="Run a projector-calibration experiment against the benchmark.",
    )

    # Dataset and benchmark parameters (match the YAML manifest)
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=DEFAULT_DATASETS,
        help="Repo-relative parquet paths to evaluate.",
    )
    parser.add_argument("--window-size", type=int, default=60)
    parser.add_argument("--forward-bars", type=int, default=30)
    parser.add_argument("--n-trials", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top-k", type=int, default=10)

    # Projector overrides — these are the experiment's independent variables
    parser.add_argument(
        "--confidence-decay-rate",
        type=float,
        default=None,
        help="Override Config.confidence_decay_rate (default: use Config default).",
    )
    parser.add_argument(
        "--koopman-blend-weight",
        type=float,
        default=None,
        help="Override Config.koopman_blend_weight (default: use Config default).",
    )

    # Lane metadata
    parser.add_argument("--benchmark-id", default="projector-calibration-core-v1")
    parser.add_argument("--lane-id", default="projector-calibration-lane-v1")
    parser.add_argument("--run-id", default=None, help="Custom run ID (auto-generated if omitted).")
    parser.add_argument("--branch", default="feat/projector-calibration")
    parser.add_argument("--report-name", default=None, help="Report filename (auto-generated if omitted).")
    parser.add_argument("--experiment-tag", default="projector-experiment", help="Short tag for the experiment.")

    # Baseline comparison
    parser.add_argument(
        "--baseline-report",
        type=str,
        default=None,
        help="Path to a baseline report JSON for comparison.",
    )

    # Ledger control
    parser.add_argument(
        "--append-ledger",
        action="store_true",
        help="Append an entry to progress/autoresearch/experiments.jsonl.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def calibration_error_p10_p90(calibration: dict[int, float]) -> float:
    """Compute mean absolute deviation of P10 and P90 containment from nominal.

    A perfectly calibrated cone has:
        containment(P10) = 0.10
        containment(P90) = 0.90

    This metric averages |actual - expected| across both.
    Lower is better; 0.0 is perfect calibration.
    """
    target_percentiles = [10, 90]
    deltas: list[float] = []
    for percentile in target_percentiles:
        if percentile in calibration:
            deltas.append(abs(calibration[percentile] - percentile / 100.0))
    if not deltas:
        return 0.0
    return sum(deltas) / len(deltas)


# ---------------------------------------------------------------------------
# Core experiment runner
# ---------------------------------------------------------------------------

def build_config(args: argparse.Namespace) -> Config:
    """Build a Config instance with projector-specific overrides applied.

    Only overrides fields that were explicitly provided on the CLI.
    All other fields keep their default values, ensuring we only
    change the independent variable under test.
    """
    config = Config()

    if args.confidence_decay_rate is not None:
        config.confidence_decay_rate = args.confidence_decay_rate

    if args.koopman_blend_weight is not None:
        config.koopman_blend_weight = args.koopman_blend_weight

    return config


def run_one_dataset(
    dataset_path: str,
    *,
    window_size: int,
    forward_bars: int,
    n_trials: int,
    seed: int,
    top_k: int,
    config: Config,
) -> DatasetReport:
    """Run the walk-forward backtest on a single dataset slice.

    Uses single-worker mode (n_workers=1) for deterministic, comparable
    runtime measurements across experiments.
    """
    resolved = REPO_ROOT / dataset_path
    if not resolved.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {resolved}")

    series = load(str(resolved))

    started = time.perf_counter()
    report = backtest(
        series,
        window_size=window_size,
        forward_bars=forward_bars,
        n_trials=n_trials,
        seed=seed,
        n_workers=1,
        config=config,
        top_k=top_k,
    )
    runtime_seconds = time.perf_counter() - started

    cal = {int(k): float(v) for k, v in report.calibration.items()}

    return DatasetReport(
        dataset_path=dataset_path,
        series_name=series.name or resolved.stem,
        n_valid_trials=int(report.n_valid_trials),
        n_skipped_trials=int(report.n_skipped_trials),
        hit_rate=float(report.hit_rate),
        mean_error=float(report.mean_error),
        crps=float(report.crps),
        calibration=cal,
        calibration_error_p10_p90=float(calibration_error_p10_p90(cal)),
        runtime_seconds=float(runtime_seconds),
    )


def aggregate(reports: list[DatasetReport]) -> AggregateReport:
    """Compute mean metrics across dataset reports."""
    count = len(reports)
    if count == 0:
        raise ValueError("Cannot aggregate zero dataset reports")
    return AggregateReport(
        datasets_evaluated=count,
        hit_rate=sum(r.hit_rate for r in reports) / count,
        mean_error=sum(r.mean_error for r in reports) / count,
        crps=sum(r.crps for r in reports) / count,
        calibration_error_p10_p90=sum(r.calibration_error_p10_p90 for r in reports) / count,
        runtime_seconds=sum(r.runtime_seconds for r in reports),
    )


# ---------------------------------------------------------------------------
# Comparison and decision logic
# ---------------------------------------------------------------------------

def compare_to_baseline(
    current: AggregateReport,
    baseline_path: str,
) -> dict[str, Any]:
    """Compare current experiment results against a stored baseline report.

    Returns a dict with deltas, relative changes, and an auto-decision.

    Decision logic (matching the playbook keep/discard criteria):
    - KEEP: at least one primary metric improves AND no hard regression
    - DISCARD: CRPS worsens >10% or hit_rate drops below 45%
    - NEUTRAL: no clear improvement or regression
    """
    path = Path(baseline_path)
    if not path.is_absolute():
        path = REPO_ROOT / path

    if not path.exists():
        return {"error": f"Baseline report not found: {path}", "decision": "retry"}

    with path.open("r", encoding="utf-8") as f:
        baseline_data = json.load(f)

    baseline_agg = baseline_data.get("aggregate", {})
    baseline_crps = baseline_agg.get("crps", float("nan"))
    baseline_cal_err = baseline_agg.get("calibration_error_p10_p90", float("nan"))
    baseline_hr = baseline_agg.get("hit_rate", float("nan"))

    # Compute deltas (negative = improvement for crps/cal_err, positive = improvement for hit_rate)
    crps_delta = current.crps - baseline_crps
    cal_err_delta = current.calibration_error_p10_p90 - baseline_cal_err
    hr_delta = current.hit_rate - baseline_hr

    # Relative change for CRPS regression check
    crps_relative = crps_delta / baseline_crps if baseline_crps != 0 else 0.0

    # Decision logic per the playbook
    hard_regression = False
    if crps_relative > 0.10:
        hard_regression = True
    if current.hit_rate < 0.45:
        hard_regression = True

    # Check for improvement in at least one primary metric
    crps_improved = crps_delta < 0
    cal_improved = cal_err_delta < 0

    if hard_regression:
        decision = "discard"
    elif crps_improved or cal_improved:
        decision = "keep"
    else:
        decision = "discard"

    return {
        "baseline_report": str(path),
        "baseline_crps": baseline_crps,
        "baseline_calibration_error_p10_p90": baseline_cal_err,
        "baseline_hit_rate": baseline_hr,
        "crps_delta": crps_delta,
        "calibration_error_delta": cal_err_delta,
        "hit_rate_delta": hr_delta,
        "crps_relative_change": crps_relative,
        "hard_regression": hard_regression,
        "crps_improved": crps_improved,
        "calibration_improved": cal_improved,
        "decision": decision,
    }


# ---------------------------------------------------------------------------
# Reporting and ledger
# ---------------------------------------------------------------------------

def write_report(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON experiment report to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def append_ledger_entry(
    *,
    ledger_path: Path,
    run_id: str,
    benchmark_id: str,
    lane_id: str,
    branch: str,
    report_name: str,
    current: AggregateReport,
    baseline_metrics: dict[str, Any],
    decision: str,
    summary: str,
    config_overrides: dict[str, Any],
) -> None:
    """Append a JSONL ledger entry conforming to experiment-ledger.schema.json.

    Each entry captures the before/after metrics, the decision, and a
    human-readable summary so that future agents can reconstruct the
    experimental history without reading every report file.
    """
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    entry = {
        "run_id": run_id,
        "timestamp": timestamp,
        "benchmark_id": benchmark_id,
        "lane_id": lane_id,
        "branch": branch,
        "commit_before": None,
        "commit_after": None,
        "status": "ok",
        "decision": decision,
        "summary": summary,
        "slices": [
            Path(ds).parts[-3] + "-" + Path(ds).stem
            for ds in DEFAULT_DATASETS
        ],
        "artifacts": [f"progress/autoresearch/reports/{report_name}"],
        "metrics_before": baseline_metrics,
        "metrics_after": {
            "crps": current.crps,
            "calibration_error_p10_p90": current.calibration_error_p10_p90,
            "hit_rate": current.hit_rate,
            "mean_error": current.mean_error,
            "runtime_seconds": current.runtime_seconds,
        },
        "regressions": [],
        "notes": json.dumps(config_overrides),
    }

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the projector-calibration experiment end-to-end."""
    args = _parse_args()
    config = build_config(args)

    # Track which Config fields were overridden for the ledger
    config_overrides: dict[str, Any] = {}
    if args.confidence_decay_rate is not None:
        config_overrides["confidence_decay_rate"] = args.confidence_decay_rate
    if args.koopman_blend_weight is not None:
        config_overrides["koopman_blend_weight"] = args.koopman_blend_weight

    # --- Run backtest on each dataset slice ---
    dataset_reports = [
        run_one_dataset(
            dataset_path,
            window_size=args.window_size,
            forward_bars=args.forward_bars,
            n_trials=args.n_trials,
            seed=args.seed,
            top_k=args.top_k,
            config=config,
        )
        for dataset_path in args.datasets
    ]

    agg = aggregate(dataset_reports)

    # --- Compare against baseline if provided ---
    comparison: dict[str, Any] | None = None
    decision = "keep"  # default when no baseline is available
    if args.baseline_report:
        comparison = compare_to_baseline(agg, args.baseline_report)
        decision = comparison.get("decision", "keep")

    # --- Generate report ---
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run_id = args.run_id or f"proj-{args.experiment_tag}-{timestamp}"

    report_name = args.report_name or f"projector-{args.experiment_tag}-{args.seed}.json"

    payload: dict[str, Any] = {
        "generated_at": timestamp,
        "benchmark_id": args.benchmark_id,
        "lane_id": args.lane_id,
        "run_id": run_id,
        "config_overrides": config_overrides,
        "parameters": {
            "window_size": args.window_size,
            "forward_bars": args.forward_bars,
            "n_trials": args.n_trials,
            "seed": args.seed,
            "top_k": args.top_k,
            "datasets": args.datasets,
        },
        "dataset_reports": [asdict(report) for report in dataset_reports],
        "aggregate": asdict(agg),
        "decision": decision,
    }

    if comparison is not None:
        payload["comparison"] = comparison

    report_path = DEFAULT_REPORT_DIR / report_name
    write_report(report_path, payload)

    # --- Append ledger entry ---
    if args.append_ledger:
        baseline_metrics: dict[str, Any] = {}
        if comparison and "error" not in comparison:
            baseline_metrics = {
                "crps": comparison["baseline_crps"],
                "calibration_error_p10_p90": comparison["baseline_calibration_error_p10_p90"],
                "hit_rate": comparison["baseline_hit_rate"],
            }

        overrides_str = ", ".join(f"{k}={v}" for k, v in config_overrides.items()) or "defaults"
        summary = f"Projector experiment [{args.experiment_tag}] with {overrides_str}. Decision: {decision}."

        append_ledger_entry(
            ledger_path=DEFAULT_LEDGER_PATH,
            run_id=run_id,
            benchmark_id=args.benchmark_id,
            lane_id=args.lane_id,
            branch=args.branch,
            report_name=report_name,
            current=agg,
            baseline_metrics=baseline_metrics,
            decision=decision,
            summary=summary,
            config_overrides=config_overrides,
        )

    # --- Console output ---
    print("=" * 60)
    print(f"Projector Experiment: {args.experiment_tag}")
    print(f"Config overrides: {config_overrides or 'defaults'}")
    print("=" * 60)
    print(json.dumps(asdict(agg), indent=2, sort_keys=True))
    print(f"\nDecision: {decision}")
    print(f"Report: {report_path.relative_to(REPO_ROOT)}")
    if args.append_ledger:
        print(f"Ledger: {DEFAULT_LEDGER_PATH.relative_to(REPO_ROOT)}")

    if comparison:
        print("\n--- Comparison ---")
        for key in ["crps_delta", "calibration_error_delta", "hit_rate_delta", "hard_regression"]:
            if key in comparison:
                print(f"  {key}: {comparison[key]}")


if __name__ == "__main__":
    main()
