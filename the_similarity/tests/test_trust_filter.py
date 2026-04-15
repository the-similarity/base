"""Tests for trust_filter — "when NOT to trust the cone" gating logic.

Covers the four signals (calibration, agreement, regime novelty, sample
size), the hard vs soft gate semantics, and a minimal end-to-end pass
through ``evaluate``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest

from the_similarity.core.trust_filter import (
    TrustDecision,
    TrustFilter,
    evaluate,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _FakeMatch:
    """Duck-typed match object — only the attrs the filter reads."""

    confidence_score: float = 70.0
    regime: str | None = None


@dataclass
class _FakeProjection:
    """Duck-typed Forecast/EnsembleForecast."""

    curves: dict[int, np.ndarray]
    all_paths: np.ndarray | None = None


class _FakeReport:
    """Duck-typed BacktestReport exposing only ``.calibration``."""

    def __init__(self, calibration: dict[int, float]):
        self.calibration = calibration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tight_projection(n_paths: int = 10, bars: int = 20) -> _FakeProjection:
    """Build a projection where all match paths strongly agree."""
    rng = np.random.default_rng(42)
    base = np.linspace(0, 0.04, bars)  # ~4% drift
    paths = np.tile(base, (n_paths, 1)) + 0.002 * rng.standard_normal((n_paths, bars))
    curves = {
        10: base - 0.01,
        25: base - 0.005,
        50: base,
        75: base + 0.005,
        90: base + 0.01,
    }
    return _FakeProjection(curves=curves, all_paths=paths)


def _wide_projection(n_paths: int = 10, bars: int = 20) -> _FakeProjection:
    """Build a projection with wildly disagreeing paths."""
    rng = np.random.default_rng(7)
    base = np.linspace(0, 0.0, bars)
    # Huge per-path variance — dispersion >> magnitude.
    paths = base + 0.5 * rng.standard_normal((n_paths, bars))
    curves = {
        10: base - 0.5,
        25: base - 0.25,
        50: base,
        75: base + 0.25,
        90: base + 0.5,
    }
    return _FakeProjection(curves=curves, all_paths=paths)


def _well_calibrated_report() -> _FakeReport:
    """Calibration where empirical ≈ stated for every percentile."""
    return _FakeReport(calibration={10: 0.10, 25: 0.25, 50: 0.50, 75: 0.75, 90: 0.90})


def _badly_calibrated_report() -> _FakeReport:
    """Calibration with huge systematic drift."""
    return _FakeReport(calibration={10: 0.40, 25: 0.55, 50: 0.80, 75: 0.95, 90: 0.99})


# ---------------------------------------------------------------------------
# Sample-size gate (hard)
# ---------------------------------------------------------------------------


def test_too_few_matches_fails_hard_gate():
    matches = [_FakeMatch(confidence_score=80) for _ in range(2)]
    proj = _tight_projection()
    report = _well_calibrated_report()

    decision = evaluate(
        match_pool=matches,
        projection=proj,
        regime_state=None,
        calibration_report=report,
        min_matches=5,
    )
    assert isinstance(decision, TrustDecision)
    assert decision.trust is False
    assert any("sample_size" in r for r in decision.reasons)
    # Sample-size sub-score must be strictly < 0.5 (n < min_matches).
    assert decision.signals["sample_size"] < 0.5


def test_plenty_of_matches_clears_sample_gate():
    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    proj = _tight_projection()
    report = _well_calibrated_report()

    decision = evaluate(
        match_pool=matches,
        projection=proj,
        calibration_report=report,
        min_matches=5,
    )
    assert decision.trust is True
    assert decision.signals["sample_size"] > 0.5


# ---------------------------------------------------------------------------
# Calibration gate (hard)
# ---------------------------------------------------------------------------


def test_bad_calibration_fails_hard_gate():
    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    proj = _tight_projection()
    report = _badly_calibrated_report()

    decision = evaluate(
        match_pool=matches,
        projection=proj,
        calibration_report=report,
        max_calibration_mae=0.15,
    )
    assert decision.trust is False
    assert any("calibration" in r.lower() for r in decision.reasons)


def test_missing_calibration_is_neutral_pass():
    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    proj = _tight_projection()

    decision = evaluate(
        match_pool=matches,
        projection=proj,
        calibration_report=None,
    )
    # With no calibration report, the sub-score defaults to 1.0 and
    # the hard gate passes (MAE defaults to 0).
    assert decision.signals["calibration"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Agreement (soft)
# ---------------------------------------------------------------------------


def test_high_dispersion_lowers_agreement_score():
    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    tight = _tight_projection()
    wide = _wide_projection()

    report = _well_calibrated_report()
    d_tight = evaluate(match_pool=matches, projection=tight, calibration_report=report)
    d_wide = evaluate(match_pool=matches, projection=wide, calibration_report=report)

    assert d_tight.signals["agreement"] > d_wide.signals["agreement"]


def test_no_paths_falls_back_to_curve_spread():
    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    # Only percentile curves, no all_paths.
    curves_tight = {
        10: np.linspace(0, 0.03, 10),
        50: np.linspace(0, 0.05, 10),
        90: np.linspace(0, 0.07, 10),
    }
    curves_wide = {
        10: np.linspace(0, -0.30, 10),
        50: np.linspace(0, 0.0, 10),
        90: np.linspace(0, 0.30, 10),
    }
    proj_tight = _FakeProjection(curves=curves_tight, all_paths=None)
    proj_wide = _FakeProjection(curves=curves_wide, all_paths=None)

    report = _well_calibrated_report()
    d_tight = evaluate(
        match_pool=matches, projection=proj_tight, calibration_report=report
    )
    d_wide = evaluate(
        match_pool=matches, projection=proj_wide, calibration_report=report
    )

    assert d_tight.signals["agreement"] > d_wide.signals["agreement"]


# ---------------------------------------------------------------------------
# Regime novelty (soft)
# ---------------------------------------------------------------------------


def test_regime_match_scores_one():
    matches = [_FakeMatch(confidence_score=80, regime="trending_up") for _ in range(10)]
    proj = _tight_projection()
    report = _well_calibrated_report()

    decision = evaluate(
        match_pool=matches,
        projection=proj,
        regime_state={"regime": "trending_up"},
        calibration_report=report,
    )
    assert decision.signals["regime_novelty"] == pytest.approx(1.0)


def test_regime_mismatch_scores_low():
    # All matches are low_vol but query is high_vol.
    matches = [_FakeMatch(confidence_score=80, regime="low_vol") for _ in range(10)]
    proj = _tight_projection()
    report = _well_calibrated_report()

    decision = evaluate(
        match_pool=matches,
        projection=proj,
        regime_state={"regime": "high_vol"},
        calibration_report=report,
    )
    assert decision.signals["regime_novelty"] == pytest.approx(0.0)
    # Mismatch reason is recorded.
    assert any("regime_novelty" in r for r in decision.reasons)


def test_no_query_regime_is_neutral():
    matches = [_FakeMatch(confidence_score=80, regime="trending_up") for _ in range(10)]
    proj = _tight_projection()

    decision = evaluate(
        match_pool=matches,
        projection=proj,
        regime_state=None,
        calibration_report=_well_calibrated_report(),
    )
    # No query regime -> no penalty.
    assert decision.signals["regime_novelty"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Overall score composition
# ---------------------------------------------------------------------------


def test_overall_score_respects_weights():
    # Build two filters that differ only in how they weight calibration,
    # and check that the overall score tracks.
    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    proj = _tight_projection()
    report = _FakeReport(calibration={10: 0.20, 50: 0.55, 90: 0.85})
    # Mild miscalibration: MAE ≈ (0.10 + 0.05 + 0.05) / 3 ≈ 0.067.

    cal_heavy = TrustFilter(
        signal_weights={
            "calibration": 0.9,
            "agreement": 0.05,
            "regime_novelty": 0.025,
            "sample_size": 0.025,
        },
        max_calibration_mae=0.3,
    )
    cal_light = TrustFilter(
        signal_weights={
            "calibration": 0.05,
            "agreement": 0.3,
            "regime_novelty": 0.3,
            "sample_size": 0.35,
        },
        max_calibration_mae=0.3,
    )

    d_heavy = cal_heavy.evaluate(
        match_pool=matches, projection=proj, calibration_report=report
    )
    d_light = cal_light.evaluate(
        match_pool=matches, projection=proj, calibration_report=report
    )
    # Because calibration is mildly off (<1.0) but the other signals are
    # high, heavier weight on calibration must LOWER the overall score.
    assert d_heavy.score < d_light.score


def test_trust_flag_requires_all_hard_gates_and_min_score():
    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    proj = _tight_projection()
    report = _well_calibrated_report()

    # Impossible-to-reach min_score — even a perfect setup fails.
    tf = TrustFilter(min_score=1.1)
    decision = tf.evaluate(
        match_pool=matches, projection=proj, calibration_report=report
    )
    assert decision.trust is False
    # But score itself should still be high and well-formed.
    assert 0.0 <= decision.score <= 1.0


def test_search_results_duck_type_accepted():
    class _Results:
        def __init__(self, ms: list[Any]):
            self.matches = ms

    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    wrapped = _Results(matches)
    decision = evaluate(
        match_pool=wrapped,
        projection=_tight_projection(),
        calibration_report=_well_calibrated_report(),
    )
    assert decision.trust is True


def test_empty_inputs_fail_closed():
    decision = evaluate(match_pool=[], projection=None, calibration_report=None)
    assert decision.trust is False
    assert decision.signals["sample_size"] == 0.0


def test_raw_calibration_dict_accepted():
    matches = [_FakeMatch(confidence_score=80) for _ in range(20)]
    proj = _tight_projection()
    # Pass a dict, not a report object.
    decision = evaluate(
        match_pool=matches,
        projection=proj,
        calibration_report={10: 0.11, 50: 0.52, 90: 0.88},
    )
    assert decision.trust is True
    assert decision.signals["calibration"] > 0.8
