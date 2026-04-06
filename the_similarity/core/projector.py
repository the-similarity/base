"""
Forward projection (forecast cone) from historical pattern matches.

Given a set of matched historical segments, this module extracts what
*actually happened* after each match ended, converts those forward paths
to cumulative returns, and builds weighted percentile curves that form
the "forecast cone" — the engine's probabilistic prediction.

Conceptual Boundary:
This projection creates empirical outcome distributions. It is NOT a predictive 
model; it is a statistical summary of empirical history post-match. The core axiom 
is that prior analogues form a useful Bayesian prior for future behavior.

Data Lifecycle & Guardrails:
- Incomplete Paths: Any match whose projection window exceeds the available 
  `history` length is silently dropped (fail-closed).
- Cone Widening: `confidence_decay_rate` artificially expands the upper and 
  lower percentile variance bounds linearly over time steps to counteract 
  over-confidence in long-term historical analogues.
- Implementation details: Because `numpy.quantile` lacks sample weight support, 
  `_weighted_quantile` uses piecewise-linear CDF center interpolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from the_similarity.config import Config
from the_similarity.core.scorer import MatchResult
from the_similarity.methods.koopman import KoopmanForecast


@dataclass
class Forecast:
    """Forward projection with uncertainty bands.

    Fields:
        bars: Number of forward bars projected.
        percentiles: Which percentiles were computed (e.g., [10, 25, 50, 75, 90]).
        curves: Maps each percentile to a 1D array of projected cumulative returns.
                E.g., curves[50] is the median projection.
        all_paths: 2D array (n_matches, bars) of all individual forward paths.
                   Each row is one match's actual post-match returns.
        weights: 1D array of normalized weights used for each path (sums to 1.0).
        koopman_forecast: Optional Koopman operator evolution for blended forecast.
    """
    bars: int
    percentiles: list[int]
    curves: dict[int, NDArray[np.float64]]  # percentile → projected values
    all_paths: NDArray[np.float64]          # (n_matches, bars) raw paths
    weights: NDArray[np.float64]            # normalized confidence weights
    koopman_forecast: KoopmanForecast | None = None


def project(
    matches: list[MatchResult],
    history: NDArray[np.float64],
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
    config: Config | None = None,
) -> Forecast:
    """Generate forward projection from matched patterns.

    Algorithm:
    1. For each match, extract the `forward_bars` candles that followed
       the match window in the history array.
    2. Convert those candles to cumulative returns relative to the last
       bar of the match (the "anchor" price).
    3. Weight each path by the match's confidence score.
    4. Compute weighted percentile curves across all paths.
    5. Optionally apply confidence decay to widen the cone over time.

    Args:
        matches: Ranked match results from the search pipeline.
        history: Full raw history series (same array used in search).
        forward_bars: How many bars to project into the future.
        percentiles: Which quantiles to compute (default: [10,25,50,75,90]).
        config: Configuration for confidence decay and Koopman blending.

    Returns:
        Forecast object containing uncertainty bands and all individual paths.
    """
    if percentiles is None:
        percentiles = Config().percentiles

    paths: list[NDArray[np.float64]] = []
    weights: list[float] = []

    for match in matches:
        # The forward window starts immediately after the match ends
        future_start = match.end_idx
        future_end = future_start + forward_bars

        # Skip matches too close to the end of the history — they don't have
        # enough post-match data to contribute a full forward path.
        if future_end > len(history):
            continue

        # Extract the raw prices that occurred after this match
        future = history[future_start:future_end]

        # The anchor is the last price in the matched window.
        # All forward prices are expressed as returns relative to this.
        anchor = history[match.end_idx - 1]

        # Skip degenerate anchors (e.g., a price of exactly zero)
        if anchor == 0:
            continue

        # Convert to cumulative returns: (future_price - anchor) / anchor
        # A return of 0.05 means "5% above the anchor price"
        returns = (future - anchor) / anchor

        # Store the returns on the match object itself so downstream consumers
        # (explainer, viz) can access them without re-computing.
        match.forward_window = returns
        paths.append(returns)

        # Higher-confidence matches get more weight in the forecast cone.
        weights.append(match.confidence_score)

    # --- Edge case: no valid forward paths ---
    # This happens when all matches are too close to the end of history.
    if not paths:
        empty = np.zeros(forward_bars)
        return Forecast(
            bars=forward_bars,
            percentiles=percentiles,
            curves={p: empty.copy() for p in percentiles},
            all_paths=np.zeros((0, forward_bars)),
            weights=np.array([]),
        )

    # --- Build the weighted percentile forecast ---
    paths_arr = np.array(paths)    # shape: (n_valid_matches, forward_bars)
    weights_arr = np.array(weights)

    # Normalize weights to sum to 1.0 for proper weighted quantile computation.
    total_weight = weights_arr.sum()
    if total_weight > 0:
        weights_arr = weights_arr / total_weight
    else:
        # All confidence scores were zero — fall back to uniform weighting.
        # This should be rare in practice but prevents division by zero.
        weights_arr = np.full(len(weights_arr), 1.0 / len(weights_arr))

    # Compute weighted percentile curves bar by bar.
    # For each future bar, we have one value per match — we compute the
    # weighted quantile across those values.
    curves: dict[int, NDArray[np.float64]] = {}
    for p in percentiles:
        curve = np.zeros(forward_bars)
        for bar in range(forward_bars):
            # Extract the column of values at this bar across all paths
            col = paths_arr[:, bar]
            curve[bar] = _weighted_quantile(col, weights_arr, p / 100.0)
        curves[p] = curve

    # --- Confidence decay: widen the cone over time ---
    # The intuition: predictions become less reliable further into the future.
    # We fan out the non-median curves by multiplying their distance from P50
    # by a linearly increasing factor.
    if config is not None and config.confidence_decay_rate > 0 and 50 in curves:
        p50 = curves[50]  # Median curve as the center reference
        for p in curves:
            if p == 50:
                continue  # Don't modify the median itself
            for bar in range(forward_bars):
                # Decay factor increases linearly with bar number
                decay = 1.0 + config.confidence_decay_rate * bar
                # Fan out the curve by scaling its distance from the median
                distance = curves[p][bar] - p50[bar]
                curves[p][bar] = p50[bar] + distance * decay

    return Forecast(
        bars=forward_bars,
        percentiles=percentiles,
        curves=curves,
        all_paths=paths_arr,
        weights=weights_arr,
    )


def _weighted_quantile(
    values: NDArray[np.float64],
    weights: NDArray[np.float64],
    quantile: float,
) -> float:
    """Compute a weighted quantile with linear interpolation.

    Standard numpy quantile doesn't support per-sample weights. This
    implementation:
    1. Sorts values and weights together by value.
    2. Computes cumulative weight, placing each value at the center of
       its weight mass.
    3. Linearly interpolates the quantile from the (cumulative_position,
       value) pairs.

    This is equivalent to a piecewise-linear CDF where each sample
    occupies a "width" proportional to its weight.

    Args:
        values: 1D array of values to take quantile of (one per match path).
        weights: 1D array of normalized weights (must sum to ~1.0).
        quantile: Target quantile in [0, 1] (e.g., 0.5 for median).

    Returns:
        Interpolated quantile value.
    """
    # Single observation: the quantile is just that value regardless of weight
    if len(values) == 1:
        return float(values[0])

    # Sort both arrays by value so we can build a proper CDF
    sorted_idx = np.argsort(values)
    sorted_values = values[sorted_idx]
    sorted_weights = weights[sorted_idx]

    # Cumulative weight gives the CDF. We place each sample at the CENTER
    # of its weight interval (not the right edge) for better interpolation.
    cumulative = np.cumsum(sorted_weights)
    centers = cumulative - 0.5 * sorted_weights

    # Clamp the extreme centers to [0, 1] so the interpolation domain is valid
    centers[0] = max(0.0, centers[0])
    centers[-1] = min(1.0, centers[-1])

    # Enforce monotonicity — numerical precision issues can cause tiny
    # inversions that would confuse np.interp.
    if len(centers) > 1:
        centers = np.maximum.accumulate(centers)

    # Standard linear interpolation: find where `quantile` falls in the
    # cumulative weight domain and interpolate the corresponding value.
    return float(np.interp(quantile, centers, sorted_values))
