"""Experiment-ledger entry builder for the foundation-bench lane.

Schema matches ``progress/autoresearch/experiments.jsonl`` as used by
``retrieval-bench-tiers-v1`` and ``projector-v2-core-v1``:

    run_id, timestamp, benchmark_id, lane_id, status, decision,
    summary, slices, artifacts, metrics_before, metrics_after,
    regressions, notes

Design choices
--------------
* ``metrics_before`` carries the wavelet_baseline aggregate (classical
  lower bound); ``metrics_after`` carries the best foundation-model
  aggregate. This keeps the row scannable by dashboards that sort runs
  by primary-metric delta.
* ``status`` defaults to ``partial_synthetic_fallback`` whenever any
  non-wavelet cell fell back — honest label for offline CI runs.
* Each appended row is one JSONL line; never overwrites.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable

from research.autoresearch.foundation_bench.run_bench import CellResult


def _aggregate_model(cells: list[CellResult]) -> dict[str, float]:
    """Return {crps, cal, hit, rt_med} means across this model's cells.

    Cells with zero trials (e.g. every trial hit the budget cap) are
    excluded so the mean is not dragged toward 0.0 spuriously.
    """
    valid = [c for c in cells if c.n_trials > 0]
    n = len(valid) or 1
    return {
        "crps": sum(c.crps for c in valid) / n,
        "calibration_error_p10_p90": (
            sum(c.calibration_error_p10_p90 for c in valid) / n
        ),
        "hit_rate": sum(c.hit_rate for c in valid) / n,
        "runtime_seconds_median": (
            sum(c.runtime.get("median", 0.0) for c in valid) / n
        ),
    }


def _group_by_model(cells: Iterable[CellResult]) -> dict[str, list[CellResult]]:
    """Group cells by model id preserving insertion order."""
    out: dict[str, list[CellResult]] = {}
    for c in cells:
        out.setdefault(c.model_id, []).append(c)
    return out


def build_ledger_entry(
    cells: list[CellResult],
    *,
    run_id: str | None = None,
    lane_id: str = "foundation-bench-v1-lane",
    benchmark_id: str = "foundation-bench-v1",
    branch: str | None = None,
    artefacts: list[str] | None = None,
    commit_before: str | None = None,
    commit_after: str | None = None,
    n_trials: int = 0,
    seeds: list[int] | None = None,
) -> dict:
    """Build a single ledger entry for a foundation-bench run.

    Decision semantics:
        - ``decision="measured"`` — this lane measures, it does not
          promote. The 2A spec explicitly forbids changing engine
          defaults from this lane, so there is no ``keep``/``discard``
          verdict.

    Status semantics (honest labelling for offline CI):
        - all cells in synthetic fallback -> "partial_synthetic_fallback"
        - any cell in synthetic fallback  -> "partial_synthetic_fallback"
        - no cells in synthetic fallback  -> "ok"
        - every cell hit the budget cap   -> "aborted"
    """
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if run_id is None:
        run_id = f"{benchmark_id}-{ts}"

    # --- Status derivation ----------------------------------------------
    if not cells:
        status = "aborted"
    else:
        synthetic_cells = sum(1 for c in cells if c.any_fallback)
        fully_skipped = all(c.n_trials == 0 for c in cells)
        if fully_skipped:
            status = "aborted"
        elif synthetic_cells > 0:
            # Honest flag: any cell that fell back to synthetic marks the
            # whole run. Downstream dashboards can still read the per-cell
            # artefacts to see which were real.
            status = "partial_synthetic_fallback"
        else:
            status = "ok"

    # --- Metrics_before / metrics_after ---------------------------------
    #
    # metrics_before = the classical (wavelet_baseline) reference.
    # metrics_after  = the best-crps foundation-model aggregate, or the
    # wavelet baseline again if no foundation model had any real trials.
    by_model = _group_by_model(cells)
    wavelet = by_model.get("wavelet_baseline", [])
    metrics_before = _aggregate_model(wavelet)

    # Pick the foundation model with the lowest mean CRPS (all
    # foundation models share the same fallback taxonomy so this is
    # effectively "which fallback-aware forecaster had the tightest
    # cone on these slices").
    foundation_ids = [m for m in by_model if m != "wavelet_baseline"]
    best_id = None
    best_crps = float("inf")
    best_metrics: dict[str, float] = {}
    for mid in foundation_ids:
        agg = _aggregate_model(by_model[mid])
        if agg["crps"] < best_crps:
            best_crps = agg["crps"]
            best_id = mid
            best_metrics = agg
    metrics_after = best_metrics or metrics_before

    # --- Regressions list (informational only) --------------------------
    regressions: list[str] = []
    if status == "partial_synthetic_fallback":
        regressions.append(
            "Non-wavelet adapters ran under synthetic fallback; absolute "
            "metrics reflect the AR(1)/bootstrap cone, not pretrained "
            "foundation weights."
        )
    if not wavelet:
        regressions.append(
            "wavelet_baseline cells missing — classical lower bound "
            "cannot be computed for this run."
        )

    # --- Summary text ---------------------------------------------------
    summary_bits = [
        f"foundation-bench-v1 run on {len(cells)} cells "
        f"({len(by_model)} models × {len({c.slice_id for c in cells})} slices)."
    ]
    if wavelet:
        summary_bits.append(
            f"wavelet_baseline mean CRPS {metrics_before['crps']:.4f} "
            f"(cal {metrics_before['calibration_error_p10_p90']:.3f}, "
            f"hit {metrics_before['hit_rate']:.2f})."
        )
    if best_id:
        summary_bits.append(
            f"best foundation adapter: {best_id} CRPS {best_metrics['crps']:.4f} "
            f"(fallback={status == 'partial_synthetic_fallback'})."
        )

    entry: dict = {
        "run_id": run_id,
        "timestamp": ts,
        "benchmark_id": benchmark_id,
        "lane_id": lane_id,
        "status": status,
        "decision": "measured",
        "summary": " ".join(summary_bits),
        "slices": sorted({c.slice_id for c in cells}),
        "artifacts": artefacts or [],
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "regressions": regressions,
        "notes": (
            f"Measurement-only lane. Engine defaults unchanged. "
            f"n_trials={n_trials} seeds={seeds or []}. "
            f"Best foundation model: {best_id or 'n/a'}."
        ),
    }
    if branch:
        entry["branch"] = branch
    if commit_before:
        entry["commit_before"] = commit_before
    if commit_after:
        entry["commit_after"] = commit_after
    return entry


def append_ledger_entry(entry: dict, ledger_path: str | Path) -> Path:
    """Append one JSON-encoded entry as a line to the ledger.

    The ledger is JSONL; creates parent dir + file if missing.
    """
    p = Path(ledger_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return p
