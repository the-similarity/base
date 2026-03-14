from __future__ import annotations

import numpy as np
import pytest

from the_similarity.core.regime import hurst_dfa, tag_regime


class TestTagRegime:
    """Tests for the regime tagger."""

    def test_trending_up(self):
        """Persistent uptrend (correlated increments) -> trending_up."""
        np.random.seed(42)
        n = 500
        # Smoothed returns create autocorrelation (high Hurst)
        noise = np.random.normal(0, 1, n)
        kernel = np.ones(10) / 10
        smoothed = np.convolve(noise, kernel, mode="same")
        # Scale so annualized vol lands ~20-30%
        log_ret = 0.003 + smoothed * 0.06
        series = 100.0 * np.exp(np.cumsum(log_ret))
        result = tag_regime(series)
        assert result == "trending_up", f"got {result}"

    def test_trending_down(self):
        """Persistent downtrend (correlated increments) -> trending_down."""
        np.random.seed(42)
        n = 500
        noise = np.random.normal(0, 1, n)
        kernel = np.ones(10) / 10
        smoothed = np.convolve(noise, kernel, mode="same")
        log_ret = -0.003 + smoothed * 0.06
        series = 100.0 * np.exp(np.cumsum(log_ret))
        result = tag_regime(series)
        assert result == "trending_down", f"got {result}"

    def test_mean_reverting(self):
        """Ornstein-Uhlenbeck process -> mean_reverting."""
        np.random.seed(42)
        n = 500
        series = np.empty(n)
        series[0] = 100.0
        # Strong mean reversion with moderate vol
        for i in range(1, n):
            series[i] = series[i - 1] + 0.15 * (100.0 - series[i - 1]) + np.random.normal(0, 1.5)
        assert tag_regime(series) == "mean_reverting"

    def test_high_vol(self):
        """Series with large random jumps -> high_vol."""
        np.random.seed(123)
        # Geometric Brownian motion with very high vol
        log_ret = np.random.normal(0, 0.08, 500)  # ~127% annualized
        series = 100.0 * np.exp(np.cumsum(log_ret))
        assert tag_regime(series) == "high_vol"

    def test_constant_series(self):
        """Constant series -> low_vol."""
        series = np.full(100, 42.0)
        assert tag_regime(series) == "low_vol"

    def test_short_series(self):
        """Very short series -> low_vol."""
        assert tag_regime([100.0, 101.0, 102.0]) == "low_vol"


class TestHurstDFA:
    """Tests for the DFA Hurst estimator."""

    def test_hurst_random_walk(self):
        """Random walk should have H roughly around 0.5."""
        np.random.seed(7)
        steps = np.random.normal(0, 1, 2000)
        rw = 100.0 + np.cumsum(steps)
        rw = np.maximum(rw, 1.0)  # keep positive for log
        H = hurst_dfa(rw)
        assert 0.35 <= H <= 0.65, f"H={H} out of expected range for random walk"

    def test_hurst_constant(self):
        """Constant series should return fallback 0.5."""
        series = np.full(200, 10.0)
        H = hurst_dfa(series)
        assert H == 0.5

    def test_hurst_short_series(self):
        """Very short series should return fallback 0.5."""
        H = hurst_dfa([1.0, 2.0, 3.0])
        assert H == 0.5
