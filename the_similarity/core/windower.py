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

    Args:
        series: 1D array of values.
        window_size: Number of elements per window.
        stride: Step between consecutive windows.

    Returns:
        2D array of shape (n_windows, window_size).
    """
    series = np.asarray(series, dtype=np.float64)
    if window_size > len(series):
        raise ValueError(
            f"window_size ({window_size}) > series length ({len(series)})"
        )
    if window_size < 1:
        raise ValueError("window_size must be >= 1")
    if stride < 1:
        raise ValueError("stride must be >= 1")

    n_windows = (len(series) - window_size) // stride + 1
    shape = (n_windows, window_size)
    strides = (series.strides[0] * stride, series.strides[0])
    return np.lib.stride_tricks.as_strided(series, shape=shape, strides=strides).copy()


def window_indices(
    series_length: int,
    window_size: int,
    stride: int = 1,
) -> list[tuple[int, int]]:
    """Return (start, end) index pairs for each window.

    Args:
        series_length: Length of the source series.
        window_size: Window size.
        stride: Step between windows.

    Returns:
        List of (start_idx, end_idx) tuples. end_idx is exclusive.
    """
    n_windows = (series_length - window_size) // stride + 1
    return [(i * stride, i * stride + window_size) for i in range(n_windows)]


# --- Multi-scale support ---

DEFAULT_SCALE_FACTORS = [0.5, 0.75, 1.0, 1.5, 2.0]


@dataclass
class MultiScaleWindow:
    """A window at a specific scale."""
    start_idx: int
    end_idx: int
    scale: float          # multiplier relative to base window size
    window_size: int      # actual number of bars in this window


def multi_scale_indices(
    series_length: int,
    base_window_size: int,
    scales: list[float] | None = None,
    stride: int = 1,
) -> list[MultiScaleWindow]:
    """Generate window indices at multiple scales.

    For fractal pattern matching, the same pattern may appear at
    different time scales. This generates candidate windows at
    several multiples of the base window size.

    Args:
        series_length: Length of the source series.
        base_window_size: Reference window size (typically len(query)).
        scales: Scale multipliers. Default: [0.5, 0.75, 1.0, 1.5, 2.0].
        stride: Step between windows (applied per-scale).

    Returns:
        List of MultiScaleWindow across all scales.
    """
    if scales is None:
        scales = DEFAULT_SCALE_FACTORS

    results: list[MultiScaleWindow] = []
    for scale in scales:
        ws = max(2, int(round(base_window_size * scale)))
        if ws > series_length:
            continue
        for start, end in window_indices(series_length, ws, stride):
            results.append(MultiScaleWindow(
                start_idx=start,
                end_idx=end,
                scale=scale,
                window_size=ws,
            ))
    return results
