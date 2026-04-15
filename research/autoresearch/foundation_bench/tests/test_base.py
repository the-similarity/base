"""Tests for the adapter base protocol and fallback helpers."""
from __future__ import annotations

import numpy as np
import pytest

from research.autoresearch.foundation_bench.adapters.base import (
    ForecastAdapter,
    ForecastResult,
    ar1_cone,
    bootstrap_residual_cone,
)


def _make_history(n: int = 400, seed: int = 0) -> np.ndarray:
    """Deterministic log-return price path for fallback tests."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0005, 0.01, size=n)
    return 100.0 * np.exp(np.cumsum(returns))


class _DummyAdapter:
    """Minimal class that satisfies the ``ForecastAdapter`` protocol."""

    name = "dummy"

    def predict_quantiles(self, history, forward_bars, percentiles):
        quantiles = ar1_cone(history, forward_bars, percentiles, seed=0)
        return ForecastResult(quantiles=quantiles, fallback_reason="dummy")


def test_protocol_is_runtime_checkable():
    # Structural check: the dummy adapter satisfies the protocol without inheritance.
    assert isinstance(_DummyAdapter(), ForecastAdapter)


def test_ar1_cone_returns_correct_shapes():
    history = _make_history()
    percentiles = [10, 25, 50, 75, 90]
    q = ar1_cone(history, forward_bars=30, percentiles=percentiles)
    assert set(q.keys()) == set(percentiles)
    for p, arr in q.items():
        assert arr.shape == (30,)


def test_ar1_cone_is_monotone_across_percentiles():
    # For every bar, quantile values must be non-decreasing in p.
    history = _make_history()
    percentiles = [10, 25, 50, 75, 90]
    q = ar1_cone(history, forward_bars=15, percentiles=percentiles)
    stacked = np.stack([q[p] for p in percentiles], axis=0)
    diffs = np.diff(stacked, axis=0)
    # Allow a tiny epsilon tolerance for floating point symmetry.
    assert np.all(diffs >= -1e-9)


def test_bootstrap_residual_cone_matches_shape_and_monotonicity():
    history = _make_history(seed=7)
    percentiles = [10, 50, 90]
    q = bootstrap_residual_cone(
        history, forward_bars=10, percentiles=percentiles, n_paths=50, seed=1
    )
    assert set(q.keys()) == set(percentiles)
    for p, arr in q.items():
        assert arr.shape == (10,)
    # Monotone in percentile at terminal bar.
    assert q[10][-1] <= q[50][-1] <= q[90][-1]


def test_forecast_result_preserves_fallback_reason():
    q = ar1_cone(_make_history(), forward_bars=5, percentiles=[10, 50, 90])
    res = ForecastResult(quantiles=q, fallback_reason="unit test")
    assert res.fallback_reason == "unit test"
    assert set(res.quantiles.keys()) == {10, 50, 90}


def test_ar1_cone_handles_short_history():
    # Short history used to crash; must now return finite arrays.
    history = np.array([100.0, 101.0, 102.0, 101.5], dtype=np.float64)
    q = ar1_cone(history, forward_bars=5, percentiles=[10, 50, 90])
    for arr in q.values():
        assert np.all(np.isfinite(arr))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
