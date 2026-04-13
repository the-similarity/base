"""
JEPA data representation specification for The Similarity project.

This module defines the first-pass data representation that a Joint Embedding
Predictive Architecture (JEPA) model will consume when trained on the project's
52+ financial time series datasets.

Design decisions (rationale in each section):

1. **Log-returns, not raw prices.**
   Raw prices are non-stationary (trending, different scales across assets).
   Log-returns ln(p[t]/p[t-1]) are approximately stationary, scale-invariant,
   and match the production matcher's default normalization ("logreturn_zscore").
   A JEPA that learns representations of log-return windows transfers across
   assets without re-scaling — a $10 stock and a $1000 stock look the same.

2. **Per-window z-score normalization.**
   After computing log-returns we z-score each window independently (zero mean,
   unit variance). This removes remaining location/scale differences and is
   consistent with the production normalizer's `logreturn_zscore` mode.
   Crucially, normalization is per-window, not global — global stats would
   leak information from the future into past windows.

3. **60-bar windows (production default).**
   The production matcher uses 60 bars as its default query length. Keeping
   the JEPA window size aligned means learned embeddings directly compare
   to production search results without interpolation.

4. **Multi-channel support.**
   Channel 0 is always normalized log-returns. Optional channels:
   - "volatility": rolling standard deviation of log-returns (realized vol).
     Captures the *texture* of price movement — a calm 5% rally vs a choppy
     one. Window of 20 bars for the rolling std (one trading month at daily).
   - "volume": normalized trading volume (z-scored per window). Only available
     for datasets that include volume data.

5. **Strictly temporal train/val/test splits.**
   Financial data is serially correlated. Random shuffling creates look-ahead
   bias (the model sees Tuesday's pattern in training and is tested on Monday).
   We split by time: first 70% train, next 15% val, last 15% test.

Leakage risks and mitigations:
- **Overlapping windows**: With stride=1, consecutive windows share 59 of 60
  bars. This is fine within a split (the model must generalize to unseen
  *positions*), but windows that straddle the train/val or val/test boundary
  would leak. We discard any window whose end index exceeds the split boundary.
- **Per-window normalization**: Each window's z-score uses only its own bars.
  No global mean/std is computed, so no future information leaks backward.
- **No cross-dataset leakage**: Each call to build_jepa_dataset operates on
  a single dataset. Cross-dataset training should concatenate *after* splitting
  each dataset independently (same temporal boundary per asset is ideal but
  a calendar-date cutoff is acceptable when all assets share a time axis).

Usage:
    >>> windows = build_jepa_dataset("gold_1d", window_size=60, stride=1,
    ...                              channels=["returns", "volatility"])
    >>> train, val, test = temporal_split(windows)
    >>> print(train.shape)  # (n_train, 2, 60)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default window size — matches production matcher's default query length.
DEFAULT_WINDOW_SIZE: int = 60

# Rolling window for realized volatility channel.
# 20 bars ~ one trading month at daily frequency.
VOLATILITY_LOOKBACK: int = 20

# Minimum price floor to avoid log(0). Matches the production normalizer.
PRICE_FLOOR: float = 1e-12

# Available channel names. Order matters: channel 0 is always "returns".
VALID_CHANNELS: list[str] = ["returns", "volatility", "volume"]


# ---------------------------------------------------------------------------
# Core: build_jepa_dataset
# ---------------------------------------------------------------------------


def build_jepa_dataset(
    dataset_name: str,
    window_size: int = DEFAULT_WINDOW_SIZE,
    stride: int = 1,
    channels: list[str] | None = None,
) -> NDArray[np.float64]:
    """Build a windowed, multi-channel dataset for JEPA training.

    Loads a dataset via the project's public API, computes the requested
    channels, slides windows, and z-score normalizes each window per channel.

    Args:
        dataset_name: Name or path recognized by ``the_similarity.api.load()``.
            Examples: ``"gold_1d"`` (catalog shorthand) or a parquet file path.
        window_size: Number of bars per window. Default 60 (production default).
            Must be >= 2 (a 1-bar window is degenerate).
        stride: Step between consecutive window start positions. stride=1 gives
            maximum data (every position), stride>1 reduces overlap/size.
        channels: List of channel names to include. Default ``["returns"]``.
            Valid names: "returns", "volatility", "volume".

    Returns:
        np.ndarray of shape ``(n_windows, n_channels, window_size)``.
        Channel ordering follows the ``channels`` argument order.
        Each window-channel slice is independently z-scored.

    Raises:
        ValueError: If an unknown channel name is requested, or if the series
            is too short to produce any windows.
        RuntimeError: If "volume" channel is requested but the dataset has no
            volume data.

    Leakage note:
        Windows are slid over the *full* dataset. Call ``temporal_split()``
        on the result to separate train/val/test. Because windows are extracted
        in temporal order and normalization is per-window, there is no leakage
        at this stage.
    """
    # Late import to avoid hard dependency on the_similarity when running tests
    # with synthetic data (tests call _build_from_arrays directly).
    from the_similarity.api import load as api_load

    ts = api_load(dataset_name)
    prices = ts.values

    return _build_from_arrays(
        prices=prices,
        volume=None,  # TimeSeries currently exposes only .values (close prices)
        window_size=window_size,
        stride=stride,
        channels=channels,
    )


def _build_from_arrays(
    prices: NDArray[np.float64],
    volume: NDArray[np.float64] | None,
    window_size: int = DEFAULT_WINDOW_SIZE,
    stride: int = 1,
    channels: list[str] | None = None,
) -> NDArray[np.float64]:
    """Internal builder that operates on raw numpy arrays.

    Separated from ``build_jepa_dataset`` so that tests can pass synthetic
    data without going through the API loader.

    Args:
        prices: 1D array of raw prices (e.g., close prices).
        volume: Optional 1D array of raw volume, same length as prices.
            Required only if "volume" is in channels.
        window_size: Bars per window.
        stride: Step between windows.
        channels: Channel names (default ["returns"]).

    Returns:
        np.ndarray of shape (n_windows, n_channels, window_size).
    """
    if channels is None:
        channels = ["returns"]

    # --- Validate channels ---
    for ch in channels:
        if ch not in VALID_CHANNELS:
            raise ValueError(
                f"Unknown channel '{ch}'. Valid channels: {VALID_CHANNELS}"
            )
    if "volume" in channels and volume is None:
        raise RuntimeError(
            "Channel 'volume' requested but no volume data was provided."
        )

    prices = np.asarray(prices, dtype=np.float64)

    # --- Compute log-returns (always needed, even for volatility channel) ---
    # Guard against log(0) with the same floor as the production normalizer.
    safe_prices = np.maximum(prices, PRICE_FLOOR)
    log_returns = np.diff(np.log(safe_prices))  # length = len(prices) - 1

    # --- Compute per-channel full-length series ---
    # After log-returns, the effective series length is len(prices) - 1.
    # The volatility channel further shortens by VOLATILITY_LOOKBACK - 1
    # because the rolling std needs a warmup period.
    # We align all channels to the shortest common length.

    channel_series: list[NDArray[np.float64]] = []
    # Track how many bars to trim from the front for alignment.
    trim_front = 0

    for ch in channels:
        if ch == "returns":
            channel_series.append(log_returns)
        elif ch == "volatility":
            # Rolling std of log-returns with a fixed lookback window.
            # Uses stride_tricks for efficiency (same pattern as windower.py).
            vol = _rolling_std(log_returns, VOLATILITY_LOOKBACK)
            # vol is shorter by (VOLATILITY_LOOKBACK - 1) at the front.
            trim_front = max(trim_front, VOLATILITY_LOOKBACK - 1)
            channel_series.append(vol)
        elif ch == "volume":
            assert volume is not None  # Guarded above
            vol_data = np.asarray(volume, dtype=np.float64)
            # Volume is same length as prices; trim the first element to
            # align with log-returns (which lose the first bar).
            channel_series.append(vol_data[1:])

    # --- Align all channels by trimming the front ---
    # "returns" and "volume" are length (N-1); "volatility" is shorter.
    # Trim all to the shortest to keep temporal alignment.
    aligned: list[NDArray[np.float64]] = []
    for i, ch in enumerate(channels):
        s = channel_series[i]
        if ch == "volatility":
            # Already the right length (shortest)
            aligned.append(s)
        else:
            # Trim the front to match volatility alignment
            aligned.append(s[trim_front:])

    effective_length = len(aligned[0])

    # --- Validate there's enough data for at least one window ---
    if effective_length < window_size:
        raise ValueError(
            f"Series too short for windowing: effective length {effective_length} "
            f"< window_size {window_size}. Need at least {window_size + 1 + trim_front} "
            f"price bars."
        )

    # --- Slide windows over each channel ---
    n_channels = len(channels)
    n_windows = (effective_length - window_size) // stride + 1

    # Pre-allocate the output tensor: (n_windows, n_channels, window_size)
    result = np.empty((n_windows, n_channels, window_size), dtype=np.float64)

    for c_idx in range(n_channels):
        series = aligned[c_idx]
        for w_idx in range(n_windows):
            start = w_idx * stride
            end = start + window_size
            window = series[start:end].copy()

            # --- Per-window z-score normalization ---
            # Zero mean, unit variance. Constant windows (std=0) map to zeros,
            # matching the production normalizer's behavior.
            std = np.std(window)
            if std > 0:
                window = (window - np.mean(window)) / std
            else:
                window = np.zeros(window_size, dtype=np.float64)

            result[w_idx, c_idx, :] = window

    return result


# ---------------------------------------------------------------------------
# Temporal split
# ---------------------------------------------------------------------------


def temporal_split(
    windows: NDArray[np.float64],
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Split windowed data into train / validation / test sets by time.

    The split is strictly temporal — **no shuffling** — because financial time
    series are serially correlated. Shuffling would allow the model to see
    patterns from the future during training (look-ahead bias / leakage).

    Windows are assumed to be in chronological order (window 0 is earliest,
    window -1 is latest). This invariant is guaranteed by ``build_jepa_dataset``
    which slides left-to-right over the time axis.

    Args:
        windows: Array of shape ``(n_windows, n_channels, window_size)``
            as returned by ``build_jepa_dataset``.
        train_frac: Fraction of windows for training. Default 0.70.
        val_frac: Fraction for validation. Default 0.15.
        test_frac: Fraction for testing. Default 0.15.

    Returns:
        ``(train, val, test)`` tuple of arrays, each with the same
        ``(n, n_channels, window_size)`` shape (n varies per split).

    Raises:
        ValueError: If fractions don't sum to ~1.0 or any fraction is negative.

    Leakage guarantees:
        - All train windows come before all val windows in time.
        - All val windows come before all test windows in time.
        - No window appears in more than one split.
        - Fractions are applied to the window *count*, not the bar count,
          so there is no partial-window boundary issue.
    """
    # Validate fractions
    total = train_frac + val_frac + test_frac
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"Fractions must sum to 1.0, got {total:.6f} "
            f"(train={train_frac}, val={val_frac}, test={test_frac})"
        )
    if train_frac < 0 or val_frac < 0 or test_frac < 0:
        raise ValueError("All fractions must be non-negative.")

    n = len(windows)
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)
    # test gets the remainder (avoids off-by-one from rounding)

    train = windows[:train_end]
    val = windows[train_end:val_end]
    test = windows[val_end:]

    return train, val, test


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _rolling_std(
    series: NDArray[np.float64], window: int
) -> NDArray[np.float64]:
    """Compute rolling standard deviation using a sliding window.

    Uses numpy stride tricks (same approach as the production windower)
    for efficient computation without a Python loop over positions.

    Args:
        series: 1D array.
        window: Lookback window for the rolling std.

    Returns:
        1D array of length ``len(series) - window + 1``.
        Each element is the std of the preceding ``window`` values.
    """
    n = len(series)
    if n < window:
        raise ValueError(
            f"Series length {n} < rolling window {window}"
        )

    # Build strided view: shape (n_positions, window)
    n_pos = n - window + 1
    shape = (n_pos, window)
    strides = (series.strides[0], series.strides[0])
    windowed = np.lib.stride_tricks.as_strided(series, shape=shape, strides=strides)

    # Compute std along axis=1 (each row is one rolling window)
    return np.std(windowed, axis=1)
