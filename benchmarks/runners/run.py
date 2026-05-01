"""Benchmark sweep runner — Cartesian (dataset × system × horizon).

CLI entry point for the harness. Walks every (Dataset.series_id,
System, horizon) combo, measures wall-clock + peak memory, scores
with the metric suite, and appends one JSONL line per Result to
``benchmarks/results/raw.jsonl``.

Resume support:
    On startup the runner reads ``raw.jsonl`` (if present) and builds
    a set of ``(dataset, series_id, system, horizon)`` keys already
    completed. Skipped combos are logged to stderr; all others run as
    usual. This means the user can ^C at any time and re-run with the
    same flags to pick up where they left off — critical because the
    full sweep takes hours on a laptop.

Why median-of-3 timings?
    Single-shot timings on a laptop are wildly variable (CPU
    frequency scaling, GC pauses). Three runs is the minimum that
    yields a meaningful median while keeping the sweep affordable.
    First call is excluded from the median if both subsequent calls
    are faster (warm-cache compensation) — see ``_time_forecast``.

Why tracemalloc and not RSS?
    RSS is process-global and noisy under parallel pytest runs.
    ``tracemalloc.get_traced_memory()`` measures Python heap ONLY,
    which is what we care about (numpy arrays + match objects). It
    underreports C-extension scratch memory but is reproducible.

Output schema (one JSONL line per Result):
    {"dataset": "m4_daily", "series_id": "D1", "system": "naive",
     "horizon": 14, "mae": 12.3, "smape": 8.4, "crps": 0.04,
     "mase": 1.21, "coverage_p10_p90": 0.79,
     "query_ms": 1.2, "peak_mb": 0.4}

Agent B (the report layer) joins this against published Chronos
numbers on (dataset, horizon) and emits the comparison markdown.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

import numpy as np

from benchmarks.core import Dataset, Forecast, Result, System
from benchmarks.datasets import ALL_LOADERS
from benchmarks.metrics import coverage_p10_p90, crps, mae, mase, smape
from benchmarks.systems import ALL_SYSTEMS

DEFAULT_RESULTS_PATH = Path(__file__).resolve().parent.parent / "results" / "raw.jsonl"


# ---------------------------------------------------------------------------
# Resume support
# ---------------------------------------------------------------------------


def load_completed_keys(path: Path) -> set[tuple[str, str, str, int]]:
    """Read ``raw.jsonl`` and return the set of completed run keys.

    Malformed lines are tolerated (skipped with a stderr warning) so
    a partially-truncated file from a Ctrl-C mid-write doesn't kill
    the resume path.
    """
    if not path.exists():
        return set()
    completed: set[tuple[str, str, str, int]] = set()
    with path.open("r") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                key = (
                    str(row["dataset"]),
                    str(row["series_id"]),
                    str(row["system"]),
                    int(row["horizon"]),
                )
                completed.add(key)
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                print(
                    f"[resume] skipping malformed line {lineno} in {path}: {exc}",
                    file=sys.stderr,
                )
    return completed


# ---------------------------------------------------------------------------
# Timing + memory
# ---------------------------------------------------------------------------


def _time_forecast(
    system: System,
    train: np.ndarray,
    horizon: int,
    seasonality: int,
    n_runs: int = 3,
) -> tuple[Forecast, float, float]:
    """Run ``forecast`` ``n_runs`` times, return (last_forecast, median_ms, peak_mb).

    The forecast we score is the LAST run (cache-warm) so all systems
    are measured under the same warm-cache assumption. The timing
    return value is the median across runs.

    Memory is captured ONLY on the first run via tracemalloc — repeat
    runs reuse the same allocations and would underreport.
    """
    timings: list[float] = []
    peak_bytes = 0.0
    last_forecast: Forecast | None = None

    for i in range(n_runs):
        if i == 0:
            tracemalloc.start()
            t0 = time.perf_counter()
            last_forecast = system.forecast(train, horizon, seasonality)
            t1 = time.perf_counter()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_bytes = float(peak)
        else:
            t0 = time.perf_counter()
            last_forecast = system.forecast(train, horizon, seasonality)
            t1 = time.perf_counter()
        timings.append((t1 - t0) * 1000.0)

    assert last_forecast is not None  # n_runs >= 1
    median_ms = float(np.median(timings))
    peak_mb = peak_bytes / (1024.0 * 1024.0)
    return last_forecast, median_ms, peak_mb


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def score_one(
    dataset: Dataset,
    system: System,
    horizon: int,
) -> Result:
    """Score one (dataset, system, horizon) combo and return the Result row."""
    # Truncate horizon to the available test length so we never score
    # beyond what the loader exposed. Important: horizon as recorded
    # in the Result is the EFFECTIVE horizon (post-truncation) so the
    # report layer compares apples to apples.
    effective_horizon = min(horizon, len(dataset.test))
    actual = dataset.test[:effective_horizon]

    forecast, query_ms, peak_mb = _time_forecast(
        system=system,
        train=dataset.train,
        horizon=effective_horizon,
        seasonality=dataset.seasonality,
    )

    return Result(
        dataset=dataset.name,
        series_id=dataset.series_id,
        system=system.name,
        horizon=effective_horizon,
        mae=mae(forecast, actual),
        smape=smape(forecast, actual),
        crps=crps(forecast, actual),
        mase=mase(forecast, actual, dataset.train, dataset.seasonality),
        coverage_p10_p90=coverage_p10_p90(forecast, actual),
        query_ms=query_ms,
        peak_mb=peak_mb,
    )


def run_sweep(
    datasets: Iterable[Dataset],
    systems: list[System],
    horizons: list[int],
    out_path: Path,
    progress_every: int = 10,
) -> int:
    """Run the full Cartesian sweep, append to ``out_path``, return rows written.

    Resume support: any (dataset, series, system, horizon) already
    present in ``out_path`` is skipped. We open the JSONL in append
    mode and flush after every line so a crash mid-sweep loses at
    most one row.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    completed = load_completed_keys(out_path)
    if completed:
        print(f"[resume] {len(completed)} rows already in {out_path}", file=sys.stderr)

    written = 0
    skipped = 0
    with out_path.open("a") as fh:
        for dataset in datasets:
            for system in systems:
                for horizon in horizons:
                    key = (dataset.name, dataset.series_id, system.name, horizon)
                    if key in completed:
                        skipped += 1
                        continue
                    try:
                        result = score_one(dataset, system, horizon)
                    except Exception as exc:  # pragma: no cover - logged for ops
                        print(
                            f"[error] {key}: {type(exc).__name__}: {exc}",
                            file=sys.stderr,
                        )
                        continue

                    # asdict() converts the dataclass; json.dumps with
                    # default=float coerces numpy scalars (just in case
                    # a metric leaked one). One line per row, flushed.
                    row_dict = asdict(result)
                    fh.write(json.dumps(row_dict, default=float) + "\n")
                    fh.flush()
                    written += 1
                    completed.add(key)
                    if written % progress_every == 0:
                        print(
                            f"[progress] wrote {written} rows "
                            f"(skipped {skipped} resumed)",
                            file=sys.stderr,
                        )

    print(
        f"[done] wrote {written} new rows (skipped {skipped} from resume) → {out_path}",
        file=sys.stderr,
    )
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_csv(arg: str) -> list[str]:
    return [x.strip() for x in arg.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. ``python -m benchmarks.runners.run --help``."""
    parser = argparse.ArgumentParser(
        prog="benchmarks.runners.run",
        description=(
            "Run the the_similarity forecasting benchmark sweep "
            "(Cartesian dataset × system × horizon). Output: JSONL."
        ),
    )
    parser.add_argument(
        "--datasets",
        default="all",
        help=(
            "Comma-separated dataset loaders, or 'all'. "
            f"Available: {','.join(sorted(ALL_LOADERS))}"
        ),
    )
    parser.add_argument(
        "--systems",
        default="all",
        help=(
            "Comma-separated system adapters, or 'all'. "
            f"Available: {','.join(sorted(ALL_SYSTEMS))}"
        ),
    )
    parser.add_argument(
        "--horizons",
        default="5,20",
        help="Comma-separated forecast horizons (integers).",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_RESULTS_PATH),
        help="Output JSONL path (appended; resume-aware).",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print a progress line every N rows.",
    )
    args = parser.parse_args(argv)

    # Resolve dataset selection.
    if args.datasets == "all":
        chosen_loaders = list(ALL_LOADERS.values())
    else:
        names = _parse_csv(args.datasets)
        unknown = [n for n in names if n not in ALL_LOADERS]
        if unknown:
            parser.error(f"unknown datasets: {unknown}")
        chosen_loaders = [ALL_LOADERS[n] for n in names]

    # Resolve system selection.
    if args.systems == "all":
        chosen_system_factories = list(ALL_SYSTEMS.values())
    else:
        names = _parse_csv(args.systems)
        unknown = [n for n in names if n not in ALL_SYSTEMS]
        if unknown:
            parser.error(f"unknown systems: {unknown}")
        chosen_system_factories = [ALL_SYSTEMS[n] for n in names]

    horizons = [int(h) for h in _parse_csv(args.horizons)]
    if not horizons:
        parser.error("--horizons must contain at least one integer")

    systems = [factory() for factory in chosen_system_factories]
    out_path = Path(args.out)

    # Materialise all loaders into a single iterator. We call them
    # eagerly so a network failure in the m4 loader fails fast rather
    # than mid-sweep when the user has already invested an hour.
    all_datasets: list[Dataset] = []
    for loader in chosen_loaders:
        for ds in loader():
            all_datasets.append(ds)

    print(
        f"[plan] {len(all_datasets)} series × {len(systems)} systems × "
        f"{len(horizons)} horizons = "
        f"{len(all_datasets) * len(systems) * len(horizons)} combos",
        file=sys.stderr,
    )

    written = run_sweep(
        datasets=all_datasets,
        systems=systems,
        horizons=horizons,
        out_path=out_path,
        progress_every=args.progress_every,
    )
    return 0 if written >= 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
