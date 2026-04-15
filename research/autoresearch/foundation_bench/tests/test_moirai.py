"""Tests for the Moirai adapter — interface + fallback contract."""
from __future__ import annotations

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import ForecastAdapter
from research.autoresearch.foundation_bench.adapters.moirai import MoiraiAdapter


def _history(n: int = 500, seed: int = 2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, size=n)))


def test_adheres_to_protocol():
    assert isinstance(MoiraiAdapter(seed=1), ForecastAdapter)


def test_fallback_fires_in_offline_env():
    res = MoiraiAdapter(seed=1).predict_quantiles(_history(), 15, [10, 50, 90])
    assert res.fallback_reason is not None
    assert "moirai" in res.fallback_reason.lower() or "uni2ts" in res.fallback_reason.lower()
    assert res.metadata["mode"] == "synthetic_fallback"
    assert res.metadata["cone"] == "ar1_gaussian"


def test_quantile_shape_and_monotonicity():
    res = MoiraiAdapter(seed=1).predict_quantiles(_history(), 8, [10, 25, 50, 75, 90])
    for arr in res.quantiles.values():
        assert arr.shape == (8,)
    ordered = [res.quantiles[p][-1] for p in [10, 25, 50, 75, 90]]
    assert ordered == sorted(ordered)
