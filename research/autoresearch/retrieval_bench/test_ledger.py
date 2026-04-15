"""Tests for the experiment-ledger entry builder."""
from __future__ import annotations

import json

from research.autoresearch.retrieval_bench.compare import (
    build_comparison_rows,
    decide,
)
from research.autoresearch.retrieval_bench.ledger import (
    append_ledger_entry,
    build_ledger_entry,
)


def _mk_grouped(d_crps: float = -0.01, rt_ratio: float = 2.0):
    def _r(arm, sid, *, corr, crps, rt):
        return {
            "slice_id": sid,
            "arm_id": arm,
            "arm_label": arm,
            "n_trials": 10,
            "forward_return_correlation": corr,
            "crps": crps,
            "calibration_error_p10_p90": 0.1,
            "hit_rate": 0.6,
            "runtime_seconds": {"median": rt, "mean": rt, "p95": rt, "n": 10},
        }

    grouped = {}
    for i in range(3):
        grouped[f"slice-{i}"] = {
            "tier1_only": _r("tier1_only", f"slice-{i}", corr=0.0, crps=0.02, rt=1.0),
            "tier1_plus_full": _r(
                "tier1_plus_full", f"slice-{i}", corr=0.05, crps=0.02 + d_crps, rt=rt_ratio,
            ),
        }
    return grouped


def test_build_ledger_entry_has_required_schema_fields():
    grouped = _mk_grouped(d_crps=-0.01, rt_ratio=2.0)
    rows = build_comparison_rows(grouped)
    v = decide(rows, thresholds={"max_runtime_multiplier": 3.0, "min_slices_improved": 2})
    entry = build_ledger_entry(v, branch="feat/bench")
    for k in ("run_id", "timestamp", "benchmark_id", "lane_id", "status",
              "decision", "summary", "metrics_before", "metrics_after"):
        assert k in entry
    assert entry["decision"] in ("keep", "discard")
    # Status mapping
    assert entry["status"] in ("ok", "discarded")


def test_build_ledger_entry_decision_matches_status_for_keep():
    grouped = _mk_grouped(d_crps=-0.01, rt_ratio=2.0)
    rows = build_comparison_rows(grouped)
    v = decide(rows, thresholds={"max_runtime_multiplier": 3.0, "min_slices_improved": 2})
    entry = build_ledger_entry(v)
    if v.decision == "keep":
        assert entry["status"] == "ok"


def test_build_ledger_entry_regressions_flagged_on_runtime_blowout():
    # rt ratio = 50 -> regression row flagged
    grouped = _mk_grouped(d_crps=0.001, rt_ratio=50.0)
    rows = build_comparison_rows(grouped)
    v = decide(rows, thresholds={"max_runtime_multiplier": 3.0, "min_slices_improved": 2})
    entry = build_ledger_entry(v)
    assert any("runtime" in r for r in entry["regressions"])


def test_append_ledger_entry_writes_jsonl_line(tmp_path):
    ledger = tmp_path / "experiments.jsonl"
    entry = {"run_id": "x", "decision": "keep"}
    append_ledger_entry(entry, ledger)
    append_ledger_entry({"run_id": "y", "decision": "discard"}, ledger)
    lines = ledger.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["run_id"] == "x"
    assert json.loads(lines[1])["decision"] == "discard"
