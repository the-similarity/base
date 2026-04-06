"""
Evaluation metrics for backtesting the pattern matching engine.

These metrics assess the quality of the engine's forecast cones by comparing
projected outcomes against what actually happened. They are applied to
`TrialResult` objects produced by the backtester.

AI AGENT NOTES:
- All functions return NaN for empty trial lists (not 0 or an error),
  so downstream aggregation code must handle NaN values.
- `hit_rate` is the simplest metric: did P50 get the direction right?
- `calibration` checks statistical consistency: a P90 curve should contain
  90% of outcomes. Deviation indicates the cone is too tight or too wide.
- `crps` is the gold-standard probabilistic forecast metric. It uses a
  discrete approximation since we only have ~5 percentile curves, not a
  continuous CDF.
- TYPE_CHECKING import avoids circular dependency with backtester.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    # TrialResult is defined in backtester.py, which imports from this module's
    # siblings. Using TYPE_CHECKING avoids a circular import at runtime.
    from the_similarity.core.backtester import TrialResult


def hit_rate(trials: list[TrialResult]) -> float:
    """Fraction of trials where P50 predicted the correct direction.

    "Directional hit" means:
    - P50 predicted positive return AND actual return was positive, OR
    - P50 predicted negative return AND actual return was negative.

    This is the most basic sanity check: a random baseline is 50%.
    Consistently above 55% suggests the pattern matching has real signal.

    Returns:
        Float in [0, 1], or NaN if trials is empty.
    """
    if not trials:
        return float("nan")
    hits = sum(1 for t in trials if t.directional_hit)
    return hits / len(trials)


def mean_absolute_error(trials: list[TrialResult]) -> float:
    """Mean absolute error of P50 terminal forecast vs actual return.

    This measures point forecast accuracy: how far off was the median
    projection at the terminal bar from what actually happened?

    Lower is better. Units match the return representation
    (typically fractional returns, e.g., 0.05 = 5% error).

    Returns:
        Float >= 0, or NaN if trials is empty.
    """
    if not trials:
        return float("nan")
    errors = [t.p50_error for t in trials]
    return float(np.mean(errors))


def calibration(
    trials: list[TrialResult],
    percentiles: list[int],
) -> dict[int, float]:
    """Per-percentile containment rate (statistical calibration check).

    For each percentile P, computes the fraction of trials where the
    actual terminal return fell below the P-th percentile forecast curve.

    A well-calibrated system should have:
        containment(P10) ≈ 0.10
        containment(P50) ≈ 0.50
        containment(P90) ≈ 0.90

    Deviations reveal systematic biases:
    - containment(P90) << 0.90 → forecast cone is too narrow (overconfident)
    - containment(P10) >> 0.10 → forecast cone is biased high

    Args:
        trials: List of completed backtest trials.
        percentiles: Which percentiles to check (e.g., [10, 25, 50, 75, 90]).

    Returns:
        Dict mapping each percentile to its observed containment rate [0, 1].
        NaN for percentiles with no valid data.
    """
    if not trials:
        return {p: float("nan") for p in percentiles}

    result: dict[int, float] = {}
    for p in percentiles:
        contained = 0
        valid = 0
        for trial in trials:
            curve = trial.forecast_curves.get(p)
            if curve is None or len(curve) == 0:
                continue
            valid += 1
            # Check if actual terminal return is at or below this percentile
            # forecast. For a perfectly calibrated P-th percentile, exactly
            # P% of actuals should satisfy this condition.
            if trial.actual_returns[-1] <= curve[-1]:
                contained += 1
        result[p] = contained / valid if valid > 0 else float("nan")
    return result


def crps(trials: list[TrialResult]) -> float:
    """Continuous Ranked Probability Score (discrete approximation).

    CRPS is a strictly proper scoring rule for probabilistic forecasts.
    It measures the integrated squared difference between the forecast CDF
    and the observation's step-function CDF. Lower is better.

    Mathematical formulation:
        CRPS = integral over x of (F(x) - H(x - y))² dx

    where F(x) is the forecast CDF and H is the Heaviside step function
    centered at the actual observation y.

    Since our forecast is represented as only ~5 percentile curves (not a
    continuous CDF), we approximate this integral using:
        CRPS ≈ mean over percentile levels of (I(y ≤ F_p) - p/100)²

    where I is the indicator function and F_p is the forecast at percentile p.

    Interpretation:
    - CRPS = 0 → perfect probabilistic forecast (impossible in practice)
    - Lower CRPS → better calibrated AND sharper forecasts
    - CRPS penalizes both miscalibration AND lack of sharpness

    Returns:
        Float >= 0, or NaN if no valid trials.
    """
    if not trials:
        return float("nan")

    crps_values = []
    for trial in trials:
        if not trial.forecast_curves:
            continue

        # Sort percentile keys to create an ordered CDF approximation
        sorted_percentiles = sorted(trial.forecast_curves.keys())
        if not sorted_percentiles:
            continue

        # Extract the terminal-bar actual return
        actual_terminal = trial.actual_returns[-1]

        # Extract the terminal-bar forecast value at each percentile level
        forecast_terminals = np.array([
            trial.forecast_curves[p][-1] for p in sorted_percentiles
        ])

        # Convert integer percentiles to [0, 1] CDF levels
        cdf_levels = np.array(sorted_percentiles) / 100.0

        # Approximate CRPS:
        # For each percentile level, the indicator I(y ≤ F_p) gives the
        # empirical CDF of the actual observation. The squared difference
        # between this and the nominal CDF level measures calibration error
        # at that point.
        indicators = (actual_terminal <= forecast_terminals).astype(float)
        crps_val = float(np.mean((indicators - cdf_levels) ** 2))
        crps_values.append(crps_val)

    if not crps_values:
        return float("nan")
    return float(np.mean(crps_values))
