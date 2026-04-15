"""Tests for the TimesFM adapter — interface + fallback contract."""
from __future__ import annotations

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import ForecastAdapter
from research.autoresearch.foundation_bench.adapters.timesfm import TimesFMAdapter


def _history(n: int = 600, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, size=n)))


def test_adheres_to_protocol():
    assert isinstance(TimesFMAdapter(seed=1), ForecastAdapter)


def test_fallback_fires_in_offline_env():
    # Environment has no timesfm / transformers installed, so every call
    # MUST return fallback_reason != None.
    res = TimesFMAdapter(seed=1).predict_quantiles(_history(), 20, [10, 50, 90])
    assert res.fallback_reason is not None
    assert "timesfm" in res.fallback_reason.lower()
    assert res.metadata["mode"] == "synthetic_fallback"


def test_quantile_shape_and_monotonicity():
    res = TimesFMAdapter(seed=1).predict_quantiles(_history(), 15, [10, 25, 50, 75, 90])
    assert set(res.quantiles.keys()) == {10, 25, 50, 75, 90}
    for arr in res.quantiles.values():
        assert arr.shape == (15,)
    # Terminal-bar monotonicity by percentile.
    ordered = [res.quantiles[p][-1] for p in [10, 25, 50, 75, 90]]
    assert ordered == sorted(ordered)
