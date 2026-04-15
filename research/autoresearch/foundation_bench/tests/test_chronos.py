"""Tests for the Chronos adapter — interface + fallback contract."""
from __future__ import annotations

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import ForecastAdapter
from research.autoresearch.foundation_bench.adapters.chronos import ChronosAdapter


def _history(n: int = 500, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.015, size=n)))


def test_adheres_to_protocol():
    assert isinstance(ChronosAdapter(seed=1), ForecastAdapter)


def test_fallback_fires_in_offline_env():
    res = ChronosAdapter(seed=1).predict_quantiles(_history(), 20, [10, 50, 90])
    assert res.fallback_reason is not None
    assert "chronos" in res.fallback_reason.lower()
    assert res.metadata["mode"] == "synthetic_fallback"


def test_quantile_shape_and_monotonicity():
    res = ChronosAdapter(seed=1).predict_quantiles(_history(), 10, [10, 25, 50, 75, 90])
    assert set(res.quantiles.keys()) == {10, 25, 50, 75, 90}
    ordered = [res.quantiles[p][-1] for p in [10, 25, 50, 75, 90]]
    assert ordered == sorted(ordered)
