"""TradingView Pine mirror for the_similarity's lightweight pattern workflow.

This module intentionally mirrors the practical subset of the engine that can
run inside TradingView Pine Script:

- query window = latest `query_length` bars
- candidate search = historical windows across configurable scale multipliers
- normalization = log-return z-score (`core/normalizer.py`)
- confidence = Pine-friendly Tier-1 style blend of correlation + distance
- projection = scale the matched historical forward path to current price

It is not a replacement for the full research engine. Pine cannot reproduce the
full Tier 2 stack (Koopman, wavelets, TDA, EMD, etc.) with acceptable runtime,
so this reference implementation focuses on the on-chart subset that can be
verified locally and mirrored into standalone Pine indicator/strategy scripts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

EPSILON = 1e-12


@dataclass(frozen=True)
class PinePatternMatch:
    """Best pattern match produced by the Pine-compatible search."""

    score: float
    scale: float
    end_idx: int
    projected_end_return: float
    projected_min_return: float
    projected_max_return: float
    matched_resampled: NDArray[np.float64]
    projected_prices: NDArray[np.float64]


def logreturn_zscore(values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Mirror Pine's log-return z-score normalization."""
    values = np.asarray(values, dtype=np.float64)
    if values.size < 2:
        return np.zeros(0, dtype=np.float64)

    safe = np.maximum(values, EPSILON)
    returns = np.diff(np.log(safe))
    std = returns.std()
    if std == 0:
        return np.zeros_like(returns)
    return (returns - returns.mean()) / std


def resample_series(values: NDArray[np.float64], target_length: int) -> NDArray[np.float64]:
    """Linearly resample a 1D series to the target length."""
    values = np.asarray(values, dtype=np.float64)
    if target_length <= 0:
        raise ValueError("target_length must be positive")
    if values.size == 0:
        return np.zeros(target_length, dtype=np.float64)
    if values.size == 1 or target_length == 1:
        return np.full(target_length, values[-1], dtype=np.float64)

    src_idx = np.linspace(0, values.size - 1, num=values.size)
    dst_idx = np.linspace(0, values.size - 1, num=target_length)
    return np.interp(dst_idx, src_idx, values).astype(np.float64)


def total_log_return(values: NDArray[np.float64]) -> float:
    """Return ln(last / first) with zero guards."""
    values = np.asarray(values, dtype=np.float64)
    if values.size < 2:
        return 0.0
    return float(np.log(max(values[-1], EPSILON) / max(values[0], EPSILON)))


def similarity_score(query: NDArray[np.float64], candidate: NDArray[np.float64]) -> float:
    """Mirror the Pine score blend used in the TradingView scripts.

    Score components:
    - Pearson correlation on log-return z-score windows
    - mean absolute deviation on the normalized windows
    - total log-return agreement on the raw windows
    """
    query = np.asarray(query, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if query.size != candidate.size:
        raise ValueError("query and candidate must have the same length")
    if query.size < 2:
        return 0.0

    q_norm = logreturn_zscore(query)
    c_norm = logreturn_zscore(candidate)

    if q_norm.size == 0 or c_norm.size == 0:
        return 0.0

    q_std = q_norm.std()
    c_std = c_norm.std()
    corr = 0.0 if q_std == 0 or c_std == 0 else float(np.corrcoef(q_norm, c_norm)[0, 1])
    if np.isnan(corr):
        corr = 0.0
    pearson_score = max(0.0, (corr + 1.0) * 0.5)

    mae_score = float(np.exp(-np.mean(np.abs(q_norm - c_norm))))
    total_return_score = float(
        np.exp(-abs(total_log_return(query) - total_log_return(candidate)) * 2.0)
    )

    raw_score = 0.65 * pearson_score + 0.20 * mae_score + 0.15 * total_return_score
    return float(np.clip(raw_score * 100.0, 0.0, 100.0))


def scale_match_to_current(match: NDArray[np.float64], current_price: float) -> NDArray[np.float64]:
    """Anchor a matched window so its last value equals `current_price`."""
    match = np.asarray(match, dtype=np.float64)
    if match.size == 0:
        return match
    anchor = max(float(match[-1]), EPSILON)
    return current_price * (match / anchor)


def project_future_to_current(
    future_segment: NDArray[np.float64],
    anchor_price: float,
    current_price: float,
) -> NDArray[np.float64]:
    """Scale a historical future path so it starts from the current price."""
    future_segment = np.asarray(future_segment, dtype=np.float64)
    anchor = max(float(anchor_price), EPSILON)
    returns = (future_segment / anchor) - 1.0
    return current_price * (1.0 + returns)


def find_best_match(
    history: NDArray[np.float64],
    query_length: int,
    forecast_bars: int,
    lookback_bars: int,
    *,
    stride: int = 5,
    min_separation: int = 20,
    min_scale: float = 0.75,
    scale_step: float = 0.25,
    scale_count: int = 4,
) -> PinePatternMatch | None:
    """Search history for the best Pine-compatible analogue of the latest window."""
    history = np.asarray(history, dtype=np.float64)
    if history.ndim != 1:
        raise ValueError("history must be 1D")
    if query_length < 2:
        raise ValueError("query_length must be at least 2")
    if forecast_bars < 1:
        raise ValueError("forecast_bars must be positive")
    if stride < 1:
        raise ValueError("stride must be positive")
    if scale_count < 1:
        raise ValueError("scale_count must be at least 1")
    if history.size < query_length + forecast_bars + min_separation + 2:
        return None

    query = history[-query_length:]
    current_price = float(query[-1])

    best: PinePatternMatch | None = None
    min_end_ago = query_length + min_separation + forecast_bars

    for scale_idx in range(scale_count):
        scale = min_scale + scale_step * scale_idx
        cand_len = max(8, int(round(query_length * scale)))
        max_end_ago = min(lookback_bars, history.size - cand_len)

        for end_ago in range(min_end_ago, max_end_ago + 1, stride):
            end_idx = history.size - 1 - end_ago
            start_idx = end_idx - cand_len + 1
            if start_idx < 0:
                continue

            future_end = end_idx + 1 + forecast_bars
            if future_end > history.size:
                continue

            candidate_raw = history[start_idx : end_idx + 1]
            candidate_resampled = resample_series(candidate_raw, query_length)
            score = similarity_score(query, candidate_resampled)

            anchor = float(candidate_raw[-1])
            future_segment = history[end_idx + 1 : future_end]
            projected_prices = project_future_to_current(future_segment, anchor, current_price)
            projected_returns = (projected_prices / current_price) - 1.0

            if best is None or score > best.score:
                best = PinePatternMatch(
                    score=score,
                    scale=scale,
                    end_idx=end_idx,
                    projected_end_return=float(projected_returns[-1]),
                    projected_min_return=float(projected_returns.min()),
                    projected_max_return=float(projected_returns.max()),
                    matched_resampled=scale_match_to_current(candidate_resampled, current_price),
                    projected_prices=projected_prices,
                )

    return best
