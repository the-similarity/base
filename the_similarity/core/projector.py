from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from the_similarity.config import Config
from the_similarity.core.scorer import MatchResult
from the_similarity.methods.koopman import KoopmanForecast


@dataclass
class Forecast:
    """Forward projection with uncertainty bands."""
    bars: int
    percentiles: list[int]
    curves: dict[int, NDArray[np.float64]]  # percentile -> projected values
    all_paths: NDArray[np.float64]  # (n_matches, bars) raw projected paths
    weights: NDArray[np.float64]  # confidence weights used
    koopman_forecast: KoopmanForecast | None = None  # Koopman operator evolution


def project(
    matches: list[MatchResult],
    history: NDArray[np.float64],
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
    config: Config | None = None,
) -> Forecast:
    """Generate forward projection from matched patterns.

    For each match, extracts the `forward_bars` candles that followed
    the match window in history, converts them to returns, and builds
    a weighted percentile forecast cone.

    Args:
        matches: Ranked match results from the matcher.
        history: Full raw history series.
        forward_bars: How many bars to project forward.
        percentiles: Which percentiles to compute.

    Returns:
        Forecast object with uncertainty bands.
    """
    if percentiles is None:
        percentiles = Config().percentiles

    paths: list[NDArray[np.float64]] = []
    weights: list[float] = []

    for match in matches:
        future_start = match.end_idx
        future_end = future_start + forward_bars

        if future_end > len(history):
            continue

        future = history[future_start:future_end]
        anchor = history[match.end_idx - 1]

        # Convert to cumulative returns relative to the end of the match
        if anchor == 0:
            continue
        returns = (future - anchor) / anchor
        match.forward_window = returns
        paths.append(returns)
        weights.append(match.confidence_score)

    if not paths:
        empty = np.zeros(forward_bars)
        return Forecast(
            bars=forward_bars,
            percentiles=percentiles,
            curves={p: empty.copy() for p in percentiles},
            all_paths=np.zeros((0, forward_bars)),
            weights=np.array([]),
        )

    paths_arr = np.array(paths)
    weights_arr = np.array(weights)
    total_weight = weights_arr.sum()
    if total_weight > 0:
        weights_arr = weights_arr / total_weight
    else:
        # Fall back to uniform weighting when all confidence scores are zero.
        weights_arr = np.full(len(weights_arr), 1.0 / len(weights_arr))

    # Weighted percentile curves with linear interpolation.
    curves: dict[int, NDArray[np.float64]] = {}
    for p in percentiles:
        curve = np.zeros(forward_bars)
        for bar in range(forward_bars):
            col = paths_arr[:, bar]
            curve[bar] = _weighted_quantile(col, weights_arr, p / 100.0)
        curves[p] = curve

    # Apply confidence decay to widen the cone over time
    if config is not None and config.confidence_decay_rate > 0 and 50 in curves:
        p50 = curves[50]
        for p in curves:
            if p == 50:
                continue
            for bar in range(forward_bars):
                decay = 1.0 + config.confidence_decay_rate * bar
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
    """Linearly interpolate a weighted quantile."""
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
