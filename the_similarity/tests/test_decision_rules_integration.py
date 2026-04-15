"""Integration test: calibration-aware rules on a real api.backtest run.

Exercises the full chain:
    api.backtest -> BacktestReport.calibration ->
    TrustFilter -> CalibrationAwareStrategy -> signals differ from naive

Uses a small synthetic slice (`the_similarity.api` + a trending series)
so this runs in seconds, keeping the ``tests/`` default suite fast.
The aim is not to measure statistical significance — it is to prove the
pipeline is wired end-to-end, and that the aware variant VETOES trades
on low-sample cones that the naive variant would accept.
"""

from __future__ import annotations

import numpy as np
import pytest

import the_similarity
from the_similarity.config import Config
from the_similarity.api import backtest, search, project
from the_similarity.core.decision_rules import (
    CalibrationAwareStrategy,
    DecisionRuleConfig,
    evaluate_with_trust,
    summarise_review,
)
from the_similarity.core.strategy import (
    Rule,
    Strategy,
    SignalType,
    evaluate_strategy,
)
from the_similarity.core.trust_filter import TrustFilter


def _always_long_strategy() -> Strategy:
    """A trivially-true rule — isolates gating, not rule logic."""

    def _cond(match, forecast, ctx):
        return True

    return Strategy(
        name="always_long",
        rules=[Rule(name="always_long", condition=_cond, signal_type=SignalType.LONG)],
        min_confidence=0.0,
    )


@pytest.mark.slow
def test_api_backtest_drives_calibration_aware_gate():
    """End-to-end: api.backtest -> CalibrationAwareStrategy on a small slice."""
    np.random.seed(42)
    t = np.arange(1500, dtype=np.float64)
    history = 100 + 0.03 * t + 2.5 * np.sin(t * 0.08) + np.random.randn(1500) * 0.4

    config = Config(
        active_methods=["dtw", "pearson_warped"],
        tier1_candidates=60,
        tier2_candidates=5,
        stride=5,
    )

    # --- 1. Backtest produces the calibration anchor ---
    report = backtest(
        history,
        window_size=40,
        forward_bars=20,
        n_trials=8,
        config=config,
        seed=42,
        n_workers=1,
    )
    assert report.n_valid_trials > 0
    cal = report.calibration  # dict[percentile] -> empirical rate
    assert cal  # non-empty

    # --- 2. Run a live search + projection on a held-out slice ---
    ts = the_similarity.load(history)
    query_vals = history[-100:-60]
    query = the_similarity.load(query_vals)
    lookback = the_similarity.load(history[:-100])

    results = search(query=query, history=lookback, top_k=5, config=config)
    forecast = project(results, lookback, forward_bars=20, config=config)

    # --- 3. Naive strategy: plain evaluate_strategy ---
    naive_signals = evaluate_strategy(
        strategy=_always_long_strategy(),
        matches=results.matches,
        history=ts.values,
        forecast=forecast,
    )
    # Naive ALWAYS emits LONG when the rule fires — it doesn't care
    # about trust or tail-percentile thresholds.
    assert len(naive_signals) >= 1
    assert naive_signals[0].signal_type == SignalType.LONG

    # --- 4. Aware strategy: high min_matches forces veto ---
    aware = CalibrationAwareStrategy(
        base_strategy=_always_long_strategy(),
        trust_filter=TrustFilter(min_matches=100),  # Impossible with top_k=5.
        decision_config=DecisionRuleConfig(
            entry_percentile=25, entry_threshold=0.005
        ),
        calibration_report=report,
    )
    aware_signals = aware.evaluate(
        matches=results.matches,
        history=ts.values,
        forecast=forecast,
    )
    assert len(aware_signals) == 1
    assert aware_signals[0].signal_type == SignalType.FLAT
    assert aware_signals[0].position_size == 0.0
    assert aware_signals[0].trust.trust is False

    # --- 5. Review summary is well-formed ---
    review = summarise_review(aware_signals, n_matches=len(results.matches))
    text = review.to_text()
    assert "ReviewSummary" in text
    assert f"n_matches = {len(results.matches)}" in text

    # --- 6. With permissive trust filter + loose threshold, aware
    #       passes through and position_size is in (0, 1]. ---
    permissive = CalibrationAwareStrategy(
        base_strategy=_always_long_strategy(),
        trust_filter=TrustFilter(min_matches=1, max_calibration_mae=1.0, min_score=0.0),
        decision_config=DecisionRuleConfig(
            entry_percentile=90,  # P10 check for LONG — very lenient
            entry_threshold=-1.0,  # basically always passes
        ),
        calibration_report=report,
    )
    permissive_signals = permissive.evaluate(
        matches=results.matches,
        history=ts.values,
        forecast=forecast,
    )
    assert len(permissive_signals) == 1
    assert permissive_signals[0].signal_type == SignalType.LONG
    assert 0.0 < permissive_signals[0].position_size <= 1.0


def test_evaluate_with_trust_on_empty_strategy():
    """A strategy whose rule never fires yields an empty aware-signal list."""
    np.random.seed(1)
    history = 100 + np.cumsum(np.random.randn(400) * 0.3)

    def _never(match, forecast, ctx):
        return False

    never_strat = Strategy(
        name="never",
        rules=[Rule(name="never", condition=_never, signal_type=SignalType.LONG)],
        min_confidence=0.0,
    )

    ts = the_similarity.load(history)
    query = the_similarity.load(history[-60:-30])
    lookback = the_similarity.load(history[:-60])
    config = Config(
        active_methods=["dtw", "pearson_warped"],
        tier1_candidates=40,
        tier2_candidates=5,
        stride=5,
    )
    results = search(query=query, history=lookback, top_k=3, config=config)
    forecast = project(results, lookback, forward_bars=10, config=config)

    out = evaluate_with_trust(
        strategy=never_strat,
        matches=results.matches,
        history=ts.values,
        forecast=forecast,
    )
    assert out == []
