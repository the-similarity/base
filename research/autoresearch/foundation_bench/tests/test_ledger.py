"""Tests for the foundation-bench ledger-row builder."""
from __future__ import annotations

import json
from pathlib import Path

from research.autoresearch.foundation_bench.ledger import (
    append_ledger_entry,
    build_ledger_entry,
)
from research.autoresearch.foundation_bench.run_bench import CellResult, TrialRecord
from research.autoresearch.retrieval_bench.metrics import TrialOutcome


def _cell(slice_id: str, model_id: str, *, fallback: bool, crps: float) -> CellResult:
    rec = TrialRecord(
        outcome=TrialOutcome(
            match_forward_returns=[],
            quantile_forecast={10: -0.01, 50: 0.0, 90: 0.01},
            realised_forward_return=0.0,
            runtime_seconds=0.01,
        ),
        fallback_reason="synthetic" if fallback else None,
        adapter_metadata={},
    )
    return CellResult(
        slice_id=slice_id,
        model_id=model_id,
        n_trials=2,
        n_skipped_budget=0,
        any_fallback=fallback,
        fallback_ratio=1.0 if fallback else 0.0,
        crps=crps,
        calibration_error_p10_p90=0.05,
        hit_rate=0.5,
        runtime={"median": 0.01, "mean": 0.01, "p95": 0.01, "n": 2},
        records=[rec],
        status="partial_synthetic_fallback" if fallback else "ok",
    )


def test_entry_shape_matches_schema_keys():
    cells = [
        _cell("s1", "wavelet_baseline", fallback=False, crps=0.020),
        _cell("s1", "timesfm", fallback=True, crps=0.030),
        _cell("s2", "timesfm", fallback=True, crps=0.025),
    ]
    entry = build_ledger_entry(cells, n_trials=12, seeds=[42])
    for key in [
        "run_id",
        "timestamp",
        "benchmark_id",
        "lane_id",
        "status",
        "decision",
        "summary",
        "slices",
        "artifacts",
        "metrics_before",
        "metrics_after",
        "regressions",
        "notes",
    ]:
        assert key in entry, f"missing required key: {key}"
    assert entry["benchmark_id"] == "foundation-bench-v1"
    assert entry["decision"] == "measured"
    # When foundation cells fall back, status reflects it honestly
    assert entry["status"] == "partial_synthetic_fallback"
    # metrics_before is wavelet; metrics_after is best non-wavelet model
    assert "crps" in entry["metrics_before"]
    assert "crps" in entry["metrics_after"]


def test_status_ok_when_no_fallbacks():
    cells = [
        _cell("s1", "wavelet_baseline", fallback=False, crps=0.020),
        _cell("s1", "x", fallback=False, crps=0.019),
    ]
    entry = build_ledger_entry(cells)
    assert entry["status"] == "ok"


def test_append_creates_jsonl_line(tmp_path: Path):
    cells = [_cell("s1", "wavelet_baseline", fallback=False, crps=0.02)]
    entry = build_ledger_entry(cells)
    p = append_ledger_entry(entry, tmp_path / "x.jsonl")
    line = p.read_text().strip()
    roundtrip = json.loads(line)
    assert roundtrip["benchmark_id"] == "foundation-bench-v1"
