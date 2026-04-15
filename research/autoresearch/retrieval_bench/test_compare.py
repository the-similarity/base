"""Tests for the Tier 1 vs Tier 1+2 ablation comparison engine."""
from __future__ import annotations

import json

import pytest

from research.autoresearch.retrieval_bench.compare import (
    ComparisonRow,
    build_comparison_rows,
    decide,
    load_arm_reports,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mk_result(arm_id, slice_id, *, corr, crps, cal, hit, rt):
    """Build a minimal run_bench-style result dict."""
    return {
        "slice_id": slice_id,
        "arm_id": arm_id,
        "arm_label": arm_id,
        "n_trials": 10,
        "forward_return_correlation": corr,
        "crps": crps,
        "calibration_error_p10_p90": cal,
        "hit_rate": hit,
        "runtime_seconds": {"median": rt, "mean": rt, "p95": rt, "n": 10},
    }


def _pairs(corr_pairs, crps_pairs, *, cal=0.1, hit=0.6, rt_tier1=0.1, rt_tier2=5.0):
    """Helper: build a grouped dict from zipped corr/crps pairs per slice."""
    grouped: dict = {}
    for i, ((c1, c2), (k1, k2)) in enumerate(zip(corr_pairs, crps_pairs)):
        slice_id = f"slice-{i}"
        grouped[slice_id] = {
            "tier1_only": _mk_result("tier1_only", slice_id, corr=c1, crps=k1, cal=cal, hit=hit, rt=rt_tier1),
            "tier1_plus_full": _mk_result("tier1_plus_full", slice_id, corr=c2, crps=k2, cal=cal, hit=hit, rt=rt_tier2),
        }
    return grouped


# ---------------------------------------------------------------------------
# load_arm_reports
# ---------------------------------------------------------------------------

def test_load_arm_reports_groups_by_slice_and_arm(tmp_path):
    # Two slices x two arms = four files
    for slice_id in ("s1", "s2"):
        for arm_id in ("tier1_only", "tier1_plus_full"):
            payload = {
                "metadata": {"benchmark_id": "retrieval-bench-tiers-v1"},
                "result": _mk_result(arm_id, slice_id, corr=0.1, crps=0.02, cal=0.05, hit=0.5, rt=0.1),
            }
            (tmp_path / f"{slice_id}-{arm_id}.json").write_text(json.dumps(payload))

    grouped = load_arm_reports(tmp_path)
    assert set(grouped.keys()) == {"s1", "s2"}
    assert set(grouped["s1"].keys()) == {"tier1_only", "tier1_plus_full"}


def test_load_arm_reports_missing_dir_raises():
    with pytest.raises(FileNotFoundError):
        load_arm_reports("/nonexistent/path/for/test")


# ---------------------------------------------------------------------------
# build_comparison_rows
# ---------------------------------------------------------------------------

def test_build_comparison_rows_skips_slices_missing_an_arm():
    grouped = {
        "complete": {
            "tier1_only": _mk_result("tier1_only", "complete", corr=0.1, crps=0.02, cal=0.05, hit=0.5, rt=0.1),
            "tier1_plus_full": _mk_result("tier1_plus_full", "complete", corr=0.2, crps=0.015, cal=0.04, hit=0.6, rt=5.0),
        },
        "half": {
            "tier1_only": _mk_result("tier1_only", "half", corr=0.0, crps=0.02, cal=0.05, hit=0.5, rt=0.1),
        },
    }
    rows = build_comparison_rows(grouped)
    assert [r.slice_id for r in rows] == ["complete"]
    r = rows[0]
    assert r.d_forward_return_correlation == pytest.approx(0.1)
    assert r.d_crps == pytest.approx(-0.005)
    assert r.runtime_ratio == pytest.approx(50.0)


def test_build_comparison_rows_applies_crps_improvement_threshold():
    # Tier 1+2 CRPS is 0.001 lower -> below threshold of 0.005 -> NOT improved.
    grouped = _pairs([(0.1, 0.1)], [(0.020, 0.019)])
    rows = build_comparison_rows(grouped, thresholds={"min_crps_improvement": 0.005})
    assert rows[0].crps_improved is False

    # Tier 1+2 CRPS is 0.01 lower -> above threshold -> improved.
    grouped = _pairs([(0.1, 0.1)], [(0.030, 0.020)])
    rows = build_comparison_rows(grouped, thresholds={"min_crps_improvement": 0.005})
    assert rows[0].crps_improved is True


# ---------------------------------------------------------------------------
# decide — gate ordering
# ---------------------------------------------------------------------------

def test_decide_discards_on_runtime_blowout_with_no_crps_wins():
    # 4 slices, no CRPS improvement, 50x slower -> DISCARD.
    grouped = _pairs(
        corr_pairs=[(0.0, 0.0)] * 4,
        crps_pairs=[(0.01, 0.02)] * 4,   # Tier 1+2 WORSE
        rt_tier1=0.1, rt_tier2=5.0,
    )
    rows = build_comparison_rows(grouped, thresholds={"min_crps_improvement": 0.005})
    v = decide(rows, thresholds={
        "max_runtime_multiplier": 3.0,
        "min_slices_improved": 3,
    })
    assert v.decision == "discard"
    assert "slower" in v.rationale
    assert v.slices_crps_improved == 0


def test_decide_keeps_when_majority_improve_crps():
    # 4 slices, 4/4 CRPS improved, within runtime budget.
    grouped = _pairs(
        corr_pairs=[(0.0, 0.0)] * 4,
        crps_pairs=[(0.03, 0.020), (0.03, 0.019), (0.03, 0.022), (0.03, 0.020)],
        rt_tier1=1.0, rt_tier2=2.0,  # 2x — within 3x budget
    )
    rows = build_comparison_rows(grouped, thresholds={"min_crps_improvement": 0.005})
    v = decide(rows, thresholds={
        "max_runtime_multiplier": 3.0,
        "min_slices_improved": 3,
    })
    assert v.decision == "keep"
    assert v.slices_crps_improved >= 3


def test_decide_keeps_on_correlation_secondary_pathway():
    # 3/4 correlation improved by enough; CRPS flat.
    grouped = _pairs(
        corr_pairs=[(0.0, 0.05), (0.0, 0.05), (0.0, 0.05), (0.0, 0.0)],
        crps_pairs=[(0.02, 0.02)] * 4,
        rt_tier1=1.0, rt_tier2=2.0,
    )
    rows = build_comparison_rows(grouped, thresholds={
        "min_crps_improvement": 0.005,
        "min_forward_corr_improvement": 0.02,
    })
    v = decide(rows, thresholds={
        "max_runtime_multiplier": 3.0,
        "min_slices_improved": 3,
    })
    assert v.decision == "keep"
    assert v.slices_corr_improved == 3


def test_decide_discards_when_no_path_qualifies():
    grouped = _pairs(
        corr_pairs=[(0.1, 0.1)] * 4,     # no corr lift
        crps_pairs=[(0.02, 0.020)] * 4,   # CRPS flat
        rt_tier1=1.0, rt_tier2=1.5,
    )
    rows = build_comparison_rows(grouped)
    v = decide(rows, thresholds={
        "max_runtime_multiplier": 3.0,
        "min_slices_improved": 3,
    })
    assert v.decision == "discard"
