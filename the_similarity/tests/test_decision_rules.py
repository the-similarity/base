"""Tests for calibration-aware decision rules.

Covers:
- Percentile-threshold entry gating.
- Trust-filter veto of directional signals.
- Position-size scaling by trust score * confidence.
- CalibrationAwareStrategy adapter.
- ReviewSummary rendering.
"""

from __future__ import annotations


import numpy as np

from the_similarity.core.decision_rules import (
    CalibrationAwareStrategy,
    DecisionRuleConfig,
    ReviewSummary,
    evaluate_with_trust,
    summarise_review,
)
from the_similarity.core.projector import Forecast
from the_similarity.core.scorer import MatchResult
from the_similarity.core.strategy import (
    Rule,
    SignalType,
    Strategy,
)
from the_similarity.core.trust_filter import TrustFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_match(score: float = 80.0, regime: str | None = "trending_up") -> MatchResult:
    return MatchResult(start_idx=0, end_idx=50, confidence_score=score, regime=regime)


def _history(n: int = 200) -> np.ndarray:
    rng = np.random.default_rng(0)
    return 100.0 * np.exp(np.cumsum(0.0005 + 0.01 * rng.standard_normal(n)))


def _forecast(p50_end: float = 0.03, spread: float = 0.02, bars: int = 20) -> Forecast:
    """Build a tight forecast with controlled endpoints."""
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
    # Tight all_paths so the agreement signal stays high.
    rng = np.random.default_rng(1)
    paths = np.tile(t * p50_end, (10, 1)) + 0.001 * rng.standard_normal((10, bars))
    return Forecast(
        bars=bars,
        percentiles=[10, 25, 50, 75, 90],
        curves=curves,
        all_paths=paths,
        weights=np.ones(10) / 10,
    )


def _always_long_strategy() -> Strategy:
    """A rule that always fires LONG regardless of context."""

    def _cond(match, forecast, ctx):
        return True

    return Strategy(
        name="always_long",
        rules=[Rule(name="always_long", condition=_cond, signal_type=SignalType.LONG)],
        min_confidence=0.0,
    )


def _always_short_strategy() -> Strategy:
    def _cond(match, forecast, ctx):
        return True

    return Strategy(
        name="always_short",
        rules=[Rule(name="always_short", condition=_cond, signal_type=SignalType.SHORT)],
        min_confidence=0.0,
    )


def _good_calibration() -> dict:
    return {10: 0.11, 25: 0.26, 50: 0.51, 75: 0.74, 90: 0.89}


# ---------------------------------------------------------------------------
# Threshold gate
# ---------------------------------------------------------------------------


def test_long_fails_when_p25_below_threshold():
    # P25 endpoint will be negative (p50_end=0.01 - spread/4 = -0.04)
    matches = [_make_match() for _ in range(20)]
    forecast = _forecast(p50_end=0.01, spread=0.20)
    out = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        decision_config=DecisionRuleConfig(entry_percentile=25, entry_threshold=0.005),
    )
    assert len(out) == 1
    sig = out[0]
    assert sig.threshold_met is False
    # Default veto_on_distrust collapses to FLAT.
    assert sig.signal_type == SignalType.FLAT
    assert sig.position_size == 0.0


def test_long_passes_when_p25_above_threshold():
    matches = [_make_match() for _ in range(20)]
    # Tight cone with strongly positive P25.
    forecast = _forecast(p50_end=0.05, spread=0.02)
    out = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        decision_config=DecisionRuleConfig(entry_percentile=25, entry_threshold=0.005),
    )
    assert len(out) == 1
    sig = out[0]
    assert sig.threshold_met is True
    assert sig.signal_type == SignalType.LONG
    assert sig.position_size > 0.0


def test_short_checks_mirror_percentile():
    # SHORT uses P{100 - entry_percentile} = P75. For short, we need
    # P75 endpoint <= -threshold.
    matches = [_make_match(regime="trending_down") for _ in range(20)]
    bars = 20
    t = np.linspace(0, 1, bars)
    curves = {
        10: t * -0.10,
        25: t * -0.08,
        50: t * -0.05,
        75: t * -0.03,  # P75 sufficiently negative for short
        90: t * -0.01,
    }
    rng = np.random.default_rng(2)
    paths = np.tile(t * -0.05, (10, 1)) + 0.001 * rng.standard_normal((10, bars))
    forecast = Forecast(
        bars=bars,
        percentiles=[10, 25, 50, 75, 90],
        curves=curves,
        all_paths=paths,
        weights=np.ones(10) / 10,
    )
    out = evaluate_with_trust(
        strategy=_always_short_strategy(),
        matches=matches,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        decision_config=DecisionRuleConfig(entry_percentile=25, entry_threshold=0.005),
    )
    assert len(out) == 1
    sig = out[0]
    assert sig.threshold_met is True
    assert sig.signal_type == SignalType.SHORT


def test_missing_percentile_fails_closed():
    matches = [_make_match() for _ in range(20)]
    # Forecast without P25 curve.
    forecast = Forecast(
        bars=20,
        percentiles=[10, 50, 90],
        curves={
            10: np.linspace(0, -0.01, 20),
            50: np.linspace(0, 0.05, 20),
            90: np.linspace(0, 0.10, 20),
        },
        all_paths=np.zeros((5, 20)),
        weights=np.ones(5) / 5,
    )
    out = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        decision_config=DecisionRuleConfig(entry_percentile=25, entry_threshold=0.005),
    )
    assert len(out) == 1
    assert out[0].threshold_met is False


# ---------------------------------------------------------------------------
# Trust veto
# ---------------------------------------------------------------------------


def test_low_sample_trust_veto_produces_flat():
    # Only 2 matches -> sample_size hard gate fires -> trust=False.
    matches = [_make_match() for _ in range(2)]
    forecast = _forecast(p50_end=0.05, spread=0.02)
    out = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        trust_filter=TrustFilter(min_matches=5),
    )
    assert len(out) == 1
    assert out[0].signal_type == SignalType.FLAT
    assert out[0].position_size == 0.0
    assert out[0].trust.trust is False


def test_distrust_without_veto_preserves_signal_with_zero_size():
    matches = [_make_match() for _ in range(2)]
    forecast = _forecast(p50_end=0.05, spread=0.02)
    out = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        trust_filter=TrustFilter(min_matches=5),
        decision_config=DecisionRuleConfig(veto_on_distrust=False),
    )
    assert len(out) == 1
    # Direction is preserved but size is zero.
    assert out[0].signal_type == SignalType.LONG
    assert out[0].position_size == 0.0
    assert out[0].trust.trust is False


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------


def test_position_size_scales_with_trust_and_confidence():
    matches_high = [_make_match(score=99.0) for _ in range(20)]
    matches_low = [_make_match(score=60.0) for _ in range(20)]
    forecast = _forecast(p50_end=0.05, spread=0.02)
    cfg = DecisionRuleConfig(
        entry_percentile=25,
        entry_threshold=0.005,
        min_position_size=0.1,
        max_position_size=1.0,
    )

    out_high = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches_high,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        decision_config=cfg,
    )
    out_low = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches_low,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        decision_config=cfg,
    )
    assert out_high[0].position_size > out_low[0].position_size
    # Size is always within [min, max] when trusted.
    assert cfg.min_position_size <= out_high[0].position_size <= cfg.max_position_size


# ---------------------------------------------------------------------------
# Differs from naive threshold
# ---------------------------------------------------------------------------


def test_behaviour_differs_from_naive_p50_threshold():
    """Naive rule: 'if P50 > 0, go long'. Calibration-aware: also
    require trust + P25 > threshold. Construct an input where naive
    fires but calibration-aware does not, and assert the difference."""
    matches = [_make_match() for _ in range(3)]  # Below min_matches.
    forecast = _forecast(p50_end=0.05, spread=0.02)

    # Naive eval: plain strategy with single P50 > 0 rule.
    from the_similarity.core.strategy import evaluate_strategy

    naive = evaluate_strategy(
        strategy=_always_long_strategy(),
        matches=matches,
        history=_history(),
        forecast=forecast,
    )
    aware = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches,
        history=_history(),
        forecast=forecast,
        calibration_report=_good_calibration(),
        trust_filter=TrustFilter(min_matches=5),
    )
    assert len(naive) >= 1
    assert naive[0].signal_type == SignalType.LONG  # Naive fires.
    assert aware[0].signal_type == SignalType.FLAT  # Aware vetoes.


# ---------------------------------------------------------------------------
# CalibrationAwareStrategy adapter
# ---------------------------------------------------------------------------


def test_calibration_aware_strategy_passes_through():
    cas = CalibrationAwareStrategy(
        base_strategy=_always_long_strategy(),
        calibration_report=_good_calibration(),
    )
    matches = [_make_match() for _ in range(20)]
    out = cas.evaluate(
        matches=matches,
        history=_history(),
        forecast=_forecast(p50_end=0.05, spread=0.02),
    )
    assert len(out) == 1
    assert out[0].signal_type == SignalType.LONG


def test_with_report_returns_new_instance():
    cas = CalibrationAwareStrategy(base_strategy=_always_long_strategy())
    new = cas.with_report({10: 0.10, 50: 0.50, 90: 0.90})
    assert cas.calibration_report is None
    assert new.calibration_report is not None
    assert new is not cas


# ---------------------------------------------------------------------------
# ReviewSummary
# ---------------------------------------------------------------------------


def test_review_summary_renders_text():
    matches = [_make_match() for _ in range(20)]
    out = evaluate_with_trust(
        strategy=_always_long_strategy(),
        matches=matches,
        history=_history(),
        forecast=_forecast(p50_end=0.05, spread=0.02),
        calibration_report=_good_calibration(),
    )
    review = summarise_review(out, n_matches=len(matches))
    assert isinstance(review, ReviewSummary)
    text = review.to_text()
    assert "ReviewSummary" in text
    assert "n_matches = 20" in text


def test_review_summary_on_empty_signals():
    # A strategy whose rule never fires -> empty signal list.
    def _never(match, forecast, ctx):
        return False

    never = Strategy(
        name="never",
        rules=[Rule(name="never", condition=_never, signal_type=SignalType.LONG)],
        min_confidence=0.0,
    )
    out = evaluate_with_trust(
        strategy=never,
        matches=[_make_match() for _ in range(20)],
        history=_history(),
        forecast=_forecast(p50_end=0.05, spread=0.02),
        calibration_report=_good_calibration(),
    )
    assert out == []
    review = summarise_review(out, n_matches=20)
    assert review.trust is False
    assert "no base signals" in review.top_reasons[0]
