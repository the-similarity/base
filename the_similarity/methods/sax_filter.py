"""SAX (Symbolic Aggregate approXimation) pre-filter.

Converts normalized time series into symbolic strings via PAA + breakpoints,
then computes MINDIST — a lower bound on Euclidean distance that guarantees
no false dismissals while eliminating most candidates cheaply.

Reference: Lin et al., "Experiencing SAX: a Novel Symbolic Representation
of Time Series" (2007).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm


def _breakpoints(alphabet_size: int) -> NDArray[np.float64]:
    """Equiprobable breakpoints for a standard normal distribution."""
    return norm.ppf(np.linspace(0, 1, alphabet_size + 1)[1:-1])


def _paa(series: NDArray[np.float64], n_segments: int) -> NDArray[np.float64]:
    """Piecewise Aggregate Approximation: reduce series to n_segments means."""
    n = len(series)
    if n_segments >= n:
        return series.copy()
    # Reshape-friendly when n is divisible; otherwise use weighted sum
    indices = np.linspace(0, n, n_segments + 1, dtype=np.float64)
    paa_values = np.empty(n_segments, dtype=np.float64)
    for i in range(n_segments):
        start = int(np.floor(indices[i]))
        end = int(np.ceil(indices[i + 1]))
        if end <= start:
            end = start + 1
        paa_values[i] = np.mean(series[start:end])
    return paa_values


def sax_transform(
    series: NDArray[np.float64],
    n_segments: int = 16,
    alphabet_size: int = 8,
) -> NDArray[np.int8]:
    """Convert a z-normalized series to a SAX integer representation.

    Args:
        series: Z-normalized 1D array.
        n_segments: Number of PAA segments.
        alphabet_size: Number of symbols (2-26).

    Returns:
        Integer array of length n_segments, values in [0, alphabet_size-1].
    """
    paa_values = _paa(series, n_segments)
    bps = _breakpoints(alphabet_size)
    return np.searchsorted(bps, paa_values).astype(np.int8)


def _build_dist_table(alphabet_size: int) -> NDArray[np.float64]:
    """Build the SAX symbol-to-symbol distance lookup table.

    dist(a, b) = 0 if |a - b| <= 1, else breakpoint[max] - breakpoint[min-1].
    """
    bps = _breakpoints(alphabet_size)
    table = np.zeros((alphabet_size, alphabet_size), dtype=np.float64)
    for i in range(alphabet_size):
        for j in range(alphabet_size):
            if abs(i - j) <= 1:
                table[i, j] = 0.0
            else:
                high = max(i, j)
                low = min(i, j)
                table[i, j] = bps[high - 1] - bps[low]
    return table


# Cache dist tables by alphabet size to avoid recomputation.
_DIST_TABLE_CACHE: dict[int, NDArray[np.float64]] = {}


def _get_dist_table(alphabet_size: int) -> NDArray[np.float64]:
    if alphabet_size not in _DIST_TABLE_CACHE:
        _DIST_TABLE_CACHE[alphabet_size] = _build_dist_table(alphabet_size)
    return _DIST_TABLE_CACHE[alphabet_size]


def sax_mindist(
    sax_a: NDArray[np.int8],
    sax_b: NDArray[np.int8],
    original_length: int,
    alphabet_size: int = 8,
) -> float:
    """MINDIST between two SAX representations.

    This is a lower bound on Euclidean distance — no false dismissals.

    Args:
        sax_a: SAX integer array for series A.
        sax_b: SAX integer array for series B.
        original_length: Length of the original (pre-PAA) series.
        alphabet_size: Number of symbols used.

    Returns:
        MINDIST value (lower bound on Euclidean distance).
    """
    n_segments = len(sax_a)
    table = _get_dist_table(alphabet_size)
    dist_sq_sum = 0.0
    for i in range(n_segments):
        d = table[sax_a[i], sax_b[i]]
        dist_sq_sum += d * d
    return float(np.sqrt(original_length / n_segments) * np.sqrt(dist_sq_sum))


def sax_score(mindist: float, window_size: int) -> float:
    """Convert MINDIST to a [0, 1] similarity score.

    Uses exponential decay normalized by window size.

    Args:
        mindist: MINDIST value.
        window_size: Original window length for normalization.

    Returns:
        Score in [0, 1], where 1 = identical SAX representations.
    """
    return float(np.exp(-mindist / max(window_size, 1)))
