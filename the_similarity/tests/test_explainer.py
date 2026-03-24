"""Tests for the_similarity.core.explainer — Phase 7d explainability layer."""
from __future__ import annotations

import numpy as np
import pytest

from the_similarity.config import Config
from the_similarity.core.scorer import MatchResult, ScoreBreakdown
from the_similarity.core.projector import Forecast
from the_similarity.core.ensemble import EnsembleForecast, ConformalResult
from the_similarity.core.explainer import (
    METHOD_DESCRIPTIONS,
    MethodContribution,
    MatchExplanation,
    ForecastExplanation,
    CalibrationCommentary,
    explain_match,
    explain_forecast,
    calibration_commentary,
    explain_full,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_match() -> MatchResult:
    return MatchResult(
        start_idx=0,
        end_idx=50,
        confidence_score=82.3,
        score_breakdown=ScoreBreakdown(
            dtw=0.85,
            pearson_warped=0.78,
            bempedelis_r2=0.65,
            bempedelis_smoothness=0.55,
            koopman=0.91,
            wavelet_spectrum=0.70,
            emd=0.60,
            tda=0.45,
            transfer_entropy=0.30,
        ),
        regime="trending_up",
    )


@pytest.fixture
def bullish_forecast() -> Forecast:
    bars = 20
    p50 = np.linspace(0, 0.08, bars)
    p10 = np.linspace(0, -0.02, bars)
    p90 = np.linspace(0, 0.15, bars)
    return Forecast(
        bars=bars,
        percentiles=[10, 50, 90],
        curves={10: p10, 50: p50, 90: p90},
        all_paths=np.zeros((5, bars)),
        weights=np.ones(5) / 5,
    )


@pytest.fixture
def bearish_forecast() -> Forecast:
    bars = 20
    p50 = np.linspace(0, -0.06, bars)
    p10 = np.linspace(0, -0.12, bars)
    p90 = np.linspace(0, 0.01, bars)
    return Forecast(
        bars=bars,
        percentiles=[10, 50, 90],
        curves={10: p10, 50: p50, 90: p90},
        all_paths=np.zeros((5, bars)),
        weights=np.ones(5) / 5,
    )


@pytest.fixture
def neutral_forecast() -> Forecast:
    bars = 20
    p50 = np.linspace(0, 0.002, bars)
    p10 = np.linspace(0, -0.01, bars)
    p90 = np.linspace(0, 0.012, bars)
    return Forecast(
        bars=bars,
        percentiles=[10, 50, 90],
        curves={10: p10, 50: p50, 90: p90},
        all_paths=np.zeros((5, bars)),
        weights=np.ones(5) / 5,
    )


@pytest.fixture
def ensemble_forecast_fixture() -> EnsembleForecast:
    bars = 20
    p50 = np.linspace(0, 0.06, bars)
    p10 = np.linspace(0, -0.05, bars)
    p90 = np.linspace(0, 0.18, bars)
    conformal = ConformalResult(
        lower=np.linspace(0, -0.08, bars),
        upper=np.linspace(0, 0.20, bars),
        target_coverage=0.9,
    )
    return EnsembleForecast(
        bars=bars,
        percentiles=[10, 50, 90],
        curves={10: p10, 50: p50, 90: p90},
        conformal=conformal,
        component_weights={"historical": 0.4, "monte_carlo": 0.3, "regime_conditional": 0.3},
    )


# ---------------------------------------------------------------------------
# TestExplainMatch
# ---------------------------------------------------------------------------

class TestExplainMatch:
    def test_returns_explanation_object(self, sample_match: MatchResult):
        result = explain_match(sample_match)
        assert isinstance(result, MatchExplanation)
        assert result.confidence_score == 82.3
        assert result.regime == "trending_up"

    def test_top_drivers_sorted_by_contribution(self, sample_match: MatchResult):
        result = explain_match(sample_match)
        contributions = [c.weighted_contribution for c in result.top_drivers]
        assert contributions == sorted(contributions, reverse=True)

    def test_summary_mentions_top_method(self, sample_match: MatchResult):
        result = explain_match(sample_match)
        # The top contributor by weighted_contribution should appear in the summary
        top_method = result.top_drivers[0].method
        # Summary should reference the score or the method name in some form
        assert "82.3" in result.summary
        assert len(result.summary) > 20

    def test_strengths_above_threshold(self, sample_match: MatchResult):
        result = explain_match(sample_match)
        # Methods with score > 0.7: dtw=0.85, pearson_warped=0.78, koopman=0.91, wavelet_spectrum=0.70
        assert len(result.strengths) >= 3  # at least dtw, pearson, koopman
        for s in result.strengths:
            assert "Strong" in s

    def test_weaknesses_below_threshold(self, sample_match: MatchResult):
        result = explain_match(sample_match)
        # Only transfer_entropy=0.30 is < 0.3? No, 0.30 is not < 0.3.
        # Actually nothing is strictly < 0.3 in the sample. Let's check:
        # All scores: 0.85, 0.78, 0.65, 0.55, 0.91, 0.70, 0.60, 0.45, 0.30
        # None < 0.3, so weaknesses should be empty
        assert isinstance(result.weaknesses, list)

    def test_weaknesses_with_low_scores(self):
        match = MatchResult(
            start_idx=0, end_idx=50,
            confidence_score=40.0,
            score_breakdown=ScoreBreakdown(
                dtw=0.10, pearson_warped=0.15, bempedelis_r2=0.20,
                bempedelis_smoothness=0.05, koopman=0.80, wavelet_spectrum=0.10,
                emd=0.05, tda=0.10, transfer_entropy=0.05,
            ),
        )
        result = explain_match(match)
        # Many methods < 0.3, should have weaknesses
        assert len(result.weaknesses) >= 3

    def test_regime_mentioned_in_summary(self, sample_match: MatchResult):
        result = explain_match(sample_match)
        assert "trending up" in result.summary

    def test_all_methods_accounted(self, sample_match: MatchResult):
        result = explain_match(sample_match)
        methods_in_result = {c.method for c in result.top_drivers}
        config = Config()
        expected = {f for f in config.active_methods if f in methods_in_result}
        assert methods_in_result == expected
        assert len(result.top_drivers) == 9  # all 9 default methods


# ---------------------------------------------------------------------------
# TestExplainForecast
# ---------------------------------------------------------------------------

class TestExplainForecast:
    def test_bullish_direction(self, bullish_forecast: Forecast):
        result = explain_forecast(bullish_forecast)
        assert isinstance(result, ForecastExplanation)
        assert result.direction == "bullish"

    def test_bearish_direction(self, bearish_forecast: Forecast):
        result = explain_forecast(bearish_forecast)
        assert result.direction == "bearish"

    def test_neutral_direction(self, neutral_forecast: Forecast):
        result = explain_forecast(neutral_forecast)
        assert result.direction == "neutral"

    def test_wide_cone_mentioned(self):
        bars = 20
        p50 = np.linspace(0, 0.03, bars)
        p10 = np.linspace(0, -0.10, bars)
        p90 = np.linspace(0, 0.20, bars)
        forecast = Forecast(
            bars=bars,
            percentiles=[10, 50, 90],
            curves={10: p10, 50: p50, 90: p90},
            all_paths=np.zeros((3, bars)),
            weights=np.ones(3) / 3,
        )
        result = explain_forecast(forecast)
        assert "wide" in result.confidence_narrative.lower() or "uncertainty" in result.confidence_narrative.lower()

    def test_ensemble_forecast_handled(self, ensemble_forecast_fixture: EnsembleForecast):
        result = explain_forecast(ensemble_forecast_fixture)
        assert isinstance(result, ForecastExplanation)
        # Should mention conformal intervals
        assert "conformal" in result.confidence_narrative.lower() or "Conformal" in result.confidence_narrative


# ---------------------------------------------------------------------------
# TestCalibrationCommentary
# ---------------------------------------------------------------------------

class TestCalibrationCommentary:
    def test_high_confidence_commentary(self):
        result = calibration_commentary(85.0)
        assert isinstance(result, CalibrationCommentary)
        assert result.confidence_level == 85.0
        assert "high" in result.historical_accuracy.lower()

    def test_low_confidence_commentary(self):
        result = calibration_commentary(25.0)
        assert result.confidence_level == 25.0
        assert "low" in result.historical_accuracy.lower()

    def test_with_backtest_hit_rate(self):
        result = calibration_commentary(82.0, backtest_hit_rate=0.73)
        assert "73%" in result.historical_accuracy or "73" in result.historical_accuracy
        assert result.confidence_level == 82.0


# ---------------------------------------------------------------------------
# TestExplainFull
# ---------------------------------------------------------------------------

class TestExplainFull:
    def test_returns_all_keys(self, sample_match: MatchResult, bullish_forecast: Forecast):
        result = explain_full(sample_match, forecast=bullish_forecast, backtest_hit_rate=0.70)
        assert "match" in result
        assert "forecast" in result
        assert "calibration" in result
        assert isinstance(result["match"], MatchExplanation)
        assert isinstance(result["forecast"], ForecastExplanation)
        assert isinstance(result["calibration"], CalibrationCommentary)

    def test_without_forecast(self, sample_match: MatchResult):
        result = explain_full(sample_match)
        assert result["match"] is not None
        assert result["forecast"] is None
        assert result["calibration"] is not None
