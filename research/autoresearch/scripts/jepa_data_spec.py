"""JEPA data specification: load, window, and split time-series data.

This module provides the data pipeline for JEPA training experiments.
It converts raw parquet price series into windowed numpy arrays suitable
for self-supervised encoder training.

Lifecycle:
  1. ``build_jepa_dataset()`` loads one or more dataset names, extracts
     the close-price column, z-normalises per-window, and returns a
     3-D array ``(n_windows, n_channels, window_size)``.
  2. ``temporal_split()`` partitions windows by index into train / val / test
     sets respecting temporal order (no look-ahead).

Immutability:
  - The returned arrays are plain numpy; callers may wrap them in tensors.
  - ``build_jepa_dataset`` is deterministic for the same inputs.

Array dimensionality:
  - Output shape: ``(N, C, W)`` where C=1 for univariate price data
    and W is the sliding-window length.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import numpy as np

# Repo root resolved relative to this file (three parents up from scripts/)
REPO_ROOT = Path(__file__).resolve().parents[3]

# Canonical dataset paths keyed by short name
DATASET_PATHS: dict[str, str] = {
    "spy": "the-similarity-data/data/stocks/spy/1d.parquet",
    "btc_usdt": "the-similarity-data/data/crypto/btc_usdt/1d.parquet",
}


class JEPADataset(NamedTuple):
    """Container returned by ``build_jepa_dataset``.

    Attributes:
        windows: float32 array of shape ``(n_windows, 1, window_size)``.
        dataset_names: list of dataset short names that contributed windows.
        window_offsets: int array of shape ``(n_windows,)`` — global offset
            within the concatenated price vector where each window starts.
    """

    windows: np.ndarray
    dataset_names: list[str]
    window_offsets: np.ndarray


class TemporalSplits(NamedTuple):
    """Train / val / test index arrays from ``temporal_split``."""

    train_idx: np.ndarray
    val_idx: np.ndarray
    test_idx: np.ndarray


def _load_close_prices(dataset_name: str) -> np.ndarray:
    """Load the close-price column from a parquet file.

    Falls back to the first numeric column if 'close' is not found.
    Returns a 1-D float64 array.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError("pandas is required for parquet loading") from exc

    path = REPO_ROOT / DATASET_PATHS[dataset_name]
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    df = pd.read_parquet(path)
    # Try common column names for close price
    for col in ("close", "Close", "adj_close", "Adj Close"):
        if col in df.columns:
            return df[col].dropna().values.astype(np.float64)
    # Fallback: first numeric column
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) == 0:
        raise ValueError(f"No numeric columns in {path}")
    return df[numeric_cols[0]].dropna().values.astype(np.float64)


def build_jepa_dataset(
    dataset_names: list[str],
    window_size: int = 60,
    stride: int = 1,
) -> JEPADataset:
    """Build a windowed dataset from one or more named price series.

    Each window is independently z-normalised (mean=0, std=1) so that the
    encoder learns shape rather than level.  Windows with zero variance
    (constant price) are dropped.

    Parameters:
        dataset_names: short names present in ``DATASET_PATHS``.
        window_size: number of bars per window.
        stride: step size between consecutive windows (default 1).

    Returns:
        A ``JEPADataset`` namedtuple.

    Raises:
        KeyError: if a dataset name is not in ``DATASET_PATHS``.
        FileNotFoundError: if the parquet file is missing.
    """
    all_windows: list[np.ndarray] = []
    all_offsets: list[int] = []
    global_offset = 0  # tracks position in the concatenated series

    for name in dataset_names:
        prices = _load_close_prices(name)
        n_windows = max(0, (len(prices) - window_size) // stride + 1)

        for i in range(n_windows):
            start = i * stride
            window = prices[start : start + window_size].copy()
            std = window.std()
            if std < 1e-12:
                # Skip constant windows — they carry no shape information
                continue
            # Z-normalise: zero mean, unit variance
            window = (window - window.mean()) / std
            all_windows.append(window)
            all_offsets.append(global_offset + start)

        global_offset += len(prices)

    if not all_windows:
        raise ValueError("No valid windows produced from the given datasets")

    # Shape: (n_windows, 1, window_size) — single channel for univariate data
    stacked = np.stack(all_windows, axis=0).astype(np.float32)[:, np.newaxis, :]
    offsets = np.array(all_offsets, dtype=np.int64)
    return JEPADataset(windows=stacked, dataset_names=list(dataset_names), window_offsets=offsets)


def build_jepa_dataset_from_array(
    prices: np.ndarray,
    window_size: int = 60,
    stride: int = 1,
    dataset_name: str = "synthetic",
) -> JEPADataset:
    """Build a windowed dataset from a raw 1-D price array.

    Same z-normalisation and windowing logic as ``build_jepa_dataset``
    but accepts an in-memory array directly.  Useful for tests and
    synthetic data experiments.
    """
    all_windows: list[np.ndarray] = []
    all_offsets: list[int] = []
    n_windows = max(0, (len(prices) - window_size) // stride + 1)

    for i in range(n_windows):
        start = i * stride
        window = prices[start : start + window_size].copy().astype(np.float64)
        std = window.std()
        if std < 1e-12:
            continue
        window = (window - window.mean()) / std
        all_windows.append(window)
        all_offsets.append(start)

    if not all_windows:
        raise ValueError("No valid windows produced from the given array")

    stacked = np.stack(all_windows, axis=0).astype(np.float32)[:, np.newaxis, :]
    offsets = np.array(all_offsets, dtype=np.int64)
    return JEPADataset(windows=stacked, dataset_names=[dataset_name], window_offsets=offsets)


def temporal_split(
    n_windows: int,
    train_frac: float = 0.7,
    val_frac: float = 0.15,
) -> TemporalSplits:
    """Split window indices temporally into train / val / test.

    The split is purely positional — the first ``train_frac`` fraction of
    indices goes to train, the next ``val_frac`` to validation, and the
    remainder to test.  This ensures no future data leaks into training.

    Parameters:
        n_windows: total number of windows.
        train_frac: proportion for training (default 0.7).
        val_frac: proportion for validation (default 0.15).

    Returns:
        A ``TemporalSplits`` namedtuple of index arrays.
    """
    assert 0 < train_frac < 1, "train_frac must be in (0, 1)"
    assert 0 < val_frac < 1, "val_frac must be in (0, 1)"
    assert train_frac + val_frac < 1, "train + val must leave room for test"

    train_end = int(n_windows * train_frac)
    val_end = int(n_windows * (train_frac + val_frac))

    return TemporalSplits(
        train_idx=np.arange(0, train_end),
        val_idx=np.arange(train_end, val_end),
        test_idx=np.arange(val_end, n_windows),
    )
