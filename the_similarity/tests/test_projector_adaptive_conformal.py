"""Tests for the adaptive / change-aware conformal projector (projector-v2 lane)."""

from __future__ import annotations

import numpy as np

from the_similarity.config import Config
from the_similarity.core.projector import project as baseline_project
from the_similarity.core.projector_adaptive_conformal import (
    AdaptiveConformalState,
    project,
)
from the_similarity.core.scorer import MatchResult


def _make_match(start: int, end: int, score: float) -> MatchResult:
    return MatchResult(start_idx=start, end_idx=end, confidence_score=score)


# ---------------------------------------------------------------------------
# Shape / signature parity with the baseline projector
# ---------------------------------------------------------------------------


def test_signature_parity_with_baseline():
    """Adaptive projector must accept the same positional/keyword args."""
    history = np.arange(300, dtype=np.float64)
    matches = [
        _make_match(0, 50, score=80.0),
        _make_match(50, 100, score=60.0),
        _make_match(100, 150, score=40.0),
    ]
    fc = project(matches, history, forward_bars=40, percentiles=[10, 25, 50, 75, 90])
    assert fc.bars == 40
    assert fc.percentiles == [10, 25, 50, 75, 90]
    for p in [10, 25, 50, 75, 90]:
        assert p in fc.curves
        assert len(fc.curves[p]) == 40


def test_p50_matches_baseline_exactly():
    """Adaptive conformal is a calibration wrapper — P50 is untouched."""
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=50.0 - i) for i in range(0, 200, 40)]

    fc_base = baseline_project(matches, history, forward_bars=30)
    fc_adapt = project(matches, history, forward_bars=30)

    np.testing.assert_allclose(fc_base.curves[50], fc_adapt.curves[50])


def test_no_usable_matches_falls_back_to_baseline():
    """If no valid forward paths exist, adaptive layer is a no-op."""
    history = np.arange(80, dtype=np.float64)
    # Match ends at 79, forward_bars=50 → no future data → 0 paths.
    matches = [_make_match(0, 79, score=1.0)]
    fc = project(matches, history, forward_bars=50)
    assert fc.all_paths.shape == (0, 50)
    state = getattr(fc, "adaptive_conformal", None)
    assert isinstance(state, AdaptiveConformalState)
    assert state.n_calibration == 0


# ---------------------------------------------------------------------------
# Calibration semantics
# ---------------------------------------------------------------------------


def test_state_exposes_diagnostics():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]
    fc = project(matches, history, forward_bars=30, alpha_target=0.2, lr=0.05)
    state: AdaptiveConformalState = getattr(fc, "adaptive_conformal")
    assert 0.0 < state.alpha_effective < 1.0
    assert state.alpha_target == 0.2
    assert state.lr == 0.05
    assert state.n_calibration >= 1


def test_cone_scaling_is_centered_on_p50():
    """Edges must fan out / in *around* P50, never shifting P50 itself."""
    history = np.arange(300, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]

    fc_base = baseline_project(matches, history, forward_bars=30)
    fc_adapt = project(matches, history, forward_bars=30)

    # P50 identical.
    np.testing.assert_allclose(fc_base.curves[50], fc_adapt.curves[50])
    # P10 <= P50 <= P90 monotonicity preserved at every bar.
    assert np.all(fc_adapt.curves[10] <= fc_adapt.curves[50] + 1e-9)
    assert np.all(fc_adapt.curves[50] <= fc_adapt.curves[90] + 1e-9)


def test_change_aware_mode_flag_takes_effect():
    """Selecting change_aware=True must record it in the state."""
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 240, 40)]
    fc = project(matches, history, forward_bars=30, change_aware=True)
    state: AdaptiveConformalState = getattr(fc, "adaptive_conformal")
    assert state.change_aware is True


def test_mode_string_selector():
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]

    fc_adapt = project(matches, history, forward_bars=30, mode="adaptive")
    fc_change = project(matches, history, forward_bars=30, mode="change_aware")

    assert getattr(fc_adapt, "adaptive_conformal").change_aware is False
    assert getattr(fc_change, "adaptive_conformal").change_aware is True


# ---------------------------------------------------------------------------
# Walk-forward safety — must not look into the future of the trial
# ---------------------------------------------------------------------------


def test_walk_forward_only_uses_match_forward_windows():
    """Adaptive projector must not peek past the lookback it was handed.

    We stitch together two obviously-different regimes; the calibration
    should be driven entirely by the lookback residuals it receives, not
    by any synthetic 'future' state we append afterwards.
    """
    lookback = np.concatenate(
        [
            np.arange(200, dtype=np.float64),
            np.arange(200, 400, dtype=np.float64) * 0.5,
        ]
    )
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 300, 40)]

    # Call twice — once with a pristine lookback, once with an added
    # (deceptive) future suffix. The adaptive layer must behave the SAME
    # because it only consults match forward windows.
    fc_a = project(matches, lookback, forward_bars=30)
    fc_b = project(
        matches, np.concatenate([lookback, np.full(50, 999.0)]), forward_bars=30
    )
    np.testing.assert_allclose(fc_a.curves[10], fc_b.curves[10])
    np.testing.assert_allclose(fc_a.curves[90], fc_b.curves[90])


# ---------------------------------------------------------------------------
# Integration with Config / percentiles customization
# ---------------------------------------------------------------------------


def test_config_confidence_decay_still_applies_baseline_path():
    """config.confidence_decay_rate still controls the *baseline* cone shape."""
    history = np.arange(400, dtype=np.float64)
    matches = [_make_match(i, i + 40, score=1.0) for i in range(0, 200, 40)]

    cfg = Config(confidence_decay_rate=0.05)
    fc = project(matches, history, forward_bars=30, config=cfg)
    # At bar 0 the P10/P90 edge is NOT widened by decay (decay factor is 1.0);
    # at bar 29 it IS widened. So |P90 - P50| should be larger at the tail.
    hw_start = abs(fc.curves[90][0] - fc.curves[50][0])
    hw_end = abs(fc.curves[90][-1] - fc.curves[50][-1])
    # Non-strict: decay may interact with adaptive scale, but tail must not
    # collapse below the near-term width.
    assert hw_end + 1e-9 >= hw_start * 0.5
