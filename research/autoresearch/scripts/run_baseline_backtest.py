"""Run and log a baseline walk-forward backtest for autoresearch lanes.

This script operationalizes the first step of an autoresearch lane:
recording a reproducible baseline before any experimental signal is added.

Lifecycle:
1. Resolve one or more parquet datasets from local repo paths.
2. Load each dataset through the public loader.
3. Run the public walk-forward backtest API with fixed parameters.
4. Compute compact scorecard metrics, including a derived
   ``calibration_error_p10_p90`` value used by the autoresearch manifests.
5. Persist a machine-readable report under ``progress/autoresearch/reports/``.
6. Optionally append a matching JSONL ledger entry.

This helper is intentionally fail-closed:
- it writes only under ``progress/autoresearch/``,
- it does not mutate engine code or benchmark manifests,
- and it exits on missing dataset paths instead of guessing.
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

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASETS = [
    "the-similarity-data/data/stocks/spy/1d.parquet",
    "the-similarity-data/data/crypto/btc_usdt/1d.parquet",
]
DEFAULT_REPORT_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports"
DEFAULT_LEDGER_PATH = REPO_ROOT / "progress" / "autoresearch" / "experiments.jsonl"


@dataclass
class DatasetReport:
    """Compact per-dataset scorecard for one baseline run."""

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
    """Simple mean aggregation across dataset reports."""

    datasets_evaluated: int
    hit_rate: float
    mean_error: float
    crps: float
    calibration_error_p10_p90: float
    runtime_seconds: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a baseline autoresearch backtest.")
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
    parser.add_argument("--benchmark-id", default="jepa-retrieval-core-v1")
    parser.add_argument("--lane-id", default="jepa-retrieval-lane-v1")
    parser.add_argument("--branch", default="exp/jepa-baseline")
    parser.add_argument("--report-name", default="baseline-jepa-report.json")
    parser.add_argument(
        "--append-ledger",
        action="store_true",
        help="Append a baseline entry to progress/autoresearch/experiments.jsonl.",
    )
    return parser.parse_args()


def _calibration_error_p10_p90(calibration: dict[int, float]) -> float:
    target_percentiles = [10, 90]
    deltas: list[float] = []
    for percentile in target_percentiles:
        if percentile in calibration:
            deltas.append(abs(calibration[percentile] - percentile / 100.0))
    if not deltas:
        return 0.0
    return sum(deltas) / len(deltas)


def _run_one_dataset(
    dataset_path: str,
    *,
    window_size: int,
    forward_bars: int,
    n_trials: int,
    seed: int,
) -> DatasetReport:
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
    )
    runtime_seconds = time.perf_counter() - started
    calibration = {int(k): float(v) for k, v in report.calibration.items()}

    return DatasetReport(
        dataset_path=dataset_path,
        series_name=series.name or resolved.stem,
        n_valid_trials=int(report.n_valid_trials),
        n_skipped_trials=int(report.n_skipped_trials),
        hit_rate=float(report.hit_rate),
        mean_error=float(report.mean_error),
        crps=float(report.crps),
        calibration=calibration,
        calibration_error_p10_p90=float(_calibration_error_p10_p90(calibration)),
        runtime_seconds=float(runtime_seconds),
    )


def _aggregate(reports: list[DatasetReport]) -> AggregateReport:
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


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_ledger_entry(
    *,
    ledger_path: Path,
    benchmark_id: str,
    lane_id: str,
    branch: str,
    report_name: str,
    aggregate: AggregateReport,
    slices: list[str],
) -> None:
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run_id = f"baseline-jepa-{timestamp}"
    entry = {
        "run_id": run_id,
        "timestamp": timestamp,
        "benchmark_id": benchmark_id,
        "lane_id": lane_id,
        "branch": branch,
        "commit_before": None,
        "commit_after": None,
        "status": "ok",
        "decision": "keep",
        "summary": "Baseline walk-forward scorecard without JEPA signal.",
        "slices": slices,
        "artifacts": [f"progress/autoresearch/reports/{report_name}"],
        "metrics_before": {},
        "metrics_after": {
            "crps": aggregate.crps,
            "calibration_error_p10_p90": aggregate.calibration_error_p10_p90,
            "hit_rate": aggregate.hit_rate,
            "mean_error": aggregate.mean_error,
            "runtime_seconds": aggregate.runtime_seconds,
        },
        "regressions": [],
        "notes": "First baseline recorded before JEPA latent rerank experiments.",
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def main() -> None:
    args = _parse_args()
    dataset_reports = [
        _run_one_dataset(
            dataset_path,
            window_size=args.window_size,
            forward_bars=args.forward_bars,
            n_trials=args.n_trials,
            seed=args.seed,
        )
        for dataset_path in args.datasets
    ]
    aggregate = _aggregate(dataset_reports)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    payload = {
        "generated_at": generated_at,
        "benchmark_id": args.benchmark_id,
        "lane_id": args.lane_id,
        "parameters": {
            "window_size": args.window_size,
            "forward_bars": args.forward_bars,
            "n_trials": args.n_trials,
            "seed": args.seed,
            "datasets": args.datasets,
        },
        "dataset_reports": [asdict(report) for report in dataset_reports],
        "aggregate": asdict(aggregate),
    }

    report_path = DEFAULT_REPORT_DIR / args.report_name
    _write_report(report_path, payload)

    if args.append_ledger:
        slices = [Path(path).parts[-3] + "-" + Path(path).stem for path in args.datasets]
        _append_ledger_entry(
            ledger_path=DEFAULT_LEDGER_PATH,
            benchmark_id=args.benchmark_id,
            lane_id=args.lane_id,
            branch=args.branch,
            report_name=args.report_name,
            aggregate=aggregate,
            slices=slices,
        )

    print(json.dumps(payload["aggregate"], indent=2, sort_keys=True))
    print(f"report_written={report_path.relative_to(REPO_ROOT)}")
    if args.append_ledger:
        print(f"ledger_appended={DEFAULT_LEDGER_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
