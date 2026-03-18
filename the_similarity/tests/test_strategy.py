"""Tests for Strategy Builder (Phase 7a).

Covers signal generation from built-in strategies, strategy evaluation
mechanics, custom rules, and strategy backtesting.
"""
import numpy as np
import pytest

from the_similarity.core.strategy import (
    SignalType,
    Signal,
    Rule,
    Strategy,
    StrategyBacktestResult,
    evaluate_strategy,
    momentum_strategy,
    mean_reversion_strategy,
    breakout_strategy,
    validate_strategy_backtest,
)
from the_similarity.core.scorer import MatchResult, ScoreBreakdown
from the_similarity.core.projector import Forecast


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


def _make_forecast(
    forward_bars: int = 50,
    p50_end: float = 0.05,
    spread: float = 0.10,
) -> Forecast:
    """Create a synthetic Forecast with controlled percentile endpoints.

    Args:
        forward_bars: Number of bars in the forecast.
        p50_end: Terminal value of P50 curve (cumulative return).
        spread: P90 - P10 spread at the endpoint.
    """
    bars = forward_bars
    t = np.linspace(0, 1, bars)

    p10_end = p50_end - spread / 2
    p25_end = p50_end - spread / 4
    p75_end = p50_end + spread / 4
    p90_end = p50_end + spread / 2

    curves = {
        10: t * p10_end,
        25: t * p25_end,
        50: t * p50_end,
        75: t * p75_end,
        90: t * p90_end,
    }

    n_paths = 5
    rng = np.random.default_rng(42)
    all_paths = np.outer(np.ones(n_paths), t * p50_end) + 0.01 * rng.standard_normal((n_paths, bars))
    weights = np.ones(n_paths) / n_paths

    return Forecast(
        bars=bars,
        percentiles=[10, 25, 50, 75, 90],
        curves=curves,
        all_paths=all_paths,
        weights=weights,
    )


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
# TestSignalGeneration
# ---------------------------------------------------------------------------

class TestSignalGeneration:

    def test_momentum_long_signal(self):
        """Momentum strategy should produce a LONG signal for trending-up match
        with positive P50 forecast."""
        history, _ = _make_test_setup()
        match = _make_match(0, 50, score=80.0, regime="trending_up")
        forecast = _make_forecast(p50_end=0.05, spread=0.10)
        strategy = momentum_strategy(min_confidence=70.0, forecast_threshold=0.02)

        signals = evaluate_strategy(
            strategy, [match], history, forecast=forecast,
        )

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.LONG
        assert signals[0].confidence == 80.0
        assert signals[0].entry_price is not None
        assert signals[0].stop_loss is not None
        assert signals[0].take_profit is not None
        assert "long" in signals[0].reason.lower() or "momentum" in signals[0].reason.lower()

    def test_momentum_short_signal(self):
        """Momentum strategy should produce a SHORT signal for trending-down
        match with negative P50 forecast."""
        history, _ = _make_test_setup()
        match = _make_match(0, 50, score=80.0, regime="trending_down")
        forecast = _make_forecast(p50_end=-0.05, spread=0.10)
        strategy = momentum_strategy(min_confidence=70.0, forecast_threshold=0.02)

        signals = evaluate_strategy(
            strategy, [match], history, forecast=forecast,
        )

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SHORT
        assert signals[0].confidence == 80.0

    def test_no_signal_below_min_confidence(self):
        """No signal should be generated when match confidence is below minimum."""
        history, _ = _make_test_setup()
        match = _make_match(0, 50, score=50.0, regime="trending_up")
        forecast = _make_forecast(p50_end=0.05, spread=0.10)
        strategy = momentum_strategy(min_confidence=70.0)

        signals = evaluate_strategy(
            strategy, [match], history, forecast=forecast,
        )

        assert len(signals) == 0

    def test_mean_reversion_long(self):
        """Mean reversion should go LONG when P50 is below negative threshold
        in mean-reverting regime with wide spread."""
        history, _ = _make_test_setup()
        match = _make_match(0, 50, score=75.0, regime="mean_reverting")
        # P50 negative, wide spread
        forecast = _make_forecast(p50_end=-0.05, spread=0.15)
        strategy = mean_reversion_strategy(min_confidence=65.0, reversion_threshold=0.03)

        signals = evaluate_strategy(
            strategy, [match], history, forecast=forecast,
        )

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.LONG

    def test_breakout_long(self):
        """Breakout strategy should go LONG when regime is high_vol and P75 > 0."""
        history, _ = _make_test_setup()
        match = _make_match(0, 50, score=80.0, regime="high_vol")
        forecast = _make_forecast(p50_end=0.03, spread=0.10)
        strategy = breakout_strategy(min_confidence=75.0)

        signals = evaluate_strategy(
            strategy, [match], history, forecast=forecast,
        )

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.LONG


# ---------------------------------------------------------------------------
# TestStrategyEvaluation
# ---------------------------------------------------------------------------

class TestStrategyEvaluation:

    def test_evaluate_returns_max_signals(self):
        """Should return at most max_signals signals."""
        history, _ = _make_test_setup()
        matches = [
            _make_match(0, 50, score=90.0, regime="trending_up"),
            _make_match(50, 100, score=85.0, regime="trending_up"),
            _make_match(100, 150, score=80.0, regime="trending_up"),
        ]
        forecast = _make_forecast(p50_end=0.05, spread=0.10)
        strategy = momentum_strategy(min_confidence=70.0)
        strategy.max_signals = 2

        signals = evaluate_strategy(
            strategy, matches, history, forecast=forecast,
        )

        assert len(signals) <= 2

    def test_rules_checked_in_priority_order(self):
        """Higher priority rules should be evaluated first."""
        history, _ = _make_test_setup()
        match = _make_match(0, 50, score=80.0, regime="trending_up")
        forecast = _make_forecast(p50_end=0.05, spread=0.10)

        call_order = []

        def _low_priority_rule(m, f, ctx):
            call_order.append("low")
            return True

        def _high_priority_rule(m, f, ctx):
            call_order.append("high")
            return True

        strategy = Strategy(
            name="priority_test",
            rules=[
                Rule(
                    name="Low priority",
                    condition=_low_priority_rule,
                    signal_type=SignalType.LONG,
                    priority=0,
                ),
                Rule(
                    name="High priority",
                    condition=_high_priority_rule,
                    signal_type=SignalType.SHORT,
                    priority=10,
                ),
            ],
            min_confidence=60.0,
        )

        signals = evaluate_strategy(
            strategy, [match], history, forecast=forecast,
        )

        assert len(signals) == 1
        # High priority rule should have been checked first and matched
        assert call_order[0] == "high"
        assert signals[0].signal_type == SignalType.SHORT

    def test_empty_matches_no_signals(self):
        """Empty match list should produce no signals."""
        history, _ = _make_test_setup()
        strategy = momentum_strategy()

        signals = evaluate_strategy(strategy, [], history)

        assert len(signals) == 0

    def test_custom_rule(self):
        """A custom rule should be evaluable in the strategy engine."""
        history, _ = _make_test_setup()
        match = _make_match(0, 50, score=90.0, regime="trending_up")
        forecast = _make_forecast(p50_end=0.05, spread=0.10)

        def _always_long(m, f, ctx):
            return m.confidence_score > 80.0

        strategy = Strategy(
            name="custom",
            rules=[
                Rule(
                    name="Always long if confidence > 80",
                    condition=_always_long,
                    signal_type=SignalType.LONG,
                    priority=1,
                ),
            ],
            min_confidence=50.0,
        )

        signals = evaluate_strategy(
            strategy, [match], history, forecast=forecast,
        )

        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.LONG
        assert signals[0].confidence == 90.0


# ---------------------------------------------------------------------------
# TestStrategyBacktest
# ---------------------------------------------------------------------------

class TestStrategyBacktest:

    def test_backtest_returns_metrics(self):
        """Backtesting should return a StrategyBacktestResult with valid metrics."""
        history = _trending_up_history(600)
        matches = [
            _make_match(0, 50, score=85.0, regime="trending_up"),
            _make_match(50, 100, score=80.0, regime="trending_up"),
            _make_match(100, 150, score=75.0, regime="trending_up"),
        ]
        strategy = momentum_strategy(min_confidence=70.0, forecast_threshold=0.0)

        result = validate_strategy_backtest(
            strategy, matches, history, forward_bars=50,
        )

        assert isinstance(result, StrategyBacktestResult)
        assert result.total_signals >= 0
        assert result.long_signals >= 0
        assert result.short_signals >= 0
        assert 0.0 <= result.win_rate <= 100.0
        assert isinstance(result.avg_return, float)
        assert isinstance(result.sharpe_ratio, float)

    def test_backtest_empty_signals(self):
        """Backtest with no qualifying matches should return zero metrics."""
        history = _trending_up_history(300)
        # All matches below min confidence
        matches = [
            _make_match(0, 50, score=30.0, regime="trending_up"),
            _make_match(50, 100, score=25.0, regime="trending_up"),
        ]
        strategy = momentum_strategy(min_confidence=90.0)

        result = validate_strategy_backtest(
            strategy, matches, history, forward_bars=50,
        )

        assert result.total_signals == 0
        assert result.long_signals == 0
        assert result.short_signals == 0
        assert result.win_rate == 0.0
        assert result.avg_return == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.signals == []
