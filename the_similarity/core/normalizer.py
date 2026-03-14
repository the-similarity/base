from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# Per-method normalization defaults.
# Shape-based methods need z-score per window so amplitude doesn't dominate.
# Fractal/dynamical methods work on log-returns to capture multiplicative structure.
# Some methods (EMD) need raw values for decomposition.
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


def normalize(series: NDArray[np.float64], method: str = "zscore") -> NDArray[np.float64]:
    """Normalize a 1D time series.

    Args:
        series: Raw price/value array.
        method: One of "zscore", "minmax", "logreturn", "logreturn_zscore", "raw".

    Returns:
        Normalized array. logreturn and logreturn_zscore reduce length by 1.
    """
    series = np.asarray(series, dtype=np.float64)

    if method == "zscore":
        return _zscore(series)
    elif method == "minmax":
        return _minmax(series)
    elif method == "logreturn":
        return _logreturn(series)
    elif method == "logreturn_zscore":
        return _zscore(_logreturn(series))
    elif method == "raw":
        return series.copy()
    else:
        raise ValueError(f"Unknown normalization method: {method}")


def normalize_pair(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    method: str = "logreturn_zscore",
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Normalize a query/candidate pair with the same method.

    Convenience function that ensures both windows go through
    identical normalization. Each window is normalized independently
    (per-window z-score, not global).

    Args:
        query: Raw query window.
        candidate: Raw candidate window.
        method: Normalization method name.

    Returns:
        (normalized_query, normalized_candidate) tuple.
    """
    return normalize(query, method), normalize(candidate, method)


def _zscore(s: NDArray[np.float64]) -> NDArray[np.float64]:
    std = np.std(s)
    if std == 0:
        return np.zeros_like(s)
    return (s - np.mean(s)) / std


def _minmax(s: NDArray[np.float64]) -> NDArray[np.float64]:
    mn, mx = np.min(s), np.max(s)
    rng = mx - mn
    if rng == 0:
        return np.zeros_like(s)
    return (s - mn) / rng


def _logreturn(s: NDArray[np.float64]) -> NDArray[np.float64]:
    s = np.maximum(s, 1e-12)  # guard against log(0)
    return np.diff(np.log(s))
