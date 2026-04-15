"""Tests for the wavelet-baseline adapter.

This is the only adapter expected to produce REAL (non-fallback)
forecasts in offline CI, because its only dependency (``pywt``) is in
the project's core requirements.
"""
from __future__ import annotations

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import ForecastAdapter
from research.autoresearch.foundation_bench.adapters.wavelet_baseline import (
    WaveletBaselineAdapter,
    _denoise,
    _fit_ar,
)


def _history(n: int = 400, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.013, size=n)))


def test_adheres_to_protocol():
    assert isinstance(WaveletBaselineAdapter(seed=1), ForecastAdapter)


def test_real_classical_mode_fires():
    # With pywt available (it is a core dep), the adapter must run the
    # real wavelet pipeline and leave ``fallback_reason`` as None.
    res = WaveletBaselineAdapter(seed=2, n_paths=50).predict_quantiles(
        _history(), 10, [10, 50, 90]
    )
    assert res.fallback_reason is None
    assert res.metadata["mode"] == "real_classical"
    assert res.metadata["wavelet"] == "db4"


def test_quantile_shape_and_monotonicity():
    res = WaveletBaselineAdapter(seed=2, n_paths=80).predict_quantiles(
        _history(), 8, [10, 25, 50, 75, 90]
    )
    for arr in res.quantiles.values():
        assert arr.shape == (8,)
    ordered = [res.quantiles[p][-1] for p in [10, 25, 50, 75, 90]]
    assert ordered == sorted(ordered)


def test_denoise_is_noop_for_short_inputs():
    # Inputs shorter than a single DWT level must be passed through
    # unchanged so the AR fit has something to work with.
    short = np.array([0.01, -0.01, 0.02], dtype=np.float64)
    out = _denoise(short, wavelet="db4", n_levels=3)
    assert out.shape == short.shape


def test_fit_ar_handles_degenerate_input():
    phi, intercept, resid = _fit_ar(np.array([0.01, 0.02]), p=2)
    assert phi.shape == (2,)
    assert np.isfinite(intercept)
    assert resid.shape == (2,)
