"""
Time series normalization strategies for the matching pipeline.

Different scoring methods require different normalization to produce
meaningful comparisons. This module provides a unified `normalize()`
function that applies the requested transform, plus per-method defaults.

AI AGENT NOTES:
- `logreturn_zscore` is the recommended default for financial data:
  log-returns make comparisons scale-invariant (a 10% rise in a $10 stock
  looks the same as a 10% rise in a $1000 stock), then z-scoring removes
  any remaining location/scale differences between windows.
- EMD uses "raw" because the decomposition needs the original signal
  structure; normalizing would destroy the oscillatory components.
- `normalize_pair()` normalizes each window *independently* — this is
  intentional. Global normalization (using both windows' joint stats)
  would leak information about the candidate into the query's representation.
- Log-return methods reduce array length by 1 (diff operation).

Normalization hierarchy:
  raw            → no change
  zscore         → zero-mean, unit-variance
  minmax         → scale to [0, 1]
  logreturn      → ln(p[t]/p[t-1]) — captures multiplicative structure
  logreturn_zscore → logreturn then zscore — the "gold standard"
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Per-method normalization defaults
# ---------------------------------------------------------------------------
# Each scoring method has a preferred normalization that best suits its
# mathematical assumptions. The matcher looks up this table when preparing
# windows for each method. Override globally via Config.normalization.
#
# Rationale for each choice:
# - dtw, pearson, matrix_profile, sax, tda: Shape-based methods that benefit
#   from z-scored log-returns. The z-scoring prevents amplitude-dominated
#   comparisons; log-returns make the comparison scale-invariant.
# - bempedelis, koopman, wavelet: Dynamical/fractal methods that work on
#   log-returns directly because they model the *incremental* dynamics,
#   and their internal math handles the remaining normalization.
# - emd: Needs raw values because the EMD decomposition algorithm expects
#   the original oscillatory structure. Normalizing would flatten the IMFs.
METHOD_NORM_DEFAULTS: dict[str, str] = {
    "dtw": "logreturn_zscore",
    "pearson": "logreturn_zscore",
    "bempedelis": "logreturn",
    "koopman": "logreturn",
    "wavelet": "logreturn",
    "emd": "raw",
    "tda": "logreturn_zscore",
    "matrix_profile": "logreturn_zscore",
    "sax": "logreturn_zscore",
}


def normalize(
    series: NDArray[np.float64], method: str = "zscore"
) -> NDArray[np.float64]:
    """Normalize a 1D time series using the specified strategy.

    Args:
        series: Raw price/value array (1D).
        method: One of:
            - "zscore" → zero-mean, unit-variance
            - "minmax" → scale to [0, 1]
            - "logreturn" → log-returns (length reduces by 1)
            - "logreturn_zscore" → log-returns then z-score (length - 1)
            - "raw" → no transformation (returns a copy)

    Returns:
        Normalized array as float64. For logreturn methods, the output is
        one element shorter than the input.

    Raises:
        ValueError: If the normalization method name is not recognized.
    """
    series = np.asarray(series, dtype=np.float64)

    if method == "zscore":
        return _zscore(series)
    elif method == "minmax":
        return _minmax(series)
    elif method == "logreturn":
        return _logreturn(series)
    elif method == "logreturn_zscore":
        # Two-step: first compute log-returns, then z-score the result.
        # This is the most robust normalization for financial pattern matching.
        return _zscore(_logreturn(series))
    elif method == "raw":
        # Return a copy so the caller can't accidentally mutate the original
        return series.copy()
    else:
        raise ValueError(f"Unknown normalization method: {method}")


def normalize_pair(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    method: str = "logreturn_zscore",
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Normalize a query/candidate pair with the same method.

    Each window is normalized independently — no information leaks between
    them. This is critical: if we z-scored using the joint distribution of
    both windows, we'd be telling the similarity measure about the candidate
    before it has a chance to make an independent judgment.

    Args:
        query: Raw query window values.
        candidate: Raw candidate window values.
        method: Normalization method name.

    Returns:
        (normalized_query, normalized_candidate) tuple.
    """
    return normalize(query, method), normalize(candidate, method)


# ---------------------------------------------------------------------------
# Internal normalization implementations
# ---------------------------------------------------------------------------


def _zscore(s: NDArray[np.float64]) -> NDArray[np.float64]:
    """Z-score normalization: (x - mean) / std.

    Constant series (std=0) maps to all zeros rather than NaN/inf.
    """
    std = np.std(s)
    if std == 0:
        return np.zeros_like(s)
    return (s - np.mean(s)) / std


def _minmax(s: NDArray[np.float64]) -> NDArray[np.float64]:
    """Min-max normalization: scale to [0, 1].

    Constant series maps to all zeros.
    """
    mn, mx = np.min(s), np.max(s)
    rng = mx - mn
    if rng == 0:
        return np.zeros_like(s)
    return (s - mn) / rng


def _logreturn(s: NDArray[np.float64]) -> NDArray[np.float64]:
    """Log-returns: ln(p[t] / p[t-1]) = diff(log(p)).

    Handles near-zero prices by clamping to 1e-12 before taking the log.
    This avoids log(0) = -inf while being negligible for any real price.
    The output is one element shorter than the input.
    """
    s = np.maximum(s, 1e-12)  # Guard against log(0)
    return np.diff(np.log(s))
