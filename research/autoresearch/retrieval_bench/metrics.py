"""Metric helpers for the retrieval benchmark lane.

This module is deliberately engine-free: every helper operates on plain
numpy arrays and lists of (offset, score) tuples so the computation is
fully unit-testable without importing ``the_similarity``.

Metrics implemented
-------------------
* ``forward_return_correlation`` — Pearson correlation between the forward
  returns that followed each retrieved match and the ACTUAL forward return
  that followed the query. This is our top-K precision proxy: if a retrieval
  method consistently finds analogues whose forward paths correlate with the
  realised future of the query, it is picking useful neighbours.
* ``empirical_crps`` — sample-based CRPS for a quantile forecast (percentiles
  array + realised return). Mirrors the definition used in
  ``the_similarity.core.metrics`` but avoids importing it so this module is
  self-contained.
* ``calibration_error_p10_p90`` — absolute deviation of the empirical [p10,
  p90] coverage from its nominal 0.80 rate, aggregated across trials.
* ``hit_rate`` — fraction of trials where the median forecast (p50) had the
  same sign as the realised forward return.
* ``summarise_runtimes`` — median, mean, p95 over a list of per-query runtimes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Per-trial container
# ---------------------------------------------------------------------------

@dataclass
class TrialOutcome:
    """Result of a single walk-forward trial for one arm.

    Fields
    ------
    match_forward_returns : list[float]
        Forward returns (signed pct change over ``forward_bars``) collected
        from the history region following each retrieved match. Used for the
        retrieval correlation metric.
    quantile_forecast : dict[int, float]
        Percentile -> forecast value for the query's forward horizon. Mirrors
        the projector output shape used in production.
    realised_forward_return : float
        The ACTUAL forward return that followed the query window. This is
        fixed by the slice / trial position and is identical across arms.
    runtime_seconds : float
        Wall-clock runtime of the retrieval+projection call for this trial.
    """

    match_forward_returns: list[float]
    quantile_forecast: dict[int, float]
    realised_forward_return: float
    runtime_seconds: float


# ---------------------------------------------------------------------------
# Retrieval-quality metric (top-K precision proxy)
# ---------------------------------------------------------------------------

def forward_return_correlation(trials: Sequence[TrialOutcome]) -> float:
    """Correlation between mean match-forward-return and realised forward.

    For each trial we take the MEAN forward return across the retrieved
    match set (a point estimate of "what past analogues said the future
    looks like") and regress it against the realised forward return that
    actually followed the query.

    A retrieval method that finds useful neighbours should produce a
    positive Pearson correlation — higher is better. Correlation is
    preferred over raw MSE because the realised returns are noisy and we
    care about directional information, not magnitude reproduction.

    Returns 0.0 when fewer than 3 valid trials exist or when either series
    has zero variance (correlation undefined).
    """
    if len(trials) < 3:
        return 0.0

    xs: list[float] = []
    ys: list[float] = []
    for t in trials:
        if not t.match_forward_returns:
            continue
        xs.append(float(np.mean(t.match_forward_returns)))
        ys.append(float(t.realised_forward_return))

    if len(xs) < 3:
        return 0.0

    x_arr = np.asarray(xs, dtype=np.float64)
    y_arr = np.asarray(ys, dtype=np.float64)
    if np.std(x_arr) == 0.0 or np.std(y_arr) == 0.0:
        return 0.0

    # np.corrcoef returns a 2x2 matrix; the off-diagonal is Pearson r.
    r = float(np.corrcoef(x_arr, y_arr)[0, 1])
    if np.isnan(r):
        return 0.0
    return r


# ---------------------------------------------------------------------------
# Forecast-quality metrics
# ---------------------------------------------------------------------------

def empirical_crps(trials: Sequence[TrialOutcome]) -> float:
    """Mean CRPS across trials using the empirical-quantile approximation.

    For each trial, we treat the quantile forecast as a piecewise-constant
    CDF at the supplied percentiles and compute

        CRPS = integral over x of (F(x) - H(x - y))**2

    where ``H`` is the Heaviside step at the realised return ``y``. In the
    finite-quantile case this reduces to a trapezoidal sum over the
    supplied percentiles. This mirrors the formulation in
    ``the_similarity.core.metrics.crps`` but without the engine import.

    Returns 0.0 when no trials are supplied.
    """
    if not trials:
        return 0.0

    total = 0.0
    n = 0
    for t in trials:
        percentiles = sorted(t.quantile_forecast.keys())
        if not percentiles:
            continue
        # Convert percentiles -> probabilities in [0, 1]
        probs = [p / 100.0 for p in percentiles]
        values = [t.quantile_forecast[p] for p in percentiles]
        y = t.realised_forward_return

        # Piecewise-constant CDF: between percentile i and i+1, F(x) = probs[i].
        # Integrand = (F(x) - H(x - y))**2.  We integrate across the quantile
        # grid AND account for realised values that fall outside the supplied
        # quantile range — otherwise extreme realised outcomes are not
        # penalised monotonically.
        crps = 0.0

        # --- Left tail: x < values[0], where F(x) ~= 0.
        # If realised y < values[0], for x in [y, values[0]] we have F = 0 but
        # H(x - y) = 1 -> integrand = 1 -> contributes (values[0] - y).
        if y < values[0]:
            crps += values[0] - y

        # --- Right tail: x > values[-1], where F(x) ~= 1.
        # If realised y > values[-1], for x in [values[-1], y] we have F = 1
        # but H(x - y) = 0 -> integrand = 1 -> contributes (y - values[-1]).
        if y > values[-1]:
            crps += y - values[-1]

        for i in range(len(values) - 1):
            lo = values[i]
            hi = values[i + 1]
            if hi <= lo:
                continue
            f = probs[i]
            # Segment [lo, hi] — the indicator H(x - y) is 0 for x < y and 1 otherwise.
            if y <= lo:
                indicator_integral = 1.0 * (hi - lo)
                integrand = (f - 1.0) ** 2
                crps += integrand * (hi - lo)
            elif y >= hi:
                indicator_integral = 0.0
                integrand = f**2
                crps += integrand * (hi - lo)
            else:
                # y lies inside [lo, hi]. Split the segment.
                crps += (f**2) * (y - lo) + ((f - 1.0) ** 2) * (hi - y)
        total += crps
        n += 1
    return total / n if n else 0.0


def calibration_error_p10_p90(trials: Sequence[TrialOutcome]) -> float:
    """|empirical coverage of [p10, p90] - 0.80|, averaged across trials.

    The nominal two-sided 80% interval should contain the realised return
    80% of the time. A well-calibrated cone has error near 0.0; overconfident
    cones have empirical coverage below 0.80 and the error grows accordingly.

    Returns 0.0 when no trials have both p10 and p90 present.
    """
    hits = 0
    total = 0
    for t in trials:
        if 10 not in t.quantile_forecast or 90 not in t.quantile_forecast:
            continue
        lo = t.quantile_forecast[10]
        hi = t.quantile_forecast[90]
        if lo <= t.realised_forward_return <= hi:
            hits += 1
        total += 1
    if total == 0:
        return 0.0
    coverage = hits / total
    return abs(coverage - 0.80)


def hit_rate(trials: Sequence[TrialOutcome]) -> float:
    """Fraction of trials where sign(p50) == sign(realised). Requires p50."""
    hits = 0
    total = 0
    for t in trials:
        if 50 not in t.quantile_forecast:
            continue
        p50 = t.quantile_forecast[50]
        y = t.realised_forward_return
        # A trial with zero p50 and zero realised is not informative — skip it.
        if p50 == 0.0 and y == 0.0:
            continue
        if (p50 >= 0.0) == (y >= 0.0):
            hits += 1
        total += 1
    if total == 0:
        return 0.0
    return hits / total


# ---------------------------------------------------------------------------
# Runtime summary
# ---------------------------------------------------------------------------

def summarise_runtimes(runtimes: Sequence[float]) -> dict[str, float]:
    """Return median / mean / p95 of per-query runtimes.

    All values are in seconds. Empty input returns zeros so downstream JSON
    writers never see NaN.
    """
    if not runtimes:
        return {"median": 0.0, "mean": 0.0, "p95": 0.0, "n": 0}
    arr = np.asarray(runtimes, dtype=np.float64)
    return {
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "p95": float(np.percentile(arr, 95)),
        "n": int(len(arr)),
    }
