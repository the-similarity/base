"""Wavelet-aware classical baseline for the foundation-bench lane.

This is the "wavelet-aware model" required by plan_april14.md Track 2A.
It is intentionally CLASSICAL (no neural network): a Daubechies-4
discrete wavelet transform denoises the history, an AR(p) is fitted to
the denoised log-return series, and a bootstrap residual cone provides
quantiles for the shared metrics.

Why classical over Wavelet-LSTM?
--------------------------------
A Wavelet-LSTM would require training per slice, which adds a training
budget to every (model, slice) cell and either violates fairness (not
every foundation adapter has the same train budget) or breaks the
25-minute wall-clock cap on CPU. The classical wavelet baseline:

* runs in O(n) per query (well under 0.1 s on 2k-bar slices),
* needs no training stage, so its budget and the engine's budget are
  directly comparable,
* is fully explainable — the per-level wavelet coefficients can be
  inspected after each prediction,
* sets a fair lower bound for "wavelet-awareness beats the engine"
  claims; a Wavelet-LSTM that cannot beat it is not a real win.

Algorithm
---------
1. Take the last ``ctx_len`` bars of ``history`` and convert to
   log returns.
2. Run a ``n_levels``-level Daubechies-``wavelet`` DWT on the returns.
3. Soft-threshold the detail coefficients at ``sigma * sqrt(2 log N)``
   (universal threshold); reconstruct to produce a denoised return
   series.
4. Fit an AR(p) (``residual_order``) via numpy least-squares on the
   denoised returns.
5. Simulate ``n_paths`` forward paths by iterating the AR recursion
   and resampling in-sample residuals; read quantiles at each horizon.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from research.autoresearch.foundation_bench.adapters.base import (
    ForecastResult,
    bootstrap_residual_cone,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _denoise(returns: np.ndarray, wavelet: str, n_levels: int) -> np.ndarray:
    """Wavelet soft-threshold denoise.

    Returns a series of the same length as ``returns``. Uses the
    universal threshold ``sigma * sqrt(2 ln N)`` where ``sigma`` is a
    MAD-based estimate of the finest-level noise — this is the standard
    Donoho-Johnstone construction, robust for log-return inputs that have
    noticeable kurtosis.

    We wrap the import of pywt in the function body (not the module) so
    this file remains importable even if pywt vanishes from the env —
    the adapter then falls back to an unfiltered AR fit.
    """
    try:
        import pywt  # type: ignore[import]
    except Exception:  # pragma: no cover
        return returns

    # Wavelet level auto-clip: pywt.wavedec requires that 2**level <=
    # len(returns).  We clip to the feasible maximum.
    max_level = int(pywt.dwt_max_level(len(returns), pywt.Wavelet(wavelet).dec_len))
    level = min(int(n_levels), max_level) if max_level > 0 else 0
    if level < 1:
        return returns

    coeffs = pywt.wavedec(returns, wavelet, level=level)
    # Robust sigma via MAD of finest detail level.
    detail = coeffs[-1]
    sigma = float(np.median(np.abs(detail))) / 0.6745 if len(detail) else 0.0
    threshold = sigma * np.sqrt(2.0 * np.log(max(len(returns), 2)))
    denoised = [coeffs[0]]
    for c in coeffs[1:]:
        denoised.append(pywt.threshold(c, threshold, mode="soft"))
    recon = pywt.waverec(denoised, wavelet)
    # Reconstruction can return one extra sample for odd-length inputs;
    # slice back to the original length so downstream shapes align.
    return np.asarray(recon[: len(returns)], dtype=np.float64)


def _fit_ar(returns: np.ndarray, p: int) -> tuple[np.ndarray, float, np.ndarray]:
    """Fit an AR(p) via OLS, returning (phi, intercept, residuals).

    Degenerate fallback (too-short input, rank-deficient): returns phi
    zeros, intercept = mean, residuals = centered returns. The caller
    then gets a white-noise bootstrap cone.
    """
    p = max(1, int(p))
    n = len(returns)
    if n <= p + 2:
        intercept = float(np.mean(returns)) if n else 0.0
        return np.zeros(p, dtype=np.float64), intercept, returns - intercept
    X = np.zeros((n - p, p + 1), dtype=np.float64)
    for i in range(p):
        X[:, i] = returns[p - 1 - i : n - 1 - i]
    X[:, -1] = 1.0
    y = returns[p:]
    # np.linalg.lstsq returns least-squares solution; residuals via subtract
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    phi = beta[:-1]
    intercept = float(beta[-1])
    resid = y - X @ beta
    return phi, intercept, resid


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class WaveletBaselineAdapter:
    """Classical wavelet-denoise + AR(p) + bootstrap residual cone.

    The ``explainability`` attribute is set to ``medium`` in ``models.yaml``;
    the report writer reads it directly for the qualitative column.
    """

    name = "wavelet_baseline"

    def __init__(
        self,
        wavelet: str = "db4",
        n_levels: int = 3,
        residual_order: int = 2,
        ctx_len: int = 512,
        n_paths: int = 200,
        seed: int = 0,
    ):
        self.wavelet = str(wavelet)
        self.n_levels = int(n_levels)
        self.residual_order = int(residual_order)
        self.ctx_len = int(ctx_len)
        self.n_paths = int(n_paths)
        self.seed = int(seed)
        self._has_pywt = True
        try:
            import pywt  # noqa: F401
        except Exception:  # pragma: no cover — pywt is a repo dep
            self._has_pywt = False

    def predict_quantiles(
        self,
        history: np.ndarray,
        forward_bars: int,
        percentiles: Sequence[int],
    ) -> ForecastResult:
        if not self._has_pywt:
            # Degenerate fallback — should basically never fire because
            # pywt is in the engine's main dependency set.
            quantiles = bootstrap_residual_cone(
                history[-self.ctx_len :],
                forward_bars=forward_bars,
                percentiles=percentiles,
                n_paths=self.n_paths,
                seed=self.seed,
            )
            return ForecastResult(
                quantiles=quantiles,
                point_forecast=quantiles[50] if 50 in quantiles else None,
                fallback_reason="pywt not importable — wavelet_baseline degraded to bootstrap",
                metadata={"adapter": self.name, "mode": "degraded_fallback"},
            )

        ctx = np.asarray(history[-self.ctx_len :], dtype=np.float64)
        # --- Log-returns of the history window ------------------------
        p = np.where(ctx <= 0.0, 1e-9, ctx)
        returns = np.diff(np.log(p))

        # --- Wavelet denoise -----------------------------------------
        denoised = _denoise(returns, wavelet=self.wavelet, n_levels=self.n_levels)

        # --- AR(p) fit on denoised returns ----------------------------
        phi, intercept, resid = _fit_ar(denoised, self.residual_order)

        # --- Simulate forward paths -----------------------------------
        rng = np.random.default_rng(self.seed)
        paths = np.zeros((self.n_paths, forward_bars), dtype=np.float64)
        order = len(phi)
        for j in range(self.n_paths):
            buf = list(denoised[-order:]) if order > 0 else [0.0]
            cum = 0.0
            for h in range(forward_bars):
                mean = intercept + sum(phi[i] * buf[-1 - i] for i in range(order))
                eps = float(rng.choice(resid)) if len(resid) else 0.0
                r = mean + eps
                cum += r
                paths[j, h] = cum
                buf.append(r)

        quantiles: dict[int, np.ndarray] = {}
        for pct in percentiles:
            q = np.percentile(paths, pct, axis=0)
            quantiles[int(pct)] = np.exp(q) - 1.0

        return ForecastResult(
            quantiles=quantiles,
            point_forecast=quantiles[50] if 50 in quantiles else None,
            fallback_reason=None,  # this is a REAL classical method, not a fallback
            metadata={
                "adapter": self.name,
                "mode": "real_classical",
                "wavelet": self.wavelet,
                "n_levels": self.n_levels,
                "residual_order": self.residual_order,
                "n_paths": self.n_paths,
                "ctx_len_used": len(ctx),
            },
        )
