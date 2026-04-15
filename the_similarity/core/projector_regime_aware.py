"""
Regime-aware cone widening projector.

Part of the ``projector-v2`` research lane. Signature-compatible with
``the_similarity.core.projector.project`` so the sweep runner can swap it
in-place as a candidate variant.

Idea
----
The baseline projector.py has a single, homogeneous cone-widening knob
(``Config.confidence_decay_rate``) that fans out non-median percentiles
linearly with horizon regardless of market context. Residual calibration
studies show a pattern: the P10/P90 band tends to be **too tight** in
high-volatility regimes and **too wide** in low-volatility regimes. This
module conditions the cone width on the *query's* regime tag (detected
from the last lookback window handed to ``project(...)``) and multiplies
the P10/P90 distance from P50 by a regime-specific factor.

Default multipliers were picked from the baseline calibration study in
``progress/autoresearch/reports/sweep-spy-initial-v1-*.json`` — they
are intentionally modest (0.8 - 1.4) so this variant can be composed
with the adaptive conformal layer without producing pathological cones.
Override via the ``regime_multipliers`` kwarg.

Walk-forward invariant
----------------------
Regime detection consumes only the *query* portion passed in via
``query`` or, if absent, the terminal ``config.sax_n_segments * 3``
bars of the raw ``history`` array. Neither source is allowed to include
the trial's future, which is enforced by the backtester's slicing
contract (``lookback = history[:query_start]``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from the_similarity.config import Config
from the_similarity.core.projector import Forecast, project as _baseline_project
from the_similarity.core.regime import tag_regime
from the_similarity.core.scorer import MatchResult


# Default multipliers chosen to gently compensate for baseline bias
# patterns observed in the projector-calibration lane. They can be
# overridden per-run by passing ``regime_multipliers`` to ``project``.
# Invariants:
# - 1.0 means "don't change the baseline cone".
# - <1.0 tightens the cone (use when baseline is consistently too wide).
# - >1.0 widens the cone (use when baseline is consistently too tight).
_DEFAULT_MULTIPLIERS: dict[str, float] = {
    "trending_up": 0.9,
    "trending_down": 0.9,
    "mean_reverting": 0.85,
    "high_vol": 1.4,  # the fat-tail case — baseline cone is too tight
    "low_vol": 0.8,  # baseline cone is too loose
    "unknown": 1.0,
}


@dataclass
class RegimeAwareState:
    """Diagnostics for regime-aware widening, attached to Forecast."""

    regime: str
    multiplier: float
    used_default_multipliers: bool


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def project(
    matches: list[MatchResult],
    history: NDArray[np.float64],
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
    config: Config | None = None,
    *,
    query: NDArray[np.float64] | None = None,
    regime_multipliers: dict[str, float] | None = None,
    apply_to: tuple[int, ...] = (10, 25, 75, 90),
) -> Forecast:
    """Produce the baseline cone, then widen/tighten per query regime.

    Args:
        matches: Ranked match results from the search pipeline.
        history: Raw price history (numpy 1-D float64). Used for regime
            detection when no ``query`` is provided — we take the tail
            ``3 * config.sax_n_segments`` samples as the proxy query.
        forward_bars: Forecast horizon in bars.
        percentiles: Percentile levels for the cone.
        config: Pipeline config, forwarded to the baseline.
        query: Optional explicit query window to detect the regime on.
            The backtester passes this through automatically.
        regime_multipliers: Overrides for the per-regime width scaling.
        apply_to: Which percentiles to rescale. Defaults to the non-median
            percentiles; P50 is always left alone.

    Returns:
        A :class:`Forecast` with non-median curves rescaled by the regime
        multiplier, plus a ``regime_aware`` attribute recording diagnostics.
    """
    baseline = _baseline_project(
        matches=matches,
        history=history,
        forward_bars=forward_bars,
        percentiles=percentiles,
        config=config,
    )

    # Fail-closed: if the baseline had no usable paths, the widening
    # layer is a no-op. Still attach diagnostic state so downstream
    # reporting can confirm the regime lookup happened.
    if baseline.all_paths.shape[0] == 0:
        setattr(
            baseline,
            "regime_aware",
            RegimeAwareState(
                regime="unknown",
                multiplier=1.0,
                used_default_multipliers=regime_multipliers is None,
            ),
        )
        return baseline

    # --- Regime detection on the query window ---
    regime = _detect_regime(
        query=query,
        history=history,
        config=config,
    )

    multipliers = dict(_DEFAULT_MULTIPLIERS)
    if regime_multipliers:
        multipliers.update(regime_multipliers)
    mult = float(multipliers.get(regime, multipliers.get("unknown", 1.0)))

    # --- Rescale the configured percentile set around P50 ---
    # We never touch the P50 curve: this module is about *width*, not
    # *direction*. Any percentile not in ``apply_to`` is copied verbatim.
    p50 = baseline.curves.get(50)
    if p50 is None or len(p50) == 0 or mult == 1.0:
        # No scaling possible or requested — return a safe copy.
        out = _copy_forecast(baseline)
        setattr(
            out,
            "regime_aware",
            RegimeAwareState(
                regime=regime,
                multiplier=mult,
                used_default_multipliers=regime_multipliers is None,
            ),
        )
        return out

    new_curves: dict[int, NDArray[np.float64]] = {}
    for p, curve in baseline.curves.items():
        if p == 50 or p not in apply_to:
            new_curves[p] = np.array(curve, copy=True)
            continue
        distance = curve - p50
        new_curves[p] = p50 + distance * mult

    widened = Forecast(
        bars=baseline.bars,
        percentiles=list(baseline.percentiles),
        curves=new_curves,
        all_paths=baseline.all_paths,
        weights=baseline.weights,
        koopman_forecast=baseline.koopman_forecast,
    )
    setattr(
        widened,
        "regime_aware",
        RegimeAwareState(
            regime=regime,
            multiplier=mult,
            used_default_multipliers=regime_multipliers is None,
        ),
    )
    return widened


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _detect_regime(
    *,
    query: NDArray[np.float64] | None,
    history: NDArray[np.float64],
    config: Config | None,
) -> str:
    """Return the regime tag for the most recent available context.

    Priority:
    1. Explicit ``query`` argument — the lane runner / backtester passes
       this through when available.
    2. Tail of ``history`` of length ``3 * sax_n_segments`` (a safe proxy
       that matches the SAX window resolution the matcher uses).
    3. "unknown" as a fail-closed fallback when too little data exists.
    """
    if query is not None and len(query) >= 10:
        return tag_regime(np.asarray(query, dtype=np.float64))

    # Pick a reasonable tail window for regime detection. We default to
    # 3 * SAX segment count so the sample is long enough for Hurst to be
    # stable but still local to the most recent market conditions.
    tail_len = 3 * (config.sax_n_segments if config else 16)
    if len(history) < 10:
        return "unknown"
    tail_len = min(tail_len, len(history))
    return tag_regime(history[-tail_len:])


def _copy_forecast(baseline: Forecast) -> Forecast:
    """Safe copy — curves are deep-copied so downstream rescaling is isolated."""
    return Forecast(
        bars=baseline.bars,
        percentiles=list(baseline.percentiles),
        curves={p: np.array(c, copy=True) for p, c in baseline.curves.items()},
        all_paths=baseline.all_paths,
        weights=baseline.weights,
        koopman_forecast=baseline.koopman_forecast,
    )
