"""Forecast accuracy and calibration metrics for the benchmark harness.

Five scoring functions, all consuming a :class:`benchmarks.core.Forecast`
plus the realised actual array:

- :func:`mae`              — point-forecast absolute error of P50.
- :func:`smape`            — symmetric MAPE of P50, in percent (0-200).
- :func:`crps`             — discrete CRPS approximation across (P10, P50, P90).
- :func:`mase`             — mean absolute scaled error vs seasonal-naive train.
- :func:`coverage_p10_p90` — empirical containment in [P10, P90].

Mathematical fidelity notes:
    - The CRPS approximation here mirrors ``the_similarity.core.metrics.crps``
      (the discrete-percentile form) rather than the continuous
      sample-pair form. Three percentiles is the minimum that gives a
      meaningful score; the bias vs the integrated form is small for
      well-calibrated distributions and constant across all systems we
      compare, so RANKING is preserved.
    - MASE divides by the in-sample seasonal-naive MAE on the train
      series. We compute that scale from ``train`` alone (no test
      leakage). If the train series is too short to admit a single
      seasonal lag the scale falls back to the mean absolute first
      difference (random-walk MASE).
    - Coverage is the canonical empirical containment statistic: it
      does NOT penalise width. Use it together with MAE/CRPS so the
      report layer can spot trivially wide cones.

All functions return ``float('nan')`` (not 0, not raise) for malformed
input — the runner asserts finiteness downstream so a NaN turns into a
loud failure rather than a silent one.
"""

from __future__ import annotations

import numpy as np

from benchmarks.core import Forecast


def _truncate(forecast: Forecast, actual: np.ndarray) -> tuple[Forecast, np.ndarray]:
    """Align forecast and actual to their common prefix.

    The runner usually constructs the forecast at exactly the test length,
    but loaders that ship test arrays shorter than the harness horizon
    would otherwise produce mismatched shapes. We trim both to the shorter
    length and let downstream metrics treat the missing tail as out of
    scope (rather than padding with NaN, which would skew aggregates).
    """
    n = min(len(forecast.p50), len(actual))
    if n == 0:
        return forecast, actual
    trimmed = Forecast(
        p10=np.asarray(forecast.p10[:n], dtype=np.float64),
        p50=np.asarray(forecast.p50[:n], dtype=np.float64),
        p90=np.asarray(forecast.p90[:n], dtype=np.float64),
    )
    return trimmed, np.asarray(actual[:n], dtype=np.float64)


def mae(forecast: Forecast, actual: np.ndarray) -> float:
    """Mean absolute error of the P50 trajectory vs realised values.

    Returns NaN on empty input rather than raising, so the runner can
    treat NaN as a failure mode instead of try/except'ing every call.
    """
    f, a = _truncate(forecast, actual)
    if len(a) == 0:
        return float("nan")
    return float(np.mean(np.abs(f.p50 - a)))


def smape(forecast: Forecast, actual: np.ndarray) -> float:
    """Symmetric MAPE in percent (0-200).

    Formula:
        sMAPE = mean( 2 * |y_hat - y| / (|y_hat| + |y|) ) * 100

    The denominator is computed pairwise per-bar; bars where both forecast
    and actual are exactly zero contribute 0 (not NaN) — this matches the
    M4 competition's published scoring rule and avoids penalising correct
    "predict zero" forecasts.
    """
    f, a = _truncate(forecast, actual)
    if len(a) == 0:
        return float("nan")
    denom = np.abs(f.p50) + np.abs(a)
    # When both sides are zero, error is zero (not NaN). We use np.where to
    # avoid creating runtime warnings for the degenerate-but-correct case.
    with np.errstate(invalid="ignore", divide="ignore"):
        per_bar = np.where(denom > 0, 2.0 * np.abs(f.p50 - a) / denom, 0.0)
    return float(np.mean(per_bar) * 100.0)


def crps(forecast: Forecast, actual: np.ndarray) -> float:
    """Discrete CRPS approximation using the three percentile curves.

    For each bar we evaluate the squared deviation between the indicator
    ``I(y <= F_p)`` and the nominal CDF level ``p/100`` at p in {10, 50,
    90}, then average over percentiles AND bars. This mirrors
    ``the_similarity.core.metrics.crps`` so the harness's reading of
    "CRPS" is consistent with what the engine reports internally.

    Lower is better. The minimum (perfect calibration AND sharpness)
    converges to 0 as more percentiles are sampled.
    """
    f, a = _truncate(forecast, actual)
    if len(a) == 0:
        return float("nan")
    # Stack into (3, n) so we can vectorise the indicator computation in
    # one broadcast — important because the runner calls this per series
    # per horizon per system, so per-call overhead matters.
    stacked = np.stack([f.p10, f.p50, f.p90], axis=0)
    cdf_levels = np.array([0.10, 0.50, 0.90], dtype=np.float64)[:, None]
    indicators = (a[None, :] <= stacked).astype(np.float64)
    per_bar = np.mean((indicators - cdf_levels) ** 2, axis=0)
    return float(np.mean(per_bar))


def mase(forecast: Forecast, actual: np.ndarray, train: np.ndarray, seasonality: int) -> float:
    """Mean absolute scaled error using seasonal-naive train MAE as the scale.

    Formula:
        scale = mean( |x_t - x_{t-m}| )   for t in [m, len(train))
        MASE  = mean( |y_hat - y| ) / scale

    where ``m`` = ``seasonality`` and the scale is computed on ``train``
    only. If the train series is shorter than ``seasonality + 1`` we fall
    back to the random-walk denominator (m=1). If even that fails (train
    length < 2) we return NaN — this means MASE is undefined for that
    series and the runner will flag it.

    Why train-only scale?
        Using the test series in the denominator would leak future
        information into the metric and break comparability with
        published M4 numbers, where the scale is fixed at training time.
    """
    f, a = _truncate(forecast, actual)
    train = np.asarray(train, dtype=np.float64)
    if len(a) == 0 or len(train) < 2:
        return float("nan")

    # Pick the largest valid seasonal lag we can afford. The fallback to
    # m=1 protects short train series (e.g. quarterly data with seasonality
    # 4 but only 8 train points) from collapsing the metric to NaN.
    m = seasonality if len(train) > seasonality else 1
    diffs = np.abs(train[m:] - train[:-m])
    if len(diffs) == 0:
        return float("nan")
    scale = float(np.mean(diffs))
    if scale == 0.0:
        # A constant train series gives a zero scale → MASE undefined.
        # Fail-closed to NaN; the runner will surface the affected series.
        return float("nan")
    err = float(np.mean(np.abs(f.p50 - a)))
    return err / scale


def coverage_p10_p90(forecast: Forecast, actual: np.ndarray) -> float:
    """Empirical fraction of actuals inside the [P10, P90] band.

    Target value is 0.80 for a well-calibrated 80% prediction interval.

    NOTE: Coverage is a one-sided diagnostic — it does NOT penalise
    width. A trivially wide forecast hits 100% but is useless. The
    report layer is expected to display CRPS and MAE alongside coverage
    so reviewers can spot that pathology.
    """
    f, a = _truncate(forecast, actual)
    if len(a) == 0:
        return float("nan")
    inside = (a >= f.p10) & (a <= f.p90)
    return float(np.mean(inside.astype(np.float64)))
