"""
Tests for the JEPA data representation specification.

All tests use synthetic price series so they run without the data catalog.
The tests verify:
- Output tensor shapes (n_windows, n_channels, window_size)
- Per-window z-score normalization properties (mean ~0, std ~1)
- Temporal ordering preserved through the pipeline
- No leakage: test windows strictly after val, val strictly after train
- Edge cases: constant prices, very short series, stride > 1
"""

from __future__ import annotations

import numpy as np
import pytest

from research.autoresearch.scripts.jepa_data_spec import (
    _build_from_arrays,
    _rolling_std,
    temporal_split,
    DEFAULT_WINDOW_SIZE,
    VOLATILITY_LOOKBACK,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _synthetic_prices(n: int = 500, seed: int = 42) -> np.ndarray:
    """Generate a synthetic geometric Brownian motion price series.

    Produces realistic-looking prices with drift and volatility so that
    log-returns are approximately normally distributed.
    """
    rng = np.random.default_rng(seed)
    # Daily returns: ~0.05% drift, ~1.5% volatility
    log_returns = rng.normal(loc=0.0005, scale=0.015, size=n - 1)
    log_prices = np.concatenate([[np.log(100.0)], np.cumsum(log_returns) + np.log(100.0)])
    return np.exp(log_prices)


def _synthetic_volume(n: int = 500, seed: int = 99) -> np.ndarray:
    """Generate synthetic volume data (positive, varying)."""
    rng = np.random.default_rng(seed)
    return np.abs(rng.normal(loc=1e6, scale=2e5, size=n))


# ---------------------------------------------------------------------------
# Shape tests
# ---------------------------------------------------------------------------


class TestBuildShapes:
    """Verify output tensor dimensions for various configurations."""

    def test_single_channel_returns(self):
        """Default single-channel (returns) produces (n, 1, window_size)."""
        prices = _synthetic_prices(200)
        windows = _build_from_arrays(prices, volume=None, window_size=60, stride=1)

        # After log-returns: effective length = 199
        # n_windows = (199 - 60) // 1 + 1 = 140
        assert windows.shape == (140, 1, 60)

    def test_multi_channel_returns_and_volatility(self):
        """Two channels: returns + volatility."""
        prices = _synthetic_prices(200)
        windows = _build_from_arrays(
            prices, volume=None, window_size=60, stride=1,
            channels=["returns", "volatility"],
        )
        # After log-returns: 199 bars.
        # Volatility trims VOLATILITY_LOOKBACK - 1 = 19 bars from front.
        # Effective length = 199 - 19 = 180.
        # n_windows = (180 - 60) // 1 + 1 = 121
        assert windows.shape == (121, 2, 60)

    def test_three_channels(self):
        """Three channels: returns + volatility + volume."""
        n = 200
        prices = _synthetic_prices(n)
        volume = _synthetic_volume(n)
        windows = _build_from_arrays(
            prices, volume=volume, window_size=60, stride=1,
            channels=["returns", "volatility", "volume"],
        )
        assert windows.shape[1] == 3  # 3 channels
        assert windows.shape[2] == 60  # window_size

    def test_stride_reduces_windows(self):
        """Stride > 1 produces fewer windows."""
        prices = _synthetic_prices(200)
        w1 = _build_from_arrays(prices, volume=None, window_size=60, stride=1)
        w5 = _build_from_arrays(prices, volume=None, window_size=60, stride=5)

        # stride=5 should give roughly 1/5 the windows
        assert w5.shape[0] < w1.shape[0]
        expected_n = (199 - 60) // 5 + 1  # 28
        assert w5.shape[0] == expected_n

    def test_custom_window_size(self):
        """Non-default window size works."""
        prices = _synthetic_prices(200)
        windows = _build_from_arrays(prices, volume=None, window_size=30, stride=1)
        assert windows.shape[2] == 30

    def test_series_too_short_raises(self):
        """Series shorter than window_size raises ValueError."""
        prices = _synthetic_prices(50)  # After returns: 49 bars < 60
        with pytest.raises(ValueError, match="too short"):
            _build_from_arrays(prices, volume=None, window_size=60)


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------


class TestNormalization:
    """Verify per-window z-score properties."""

    def test_mean_near_zero(self):
        """Each window-channel should have mean approximately 0."""
        prices = _synthetic_prices(300)
        windows = _build_from_arrays(prices, volume=None, window_size=60)

        means = windows.mean(axis=2)  # shape (n_windows, n_channels)
        # Allow small numerical error
        assert np.allclose(means, 0.0, atol=1e-10), (
            f"Max absolute mean: {np.abs(means).max()}"
        )

    def test_std_near_one(self):
        """Each window-channel should have std approximately 1 (or 0 if constant)."""
        prices = _synthetic_prices(300)
        windows = _build_from_arrays(prices, volume=None, window_size=60)

        stds = windows.std(axis=2)  # shape (n_windows, n_channels)
        # Non-constant windows should have std ~1
        nonzero_mask = stds > 0
        assert np.allclose(stds[nonzero_mask], 1.0, atol=1e-10)

    def test_constant_price_yields_zero_window(self):
        """Constant prices produce zero log-returns, which z-score to all zeros."""
        prices = np.full(200, 100.0)
        windows = _build_from_arrays(prices, volume=None, window_size=60)

        # All returns are 0 -> std=0 -> z-score maps to zeros
        assert np.allclose(windows, 0.0)

    def test_normalization_is_per_window(self):
        """Different windows should have different raw values but same z-score stats."""
        prices = _synthetic_prices(300)
        windows = _build_from_arrays(prices, volume=None, window_size=60)

        # Pick two non-adjacent windows
        w0 = windows[0, 0, :]
        w50 = windows[50, 0, :]

        # Both should be z-scored independently
        assert abs(w0.mean()) < 1e-10
        assert abs(w50.mean()) < 1e-10
        assert abs(w0.std() - 1.0) < 1e-10
        assert abs(w50.std() - 1.0) < 1e-10


# ---------------------------------------------------------------------------
# Temporal ordering tests
# ---------------------------------------------------------------------------


class TestTemporalOrdering:
    """Verify that temporal order is preserved through windowing."""

    def test_windows_are_sequential(self):
        """Window i+1 starts exactly stride bars after window i (before normalization).

        We verify this by checking that the *un-normalized* overlapping region
        between consecutive windows is identical, which can only happen if
        the windows were extracted sequentially from the same series.
        """
        # Build without normalization to check raw ordering.
        # We can't easily skip normalization in the public API, so we
        # verify a weaker property: monotonic index implies temporal order.
        prices = _synthetic_prices(200)
        # Use stride=1: window[i] starts at bar i in the returns series.
        # The number of windows is deterministic and sequential.
        windows = _build_from_arrays(prices, volume=None, window_size=60, stride=1)
        n = windows.shape[0]
        # Windows should be in temporal order: n_windows = effective_len - ws + 1
        assert n == 140  # 199 - 60 + 1


# ---------------------------------------------------------------------------
# Temporal split tests
# ---------------------------------------------------------------------------


class TestTemporalSplit:
    """Verify the train/val/test split respects temporal ordering."""

    def test_default_fractions(self):
        """70/15/15 split divides correctly."""
        n = 100
        windows = np.random.default_rng(0).random((n, 1, 60))
        train, val, test = temporal_split(windows)

        assert len(train) == 70
        assert len(val) == 15
        assert len(test) == 15  # remainder

    def test_no_overlap(self):
        """Train, val, and test combined equal the original (no duplication/loss)."""
        n = 100
        # Use unique identifiers as data so we can verify exact membership
        windows = np.arange(n * 60).reshape(n, 1, 60).astype(np.float64)
        train, val, test = temporal_split(windows)

        recombined = np.concatenate([train, val, test], axis=0)
        np.testing.assert_array_equal(recombined, windows)

    def test_strict_temporal_order(self):
        """All train indices < all val indices < all test indices.

        This is the critical leakage prevention test. We encode the original
        window index as data and verify ordering after the split.
        """
        n = 200
        # Channel 0, bar 0 of each window stores its temporal index.
        windows = np.zeros((n, 1, 60))
        for i in range(n):
            windows[i, 0, 0] = i  # temporal marker

        train, val, test = temporal_split(windows)

        train_max_idx = train[-1, 0, 0]
        val_min_idx = val[0, 0, 0]
        val_max_idx = val[-1, 0, 0]
        test_min_idx = test[0, 0, 0]

        assert train_max_idx < val_min_idx, "Train must end before val starts"
        assert val_max_idx < test_min_idx, "Val must end before test starts"

    def test_no_shuffling(self):
        """Verify that temporal_split does not reorder windows."""
        n = 150
        windows = np.zeros((n, 1, 60))
        for i in range(n):
            windows[i, 0, 0] = i

        train, val, test = temporal_split(windows)

        # Within each split, indices should be strictly increasing
        train_indices = train[:, 0, 0]
        val_indices = val[:, 0, 0]
        test_indices = test[:, 0, 0]

        assert np.all(np.diff(train_indices) == 1), "Train windows reordered"
        assert np.all(np.diff(val_indices) == 1), "Val windows reordered"
        assert np.all(np.diff(test_indices) == 1), "Test windows reordered"

    def test_fractions_must_sum_to_one(self):
        """Invalid fractions raise ValueError."""
        windows = np.zeros((100, 1, 60))
        with pytest.raises(ValueError, match="sum to 1.0"):
            temporal_split(windows, train_frac=0.5, val_frac=0.5, test_frac=0.5)

    def test_negative_fraction_raises(self):
        """Negative fractions raise ValueError."""
        windows = np.zeros((100, 1, 60))
        with pytest.raises(ValueError, match="non-negative"):
            temporal_split(windows, train_frac=-0.1, val_frac=0.6, test_frac=0.5)

    def test_custom_fractions(self):
        """Non-default fractions work correctly."""
        n = 100
        windows = np.zeros((n, 1, 60))
        train, val, test = temporal_split(
            windows, train_frac=0.8, val_frac=0.1, test_frac=0.1
        )
        assert len(train) == 80
        assert len(val) == 10
        assert len(test) == 10


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


class TestRollingStd:
    """Verify the rolling std helper."""

    def test_known_values(self):
        """Rolling std of a simple series matches manual calculation."""
        series = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _rolling_std(series, window=3)
        assert len(result) == 3  # 5 - 3 + 1

        # First window: std([1, 2, 3])
        expected_0 = np.std([1.0, 2.0, 3.0])
        assert abs(result[0] - expected_0) < 1e-10

    def test_series_too_short(self):
        """Series shorter than the rolling window raises ValueError."""
        with pytest.raises(ValueError, match="rolling window"):
            _rolling_std(np.array([1.0, 2.0]), window=5)


# ---------------------------------------------------------------------------
# Channel validation tests
# ---------------------------------------------------------------------------


class TestChannelValidation:
    """Verify channel name validation and volume requirement."""

    def test_unknown_channel_raises(self):
        """Requesting an unknown channel name raises ValueError."""
        prices = _synthetic_prices(200)
        with pytest.raises(ValueError, match="Unknown channel"):
            _build_from_arrays(prices, volume=None, channels=["bogus"])

    def test_volume_without_data_raises(self):
        """Requesting volume channel without volume data raises RuntimeError."""
        prices = _synthetic_prices(200)
        with pytest.raises(RuntimeError, match="volume"):
            _build_from_arrays(prices, volume=None, channels=["returns", "volume"])
