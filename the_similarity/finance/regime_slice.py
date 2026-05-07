"""Regime-sliced backtest metrics for the finance pillar.

Mirrors the evaluation framework from Correia (2015) Table 7, which slices
strategy performance across four macro-regime axes (Growth, Inflation,
Volatility, Liquidity). The point of the slice is to surface *where* the
analog approach excels vs. struggles: the paper's headline robustness
claim - "performs in bearish + tightening regimes when typical strategies
suffer" - only becomes legible after this slicing.

Design
------
The slicing function is intentionally generic: it takes a sequence of
``TrialResult`` objects plus a callable that returns a regime label per
trial, and returns a per-label info-Sharpe (the same ``r_p / sigma`` ratio
the source paper uses). This keeps the metric decoupled from any specific
data source, which is important because regime indicators (GDP, CPI, VIX,
FED rate) are pulled from FRED / Bloomberg / proprietary feeds and we do
not want to bake any of those backends into ``the_similarity``.

Two lightweight helpers (:func:`label_growth_inflation` and
:func:`label_volatility_liquidity`) build the canonical Correia-style
labels from raw indicator series. Callers compose them with whatever data
they already pulled.

Mathematical formulation
------------------------
For each regime label *L* with ``n_L`` qualifying trials::

    r_i        = sign(P50_i_terminal) * actual_i_terminal
    info_sharpe_L = mean_{i in L}(r_i) / std_{i in L}(r_i)

This is a *non-annualised* per-period Sharpe by design - regime windows
are highly variable in length, so annualising would give misleading
period-to-period comparisons. The metric is meant to be read relatively
across regimes within a single backtest, not in absolute terms.

Edge cases
----------
- Buckets with fewer than 2 qualifying trials produce NaN (Sharpe is
  undefined on a single observation).
- Buckets where every realised return is zero produce NaN (zero variance,
  fail-closed rather than infinite Sharpe).
- Trials with no P50 forecast curve are skipped silently (consistent with
  ``the_similarity.core.metrics.sharpe_ratio``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    # Avoid a runtime import: TrialResult lives in
    # ``the_similarity.core.backtester`` which itself imports from many
    # modules. Pulling it in only for typing keeps this finance-tier
    # module light to import.
    from the_similarity.core.backtester import TrialResult


# -------------------------------------------------------------------------
# Canonical regime labels - mirror Correia (2015) Table 7.
#
# Why string constants rather than an Enum? Downstream consumers (the
# review UI, JSON artifacts on disk, the platform registry's scorecard
# rows) all serialise regime labels as plain strings. Keeping the source
# of truth as constants avoids an Enum -> str round-trip in every
# serialisation path.
# -------------------------------------------------------------------------

GROWTH_UP = "growth_up"
GROWTH_DOWN = "growth_down"

INFLATION_UP = "inflation_up"
INFLATION_DOWN = "inflation_down"

VOLATILITY_BULLISH = "volatility_bullish"  # VIX below 1y average
VOLATILITY_BEARISH = "volatility_bearish"  # VIX above 1y average

LIQUIDITY_UP = "liquidity_up"  # rate cut
LIQUIDITY_DOWN = "liquidity_down"  # rate hike


def info_sharpe_by_regime(
    trials: Sequence[TrialResult],
    regime_for_trial: Callable[["TrialResult"], str | None],
) -> dict[str, float]:
    """Bucket trials by regime label and report per-bucket info-Sharpe.

    Args:
        trials: Completed backtest trials. Trials with no P50 curve, or
            with ``regime_for_trial`` returning ``None``, are dropped.
        regime_for_trial: Callable mapping each trial to a regime label
            string (or ``None`` to exclude that trial). Typical
            implementations index a date-keyed regime series by
            ``trial.query_start`` mapped to the underlying timestamp.

    Returns:
        Dict ``{regime_label: info_sharpe}``. Empty dict if no trials
        qualified. NaN values for buckets with insufficient data
        (fewer than 2 trials or zero-variance returns).
    """
    # Bucket realised directional returns by regime label in a single pass.
    # Using a plain dict-of-lists keeps memory linear in the number of
    # qualifying trials and avoids a pandas dependency in this module.
    buckets: dict[str, list[float]] = {}

    for trial in trials:
        # Skip trials missing the P50 curve - same fail-closed convention as
        # the_similarity.core.metrics.sharpe_ratio. We do not silently treat
        # them as flat trades because that would distort per-regime means.
        p50_curve = trial.forecast_curves.get(50)
        if p50_curve is None or len(p50_curve) == 0:
            continue

        label = regime_for_trial(trial)
        if label is None:
            # Caller signalled that this trial does not belong to any
            # regime bucket (e.g. timestamp outside the regime series'
            # coverage window). Skip rather than coerce to a default.
            continue

        direction = float(np.sign(float(p50_curve[-1])))
        realised = float(trial.actual_returns[-1])
        buckets.setdefault(label, []).append(direction * realised)

    result: dict[str, float] = {}
    for label, returns in buckets.items():
        # Sharpe is ill-defined on a single observation; fail-closed to NaN
        # so downstream aggregation can treat sparse buckets uniformly.
        if len(returns) < 2:
            result[label] = float("nan")
            continue

        arr = np.asarray(returns, dtype=np.float64)
        sigma = float(np.std(arr, ddof=0))
        if sigma == 0.0:
            # Zero variance means every directional trade closed at the
            # same magnitude - either degenerate test data or the regime
            # bucket caught nothing meaningful. NaN, not infinity.
            result[label] = float("nan")
            continue

        mu = float(np.mean(arr))
        result[label] = mu / sigma

    return result


# -------------------------------------------------------------------------
# Helpers for building Correia-style regime labels from raw indicator
# arrays. They are pure functions over numpy arrays / floats so callers
# can wire them to any data backend (FRED, Bloomberg, parquet cache).
#
# The thresholds match Correia (2015) Table 7 verbatim:
#   Growth:      current GDP growth vs. 2-year rolling average
#   Inflation:   current CPI YoY vs. 5-year rolling average
#   Volatility:  current VIX vs. 1-year rolling average
#   Liquidity:   FED rate change sign (Hike => liquidity_down, Cut => up)
# -------------------------------------------------------------------------


def label_growth_inflation(
    growth: float,
    growth_2y_avg: float,
    inflation: float,
    inflation_5y_avg: float,
) -> tuple[str, str]:
    """Return (growth_label, inflation_label) for one period.

    Mirrors the Correia (2015) Table 7 definition exactly:
        - Growth Up if current growth > 2y average, else Growth Down.
        - Inflation Up if current YoY > 5y average, else Inflation Down.

    No tolerance band - the original paper uses a strict comparison so
    every period falls into exactly one bucket on each axis. We preserve
    that to keep results reproducible against the paper's tables.
    """
    growth_label = GROWTH_UP if growth > growth_2y_avg else GROWTH_DOWN
    inflation_label = INFLATION_UP if inflation > inflation_5y_avg else INFLATION_DOWN
    return growth_label, inflation_label


def label_volatility_liquidity(
    vix: float,
    vix_1y_avg: float,
    fed_rate_change: float,
) -> tuple[str, str]:
    """Return (volatility_label, liquidity_label) for one period.

    Correia (2015) Table 7 conventions:
        - VIX above 1y average  => Bearish (more risk-off);
          VIX below 1y average => Bullish.
        - FED rate hike (positive change) => liquidity_down;
          FED rate cut  (negative change) => liquidity_up.
        - A zero change is treated as ``liquidity_down`` to match the
          paper's intent (no easing, so liquidity is not loosening).

    Both labels are independent of each other - the caller decides
    whether to combine them into a 2x2 grid or keep them as separate
    slicing axes.
    """
    volatility_label = VOLATILITY_BEARISH if vix > vix_1y_avg else VOLATILITY_BULLISH
    # ``> 0`` vs ``>= 0`` matters: a flat-policy month is closer to
    # "tightening continues" than to "easing", per the paper's hawkish
    # treatment of unchanged rates as "no liquidity injection".
    liquidity_label = LIQUIDITY_DOWN if fed_rate_change >= 0 else LIQUIDITY_UP
    return volatility_label, liquidity_label


__all__ = [
    "GROWTH_DOWN",
    "GROWTH_UP",
    "INFLATION_DOWN",
    "INFLATION_UP",
    "LIQUIDITY_DOWN",
    "LIQUIDITY_UP",
    "VOLATILITY_BEARISH",
    "VOLATILITY_BULLISH",
    "info_sharpe_by_regime",
    "label_growth_inflation",
    "label_volatility_liquidity",
]
