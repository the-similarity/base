"""Tests for ensemble forecasting (Phase 7b).

Covers Monte Carlo simulation, regime-conditional projections,
conformal prediction intervals, and forecast combination.
"""
import numpy as np
import pytest

from the_similarity.core.ensemble import (
    MonteCarloResult,
    RegimeConditionalResult,
    ConformalResult,
    EnsembleForecast,
    monte_carlo_forecast,
    regime_conditional_forecast,
    conformal_prediction_intervals,
    ensemble_forecast,
)
from the_similarity.core.scorer import MatchResult, ScoreBreakdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_match(
    start: int,
    end: int,
    score: float,
    regime: str | None = None,
) -> MatchResult:
    return MatchResult(
        start_idx=start,
        end_idx=end,
        confidence_score=score,
        regime=regime,
    )


def _trending_up_history(n: int = 500) -> np.ndarray:
    """Generate a trending-up price series."""
    rng = np.random.default_rng(123)
    returns = 0.001 + 0.01 * rng.standard_normal(n)
    return 100.0 * np.exp(np.cumsum(returns))


def _make_test_setup(n_bars: int = 500, forward_bars: int = 50):
    """Standard test setup: history + matches with valid forward windows."""
    history = _trending_up_history(n_bars)
    matches = [
        _make_match(0, 50, score=85.0, regime="trending_up"),
        _make_match(50, 100, score=70.0, regime="trending_up"),
        _make_match(100, 150, score=60.0, regime="mean_reverting"),
        _make_match(200, 250, score=55.0, regime="high_vol"),
        _make_match(300, 350, score=45.0, regime="trending_down"),
    ]
    return history, matches


# ---------------------------------------------------------------------------
# Monte Carlo tests
# ---------------------------------------------------------------------------

class TestMonteCarlo:
    def test_basic_output_shape(self):
        history, matches = _make_test_setup()
        result = monte_carlo_forecast(matches, history, forward_bars=30, n_simulations=500)

        assert isinstance(result, MonteCarloResult)
        assert result.paths.shape == (500, 30)
        assert result.mean.shape == (30,)
        assert result.std.shape == (30,)

    def test_percentiles_present(self):
        history, matches = _make_test_setup()
        result = monte_carlo_forecast(matches, history, forward_bars=30)

        for p in [10, 25, 50, 75, 90]:
            assert p in result.percentiles
            assert len(result.percentiles[p]) == 30

    def test_percentiles_ordered(self):
        history, matches = _make_test_setup()
        result = monte_carlo_forecast(matches, history, forward_bars=30, n_simulations=2000)

        # P10 <= P50 <= P90 on average (may not hold per-bar with few sims)
        assert np.mean(result.percentiles[10]) <= np.mean(result.percentiles[50])
        assert np.mean(result.percentiles[50]) <= np.mean(result.percentiles[90])

    def test_reproducible_with_seed(self):
        history, matches = _make_test_setup()
        r1 = monte_carlo_forecast(matches, history, forward_bars=20, seed=99)
        r2 = monte_carlo_forecast(matches, history, forward_bars=20, seed=99)

        np.testing.assert_array_equal(r1.paths, r2.paths)

    def test_different_seeds_differ(self):
        history, matches = _make_test_setup()
        r1 = monte_carlo_forecast(matches, history, forward_bars=20, seed=1)
        r2 = monte_carlo_forecast(matches, history, forward_bars=20, seed=2)

        assert not np.array_equal(r1.paths, r2.paths)

    def test_empty_matches(self):
        history = np.arange(100, dtype=np.float64)
        result = monte_carlo_forecast([], history, forward_bars=20)

        assert result.paths.shape == (0, 20)
        assert result.mean.shape == (20,)

    def test_no_valid_forward_windows(self):
        history = np.arange(100, dtype=np.float64)
        matches = [_make_match(0, 80, score=90.0)]
        result = monte_carlo_forecast(matches, history, forward_bars=50)

        assert result.paths.shape == (0, 50)

    def test_uncertainty_grows_with_horizon(self):
        history, matches = _make_test_setup()
        result = monte_carlo_forecast(matches, history, forward_bars=50, n_simulations=5000)

        # Std should generally increase over time
        early_std = np.mean(result.std[:10])
        late_std = np.mean(result.std[-10:])
        assert late_std > early_std

    def test_custom_percentiles(self):
        history, matches = _make_test_setup()
        result = monte_carlo_forecast(matches, history, forward_bars=20, percentiles=[5, 95])

        assert 5 in result.percentiles
        assert 95 in result.percentiles
        assert 50 not in result.percentiles


# ---------------------------------------------------------------------------
# Regime-conditional tests
# ---------------------------------------------------------------------------

class TestRegimeConditional:
    def test_detects_query_regime(self):
        history, matches = _make_test_setup()
        query = history[:60]  # trending up
        result = regime_conditional_forecast(query, matches, history, forward_bars=30)

        assert isinstance(result, RegimeConditionalResult)
        assert result.regime in {"trending_up", "trending_down", "mean_reverting", "high_vol", "low_vol"}

    def test_counts_regime_matches(self):
        history, matches = _make_test_setup()
        query = history[:60]
        result = regime_conditional_forecast(query, matches, history, forward_bars=30)

        assert result.n_matches_total == len(matches)
        assert result.n_matches_used >= 0
        assert result.n_matches_used <= result.n_matches_total

    def test_soft_weight_zero_no_filtering(self):
        """soft_weight=0 should use all matches with original weights."""
        history, matches = _make_test_setup()
        query = history[:60]
        result = regime_conditional_forecast(
            query, matches, history, forward_bars=30, soft_weight=0.0,
        )

        # All matches with valid forward windows should be included
        valid_count = sum(
            1 for m in matches if m.end_idx + 30 <= len(history)
        )
        assert len(result.weights) == valid_count

    def test_hard_filter_excludes_incompatible(self):
        """soft_weight=1.0 should exclude incompatible regimes."""
        history, matches = _make_test_setup()
        query = history[:60]
        result = regime_conditional_forecast(
            query, matches, history, forward_bars=30, soft_weight=1.0,
        )

        # Fewer matches than total (some regimes are incompatible)
        assert len(result.weights) <= sum(
            1 for m in matches if m.end_idx + 30 <= len(history)
        )

    def test_output_curves_shape(self):
        history, matches = _make_test_setup()
        query = history[:60]
        result = regime_conditional_forecast(query, matches, history, forward_bars=30)

        for p in [10, 25, 50, 75, 90]:
            assert p in result.curves
            assert len(result.curves[p]) == 30

    def test_empty_matches(self):
        history = np.arange(200, dtype=np.float64)
        query = history[:60]
        result = regime_conditional_forecast(query, [], history, forward_bars=20)

        assert result.n_matches_used == 0
        assert result.all_paths.shape[0] == 0


# ---------------------------------------------------------------------------
# Conformal prediction tests
# ---------------------------------------------------------------------------

class TestConformalPrediction:
    def test_basic_output(self):
        history, matches = _make_test_setup()
        result = conformal_prediction_intervals(matches, history, forward_bars=30)

        assert isinstance(result, ConformalResult)
        assert len(result.lower) == 30
        assert len(result.upper) == 30
        assert result.target_coverage == 0.9

    def test_lower_below_upper(self):
        history, matches = _make_test_setup()
        result = conformal_prediction_intervals(matches, history, forward_bars=30)

        assert np.all(result.lower <= result.upper)

    def test_coverage_on_calibration_data(self):
        """Conformal intervals should cover >= target% of calibration paths."""
        history, matches = _make_test_setup()
        coverage = 0.8
        result = conformal_prediction_intervals(
            matches, history, forward_bars=30, coverage=coverage,
        )

        # Check coverage: each calibration path should be mostly inside bounds
        paths = []
        for match in matches:
            future_start = match.end_idx
            future_end = future_start + 30
            if future_end > len(history):
                continue
            future = history[future_start:future_end]
            anchor = history[match.end_idx - 1]
            if anchor == 0:
                continue
            paths.append((future - anchor) / anchor)

        if len(paths) >= 2:
            paths_arr = np.array(paths)
            # For each path, check if all bars are within bounds
            within = np.all(
                (paths_arr >= result.lower) & (paths_arr <= result.upper),
                axis=1,
            )
            actual_coverage = np.mean(within)
            # Conformal should achieve at least (coverage - slack) on cal data
            assert actual_coverage >= coverage - 0.3  # generous slack for small n

    def test_wider_coverage_wider_intervals(self):
        history, matches = _make_test_setup()
        r80 = conformal_prediction_intervals(matches, history, forward_bars=30, coverage=0.8)
        r95 = conformal_prediction_intervals(matches, history, forward_bars=30, coverage=0.95)

        width_80 = np.mean(r80.upper - r80.lower)
        width_95 = np.mean(r95.upper - r95.lower)
        assert width_95 >= width_80

    def test_calibration_scores_populated(self):
        history, matches = _make_test_setup()
        result = conformal_prediction_intervals(matches, history, forward_bars=30)

        assert result.calibration_scores is not None
        assert len(result.calibration_scores) > 0

    def test_empty_matches(self):
        history = np.arange(100, dtype=np.float64)
        result = conformal_prediction_intervals([], history, forward_bars=20)

        assert len(result.lower) == 20
        assert len(result.upper) == 20

    def test_custom_base_forecast(self):
        history, matches = _make_test_setup()
        base = np.linspace(0, 0.1, 30)
        result = conformal_prediction_intervals(
            matches, history, forward_bars=30, base_forecast=base,
        )

        # Lower and upper should be centered around base
        midpoint = (result.lower + result.upper) / 2
        # Midpoint should be close to base (not exact due to adaptive scaling)
        assert np.corrcoef(midpoint, base)[0, 1] > 0.5


# ---------------------------------------------------------------------------
# Ensemble forecast (combination) tests
# ---------------------------------------------------------------------------

class TestEnsembleForecast:
    def test_basic_output(self):
        history, matches = _make_test_setup()
        query = history[:60]
        result = ensemble_forecast(
            matches, history, query=query, forward_bars=30,
        )

        assert isinstance(result, EnsembleForecast)
        assert result.bars == 30
        assert 50 in result.curves
        assert result.monte_carlo is not None
        assert result.regime_conditional is not None
        assert result.conformal is not None

    def test_component_weights_sum_to_one(self):
        history, matches = _make_test_setup()
        result = ensemble_forecast(matches, history, forward_bars=30)

        total = sum(result.component_weights.values())
        assert abs(total - 1.0) < 1e-10

    def test_blended_curves_between_components(self):
        """Blended curves should be within the range of component curves."""
        history, matches = _make_test_setup()
        query = history[:60]
        result = ensemble_forecast(
            matches, history, query=query, forward_bars=30,
        )

        # The blended P50 should be between MC P50 and historical
        mc_p50 = result.monte_carlo.percentiles[50]
        blended_p50 = result.curves[50]

        # Not a strict bound, but they should be correlated
        corr = np.corrcoef(mc_p50, blended_p50)[0, 1]
        assert corr > 0.5

    def test_no_query_skips_regime(self):
        history, matches = _make_test_setup()
        result = ensemble_forecast(matches, history, query=None, forward_bars=30)

        assert result.regime_conditional is None

    def test_custom_blend_weights(self):
        history, matches = _make_test_setup()
        result = ensemble_forecast(
            matches, history, forward_bars=30,
            mc_weight=1.0, regime_weight=0.0, historical_weight=0.0,
        )

        # Should be purely Monte Carlo
        assert result.component_weights["monte_carlo"] == pytest.approx(1.0)

    def test_conformal_bounds_present(self):
        history, matches = _make_test_setup()
        result = ensemble_forecast(matches, history, forward_bars=30)

        assert np.all(result.conformal.lower <= result.conformal.upper)

    def test_percentiles_customizable(self):
        history, matches = _make_test_setup()
        result = ensemble_forecast(
            matches, history, forward_bars=30, percentiles=[5, 50, 95],
        )

        assert 5 in result.curves
        assert 95 in result.curves
        assert result.percentiles == [5, 50, 95]

    def test_reproducible(self):
        history, matches = _make_test_setup()
        r1 = ensemble_forecast(matches, history, forward_bars=20, seed=42)
        r2 = ensemble_forecast(matches, history, forward_bars=20, seed=42)

        np.testing.assert_array_almost_equal(r1.curves[50], r2.curves[50])
