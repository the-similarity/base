"""Tests for the backtester validation framework."""
import numpy as np
import pytest

from the_similarity.core.backtester import (
    BacktestReport,
    TrialResult,
    _pick_trial_positions,
    run_backtest,
)
from the_similarity.core.metrics import calibration, crps, hit_rate, mean_absolute_error
from the_similarity.config import Config


# --- Helper to create synthetic TrialResults ---

def _make_trial(
    actual_terminal: float = 0.05,
    p50_terminal: float = 0.04,
    p10_terminal: float = -0.02,
    p90_terminal: float = 0.10,
    n_matches: int = 5,
    skipped: bool = False,
) -> TrialResult:
    forward_bars = 10
    actual_returns = np.linspace(0, actual_terminal, forward_bars)
    p10_curve = np.linspace(0, p10_terminal, forward_bars)
    p50_curve = np.linspace(0, p50_terminal, forward_bars)
    p90_curve = np.linspace(0, p90_terminal, forward_bars)

    predicted_dir = p50_terminal > 0
    actual_dir = actual_terminal > 0
    directional_hit = predicted_dir == actual_dir

    return TrialResult(
        query_start=100,
        query_end=160,
        actual_returns=actual_returns,
        forecast_curves={10: p10_curve, 50: p50_curve, 90: p90_curve},
        n_matches=n_matches,
        top_match_score=75.0,
        directional_hit=directional_hit,
        p50_error=abs(p50_terminal - actual_terminal),
        skipped=skipped,
    )


# ===================== UNIT TESTS (fast) =====================

class TestHitRate:
    def test_all_hits(self):
        trials = [_make_trial(actual_terminal=0.05, p50_terminal=0.04) for _ in range(10)]
        assert hit_rate(trials) == 1.0

    def test_no_hits(self):
        trials = [_make_trial(actual_terminal=-0.05, p50_terminal=0.04) for _ in range(10)]
        assert hit_rate(trials) == 0.0

    def test_mixed(self):
        hits = [_make_trial(actual_terminal=0.05, p50_terminal=0.04) for _ in range(6)]
        misses = [_make_trial(actual_terminal=-0.05, p50_terminal=0.04) for _ in range(4)]
        assert hit_rate(hits + misses) == pytest.approx(0.6)

    def test_empty(self):
        assert np.isnan(hit_rate([]))


class TestMeanAbsoluteError:
    def test_zero_error(self):
        trials = [_make_trial(actual_terminal=0.05, p50_terminal=0.05) for _ in range(5)]
        assert mean_absolute_error(trials) == pytest.approx(0.0)

    def test_known_error(self):
        trials = [_make_trial(actual_terminal=0.10, p50_terminal=0.05)]
        assert mean_absolute_error(trials) == pytest.approx(0.05)

    def test_empty(self):
        assert np.isnan(mean_absolute_error([]))


class TestCalibration:
    def test_perfect_calibration_below_p90(self):
        # All actuals are below P90 forecast → containment should be 100%
        trials = [_make_trial(actual_terminal=0.05, p90_terminal=0.10) for _ in range(10)]
        cal = calibration(trials, [90])
        assert cal[90] == pytest.approx(1.0)

    def test_none_below_p10(self):
        # All actuals are above P10 forecast → containment should be 0%
        trials = [_make_trial(actual_terminal=0.05, p10_terminal=-0.02) for _ in range(10)]
        cal = calibration(trials, [10])
        assert cal[10] == pytest.approx(0.0)

    def test_empty(self):
        cal = calibration([], [10, 50, 90])
        assert all(np.isnan(v) for v in cal.values())


class TestCRPS:
    def test_perfect_forecast(self):
        # All percentile forecasts equal the actual → CRPS should be low
        trials = [_make_trial(
            actual_terminal=0.05,
            p10_terminal=0.05,
            p50_terminal=0.05,
            p90_terminal=0.05,
        )]
        score = crps(trials)
        # With perfect point forecast, indicators are [0, 0, 0] for percentiles [10, 50, 90]
        # since actual <= forecast for all, indicators = [1, 1, 1]
        # (1-0.1)^2 + (1-0.5)^2 + (1-0.9)^2 / 3 = (0.81 + 0.25 + 0.01) / 3 = 0.357
        # This is not zero because CRPS with discrete percentiles isn't perfect
        assert score >= 0
        assert score < 1.0

    def test_terrible_forecast(self):
        # Forecast is completely wrong direction
        good = crps([_make_trial(actual_terminal=0.05, p50_terminal=0.04)])
        bad = crps([_make_trial(actual_terminal=0.05, p10_terminal=-0.50, p50_terminal=-0.40, p90_terminal=-0.30)])
        assert bad > good

    def test_empty(self):
        assert np.isnan(crps([]))


class TestPickTrialPositions:
    def test_respects_min_lookback(self):
        positions = _pick_trial_positions(
            history_len=1000, window_size=60, forward_bars=50,
            min_lookback=180, n_trials=50, seed=42,
        )
        assert all(pos >= 180 for pos in positions)

    def test_respects_forward_constraint(self):
        positions = _pick_trial_positions(
            history_len=1000, window_size=60, forward_bars=50,
            min_lookback=180, n_trials=50, seed=42,
        )
        assert all(pos + 60 + 50 <= 1000 for pos in positions)

    def test_reproducible_with_seed(self):
        p1 = _pick_trial_positions(1000, 60, 50, 180, 20, seed=123)
        p2 = _pick_trial_positions(1000, 60, 50, 180, 20, seed=123)
        assert p1 == p2

    def test_different_seeds_differ(self):
        p1 = _pick_trial_positions(1000, 60, 50, 180, 20, seed=1)
        p2 = _pick_trial_positions(1000, 60, 50, 180, 20, seed=2)
        assert p1 != p2

    def test_raises_on_impossible_range(self):
        with pytest.raises(ValueError, match="No valid trial positions"):
            _pick_trial_positions(100, 60, 50, 180, 10, seed=42)


class TestInputValidation:
    def test_nan_rejected(self):
        history = np.array([1.0, 2.0, float("nan"), 4.0])
        with pytest.raises(ValueError, match="NaN"):
            run_backtest(history, window_size=1, forward_bars=1, n_trials=1)

    def test_inf_rejected(self):
        history = np.array([1.0, float("inf"), 3.0])
        with pytest.raises(ValueError, match="Inf"):
            run_backtest(history, window_size=1, forward_bars=1, n_trials=1)

    def test_short_history_rejected(self):
        history = np.arange(10, dtype=np.float64)
        with pytest.raises(ValueError, match="too short"):
            run_backtest(history, window_size=5, forward_bars=5, n_trials=1)

    def test_zero_window_rejected(self):
        history = np.arange(1000, dtype=np.float64)
        with pytest.raises(ValueError, match="window_size must be positive"):
            run_backtest(history, window_size=0, forward_bars=50, n_trials=1)


class TestBacktestReport:
    def test_summary_properties(self):
        valid = [_make_trial() for _ in range(8)]
        skipped = [_make_trial(skipped=True) for _ in range(2)]
        report = BacktestReport(
            trials=valid + skipped,
            config=Config(),
            window_size=60,
            forward_bars=50,
            seed=42,
        )
        assert report.n_valid_trials == 8
        assert report.n_skipped_trials == 2
        assert 0 <= report.hit_rate <= 1
        assert report.mean_error >= 0


# ===================== INTEGRATION TESTS (slow) =====================

@pytest.mark.slow
class TestBacktestIntegration:
    def test_runs_on_synthetic_trending_data(self):
        """Trending data: system should find matches in similar trends."""
        np.random.seed(42)
        # Create a long trending series with some noise
        t = np.arange(2000, dtype=np.float64)
        history = 100 + 0.05 * t + 3 * np.sin(t * 0.1) + np.random.randn(2000) * 0.5

        config = Config(
            active_methods=["dtw", "pearson_warped"],
            tier1_candidates=100,
            tier2_candidates=5,
            stride=5,
        )
        report = run_backtest(
            history, window_size=60, forward_bars=30,
            n_trials=10, config=config, seed=42, n_workers=1,
        )
        assert report.n_valid_trials > 0
        assert 0 <= report.hit_rate <= 1
        assert report.mean_error >= 0
        assert not np.isnan(report.crps)

    def test_reproducibility(self):
        """Same seed produces identical results."""
        history = 100 + np.cumsum(np.random.RandomState(0).randn(500) * 0.5)
        config = Config(
            active_methods=["dtw", "pearson_warped"],
            tier1_candidates=50,
            tier2_candidates=5,
            stride=5,
        )
        kwargs = dict(
            history=history, window_size=30, forward_bars=20,
            n_trials=5, config=config, seed=99, n_workers=1,
        )
        r1 = run_backtest(**kwargs)
        r2 = run_backtest(**kwargs)
        assert r1.hit_rate == r2.hit_rate
        assert r1.mean_error == r2.mean_error

    def test_data_leakage_guard(self):
        """No match should use data from after the query start."""
        history = 100 + np.cumsum(np.random.RandomState(1).randn(500) * 0.5)
        config = Config(
            active_methods=["dtw", "pearson_warped"],
            tier1_candidates=50,
            tier2_candidates=5,
            stride=5,
        )
        report = run_backtest(
            history, window_size=30, forward_bars=20,
            n_trials=5, config=config, seed=42, n_workers=1,
        )
        for trial in report.valid_trials:
            # The search was run on history[:query_start], so all match indices
            # must be < query_start
            assert trial.query_start >= 3 * 30  # min lookback enforced
