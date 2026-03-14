"""Matrix Profile pre-filter using MASS (Mueen's Algorithm for Similarity Search).

Computes the z-normalized Euclidean distance between a query subsequence and
every position in a longer time series in O(n log n) via FFT — making it an
ideal Tier 1 ranking signal.

This is a pure-numpy implementation (no stumpy dependency) to avoid
numba JIT compatibility issues.

Reference: Mueen et al., "Exact Discovery of Time Series Motifs" (2009).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# Keep this True — our implementation has no external dependency.
HAS_STUMPY = True


def _sliding_dot_product(query: NDArray[np.float64], ts: NDArray[np.float64]) -> NDArray[np.float64]:
    """Compute sliding dot product of query against ts using FFT."""
    n = len(ts)
    m = len(query)
    # Reverse query and zero-pad both to length n
    query_rev = query[::-1]
    padded_query = np.zeros(n)
    padded_query[:m] = query_rev
    # FFT-based convolution
    fft_ts = np.fft.rfft(ts)
    fft_q = np.fft.rfft(padded_query)
    result = np.fft.irfft(fft_ts * fft_q, n=n)
    return result[m - 1: n]


def query_profile(
    history: NDArray[np.float64],
    query: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Compute z-normalized Euclidean distance profile of query against history.

    Uses O(n log n) FFT-based MASS algorithm.

    Args:
        history: Full history array (1D).
        query: Query subsequence (1D, shorter than history).

    Returns:
        Distance array of shape (len(history) - len(query) + 1,).
        Each value is the z-normalized Euclidean distance at that position.
    """
    history = np.asarray(history, dtype=np.float64)
    query = np.asarray(query, dtype=np.float64)
    n = len(history)
    m = len(query)

    # Query statistics
    mu_q = np.mean(query)
    std_q = np.std(query)
    if std_q < 1e-10:
        std_q = 1e-10

    # Sliding mean and std of history windows
    cumsum = np.concatenate([[0], np.cumsum(history)])
    cumsum2 = np.concatenate([[0], np.cumsum(history ** 2)])
    window_sum = cumsum[m:] - cumsum[:n - m + 1]
    window_sum2 = cumsum2[m:] - cumsum2[:n - m + 1]
    mu_t = window_sum / m
    # Variance with clamp to avoid negative values from floating point
    var_t = np.maximum(window_sum2 / m - mu_t ** 2, 0.0)
    std_t = np.sqrt(var_t)
    std_t = np.maximum(std_t, 1e-10)

    # Sliding dot product
    dot = _sliding_dot_product(query, history)

    # z-normalized Euclidean distance
    # d^2 = 2m * (1 - (dot - m*mu_q*mu_t) / (m*std_q*std_t))
    dist_sq = 2 * m * (1 - (dot - m * mu_q * mu_t) / (m * std_q * std_t))
    dist_sq = np.maximum(dist_sq, 0.0)
    return np.sqrt(dist_sq)


def mp_score(distance: float, window_size: int) -> float:
    """Convert a MASS distance to a [0, 1] similarity score.

    Uses exponential decay normalized by sqrt(window_size) since
    z-normalized Euclidean distance scales with sqrt(length).

    Args:
        distance: Z-normalized Euclidean distance from MASS.
        window_size: Length of the query subsequence.

    Returns:
        Score in [0, 1], where 1 = identical (distance ≈ 0).
    """
    return float(np.exp(-distance / max(np.sqrt(window_size), 1.0)))


def mp_score_profile(
    distances: NDArray[np.float64],
    window_size: int,
) -> NDArray[np.float64]:
    """Convert a full distance profile to similarity scores.

    Args:
        distances: Distance profile from query_profile().
        window_size: Length of the query subsequence.

    Returns:
        Score array in [0, 1] for each position.
    """
    return np.exp(-distances / max(np.sqrt(window_size), 1.0))
