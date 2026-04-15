"""Shared protocol and fallback helpers for foundation-bench adapters.

The lane defines exactly ONE public interface every adapter must satisfy::

    class ForecastAdapter(Protocol):
        name: str
        def predict_quantiles(
            self,
            history: np.ndarray,
            forward_bars: int,
            percentiles: Sequence[int],
        ) -> ForecastResult: ...

A ``ForecastResult`` is a thin container that carries either a real
probabilistic forecast from the pretrained model (``fallback_reason
is None``) or a synthetic fallback forecast clearly marked with a
``fallback_reason`` string. The runner keys on this field to decide
whether a given (model, slice) cell is recorded as a real benchmark or
as ``partial_synthetic_fallback``.

Why a Protocol and not an ABC?
------------------------------
The adapters live in separate modules that should be importable even
when their optional heavy dependencies (``torch``, ``transformers``,
``gluonts``) are absent. Using ``typing.Protocol`` lets each adapter
class register structurally without forcing a runtime import chain.

Fallback primitives
-------------------
Two reusable fallback generators are provided here so every foundation
adapter behaves the same way when real weights cannot be loaded:

* ``ar1_cone`` — fits an AR(1) on the provided history and produces a
  Gaussian cone of quantiles at each forward horizon bar. Cheap and
  deterministic for a given seed.
* ``bootstrap_residual_cone`` — fits an AR(1) mean, then resamples its
  in-sample residuals with replacement to generate N paths and reads
  the empirical quantiles at each horizon bar.

Both return a ``dict[int, np.ndarray]`` where each array has length
``forward_bars`` — matching the shape the runner expects to hand to the
shared metrics helpers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

import numpy as np


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
#
# Immutability note: the quantile dict is returned by value; the runner
# must treat it as read-only. Adapters must not mutate the dict after
# returning it (pytest guards this for each adapter).
# ---------------------------------------------------------------------------

@dataclass
class ForecastResult:
    """A single (model, query) forecast.

    Fields
    ------
    quantiles : dict[int, np.ndarray]
        Percentile -> 1-D array of length ``forward_bars`` with the forecast
        value at each forward bar. A realised-return-level quantile is
        computed by the runner at the terminal bar.
    point_forecast : np.ndarray | None
        Optional point forecast path (length ``forward_bars``). The runner
        falls back to ``quantiles[50]`` when this is absent.
    fallback_reason : str | None
        If present, this (model, query) forecast was produced by the
        synthetic-fallback code path. The runner propagates this reason
        into the per-cell artefact and the ledger row.
    metadata : dict[str, object]
        Free-form adapter notes (e.g. real weights loaded, inference
        time, bootstrap sample size). Serialised into the artefact.
    """

    quantiles: dict[int, np.ndarray]
    point_forecast: np.ndarray | None = None
    fallback_reason: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public protocol
# ---------------------------------------------------------------------------
#
# Using runtime_checkable makes it trivial to assert adherence in tests
# (``isinstance(adapter, ForecastAdapter)``) without forcing inheritance.
# ---------------------------------------------------------------------------

@runtime_checkable
class ForecastAdapter(Protocol):
    """Minimal interface every foundation-bench adapter satisfies.

    Lifecycle
    ---------
    One adapter instance is constructed per (model, slice) cell. Heavy
    weights, if loadable, should be cached on ``self`` in ``__init__`` so
    the cost is amortised across trials within a cell.

    Thread safety
    -------------
    Adapters are invoked sequentially by the runner; no locking required.
    """

    name: str

    def predict_quantiles(
        self,
        history: np.ndarray,
        forward_bars: int,
        percentiles: Sequence[int],
    ) -> ForecastResult:
        """Produce a quantile forecast for ``history[-ctx_len:]``.

        Walk-forward contract: ``history`` is the ENTIRE slice of prices
        the runner is willing to show the model. The adapter may use at
        most the last ``ctx_len`` bars; it must never peek at any global
        state that depends on bars after ``history[-1]``.
        """
        ...


# ---------------------------------------------------------------------------
# Fallback forecasts
# ---------------------------------------------------------------------------


def _to_log_returns(prices: np.ndarray) -> np.ndarray:
    """Safe log-returns helper used by every fallback.

    Zeros and negatives are clipped to a small positive floor to avoid
    ``log(non-positive)`` exploding on malformed inputs.
    """
    p = np.asarray(prices, dtype=np.float64)
    p = np.where(p <= 0.0, 1e-9, p)
    return np.diff(np.log(p))


def _fit_ar1(returns: np.ndarray) -> tuple[float, float, float]:
    """Return (phi, mu, sigma_resid) for an AR(1) on the returns series.

    Uses closed-form OLS for speed; sample size is bounded by history
    which is typically 60-2500 bars. Returns (0, 0, std(returns)) if the
    series is too short or degenerate.
    """
    if len(returns) < 5:
        return 0.0, 0.0, float(np.std(returns) or 1e-6)
    y = returns[1:]
    x = returns[:-1]
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    denom = float(np.sum((x - x_mean) ** 2))
    if denom == 0.0:
        return 0.0, y_mean, float(np.std(y) or 1e-6)
    phi = float(np.sum((x - x_mean) * (y - y_mean)) / denom)
    # Clip phi to (-0.99, 0.99) so simulated paths don't explode for fat
    # tailed inputs where OLS can overshoot beyond unit root.
    phi = max(min(phi, 0.99), -0.99)
    mu = y_mean * (1.0 - phi)
    resid = y - (mu + phi * x)
    sigma = float(np.std(resid))
    if sigma == 0.0:
        sigma = float(np.std(returns)) or 1e-6
    return phi, mu, sigma


def ar1_cone(
    history: np.ndarray,
    forward_bars: int,
    percentiles: Sequence[int],
    seed: int = 0,
) -> dict[int, np.ndarray]:
    """Return percentile -> forecast-path array using an AR(1) Gaussian cone.

    This is the cheapest deterministic fallback. We fit (phi, mu, sigma)
    on the in-sample log returns, then compute the analytic variance of
    the cumulative return at horizon ``h`` under the AR(1) with Gaussian
    innovations. Quantiles at each horizon are derived from the
    analytic Gaussian CDF.

    The returned forecasts are PRICE-RELATIVE cumulative returns (i.e.
    ``price_h / price_0 - 1``), matching what the runner compares to the
    realised forward return.
    """
    _ = seed  # deterministic closed form; seed is unused here
    returns = _to_log_returns(history)
    phi, mu, sigma = _fit_ar1(returns)

    # Cumulative log-return variance under AR(1) closed form:
    #   Var(sum_{i=1..h} r_i) ~ sigma^2 * (h + 2*sum_{k=1..h-1} (h-k) * phi^k)
    # We compute it iteratively for numerical stability at small h.
    horizon = forward_bars
    var_cum = np.zeros(horizon, dtype=np.float64)
    mean_cum = np.zeros(horizon, dtype=np.float64)
    # AR(1) steady-state mean of the log-return process is mu / (1 - phi).
    long_mean = mu / (1.0 - phi) if abs(phi) < 1.0 else mu
    mean_cum[0] = long_mean
    var_cum[0] = sigma * sigma
    for h in range(1, horizon):
        # Cumulative mean grows linearly by the long-run per-step mean.
        mean_cum[h] = mean_cum[h - 1] + long_mean
        # Variance: sigma^2 * (1 + 2*phi + 3*phi^2 ... depending on h)
        # expressed via iterative sum of (1 + phi + phi^2 + ... + phi^h).
        s = (1.0 - phi ** (h + 1)) / (1.0 - phi) if abs(phi) < 1.0 else (h + 1)
        var_cum[h] = sigma * sigma * s * s

    std_cum = np.sqrt(var_cum)

    quantiles: dict[int, np.ndarray] = {}
    # Inverse-CDF of the standard normal — numpy has no erfinv, so we
    # use the closed-form approximation from numpy.random via ppf.
    from scipy.stats import norm  # type: ignore[import]

    for p in percentiles:
        z = float(norm.ppf(p / 100.0))
        # Convert log-return cone to arithmetic return ratio
        # price_h / price_0 - 1 = exp(cumulative_log_return) - 1
        log_q = mean_cum + z * std_cum
        quantiles[int(p)] = np.exp(log_q) - 1.0
    return quantiles


def bootstrap_residual_cone(
    history: np.ndarray,
    forward_bars: int,
    percentiles: Sequence[int],
    n_paths: int = 200,
    seed: int = 0,
) -> dict[int, np.ndarray]:
    """AR(1) mean path + bootstrapped in-sample residuals -> empirical cone.

    Unlike ``ar1_cone`` (which assumes Gaussian innovations), this helper
    captures the empirical fat-tailed residual distribution of the
    history. Used by adapters whose real model is a point-forecaster
    (MOMENT, wavelet baseline) to supply quantiles from a fitted
    residual distribution rather than a parametric one.
    """
    rng = np.random.default_rng(int(seed))
    returns = _to_log_returns(history)
    phi, mu, sigma = _fit_ar1(returns)

    if len(returns) < 5:
        # Degenerate — fall back to Gaussian cone with tiny sigma.
        return ar1_cone(history, forward_bars, percentiles, seed=seed)

    y = returns[1:]
    x = returns[:-1]
    resid = y - (mu + phi * x)

    paths = np.zeros((n_paths, forward_bars), dtype=np.float64)
    last = float(returns[-1])
    for j in range(n_paths):
        r = last
        cum = 0.0
        for h in range(forward_bars):
            r = mu + phi * r + float(rng.choice(resid))
            cum += r
            paths[j, h] = cum

    quantiles: dict[int, np.ndarray] = {}
    for p in percentiles:
        q = np.percentile(paths, p, axis=0)
        quantiles[int(p)] = np.exp(q) - 1.0
    return quantiles


__all__ = [
    "ForecastAdapter",
    "ForecastResult",
    "ar1_cone",
    "bootstrap_residual_cone",
]
