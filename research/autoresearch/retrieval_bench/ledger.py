"""Experiment-ledger entry builder for the retrieval-bench lane.

The ledger (``progress/autoresearch/experiments.jsonl``) is the append-only
machine-readable log of every lane run.  Schema is defined at
``research/autoresearch/ledger/experiment-ledger.schema.json`` and requires
these fields:

    run_id, timestamp, benchmark_id, lane_id, status, decision,
    summary, metrics_before, metrics_after

This module builds a conformant entry from a ``Verdict`` and the artefact
paths, and appends it to the ledger file (never overwriting).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from research.autoresearch.retrieval_bench.compare import Verdict


def build_ledger_entry(
    verdict: Verdict,
    *,
    run_id: str | None = None,
    lane_id: str = "retrieval-bench-tiers-v1-lane",
    benchmark_id: str = "retrieval-bench-tiers-v1",
    branch: str | None = None,
    artefacts: list[str] | None = None,
    commit_before: str | None = None,
    commit_after: str | None = None,
) -> dict:
    """Build a ledger entry dictionary matching ``experiment-ledger.schema.json``.

    Status mapping:
        - ``verdict.decision == "keep"``  -> status "ok"
        - ``verdict.decision == "discard"`` -> status "discarded"

    ``metrics_before`` carries the Tier 1 (baseline) aggregates across slices;
    ``metrics_after`` carries the Tier 1+2 aggregates.  This makes the entry
    scannable by tools that sort runs by primary metric delta.
    """
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if run_id is None:
        run_id = f"retrieval-bench-tiers-v1-{ts}"

    status_map = {"keep": "ok", "discard": "discarded"}

    # Aggregate per-arm across slices (simple arithmetic means).
    rows = verdict.rows
    n = len(rows) or 1

    def _mean(key: str, arm: str) -> float:
        vals = [float(getattr(r, arm)[key]) for r in rows]
        return sum(vals) / n

    metrics_before = {
        "forward_return_correlation": _mean("forward_return_correlation", "tier1_only"),
        "crps": _mean("crps", "tier1_only"),
        "calibration_error_p10_p90": _mean("calibration_error_p10_p90", "tier1_only"),
        "hit_rate": _mean("hit_rate", "tier1_only"),
        "runtime_seconds_median": sum(
            float(r.tier1_only["runtime_seconds"]["median"]) for r in rows
        ) / n,
    }
    metrics_after = {
        "forward_return_correlation": _mean("forward_return_correlation", "tier1_plus_full"),
        "crps": _mean("crps", "tier1_plus_full"),
        "calibration_error_p10_p90": _mean("calibration_error_p10_p90", "tier1_plus_full"),
        "hit_rate": _mean("hit_rate", "tier1_plus_full"),
        "runtime_seconds_median": sum(
            float(r.tier1_plus_full["runtime_seconds"]["median"]) for r in rows
        ) / n,
        "runtime_multiplier_vs_baseline": verdict.mean_runtime_ratio,
    }

    regressions: list[str] = []
    if verdict.mean_d_crps > 0:
        regressions.append("CRPS worsened on average across slices")
    if verdict.mean_runtime_ratio > 3.0:
        regressions.append(
            f"Tier1+2 runtime is {verdict.mean_runtime_ratio:.1f}x Tier1"
        )

    entry: dict = {
        "run_id": run_id,
        "timestamp": ts,
        "benchmark_id": benchmark_id,
        "lane_id": lane_id,
        "status": status_map.get(verdict.decision, "aborted"),
        "decision": verdict.decision,
        "summary": verdict.rationale,
        "slices": [r.slice_id for r in rows],
        "artifacts": artefacts or [],
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "regressions": regressions,
        "notes": (
            f"Measurement lane: Tier 1 (SAX+MASS -> DTW + Pearson) vs Tier 1+2 "
            f"(9-method default). Walk-forward.  Engine defaults NOT changed by "
            f"this run."
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

    The ledger is JSONL (one object per line).  The function creates the
    parent directory and file if missing, and always writes a trailing
    newline so future appends are separated.
    """
    p = Path(ledger_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return p
