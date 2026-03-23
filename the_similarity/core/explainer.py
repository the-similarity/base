"""Explainability layer: natural language match explanations and per-method contribution analysis.

Phase 7d — provides human-readable explanations for match results,
forecast projections, and calibration commentary.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from the_similarity.config import Config
from the_similarity.core.scorer import MatchResult, ScoreBreakdown, _SCORE_FIELDS
from the_similarity.core.projector import Forecast
from the_similarity.core.ensemble import EnsembleForecast


# ---------------------------------------------------------------------------
# Method descriptions
# ---------------------------------------------------------------------------

METHOD_DESCRIPTIONS: dict[str, str] = {
    "dtw": "Dynamic Time Warping shape similarity",
    "pearson_warped": "Pearson correlation after warping alignment",
    "bempedelis_r2": "Self-similarity transform fit quality (power law)",
    "bempedelis_smoothness": "Smoothness of the transform parameters",
    "koopman": "Koopman eigenvalue spectrum similarity (dynamical systems)",
    "wavelet_spectrum": "Multifractal wavelet spectrum similarity",
    "emd": "Empirical Mode Decomposition multi-scale match",
    "tda": "Topological structure similarity (persistence diagrams)",
    "transfer_entropy": "Predictive information flow from match to future",
}

# Short names for natural language summaries
_METHOD_SHORT_NAMES: dict[str, str] = {
    "dtw": "DTW shape alignment",
    "pearson_warped": "warped correlation",
    "bempedelis_r2": "power-law fit",
    "bempedelis_smoothness": "transform smoothness",
    "koopman": "Koopman eigenvalue similarity",
    "wavelet_spectrum": "wavelet spectrum match",
    "emd": "EMD multi-scale match",
    "tda": "topological similarity",
    "transfer_entropy": "predictive information flow",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MethodContribution:
    """Per-method contribution to the overall match confidence score."""
    method: str
    score: float                 # raw score 0-1
    weight: float                # config weight
    weighted_contribution: float  # score * weight (renormalized)
    percentile_rank: float       # how this score compares to typical (0-100)
    description: str             # from METHOD_DESCRIPTIONS
    verdict: str                 # "strong", "moderate", "weak", "negligible"


@dataclass
class MatchExplanation:
    """Human-readable explanation of a match result."""
    confidence_score: float
    regime: str | None
    top_drivers: list[MethodContribution]  # sorted by contribution desc
    summary: str                            # 1-2 sentence natural language
    detailed: str                           # full multi-line explanation
    strengths: list[str]                    # what's good about this match
    weaknesses: list[str]                   # what's weak


@dataclass
class ForecastExplanation:
    """Human-readable explanation of a forecast projection."""
    direction: str             # "bullish", "bearish", "neutral"
    magnitude: str             # "strong", "moderate", "mild"
    confidence_narrative: str  # explanation of confidence bands
    summary: str               # 1-2 sentence explanation
    risk_factors: list[str]    # potential risks


@dataclass
class CalibrationCommentary:
    """Commentary on match confidence calibration."""
    confidence_level: float       # the match's score
    historical_accuracy: str      # "This confidence level..."
    recommendation: str           # action recommendation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_verdict(score: float) -> str:
    """Map a 0-1 score to a qualitative verdict."""
    if score >= 0.7:
        return "strong"
    elif score >= 0.4:
        return "moderate"
    elif score >= 0.15:
        return "weak"
    else:
        return "negligible"


def _score_to_percentile(score: float) -> float:
    """Estimate percentile rank from a 0-1 score.

    Uses a sigmoid-like mapping that assumes most scores cluster
    around 0.4-0.6, with extreme values being rarer.
    """
    # Simple mapping: treat score as roughly the percentile / 100
    # with some non-linearity to reflect that very high/low scores are rare
    return float(np.clip(score * 100, 0, 100))


# ---------------------------------------------------------------------------
# explain_match
# ---------------------------------------------------------------------------

def explain_match(
    match: MatchResult,
    config: Config | None = None,
) -> MatchExplanation:
    """Decompose a match result into per-method contributions with natural language.

    Args:
        match: A single match result with score breakdown.
        config: Configuration with weights and active methods. Uses defaults if None.

    Returns:
        MatchExplanation with sorted contributions, summary, and analysis.
    """
    if config is None:
        config = Config()

    breakdown = match.score_breakdown
    w = config.weights

    # Determine active fields with positive weights
    active_fields = [
        f for f in config.active_methods
        if f in _SCORE_FIELDS and w.get(f, 0.0) > 0
    ]

    weight_total = sum(w[f] for f in active_fields) if active_fields else 1.0
    if weight_total <= 0:
        weight_total = 1.0

    # Build per-method contributions
    contributions: list[MethodContribution] = []
    for f in active_fields:
        raw_score = getattr(breakdown, f, 0.0)
        norm_weight = w[f] / weight_total
        weighted = raw_score * norm_weight

        contributions.append(MethodContribution(
            method=f,
            score=raw_score,
            weight=norm_weight,
            weighted_contribution=weighted,
            percentile_rank=_score_to_percentile(raw_score),
            description=METHOD_DESCRIPTIONS.get(f, f),
            verdict=_score_to_verdict(raw_score),
        ))

    # Sort by weighted contribution descending
    contributions.sort(key=lambda c: c.weighted_contribution, reverse=True)

    # Identify strengths and weaknesses
    strengths: list[str] = []
    weaknesses: list[str] = []
    for c in contributions:
        short = _METHOD_SHORT_NAMES.get(c.method, c.method)
        if c.score > 0.7:
            strengths.append(f"Strong {short} ({c.score:.2f})")
        if c.score < 0.3:
            weaknesses.append(f"Weak {short} ({c.score:.2f})")

    # Build summary
    confidence = match.confidence_score
    top = contributions[:2] if len(contributions) >= 2 else contributions
    driver_parts = []
    for c in top:
        short = _METHOD_SHORT_NAMES.get(c.method, c.method)
        driver_parts.append(f"{c.verdict} {short} ({c.score:.2f})")
    drivers_text = " and ".join(driver_parts)

    summary = f"This match scored {confidence:.1f}/100, primarily driven by {drivers_text}."
    if match.regime:
        regime_display = match.regime.replace("_", " ")
        summary += f" The match was found in a {regime_display} regime."

    # Build detailed multi-line breakdown
    lines = [
        f"Match Confidence: {confidence:.1f}/100",
        "",
        "Per-method breakdown:",
    ]
    for c in contributions:
        bar_len = int(c.score * 20)
        bar = "#" * bar_len + "." * (20 - bar_len)
        lines.append(
            f"  {c.method:<25s} [{bar}] {c.score:.2f}  "
            f"(weight: {c.weight:.1%}, contribution: {c.weighted_contribution:.3f}, {c.verdict})"
        )
    if match.regime:
        lines.append(f"\nRegime: {match.regime}")
    if strengths:
        lines.append(f"\nStrengths: {'; '.join(strengths)}")
    if weaknesses:
        lines.append(f"Weaknesses: {'; '.join(weaknesses)}")

    detailed = "\n".join(lines)

    return MatchExplanation(
        confidence_score=confidence,
        regime=match.regime,
        top_drivers=contributions,
        summary=summary,
        detailed=detailed,
        strengths=strengths,
        weaknesses=weaknesses,
    )


# ---------------------------------------------------------------------------
# explain_forecast
# ---------------------------------------------------------------------------

def explain_forecast(
    forecast: Forecast | EnsembleForecast,
    forward_bars: int | None = None,
) -> ForecastExplanation:
    """Generate natural language explanation of a forecast projection.

    Args:
        forecast: A Forecast or EnsembleForecast object.
        forward_bars: Number of forward bars (inferred from forecast if None).

    Returns:
        ForecastExplanation with direction, magnitude, and risk factors.
    """
    bars = forward_bars if forward_bars is not None else forecast.bars
    curves = forecast.curves

    # Get P50 for direction analysis
    p50 = curves.get(50)
    if p50 is None or len(p50) == 0:
        return ForecastExplanation(
            direction="neutral",
            magnitude="mild",
            confidence_narrative="Insufficient data to generate forecast confidence bands.",
            summary="No meaningful forecast could be generated.",
            risk_factors=["Insufficient match data for projection"],
        )

    # Direction from final P50 value
    final_p50 = float(p50[-1])
    if final_p50 > 0.005:
        direction = "bullish"
    elif final_p50 < -0.005:
        direction = "bearish"
    else:
        direction = "neutral"

    # Magnitude from absolute final value
    abs_final = abs(final_p50)
    if abs_final > 0.05:
        magnitude = "strong"
    elif abs_final > 0.02:
        magnitude = "moderate"
    else:
        magnitude = "mild"

    # Confidence narrative from P10-P90 spread
    p10 = curves.get(10)
    p90 = curves.get(90)
    risk_factors: list[str] = []

    if p10 is not None and p90 is not None:
        spread = float(p90[-1] - p10[-1])
        if spread > 0.10:
            confidence_narrative = (
                f"The P10-P90 spread at bar {bars} is wide ({spread:.1%}), "
                "indicating significant uncertainty in the projection."
            )
            risk_factors.append("Wide confidence cone suggests high forecast uncertainty")
        elif spread > 0.04:
            confidence_narrative = (
                f"The P10-P90 spread at bar {bars} is moderate ({spread:.1%}), "
                "suggesting reasonable but not high confidence."
            )
        else:
            confidence_narrative = (
                f"The P10-P90 spread at bar {bars} is narrow ({spread:.1%}), "
                "indicating relatively high confidence in the direction."
            )
    else:
        confidence_narrative = "Limited percentile data available for confidence assessment."

    # Conformal interval commentary for EnsembleForecast
    if isinstance(forecast, EnsembleForecast) and forecast.conformal is not None:
        conf = forecast.conformal
        conf_spread = float(conf.upper[-1] - conf.lower[-1])
        confidence_narrative += (
            f" Conformal intervals ({conf.target_coverage:.0%} coverage) "
            f"span {conf_spread:.1%} at the forecast horizon."
        )
        if conf_spread > 0.15:
            risk_factors.append(
                "Conformal intervals are wide, suggesting limited historical precedent"
            )

    # General risk factors
    if direction != "neutral" and magnitude == "mild":
        risk_factors.append("Mild magnitude suggests the directional signal may not be actionable")

    # Check for path divergence (early vs late direction change)
    if len(p50) > 2:
        mid = len(p50) // 2
        early_dir = float(p50[mid])
        if (early_dir > 0 and final_p50 < 0) or (early_dir < 0 and final_p50 > 0):
            risk_factors.append("Forecast direction reverses mid-horizon")

    # Summary
    direction_word = {"bullish": "upward", "bearish": "downward", "neutral": "sideways"}[direction]
    summary = (
        f"The forecast projects a {magnitude} {direction_word} move of {final_p50:+.1%} "
        f"over {bars} bars."
    )
    if risk_factors:
        summary += f" Key risk: {risk_factors[0].lower()}."

    return ForecastExplanation(
        direction=direction,
        magnitude=magnitude,
        confidence_narrative=confidence_narrative,
        summary=summary,
        risk_factors=risk_factors,
    )


# ---------------------------------------------------------------------------
# calibration_commentary
# ---------------------------------------------------------------------------

def calibration_commentary(
    confidence_score: float,
    backtest_hit_rate: float | None = None,
) -> CalibrationCommentary:
    """Generate calibration commentary for a confidence score.

    Args:
        confidence_score: The match confidence score (0-100).
        backtest_hit_rate: Historical directional hit rate (0-1) if available.

    Returns:
        CalibrationCommentary with qualitative assessment and recommendation.
    """
    # Qualitative description based on confidence level
    if confidence_score >= 80:
        tier = "high"
        accuracy_desc = (
            f"This is a high-confidence match ({confidence_score:.0f}/100). "
            "Matches at this level typically show strong agreement across multiple methods."
        )
        recommendation = (
            "High confidence suggests this pattern is worth further investigation. "
            "Consider using this as a primary signal."
        )
    elif confidence_score >= 60:
        tier = "moderate"
        accuracy_desc = (
            f"This is a moderate-confidence match ({confidence_score:.0f}/100). "
            "Several methods agree, but some show weaker alignment."
        )
        recommendation = (
            "Moderate confidence warrants attention but should be confirmed "
            "with additional analysis or signals."
        )
    elif confidence_score >= 40:
        tier = "low-moderate"
        accuracy_desc = (
            f"This is a below-average match ({confidence_score:.0f}/100). "
            "Method agreement is limited."
        )
        recommendation = (
            "Below-average confidence suggests caution. "
            "Use as a secondary signal only, combined with other indicators."
        )
    else:
        tier = "low"
        accuracy_desc = (
            f"This is a low-confidence match ({confidence_score:.0f}/100). "
            "Most methods show weak alignment."
        )
        recommendation = (
            "Low confidence indicates this match may not be meaningful. "
            "Consider discarding or using only for exploratory analysis."
        )

    # Incorporate backtest hit rate if available
    if backtest_hit_rate is not None:
        hit_pct = backtest_hit_rate * 100
        accuracy_desc += (
            f" Matches at this confidence level ({confidence_score:.0f}) have "
            f"historically been accurate about {hit_pct:.0f}% of the time."
        )
        if backtest_hit_rate >= 0.65:
            recommendation += (
                f" Historical accuracy ({hit_pct:.0f}%) supports this confidence level."
            )
        elif backtest_hit_rate < 0.50:
            recommendation = (
                f"Despite the confidence score, historical accuracy ({hit_pct:.0f}%) "
                "is below 50%. Treat this signal with skepticism."
            )

    return CalibrationCommentary(
        confidence_level=confidence_score,
        historical_accuracy=accuracy_desc,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# explain_full — convenience function combining all
# ---------------------------------------------------------------------------

def explain_full(
    match: MatchResult,
    forecast: Forecast | EnsembleForecast | None = None,
    config: Config | None = None,
    backtest_hit_rate: float | None = None,
) -> dict:
    """Convenience function combining match, forecast, and calibration explanations.

    Args:
        match: A single match result.
        forecast: Optional forecast to explain.
        config: Configuration for weight decomposition.
        backtest_hit_rate: Optional historical hit rate for calibration.

    Returns:
        Dict with keys "match", "forecast" (or None), "calibration".
    """
    match_explanation = explain_match(match, config)

    forecast_explanation = None
    if forecast is not None:
        forecast_explanation = explain_forecast(forecast)

    cal = calibration_commentary(match.confidence_score, backtest_hit_rate)

    return {
        "match": match_explanation,
        "forecast": forecast_explanation,
        "calibration": cal,
    }
