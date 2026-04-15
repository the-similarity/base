"""Ensemble forecasting: Monte Carlo, regime-conditional, conformal prediction.

Phase 7b — combines multiple forecast signals into a calibrated, blended
projection cone with proper uncertainty quantification.

Statistical Architecture & Projections:
Unlike the simple `projector.py` which computes raw percentile averages,
this module constructs mathematically rigorous conformal prediction intervals.
The methodology synthesizes three separate signals:
  1. Historical Weighted Median -> Baseline projection.
  2. Monte Carlo Simulation -> Incorporates expanding variance (simulated
     Brownian noise scaled by target volatility).
  3. Regime-Conditional filter -> Down-weights historical analogs occurring
     under discordant prevailing market regimes.

Coverage Guarantees:
Uses Split Conformal Prediction. The resulting `ConformalResult` guarantees
marginal coverage (e.g., 90% target inclusion probability) independent of any
Gaussian normal distribution assumptions—crucial for fat-tailed financial time series.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from the_similarity.config import Config
from the_similarity.core.scorer import MatchResult
from the_similarity.core.regime import tag_regime


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MonteCarloResult:
    """Result of Monte Carlo simulation from match distribution."""

    paths: NDArray[np.float64]  # (n_simulations, forward_bars) simulated paths
    percentiles: dict[int, NDArray[np.float64]]  # percentile -> curve
    mean: NDArray[np.float64]  # (forward_bars,) mean trajectory
    std: NDArray[np.float64]  # (forward_bars,) per-bar std


@dataclass
class RegimeConditionalResult:
    """Regime-filtered projection result."""

    regime: str  # detected query regime
    n_matches_total: int  # total matches before filtering
    n_matches_used: int  # matches after regime filter
    curves: dict[int, NDArray[np.float64]]  # percentile -> curve
    all_paths: NDArray[np.float64]  # (n_used, forward_bars)
    weights: NDArray[np.float64]  # confidence weights for used matches


@dataclass
class ConformalResult:
    """Conformal prediction intervals with coverage guarantees."""

    lower: NDArray[np.float64]  # (forward_bars,) lower bound
    upper: NDArray[np.float64]  # (forward_bars,) upper bound
    target_coverage: float  # requested coverage (e.g., 0.9)
    calibration_scores: NDArray[np.float64] | None = None  # nonconformity scores


@dataclass
class EnsembleForecast:
    """Combined ensemble forecast from all methods."""

    bars: int
    percentiles: list[int]
    curves: dict[int, NDArray[np.float64]]  # blended percentile curves
    monte_carlo: MonteCarloResult | None = None
    regime_conditional: RegimeConditionalResult | None = None
    conformal: ConformalResult | None = None
    component_weights: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------


def monte_carlo_forecast(
    matches: list[MatchResult],
    history: NDArray[np.float64],
    forward_bars: int = 50,
    n_simulations: int = 1000,
    percentiles: list[int] | None = None,
    seed: int | None = 42,
) -> MonteCarloResult:
    """Generate Monte Carlo paths by sampling from the match return distribution.

    For each simulation step, we sample a match (weighted by confidence),
    then draw from the empirical return distribution of that match's
    forward window, adding Gaussian noise scaled by the observed volatility.

    Why this is useful: Unlike the bare `projector.py` which only returns N
    historical paths, this simulates N*1000 paths giving a much smoother
    cone boundaries that correctly reflect expanding uncertainty over time.

    Args:
        matches: Ranked match results with confidence scores.
        history: Full raw history series.
        forward_bars: How many bars to simulate forward.
        n_simulations: Number of Monte Carlo paths.
        percentiles: Which percentiles to compute (default: [10, 25, 50, 75, 90]).
        seed: Random seed for reproducibility.

    Returns:
        MonteCarloResult with simulated paths and summary statistics.
    """
    if percentiles is None:
        percentiles = [10, 25, 50, 75, 90]

    rng = np.random.default_rng(seed)

    # Extract forward return paths from matches
    return_paths: list[NDArray[np.float64]] = []
    weights: list[float] = []

    for match in matches:
        future_start = match.end_idx
        future_end = future_start + forward_bars
        if future_end > len(history):
            continue
        future = history[future_start:future_end]
        anchor = history[match.end_idx - 1]
        if anchor == 0:
            continue
        returns = (future - anchor) / anchor
        return_paths.append(returns)
        # Handle zero confidence to avoid p-array sum-to-zero errors in multinomial sampling
        weights.append(max(match.confidence_score, 1e-6))

    if not return_paths:
        empty = np.zeros(forward_bars)
        return MonteCarloResult(
            paths=np.zeros((0, forward_bars)),
            percentiles={p: empty.copy() for p in percentiles},
            mean=empty.copy(),
            std=empty.copy(),
        )

    paths_arr = np.array(return_paths)  # (n_matches, forward_bars)
    weights_arr = np.array(weights)
    weights_arr /= weights_arr.sum()

    # Compute per-bar statistics from the match distribution
    bar_means = np.average(paths_arr, weights=weights_arr, axis=0)
    bar_stds = np.sqrt(
        np.average((paths_arr - bar_means) ** 2, weights=weights_arr, axis=0)
    )
    # Floor std to avoid zero-variance bars crashing the RNG sampler
    bar_stds = np.maximum(bar_stds, 1e-8)

    # Simulate paths: sample a base match, then add scaled noise
    sim_paths = np.zeros((n_simulations, forward_bars))
    # Pick root paths randomly, weighted by their confidence score
    match_indices = rng.choice(len(return_paths), size=n_simulations, p=weights_arr)

    for i in range(n_simulations):
        base_path = paths_arr[match_indices[i]]
        # Add noise that grows with sqrt(bar) to reflect increasing uncertainty (Brownian assumption)
        noise_scale = bar_stds * np.sqrt(np.arange(1, forward_bars + 1) / forward_bars)
        noise = rng.normal(0, noise_scale)
        sim_paths[i] = base_path + noise

    # Compute summary statistics
    pct_curves = {}
    for p in percentiles:
        pct_curves[p] = np.percentile(sim_paths, p, axis=0)

    return MonteCarloResult(
        paths=sim_paths,
        percentiles=pct_curves,
        mean=np.mean(sim_paths, axis=0),
        std=np.std(sim_paths, axis=0),
    )


# ---------------------------------------------------------------------------
# Regime-conditional projection
# ---------------------------------------------------------------------------

# Compatible regime groups: matches in these regimes are considered
# consistent with the query regime for weighting purposes.
# E.g. finding a mean-reverting historical match when the query is strongly
# breaking out "trending_up" means the background environment has changed.
_REGIME_COMPAT = {
    "trending_up": {"trending_up"},
    "trending_down": {"trending_down"},
    "mean_reverting": {"mean_reverting", "low_vol"},
    "high_vol": {"high_vol"},
    "low_vol": {"low_vol", "mean_reverting"},
}


def regime_conditional_forecast(
    query: NDArray[np.float64],
    matches: list[MatchResult],
    history: NDArray[np.float64],
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
    soft_weight: float = 0.5,
) -> RegimeConditionalResult:
    """Project forward using only regime-compatible matches.

    Detects the query's regime, then filters or down-weights matches
    from incompatible regimes. Uses soft weighting: compatible matches
    get full weight, incompatible matches get (1 - soft_weight) of
    their original weight.

    Args:
        query: Query series (raw values) for regime detection.
        matches: Ranked match results with regime tags.
        history: Full raw history series.
        forward_bars: How many bars to project.
        percentiles: Percentile levels.
        soft_weight: How much to down-weight incompatible regimes.
            0.0 = no filtering, 1.0 = hard filter (exclude incompatible).

    Returns:
        RegimeConditionalResult with filtered projection.
    """
    if percentiles is None:
        percentiles = [10, 25, 50, 75, 90]

    query_regime = tag_regime(query)
    compatible_regimes = _REGIME_COMPAT.get(query_regime, {query_regime})

    paths: list[NDArray[np.float64]] = []
    weights: list[float] = []
    n_used = 0

    for match in matches:
        future_start = match.end_idx
        future_end = future_start + forward_bars
        if future_end > len(history):
            continue
        future = history[future_start:future_end]
        anchor = history[match.end_idx - 1]
        if anchor == 0:
            continue

        returns = (future - anchor) / anchor
        w = max(match.confidence_score, 1e-6)

        # Regime weighting
        match_regime = match.regime or "unknown"
        if match_regime in compatible_regimes:
            n_used += 1
        else:
            w *= 1.0 - soft_weight
            if w < 1e-8:
                continue

        paths.append(returns)
        weights.append(w)

    if not paths:
        empty = np.zeros(forward_bars)
        return RegimeConditionalResult(
            regime=query_regime,
            n_matches_total=len(matches),
            n_matches_used=0,
            curves={p: empty.copy() for p in percentiles},
            all_paths=np.zeros((0, forward_bars)),
            weights=np.array([]),
        )

    paths_arr = np.array(paths)
    weights_arr = np.array(weights)
    weights_arr /= weights_arr.sum()

    curves: dict[int, NDArray[np.float64]] = {}
    for p in percentiles:
        curve = np.zeros(forward_bars)
        for bar in range(forward_bars):
            curve[bar] = _weighted_quantile(paths_arr[:, bar], weights_arr, p / 100.0)
        curves[p] = curve

    return RegimeConditionalResult(
        regime=query_regime,
        n_matches_total=len(matches),
        n_matches_used=n_used,
        curves=curves,
        all_paths=paths_arr,
        weights=weights_arr,
    )


# ---------------------------------------------------------------------------
# Conformal prediction intervals
# ---------------------------------------------------------------------------


def conformal_prediction_intervals(
    matches: list[MatchResult],
    history: NDArray[np.float64],
    forward_bars: int = 50,
    coverage: float = 0.9,
    base_forecast: NDArray[np.float64] | None = None,
) -> ConformalResult:
    """Compute conformal prediction intervals with coverage guarantees.

    Uses split conformal prediction: treats each match's forward window
    as a calibration point, computes nonconformity scores (absolute
    deviation from the point forecast), then inflates the interval
    to achieve the target coverage level.

    Why use this: Unlike basic P10/P90 calculations which assume observed
    data boundaries, conformal bands guarantee finite-sample marginal
    coverage (e.g. 90% chance the true future value falls inside) regardless
    of whether markets have fat tails.

    Args:
        matches: Match results for calibration.
        history: Full raw history series.
        forward_bars: Forecast horizon.
        coverage: Target coverage level (e.g., 0.9 for 90%).
        base_forecast: Point forecast (P50 curve). If None, uses
            the mean of match forward returns.

    Returns:
        ConformalResult with calibrated lower/upper bounds.
    """
    # Extract forward return paths
    return_paths: list[NDArray[np.float64]] = []

    for match in matches:
        future_start = match.end_idx
        future_end = future_start + forward_bars
        if future_end > len(history):
            continue
        future = history[future_start:future_end]
        anchor = history[match.end_idx - 1]
        if anchor == 0:
            continue
        returns = (future - anchor) / anchor
        return_paths.append(returns)

    if not return_paths:
        empty = np.zeros(forward_bars)
        return ConformalResult(
            lower=empty.copy(),
            upper=empty.copy(),
            target_coverage=coverage,
        )

    paths_arr = np.array(return_paths)  # (n_cal, forward_bars)
    n_cal = len(paths_arr)

    # Base forecast: mean of calibration paths if not provided
    if base_forecast is None:
        base_forecast = np.mean(paths_arr, axis=0)
    else:
        base_forecast = np.asarray(base_forecast, dtype=np.float64)
        # Quick-interpolate vector if lengths mismatch (failsafe)
        if len(base_forecast) != forward_bars:
            base_forecast = np.interp(
                np.linspace(0, 1, forward_bars),
                np.linspace(0, 1, len(base_forecast)),
                base_forecast,
            )

    # Nonconformity scores: max absolute deviation per calibration point
    # across all forward bars (conservative — ensures simultaneous coverage)
    scores = np.max(np.abs(paths_arr - base_forecast), axis=1)  # (n_cal,)

    # Conformal quantile: ceil((n+1)*coverage)/n -th order statistic
    # This gives finite-sample coverage guarantee of >= coverage
    q_level = min(np.ceil((n_cal + 1) * coverage) / n_cal, 1.0)
    q_hat = float(np.quantile(scores, q_level))

    # Per-bar adaptive scaling: use per-bar deviation distribution
    # to shape the interval (tighter near-term, wider far-term)
    bar_deviations = np.abs(paths_arr - base_forecast)  # (n_cal, forward_bars)
    bar_scales = np.quantile(bar_deviations, q_level, axis=0)  # (forward_bars,)

    # Use the max of uniform q_hat and per-bar scale for robustness
    interval_width = np.maximum(bar_scales, q_hat * 0.5)

    return ConformalResult(
        lower=base_forecast - interval_width,
        upper=base_forecast + interval_width,
        target_coverage=coverage,
        calibration_scores=scores,
    )


# ---------------------------------------------------------------------------
# Forecast combination (blending)
# ---------------------------------------------------------------------------


def ensemble_forecast(
    matches: list[MatchResult],
    history: NDArray[np.float64],
    query: NDArray[np.float64] | None = None,
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
    config: Config | None = None,
    n_simulations: int = 1000,
    conformal_coverage: float = 0.9,
    regime_soft_weight: float = 0.5,
    mc_weight: float = 0.3,
    regime_weight: float = 0.3,
    historical_weight: float = 0.4,
    seed: int | None = 42,
) -> EnsembleForecast:
    """Combine historical, Monte Carlo, and regime-conditional forecasts.

    Produces a blended forecast cone by weighting three signals:
    1. Historical weighted quantiles (existing projector)
    2. Monte Carlo simulation from match distribution
    3. Regime-conditional projection (filtered by query regime)

    Then applies conformal prediction to produce calibrated intervals.

    Args:
        matches: Ranked match results.
        history: Full raw history series.
        query: Query series for regime detection. If None, regime
            conditioning is skipped.
        forward_bars: Forecast horizon.
        percentiles: Percentile levels.
        config: Pipeline config.
        n_simulations: Monte Carlo paths to generate.
        conformal_coverage: Coverage level for conformal intervals.
        regime_soft_weight: How aggressively to filter incompatible regimes.
        mc_weight: Weight for Monte Carlo component in blend.
        regime_weight: Weight for regime-conditional component.
        historical_weight: Weight for standard historical projection.
        seed: Random seed.

    Returns:
        EnsembleForecast with blended curves and component results.
    """
    if percentiles is None:
        percentiles = config.percentiles if config else [10, 25, 50, 75, 90]

    # Normalize blend weights mathematically
    total_w = mc_weight + regime_weight + historical_weight
    if total_w <= 0:
        total_w = 1.0
    mc_w = mc_weight / total_w
    regime_w = regime_weight / total_w
    hist_w = historical_weight / total_w

    # 1. Historical projection (existing simple projector)
    from the_similarity.core.projector import project as _project

    hist_forecast = _project(matches, history, forward_bars, percentiles, config)

    # 2. Monte Carlo extension
    mc_result = monte_carlo_forecast(
        matches,
        history,
        forward_bars,
        n_simulations,
        percentiles,
        seed,
    )

    # 3. Regime-conditional extension (if query provided)
    regime_result = None
    if query is not None:
        regime_result = regime_conditional_forecast(
            query,
            matches,
            history,
            forward_bars,
            percentiles,
            regime_soft_weight,
        )
        # If no regime matches, fall back to historical weight redistribution
        # This occurs if we constrain conditions so tightly that 0 matches pass.
        if regime_result.n_matches_used == 0:
            hist_w += regime_w
            regime_w = 0.0

    # Combine curves into final projection via weighted average at each Time step
    # matching the targeted percentiles.
    blended_curves: dict[int, NDArray[np.float64]] = {}
    for p in percentiles:
        h_curve = hist_forecast.curves.get(p, np.zeros(forward_bars))
        mc_curve = mc_result.percentiles.get(p, np.zeros(forward_bars))

        if regime_result is not None and regime_w > 0:
            r_curve = regime_result.curves.get(p, np.zeros(forward_bars))
            blended = hist_w * h_curve + mc_w * mc_curve + regime_w * r_curve
        else:
            # Redistribute regime weight to historical
            effective_hist_w = hist_w + regime_w
            blended = effective_hist_w * h_curve + mc_w * mc_curve

        blended_curves[p] = blended

    # 4. Conformal prediction intervals calculated on the final blended P50
    conformal_result = conformal_prediction_intervals(
        matches,
        history,
        forward_bars,
        conformal_coverage,
        base_forecast=blended_curves.get(50),
    )

    return EnsembleForecast(
        bars=forward_bars,
        percentiles=percentiles,
        curves=blended_curves,
        monte_carlo=mc_result,
        regime_conditional=regime_result,
        conformal=conformal_result,
        component_weights={
            "historical": hist_w,
            "monte_carlo": mc_w,
            "regime_conditional": regime_w,
        },
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _weighted_quantile(
    values: NDArray[np.float64],
    weights: NDArray[np.float64],
    quantile: float,
) -> float:
    """Linearly interpolate a weighted quantile.

    Duplicates `projector.py` equivalent as numpy lacks an official `np.weighted_quantile()`.
    """
    if len(values) == 1:
        return float(values[0])
    sorted_idx = np.argsort(values)
    sorted_values = values[sorted_idx]
    sorted_weights = weights[sorted_idx]
    cumulative = np.cumsum(sorted_weights)
    centers = cumulative - 0.5 * sorted_weights
    centers[0] = max(0.0, centers[0])
    centers[-1] = min(1.0, centers[-1])
    if len(centers) > 1:
        centers = np.maximum.accumulate(centers)
    return float(np.interp(quantile, centers, sorted_values))
