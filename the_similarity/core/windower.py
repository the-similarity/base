"""
Sliding window generation for the pattern matching pipeline.

Provides two main capabilities:
1. `sliding_windows()` — generates a 2D array of overlapping windows using
   numpy stride tricks (zero-copy view, then explicitly copied for safety).
2. `multi_scale_indices()` — generates window positions at multiple time
   scales for cross-scale pattern discovery.

AI AGENT NOTES:
- `sliding_windows()` uses `np.lib.stride_tricks.as_strided` for O(1) memory
  allocation of the windowed view, then `.copy()` materializes it. The copy
  is necessary because consumers (normalization, DTW) modify windows in-place.
- Stride parameter directly controls throughput: stride=1 checks every position
  (max recall), stride=5 checks every 5th position (5× faster, minimal recall
  loss in practice for smooth series).
- Multi-scale search is the self-similarity hypothesis in action: the same
  market pattern may have played out over 20 bars or 40 bars. Checking
  windows at 0.5×–2.0× the query length catches time-stretched analogs.
- DEFAULT_SCALE_FACTORS includes sub-1× scales (0.5, 0.75) because we may
  want to find a faster version of the query pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


def sliding_windows(
    series: NDArray[np.float64],
    window_size: int,
    stride: int = 1,
) -> NDArray[np.float64]:
    """Generate sliding windows over a 1D series using stride tricks.

    This is the fundamental operation that turns a flat history array into
    a matrix of candidate windows for comparison against the query.

    Implementation note: `as_strided` creates a view where each row shares
    memory with the original array. This is extremely fast but the view is
    read-only in practice (writing to a strided view causes aliasing bugs).
    We call `.copy()` to produce safe, independent windows.

    Args:
        series: 1D array of values (typically the full history).
        window_size: Number of elements per window. Must equal len(query)
                     for same-scale matching.
        stride: Step between consecutive window start positions.
                stride=1 → max recall, stride=5 → 5× fewer candidates.

    Returns:
        2D float64 array of shape (n_windows, window_size).
        Each row is one candidate window.

    Raises:
        ValueError: If window_size > series length, or if window_size or
                    stride is less than 1.

    Performance:
        Memory: O(n_windows × window_size) after the copy.
        Time: O(n_windows × window_size) for the copy.
        n_windows = (len(series) - window_size) // stride + 1
    """
    series = np.asarray(series, dtype=np.float64)
    if window_size > len(series):
        raise ValueError(f"window_size ({window_size}) > series length ({len(series)})")
    if window_size < 1:
        raise ValueError("window_size must be >= 1")
    if stride < 1:
        raise ValueError("stride must be >= 1")

    # Number of complete windows that fit with the given stride
    n_windows = (len(series) - window_size) // stride + 1

    # Build a strided view — no data is copied here, just a pointer + shape
    shape = (n_windows, window_size)
    # strides[0] * stride = bytes to skip between window starts
    # strides[0] = bytes per element (8 for float64)
    strides = (series.strides[0] * stride, series.strides[0])

    # as_strided creates overlapping views; .copy() materializes them into
    # independent memory so downstream code can normalize windows in-place.
    return np.lib.stride_tricks.as_strided(series, shape=shape, strides=strides).copy()


def window_indices(
    series_length: int,
    window_size: int,
    stride: int = 1,
) -> list[tuple[int, int]]:
    """Return (start, end) index pairs for each sliding window position.

    This function computes only the *positions* without accessing the data,
    which is useful when you need indices for slicing the original array
    (e.g., for date lookup or forward window extraction).

    Args:
        series_length: Length of the source series.
        window_size: Window length.
        stride: Step between consecutive windows.

    Returns:
        List of (start_idx, end_idx) tuples. end_idx is exclusive
        (Python slice convention: series[start:end]).
    """
    n_windows = (series_length - window_size) // stride + 1
    return [(i * stride, i * stride + window_size) for i in range(n_windows)]


# ---------------------------------------------------------------------------
# Multi-scale search support
# ---------------------------------------------------------------------------
# The core idea: if the query is 30 bars long, also search for 15-bar and
# 60-bar windows. The same fractal/self-similar pattern may appear at
# different speeds in different market regimes.

# Default scale multipliers applied to the base query length.
# 0.5 → half-length (faster playback of the pattern)
# 1.0 → same length (standard matching)
# 2.0 → double-length (slower playback of the pattern)
DEFAULT_SCALE_FACTORS = [0.5, 0.75, 1.0, 1.5, 2.0]


@dataclass
class MultiScaleWindow:
    """A candidate window at a specific time scale.

    Carries the scale metadata alongside the index range so the scorer
    can account for time-stretching when comparing against the query.
    """

    start_idx: int  # Start position in the original series
    end_idx: int  # End position (exclusive) in the original series
    scale: float  # Multiplier relative to base query length
    window_size: int  # Actual number of bars in this window


def multi_scale_indices(
    series_length: int,
    base_window_size: int,
    scales: list[float] | None = None,
    stride: int = 1,
) -> list[MultiScaleWindow]:
    """Generate window indices at multiple time scales.

    For each scale factor, computes the scaled window size and generates
    sliding window positions at that size. Windows that would exceed the
    series length are silently skipped.

    This is the mechanism that enables cross-scale pattern discovery:
    a query that was 30 bars long will also be searched as 15-bar and
    60-bar patterns. The similarity methods (especially DTW) can handle
    the length mismatch via alignment or resampling.

    Args:
        series_length: Length of the source series.
        base_window_size: Reference window size (typically len(query)).
        scales: Scale multipliers. Defaults to [0.5, 0.75, 1.0, 1.5, 2.0].
        stride: Step between windows (applied independently per scale).

    Returns:
        List of MultiScaleWindow objects across all valid scales, ordered
        by scale then by position within each scale.
    """
    if scales is None:
        scales = DEFAULT_SCALE_FACTORS

    results: list[MultiScaleWindow] = []
    for scale in scales:
        # Compute the actual window size at this scale, with a floor of 2
        # (a 1-bar window is degenerate for all similarity methods).
        ws = max(2, int(round(base_window_size * scale)))

        # Skip scales that produce windows longer than the available data
        if ws > series_length:
            continue

        # Generate standard sliding window positions at this scale
        for start, end in window_indices(series_length, ws, stride):
            results.append(
                MultiScaleWindow(
                    start_idx=start,
                    end_idx=end,
                    scale=scale,
                    window_size=ws,
                )
            )
    return results
