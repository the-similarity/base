"""Smoke tests for the projector-v2 sweep runner.

These tests do NOT execute the full backtest sweep (which is heavy) —
instead they exercise the individual helpers: slice loading with the
synthetic fallback, the decision rule, and the patched-project wrapper
contract.

The full sweep is validated end-to-end during the lane run itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

# Make the sibling `run_projector_v2_sweep` module importable.
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_projector_v2_sweep as sweep  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fallback
# ---------------------------------------------------------------------------


def test_synthetic_fallback_is_deterministic():
    """If the parquet is missing, the sweep must produce a reproducible series."""
    fake_spec = {
        "id": "synthetic-test",
        "dataset_path": "the-similarity-data/data/nonexistent/path.parquet",
        "synthetic_seed": 999,
        "synthetic_bars": 500,
    }
    a, syn_a = sweep._load_series(fake_spec)
    b, syn_b = sweep._load_series(fake_spec)
    assert syn_a is True and syn_b is True
    assert len(a) == 500
    np.testing.assert_allclose(a, b)
    # Prices must be strictly positive (they come from exp(cumsum)).
    assert np.all(a > 0)


# ---------------------------------------------------------------------------
# Decision rule
# ---------------------------------------------------------------------------


def _agg(crps: float, cal: float, hit: float, runtime: float = 1.0, jp: float = 0.02):
    return sweep.VariantAggregate(
        variant="v",
        slices_evaluated=1,
        hit_rate=hit,
        mean_error=0.0,
        crps=crps,
        calibration_error_p10_p90=cal,
        calibration_error_over_time_p10_p90=cal,
        joint_path_crps=jp,
        runtime_seconds=runtime,
    )


class TestDecisionRule:
    def test_improvement_keeps(self):
        baseline = _agg(crps=0.05, cal=0.08, hit=0.55)
        variant = _agg(crps=0.045, cal=0.07, hit=0.55)
        decision = sweep._decide_keep_discard(variant, baseline)
        assert decision["decision"] == "keep"

    def test_crps_regression_discards(self):
        baseline = _agg(crps=0.05, cal=0.08, hit=0.55)
        variant = _agg(crps=0.07, cal=0.07, hit=0.55)  # CRPS up 40%
        decision = sweep._decide_keep_discard(variant, baseline)
        assert decision["decision"] == "discard"
        assert decision["hard_regression"] is True

    def test_hit_rate_below_45_discards(self):
        baseline = _agg(crps=0.05, cal=0.08, hit=0.55)
        variant = _agg(crps=0.04, cal=0.07, hit=0.40)
        decision = sweep._decide_keep_discard(variant, baseline)
        assert decision["decision"] == "discard"
        assert decision["hard_regression"] is True

    def test_no_improvement_discards(self):
        baseline = _agg(crps=0.05, cal=0.08, hit=0.55)
        variant = _agg(crps=0.05, cal=0.08, hit=0.55)  # no change
        decision = sweep._decide_keep_discard(variant, baseline)
        assert decision["decision"] == "discard"


# ---------------------------------------------------------------------------
# Patched-project wrapper contract
# ---------------------------------------------------------------------------


def test_patched_project_wrapper_delegates():
    """The wrapper must forward the canonical kwargs to the variant module."""
    # Build a wrapper around the regime-aware variant and call it directly.
    from the_similarity.core.scorer import MatchResult

    wrapped = sweep._make_patched_project(
        "the_similarity.core.projector_regime_aware",
        {"regime_multipliers": {k: 1.0 for k in [
            "trending_up", "trending_down", "mean_reverting",
            "high_vol", "low_vol", "unknown",
        ]}},
    )
    history = np.arange(300, dtype=np.float64)
    matches = [MatchResult(start_idx=i, end_idx=i + 40, confidence_score=1.0) for i in range(0, 160, 40)]
    fc = wrapped(matches, history, forward_bars=30)
    assert 10 in fc.curves
    assert 90 in fc.curves
    assert len(fc.curves[50]) == 30


# ---------------------------------------------------------------------------
# Report writer — basic schema check
# ---------------------------------------------------------------------------


def test_write_json_report_is_loadable(tmp_path):
    path = tmp_path / "x.json"
    sweep._write_json_report(path, {"foo": 1, "bar": [1, 2]})
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["foo"] == 1
    assert payload["bar"] == [1, 2]
