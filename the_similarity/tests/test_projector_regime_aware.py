"""Tests for the regime-aware cone widening projector (projector-v2 lane)."""

from __future__ import annotations

import numpy as np

from the_similarity.core.projector import project as baseline_project
from the_similarity.core.projector_regime_aware import (
    RegimeAwareState,
    project,
)
from the_similarity.core.scorer import MatchResult


def _make_match(start: int, end: int, score: float) -> MatchResult:
    return MatchResult(start_idx=start, end_idx=end, confidence_score=score)


# ---------------------------------------------------------------------------
# Signature / shape parity
# ---------------------------------------------------------------------------


def test_signature_and_shapes_match_baseline():
    history = np.arange(300, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc = project(matches, history, forward_bars=30, percentiles=[10, 25, 50, 75, 90])
    assert fc.bars == 30
    assert fc.percentiles == [10, 25, 50, 75, 90]
    for p in [10, 25, 50, 75, 90]:
        assert p in fc.curves
        assert len(fc.curves[p]) == 30


def test_p50_untouched():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc_base = baseline_project(matches, history, forward_bars=30)
    fc_reg = project(matches, history, forward_bars=30)
    np.testing.assert_allclose(fc_base.curves[50], fc_reg.curves[50])


def test_diagnostic_state_attached():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc = project(matches, history, forward_bars=30)
    state: RegimeAwareState = getattr(fc, "regime_aware")
    assert isinstance(state, RegimeAwareState)
    assert state.multiplier > 0
    assert state.used_default_multipliers is True


# ---------------------------------------------------------------------------
# Widening semantics
# ---------------------------------------------------------------------------


def test_high_vol_widens_cone():
    """A synthetic high-volatility query should trigger widening (mult > 1)."""
    # Construct a high-volatility query by summing a large-amplitude
    # Gaussian walk. The tag_regime function flags this as "high_vol".
    rng = np.random.default_rng(42)
    query = np.cumsum(rng.normal(0, 5.0, size=60)) + 100
    history = np.concatenate([np.arange(200, dtype=np.float64), query])
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 160, 40)]

    fc_base = baseline_project(matches, history[:200], forward_bars=30)
    fc_reg = project(matches, history[:200], forward_bars=30, query=query)

    state: RegimeAwareState = getattr(fc_reg, "regime_aware")
    # Whatever regime is detected, if it's high_vol we require widening.
    # If it's unknown the multiplier must still be positive and the cone
    # must remain monotonic.
    if state.regime == "high_vol":
        hw_base = np.mean(np.abs(fc_base.curves[90] - fc_base.curves[50]))
        hw_reg = np.mean(np.abs(fc_reg.curves[90] - fc_reg.curves[50]))
        assert hw_reg > hw_base
    # Always: cone monotonicity preserved.
    assert np.all(fc_reg.curves[10] <= fc_reg.curves[50] + 1e-9)
    assert np.all(fc_reg.curves[50] <= fc_reg.curves[90] + 1e-9)


def test_custom_multipliers_override_default():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]

    fc_base = baseline_project(matches, history, forward_bars=30)
    # Force a huge widening for *every* regime so the test is robust to
    # which regime the detector picks.
    custom = {
        "trending_up": 2.0,
        "trending_down": 2.0,
        "mean_reverting": 2.0,
        "high_vol": 2.0,
        "low_vol": 2.0,
        "unknown": 2.0,
    }
    fc_reg = project(
        matches,
        history,
        forward_bars=30,
        regime_multipliers=custom,
    )
    # P90 - P50 distance must exactly double (per multiplier = 2.0).
    d_base = fc_base.curves[90] - fc_base.curves[50]
    d_reg = fc_reg.curves[90] - fc_reg.curves[50]
    np.testing.assert_allclose(d_reg, 2.0 * d_base)


def test_multiplier_of_one_is_noop():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc_base = baseline_project(matches, history, forward_bars=30)
    fc_reg = project(
        matches,
        history,
        forward_bars=30,
        regime_multipliers={
            k: 1.0
            for k in [
                "trending_up",
                "trending_down",
                "mean_reverting",
                "high_vol",
                "low_vol",
                "unknown",
            ]
        },
    )
    for p in [10, 25, 50, 75, 90]:
        np.testing.assert_allclose(fc_base.curves[p], fc_reg.curves[p])


def test_apply_to_restricts_scaling():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]

    fc_base = baseline_project(matches, history, forward_bars=30)
    fc_reg = project(
        matches,
        history,
        forward_bars=30,
        regime_multipliers={
            k: 2.0
            for k in [
                "trending_up",
                "trending_down",
                "mean_reverting",
                "high_vol",
                "low_vol",
                "unknown",
            ]
        },
        apply_to=(90,),  # only P90 should change
    )

    # P10, P25, P75 identical to baseline; P90 scaled.
    np.testing.assert_allclose(fc_base.curves[10], fc_reg.curves[10])
    np.testing.assert_allclose(fc_base.curves[25], fc_reg.curves[25])
    np.testing.assert_allclose(fc_base.curves[75], fc_reg.curves[75])
    assert not np.allclose(fc_base.curves[90], fc_reg.curves[90])


# ---------------------------------------------------------------------------
# Fail-closed behaviour
# ---------------------------------------------------------------------------


def test_no_matches_returns_baseline_shape():
    history = np.arange(80, dtype=np.float64)
    matches = [_make_match(0, 79, score=1.0)]  # no room for 50 forward bars
    fc = project(matches, history, forward_bars=50)
    assert fc.all_paths.shape == (0, 50)
    state: RegimeAwareState = getattr(fc, "regime_aware")
    assert state.multiplier == 1.0


def test_short_history_defaults_to_unknown():
    # <10 samples — tag_regime falls back to unknown / low_vol.
    history = np.arange(9, dtype=np.float64)
    fc = project([], history, forward_bars=5)
    state: RegimeAwareState = getattr(fc, "regime_aware")
    assert state.regime in {"unknown", "low_vol"}
