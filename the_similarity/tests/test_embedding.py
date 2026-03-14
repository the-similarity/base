from __future__ import annotations

import numpy as np
import pytest

from the_similarity.core.embedding import auto_dim, auto_lag, delay_embed


# ---------- delay_embed ----------


def test_delay_embed_shape():
    """Output shape matches (n - (d-1)*tau, d)."""
    n, dim, lag = 100, 5, 3
    series = np.random.default_rng(0).standard_normal(n)
    embedded = delay_embed(series, dim, lag)
    expected_rows = n - (dim - 1) * lag
    assert embedded.shape == (expected_rows, dim)


def test_delay_embed_values():
    """Verify actual values match manual construction."""
    series = np.arange(20, dtype=np.float64)
    dim, lag = 3, 2
    embedded = delay_embed(series, dim, lag)

    # Row 0 corresponds to t = (dim-1)*lag = 4
    # Row 0: [x(4), x(4-2), x(4-4)] = [4, 2, 0]
    np.testing.assert_array_equal(embedded[0], [4, 2, 0])

    # Row 1: [x(5), x(3), x(1)]
    np.testing.assert_array_equal(embedded[1], [5, 3, 1])

    # Last row: t = 19 -> [19, 17, 15]
    np.testing.assert_array_equal(embedded[-1], [19, 17, 15])


# ---------- auto_lag ----------


def test_auto_lag_sine():
    """Sine wave -> lag approx period/4 (within +/-3)."""
    period = 20
    t = np.arange(500, dtype=np.float64)
    series = np.sin(2 * np.pi * t / period)
    lag = auto_lag(series)
    expected = period // 4  # 5
    assert abs(lag - expected) <= 3, f"lag={lag}, expected ~{expected}"


def test_auto_lag_short_series():
    """Series of length 10 -> returns valid lag >= 1."""
    series = np.random.default_rng(7).standard_normal(10)
    lag = auto_lag(series)
    assert lag >= 1
    assert lag <= len(series) // 4 or lag == 1


# ---------- auto_dim ----------


def test_auto_dim_returns_reasonable():
    """Random walk -> dim in [2, 15]."""
    rng = np.random.default_rng(42)
    series = np.cumsum(rng.standard_normal(500))
    lag = auto_lag(series)
    dim = auto_dim(series, lag)
    assert 2 <= dim <= 15, f"dim={dim} out of expected range"
