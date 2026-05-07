"""Tests for the regime-sliced info-Sharpe metric and its label helpers."""

from __future__ import annotations

import math

import numpy as np

from the_similarity.core.backtester import TrialResult
from the_similarity.finance.regime_slice import (
    GROWTH_DOWN,
    GROWTH_UP,
    INFLATION_DOWN,
    INFLATION_UP,
    LIQUIDITY_DOWN,
    LIQUIDITY_UP,
    VOLATILITY_BEARISH,
    VOLATILITY_BULLISH,
    info_sharpe_by_regime,
    label_growth_inflation,
    label_volatility_liquidity,
)


def _trial(*, p50_terminal: float, actual_terminal: float) -> TrialResult:
    """Build a TrialResult whose only relevant fields are P50 + actual.

    The metric only consumes ``forecast_curves[50][-1]`` and
    ``actual_returns[-1]`` so we keep the rest minimal.
    """
    return TrialResult(
        query_start=0,
        query_end=10,
        actual_returns=np.array([actual_terminal], dtype=np.float64),
        forecast_curves={50: np.array([p50_terminal], dtype=np.float64)},
        n_matches=5,
        top_match_score=1.0,
        directional_hit=(p50_terminal > 0) == (actual_terminal > 0),
        p50_error=abs(p50_terminal - actual_terminal),
        skipped=False,
    )


# ---------------------------------------------------------------------------
# info_sharpe_by_regime
# ---------------------------------------------------------------------------


def test_info_sharpe_buckets_trials_by_label() -> None:
    """Trials with different regime labels land in different buckets."""
    trials = [
        _trial(p50_terminal=0.01, actual_terminal=0.02),  # bull, hit
        _trial(p50_terminal=0.01, actual_terminal=0.03),  # bull, hit
        _trial(p50_terminal=0.01, actual_terminal=-0.05),  # bear, miss
        _trial(p50_terminal=-0.01, actual_terminal=-0.04),  # bear, hit
    ]
    labels = ["bull", "bull", "bear", "bear"]

    # Index trials by their position in the input list so the test does
    # not depend on any timestamp wiring.
    by_id = {id(t): labels[i] for i, t in enumerate(trials)}
    result = info_sharpe_by_regime(trials, regime_for_trial=lambda t: by_id[id(t)])

    assert set(result.keys()) == {"bull", "bear"}
    # Both buckets had >=2 trials with non-zero variance, so Sharpe is finite.
    assert math.isfinite(result["bull"])
    assert math.isfinite(result["bear"])


def test_info_sharpe_matches_manual_computation() -> None:
    """Per-bucket Sharpe = mean / std on directional returns (ddof=0)."""
    trials = [
        _trial(p50_terminal=0.01, actual_terminal=0.02),  # +1 * 0.02 = 0.02
        _trial(p50_terminal=0.01, actual_terminal=0.04),  # +1 * 0.04 = 0.04
        _trial(p50_terminal=-0.01, actual_terminal=-0.06),  # -1 * -0.06 = 0.06
    ]
    result = info_sharpe_by_regime(trials, regime_for_trial=lambda _t: "only")

    expected_returns = np.array([0.02, 0.04, 0.06])
    expected_sharpe = float(
        np.mean(expected_returns) / np.std(expected_returns, ddof=0)
    )
    assert result["only"] == expected_sharpe


def test_info_sharpe_returns_nan_on_singleton_bucket() -> None:
    """Single-observation buckets are NaN (Sharpe ill-defined)."""
    trials = [_trial(p50_terminal=0.01, actual_terminal=0.02)]
    result = info_sharpe_by_regime(trials, regime_for_trial=lambda _t: "only")
    assert math.isnan(result["only"])


def test_info_sharpe_returns_nan_on_zero_variance_bucket() -> None:
    """Zero variance => NaN, not infinity (fail-closed convention)."""
    trials = [
        _trial(p50_terminal=0.01, actual_terminal=0.02),
        _trial(p50_terminal=0.01, actual_terminal=0.02),
    ]
    result = info_sharpe_by_regime(trials, regime_for_trial=lambda _t: "only")
    assert math.isnan(result["only"])


def test_info_sharpe_skips_trials_with_none_label() -> None:
    """Returning None excludes a trial from every bucket."""
    trials = [
        _trial(p50_terminal=0.01, actual_terminal=0.02),
        _trial(p50_terminal=0.01, actual_terminal=0.03),
        _trial(p50_terminal=0.01, actual_terminal=0.99),  # excluded
    ]
    labels = ["A", "A", None]
    by_id = {id(t): labels[i] for i, t in enumerate(trials)}

    result = info_sharpe_by_regime(trials, regime_for_trial=lambda t: by_id[id(t)])

    # Only bucket A exists; the excluded trial's outsized return does not
    # appear, which we verify indirectly by recomputing manually.
    expected = np.array([0.02, 0.03])
    expected_sharpe = float(np.mean(expected) / np.std(expected, ddof=0))
    assert result == {"A": expected_sharpe}


def test_info_sharpe_skips_trials_without_p50_curve() -> None:
    """Trials missing forecast_curves[50] are silently skipped."""
    no_p50 = TrialResult(
        query_start=0,
        query_end=10,
        actual_returns=np.array([0.05], dtype=np.float64),
        forecast_curves={},  # no curves at all
        n_matches=0,
        top_match_score=0.0,
        directional_hit=False,
        p50_error=0.05,
        skipped=True,
    )
    trials = [
        _trial(p50_terminal=0.01, actual_terminal=0.02),
        _trial(p50_terminal=0.01, actual_terminal=0.03),
        no_p50,
    ]
    result = info_sharpe_by_regime(trials, regime_for_trial=lambda _t: "only")
    # Only the two well-formed trials feed the Sharpe.
    expected = np.array([0.02, 0.03])
    expected_sharpe = float(np.mean(expected) / np.std(expected, ddof=0))
    assert result["only"] == expected_sharpe


def test_info_sharpe_empty_input_returns_empty_dict() -> None:
    """No trials => no buckets, not an error."""
    assert info_sharpe_by_regime([], regime_for_trial=lambda _t: "x") == {}


# ---------------------------------------------------------------------------
# label_growth_inflation / label_volatility_liquidity
# ---------------------------------------------------------------------------


def test_growth_inflation_strict_above_average() -> None:
    """Strict > comparison per Correia (2015) Table 7."""
    g, i = label_growth_inflation(
        growth=3.0,
        growth_2y_avg=2.0,
        inflation=2.5,
        inflation_5y_avg=2.0,
    )
    assert g == GROWTH_UP
    assert i == INFLATION_UP


def test_growth_inflation_below_average() -> None:
    g, i = label_growth_inflation(
        growth=1.0,
        growth_2y_avg=2.0,
        inflation=1.5,
        inflation_5y_avg=2.0,
    )
    assert g == GROWTH_DOWN
    assert i == INFLATION_DOWN


def test_growth_inflation_equal_classed_as_down() -> None:
    """Equality (current == average) falls into the Down bucket."""
    g, i = label_growth_inflation(
        growth=2.0,
        growth_2y_avg=2.0,
        inflation=2.0,
        inflation_5y_avg=2.0,
    )
    assert g == GROWTH_DOWN
    assert i == INFLATION_DOWN


def test_volatility_bearish_when_vix_above_avg() -> None:
    vol, _ = label_volatility_liquidity(vix=25.0, vix_1y_avg=18.0, fed_rate_change=0.0)
    assert vol == VOLATILITY_BEARISH


def test_volatility_bullish_when_vix_below_avg() -> None:
    vol, _ = label_volatility_liquidity(vix=12.0, vix_1y_avg=18.0, fed_rate_change=0.0)
    assert vol == VOLATILITY_BULLISH


def test_liquidity_down_on_hike() -> None:
    """Rate hike removes liquidity per Correia Table 7."""
    _, liq = label_volatility_liquidity(vix=15.0, vix_1y_avg=18.0, fed_rate_change=0.25)
    assert liq == LIQUIDITY_DOWN


def test_liquidity_up_on_cut() -> None:
    """Rate cut adds liquidity."""
    _, liq = label_volatility_liquidity(
        vix=15.0, vix_1y_avg=18.0, fed_rate_change=-0.25
    )
    assert liq == LIQUIDITY_UP


def test_liquidity_flat_treated_as_down() -> None:
    """Unchanged rate is hawkish-by-default per the paper's framing."""
    _, liq = label_volatility_liquidity(vix=15.0, vix_1y_avg=18.0, fed_rate_change=0.0)
    assert liq == LIQUIDITY_DOWN
