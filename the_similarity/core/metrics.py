"""Backtest evaluation metrics.

All functions operate on lists of TrialResult and return scalar metrics.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from the_similarity.core.backtester import TrialResult


def hit_rate(trials: list[TrialResult]) -> float:
    """Fraction of trials where P50 predicted the correct direction."""
    if not trials:
        return float("nan")
    hits = sum(1 for t in trials if t.directional_hit)
    return hits / len(trials)


def mean_absolute_error(trials: list[TrialResult]) -> float:
    """Mean absolute error of P50 terminal forecast vs actual."""
    if not trials:
        return float("nan")
    errors = [t.p50_error for t in trials]
    return float(np.mean(errors))


def calibration(
    trials: list[TrialResult],
    percentiles: list[int],
) -> dict[int, float]:
    """Per-percentile containment rate.

    For each percentile P, computes the fraction of trials where the
    actual terminal return fell below the P-th percentile forecast.
    A well-calibrated system should have containment(P) ≈ P/100.

    For symmetric bands (e.g. P10/P90), we check if the actual value
    falls within the band and compare to the expected containment.
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
            # Check if actual terminal return is below this percentile's forecast
            if trial.actual_returns[-1] <= curve[-1]:
                contained += 1
        result[p] = contained / valid if valid > 0 else float("nan")
    return result


def crps(trials: list[TrialResult]) -> float:
    """Continuous Ranked Probability Score.

    CRPS measures the quality of probabilistic forecasts. Lower is better.
    Uses the percentile-based approximation:
    CRPS ≈ (2/K) * Σ_k (I(y ≤ F_k) - k/(K+1))² * Δf_k

    where F_k are the percentile forecast values, y is the actual value,
    and I is the indicator function.

    For our discrete percentile representation, we use:
    CRPS ≈ mean over trials of: mean |F_percentile - actual| weighted
    by how far off the CDF step is.
    """
    if not trials:
        return float("nan")

    crps_values = []
    for trial in trials:
        if not trial.forecast_curves:
            continue
        # Get sorted percentile forecasts at terminal bar
        sorted_percentiles = sorted(trial.forecast_curves.keys())
        if not sorted_percentiles:
            continue

        actual_terminal = trial.actual_returns[-1]
        forecast_terminals = np.array([
            trial.forecast_curves[p][-1] for p in sorted_percentiles
        ])
        cdf_levels = np.array(sorted_percentiles) / 100.0

        # CRPS via integration of (CDF_forecast - CDF_actual)^2
        # CDF_actual is a step function at y
        indicators = (actual_terminal <= forecast_terminals).astype(float)
        crps_val = float(np.mean((indicators - cdf_levels) ** 2))
        crps_values.append(crps_val)

    if not crps_values:
        return float("nan")
    return float(np.mean(crps_values))
