"""Strategy Builder — rule engine for trading signal generation.

Phase 7a — chains pattern matches + forecast cones into entry/exit
trading signals using configurable rule-based strategies.

AI AGENT NOTES:
- This is the execution tier bridging the gap between raw pattern recognition
  and actionable trading signals.
- Architecture: A `Strategy` is a named collection of `Rule` objects evaluated
  in priority order.
- The `evaluate_strategy()` loop runs through matched analogs. The first Rule
  that fires generates a `Signal` (Long/Short/Flat) tagged with dynamic Stops
  and Take Profits derived from the Forecast percentiles (e.g., P10 for Long
  Stop, P75 for Long Target).
- The module includes a mini backtesting engine (`validate_strategy_backtest`)
  that evaluates the historical performance of these logical rules directly over
  the matched instances, returning Win Rates and average returns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import numpy as np
from numpy.typing import NDArray

from the_similarity.core.scorer import MatchResult
from the_similarity.core.projector import Forecast
from the_similarity.core.ensemble import EnsembleForecast


# ---------------------------------------------------------------------------
# Signal types
# ---------------------------------------------------------------------------

class SignalType(Enum):
    """Direction of a trading signal."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """A trading signal produced by strategy evaluation."""
    signal_type: SignalType
    confidence: float  # 0-100, from match confidence
    entry_price: float | None = None  # suggested entry
    stop_loss: float | None = None  # suggested stop
    take_profit: float | None = None  # suggested take profit
    reason: str = ""  # human-readable explanation
    match: MatchResult | None = None  # source match
    forecast: Forecast | EnsembleForecast | None = None


@dataclass
class Rule:
    """A single condition that can produce a signal."""
    name: str
    condition: Callable[[MatchResult, Forecast | EnsembleForecast | None, dict], bool]
    signal_type: SignalType
    priority: int = 0  # higher = checked first


@dataclass
class Strategy:
    """Named collection of rules for signal generation."""
    name: str
    rules: list[Rule]
    min_confidence: float = 60.0  # minimum match confidence to consider
    max_signals: int = 1  # max concurrent signals


@dataclass
class StrategyBacktestResult:
    """Result of backtesting a strategy against historical matches."""
    total_signals: int
    long_signals: int
    short_signals: int
    win_rate: float  # % of signals where price moved in signal direction
    avg_return: float
    sharpe_ratio: float  # annualized, if enough signals
    signals: list[Signal] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Forecast helpers
# ---------------------------------------------------------------------------

def _get_forecast_curves(
    forecast: Forecast | EnsembleForecast | None,
) -> dict[int, NDArray[np.float64]]:
    """Extract percentile curves from a Forecast or EnsembleForecast."""
    if forecast is None:
        return {}
    return forecast.curves


def _get_curve_endpoint(
    curves: dict[int, NDArray[np.float64]],
    percentile: int,
) -> float | None:
    """Get the final value of a percentile curve (cumulative return at horizon)."""
    curve = curves.get(percentile)
    if curve is None or len(curve) == 0:
        return None
    return float(curve[-1])


# ---------------------------------------------------------------------------
# Strategy evaluation
# ---------------------------------------------------------------------------

def evaluate_strategy(
    strategy: Strategy,
    matches: list[MatchResult],
    history: NDArray,
    forecast: Forecast | EnsembleForecast | None = None,
    current_price: float | None = None,
) -> list[Signal]:
    """Evaluate a strategy against matches and produce trading signals.

    Filters matches by min_confidence, then for each match (sorted by
    confidence descending) evaluates rules in priority order. The first
    matching rule produces a Signal. Returns up to max_signals signals.

    Args:
        strategy: Strategy with rules to evaluate.
        matches: Match results from the pattern matcher.
        history: Full raw price history.
        forecast: Optional forecast (Forecast or EnsembleForecast).
        current_price: Current market price for entry/stop/target calc.
            If None, uses the last value of history.

    Returns:
        List of Signal objects, up to strategy.max_signals.
    """
    if not matches:
        return []

    if current_price is None:
        current_price = float(history[-1]) if len(history) > 0 else None

    # Filter by minimum confidence
    qualified = [m for m in matches if m.confidence_score >= strategy.min_confidence]
    if not qualified:
        return []

    # Sort by confidence descending
    qualified.sort(key=lambda m: m.confidence_score, reverse=True)

    # Sort rules by priority descending
    sorted_rules = sorted(strategy.rules, key=lambda r: r.priority, reverse=True)

    curves = _get_forecast_curves(forecast)

    # Build context dict for rule conditions
    context = {
        "history": history,
        "current_price": current_price,
        "curves": curves,
        "forecast": forecast,
    }

    # Add percentile endpoints to context for convenient access
    for p in [10, 25, 50, 75, 90]:
        endpoint = _get_curve_endpoint(curves, p)
        context[f"p{p}"] = endpoint

    # Add spread info
    p90 = context.get("p90")
    p10 = context.get("p10")
    if p90 is not None and p10 is not None:
        context["spread"] = p90 - p10
    else:
        context["spread"] = None

    signals: list[Signal] = []

    for match in qualified:
        if len(signals) >= strategy.max_signals:
            break

        # Add match-specific context
        context["regime"] = match.regime

        for rule in sorted_rules:
            try:
                if rule.condition(match, forecast, context):
                    # Build signal with price levels
                    entry = current_price
                    stop_loss = _compute_stop(
                        rule.signal_type, current_price, curves,
                    )
                    take_profit = _compute_target(
                        rule.signal_type, current_price, curves,
                    )

                    signal = Signal(
                        signal_type=rule.signal_type,
                        confidence=match.confidence_score,
                        entry_price=entry,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        reason=rule.name,
                        match=match,
                        forecast=forecast,
                    )
                    signals.append(signal)
                    break  # first matching rule wins for this match
            except Exception:
                # Rule evaluation failed; skip to next rule
                continue

    return signals


def _compute_stop(
    signal_type: SignalType,
    current_price: float | None,
    curves: dict[int, NDArray[np.float64]],
) -> float | None:
    """Compute stop-loss price from forecast curves."""
    if current_price is None:
        return None

    if signal_type == SignalType.LONG:
        p10 = _get_curve_endpoint(curves, 10)
        if p10 is not None:
            return current_price * (1.0 + p10)
    elif signal_type == SignalType.SHORT:
        p90 = _get_curve_endpoint(curves, 90)
        if p90 is not None:
            return current_price * (1.0 + p90)

    return None


def _compute_target(
    signal_type: SignalType,
    current_price: float | None,
    curves: dict[int, NDArray[np.float64]],
) -> float | None:
    """Compute take-profit price from forecast curves."""
    if current_price is None:
        return None

    if signal_type == SignalType.LONG:
        p75 = _get_curve_endpoint(curves, 75)
        if p75 is not None:
            return current_price * (1.0 + p75)
    elif signal_type == SignalType.SHORT:
        p25 = _get_curve_endpoint(curves, 25)
        if p25 is not None:
            return current_price * (1.0 + p25)

    return None


# ---------------------------------------------------------------------------
# Built-in strategy templates
# ---------------------------------------------------------------------------

def momentum_strategy(
    min_confidence: float = 70.0,
    forecast_threshold: float = 0.02,
) -> Strategy:
    """Momentum-following strategy.

    Goes long when P50 forecast exceeds threshold in trending-up regime,
    short when P50 is below negative threshold in trending-down regime.
    Stop loss at P10 (longs) / P90 (shorts), take profit at P75 / P25.

    Args:
        min_confidence: Minimum match confidence to consider.
        forecast_threshold: P50 return threshold to trigger signal.

    Returns:
        Strategy configured for momentum trading.
    """

    def _long_condition(
        match: MatchResult,
        forecast: Forecast | EnsembleForecast | None,
        ctx: dict,
    ) -> bool:
        p50 = ctx.get("p50")
        regime = ctx.get("regime")
        return (
            p50 is not None
            and p50 > forecast_threshold
            and regime == "trending_up"
        )

    def _short_condition(
        match: MatchResult,
        forecast: Forecast | EnsembleForecast | None,
        ctx: dict,
    ) -> bool:
        p50 = ctx.get("p50")
        regime = ctx.get("regime")
        return (
            p50 is not None
            and p50 < -forecast_threshold
            and regime == "trending_down"
        )

    return Strategy(
        name="momentum",
        rules=[
            Rule(
                name="Momentum long: P50 > threshold, trending up",
                condition=_long_condition,
                signal_type=SignalType.LONG,
                priority=1,
            ),
            Rule(
                name="Momentum short: P50 < -threshold, trending down",
                condition=_short_condition,
                signal_type=SignalType.SHORT,
                priority=1,
            ),
        ],
        min_confidence=min_confidence,
    )


def mean_reversion_strategy(
    min_confidence: float = 65.0,
    reversion_threshold: float = 0.03,
) -> Strategy:
    """Mean-reversion strategy.

    Looks for wide P90-P10 spread in mean-reverting regime, then trades
    against the P50 direction expecting reversion. Stop loss at extremes,
    take profit at P50.

    Args:
        min_confidence: Minimum match confidence.
        reversion_threshold: P50 magnitude threshold for entry.

    Returns:
        Strategy configured for mean reversion.
    """

    def _long_condition(
        match: MatchResult,
        forecast: Forecast | EnsembleForecast | None,
        ctx: dict,
    ) -> bool:
        p50 = ctx.get("p50")
        spread = ctx.get("spread")
        regime = ctx.get("regime")
        return (
            p50 is not None
            and spread is not None
            and spread > reversion_threshold
            and regime == "mean_reverting"
            and p50 < -reversion_threshold
        )

    def _short_condition(
        match: MatchResult,
        forecast: Forecast | EnsembleForecast | None,
        ctx: dict,
    ) -> bool:
        p50 = ctx.get("p50")
        spread = ctx.get("spread")
        regime = ctx.get("regime")
        return (
            p50 is not None
            and spread is not None
            and spread > reversion_threshold
            and regime == "mean_reverting"
            and p50 > reversion_threshold
        )

    return Strategy(
        name="mean_reversion",
        rules=[
            Rule(
                name="Mean reversion long: wide spread, P50 below threshold",
                condition=_long_condition,
                signal_type=SignalType.LONG,
                priority=1,
            ),
            Rule(
                name="Mean reversion short: wide spread, P50 above threshold",
                condition=_short_condition,
                signal_type=SignalType.SHORT,
                priority=1,
            ),
        ],
        min_confidence=min_confidence,
    )


def breakout_strategy(
    min_confidence: float = 75.0,
    vol_expansion: float = 1.5,
) -> Strategy:
    """Volatility breakout strategy.

    Trades in the direction of the forecast when regime is high-volatility,
    using wider stops to account for elevated volatility.

    Args:
        min_confidence: Minimum match confidence.
        vol_expansion: Not used directly in rules but documents the
            intended volatility context (high_vol regime implies expansion).

    Returns:
        Strategy configured for breakout trading.
    """

    def _long_condition(
        match: MatchResult,
        forecast: Forecast | EnsembleForecast | None,
        ctx: dict,
    ) -> bool:
        p75 = ctx.get("p75")
        regime = ctx.get("regime")
        return (
            p75 is not None
            and regime == "high_vol"
            and p75 > 0
        )

    def _short_condition(
        match: MatchResult,
        forecast: Forecast | EnsembleForecast | None,
        ctx: dict,
    ) -> bool:
        p25 = ctx.get("p25")
        regime = ctx.get("regime")
        return (
            p25 is not None
            and regime == "high_vol"
            and p25 < 0
        )

    return Strategy(
        name="breakout",
        rules=[
            Rule(
                name="Breakout long: high vol, P75 > 0",
                condition=_long_condition,
                signal_type=SignalType.LONG,
                priority=1,
            ),
            Rule(
                name="Breakout short: high vol, P25 < 0",
                condition=_short_condition,
                signal_type=SignalType.SHORT,
                priority=1,
            ),
        ],
        min_confidence=min_confidence,
    )


# ---------------------------------------------------------------------------
# Strategy backtesting
# ---------------------------------------------------------------------------

def validate_strategy_backtest(
    strategy: Strategy,
    matches: list[MatchResult],
    history: NDArray,
    forward_bars: int = 50,
) -> StrategyBacktestResult:
    """Backtest a strategy against historical matches.

    For each match with a valid forward window, generates a forecast
    from that single match, evaluates the strategy, and checks whether
    the resulting signal was correct (price moved in signal direction).

    Args:
        strategy: Strategy to test.
        matches: Historical match results.
        history: Full raw price history.
        forward_bars: Bars to look forward for outcome evaluation.

    Returns:
        StrategyBacktestResult with performance metrics.
    """
    from the_similarity.core.projector import project

    all_signals: list[Signal] = []

    for match in matches:
        future_start = match.end_idx
        future_end = future_start + forward_bars

        if future_end > len(history):
            continue

        anchor = history[match.end_idx - 1]
        if anchor == 0:
            continue

        # Generate forecast from this single match
        forecast = project(
            [match], history, forward_bars=forward_bars,
        )

        current_price = float(history[match.end_idx - 1])

        signals = evaluate_strategy(
            strategy, [match], history,
            forecast=forecast,
            current_price=current_price,
        )
        all_signals.extend(signals)

    # Compute metrics
    total = len(all_signals)
    longs = sum(1 for s in all_signals if s.signal_type == SignalType.LONG)
    shorts = sum(1 for s in all_signals if s.signal_type == SignalType.SHORT)

    if total == 0:
        return StrategyBacktestResult(
            total_signals=0,
            long_signals=0,
            short_signals=0,
            win_rate=0.0,
            avg_return=0.0,
            sharpe_ratio=0.0,
            signals=[],
        )

    # Evaluate outcomes
    returns: list[float] = []
    wins = 0

    for signal in all_signals:
        if signal.match is None:
            continue

        future_start = signal.match.end_idx
        future_end = future_start + forward_bars

        if future_end > len(history):
            continue

        entry = history[signal.match.end_idx - 1]
        exit_price = history[future_end - 1]

        if entry == 0:
            continue

        pct_return = (exit_price - entry) / entry

        if signal.signal_type == SignalType.SHORT:
            pct_return = -pct_return

        returns.append(pct_return)
        if pct_return > 0:
            wins += 1

    n_evaluated = len(returns)
    win_rate = (wins / n_evaluated * 100.0) if n_evaluated > 0 else 0.0
    avg_return = float(np.mean(returns)) if returns else 0.0

    # Sharpe ratio (annualized, assume daily bars)
    if len(returns) >= 2:
        ret_arr = np.array(returns)
        std = float(np.std(ret_arr, ddof=1))
        if std > 0:
            sharpe = float(np.mean(ret_arr) / std * np.sqrt(252))
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    return StrategyBacktestResult(
        total_signals=total,
        long_signals=longs,
        short_signals=shorts,
        win_rate=win_rate,
        avg_return=avg_return,
        sharpe_ratio=sharpe,
        signals=all_signals,
    )
