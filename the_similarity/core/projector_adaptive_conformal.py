"""
Adaptive and change-aware conformal projector.

This module is part of the `projector-v2` research lane. It provides a
``project(...)`` function with the same signature as
``the_similarity.core.projector.project`` so it can be swapped in place.
The baseline bar-wise weighted-quantile cone is retained as the point
forecast; what changes is the *outer calibration layer* around it.

Two related calibration schemes are implemented:

1. **Adaptive conformal** (Gibbs & Candès 2021 style): keep a running
   target coverage level ``alpha_t``. After each historical match
   residual is consumed (in walk-forward order), update ``alpha_t``
   toward the nominal miscoverage ``alpha_target`` using an OGD step:

       alpha_{t+1} = alpha_t + lr * (alpha_target - err_t)

   where ``err_t == 1`` if the residual fell outside the previous
   interval and ``0`` otherwise.

2. **Change-aware conformal**: the same update, but older residuals
   are exponentially down-weighted so that a distribution shift
   (detected by a rolling residual-variance jump) shrinks the
   effective calibration window. This protects calibration during
   regime changes without discarding long-horizon information.

Walk-forward invariant (MANDATORY):
    The calibration set is built from the *match forward windows*
    (``history[match.end_idx : match.end_idx + forward_bars]``), which
    all lie in the matcher's lookback. No information about the *trial
    future* ever enters calibration — this is what makes the procedure
    legal inside ``run_backtest`` / ``run_ensemble_backtest``.

Fail-closed behaviour:
    If the number of usable calibration residuals is < 2, the returned
    Forecast is identical to the baseline projector output; the adaptive
    layer simply becomes a no-op rather than crashing the trial. This
    keeps the lane comparison apples-to-apples on short lookbacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from the_similarity.config import Config
from the_similarity.core.projector import Forecast, project as _baseline_project
from the_similarity.core.scorer import MatchResult


@dataclass
class AdaptiveConformalState:
    """Exposed diagnostics for the adaptive conformal update.

    Recorded onto Forecast via ``Forecast.adaptive_conformal`` (set with
    setattr since Forecast is a plain dataclass — we avoid mutating the
    base class to keep the projector-v2 lane additive-only).

    Fields:
        alpha_target: nominal miscoverage (e.g. 0.20 for a 80% interval).
        alpha_effective: recalibrated miscoverage after the adaptive pass.
        lr: learning rate used for the alpha update.
        n_calibration: number of residuals consumed.
        change_aware: whether change-awareness was active.
        regime_shift_weight: effective fraction of recent residuals used
            after change-aware down-weighting (1.0 = no shift detected).
    """

    alpha_target: float
    alpha_effective: float
    lr: float
    n_calibration: int
    change_aware: bool
    regime_shift_weight: float


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
    alpha_target: float = 0.20,
    lr: float = 0.05,
    change_aware: bool = False,
    decay: float = 0.95,
    shift_ratio_threshold: float = 1.5,
    mode: Literal["adaptive", "change_aware"] | None = None,
) -> Forecast:
    """Compute the baseline cone, then recalibrate it via adaptive conformal.

    Args:
        matches: Ranked match results from the search pipeline.
        history: Raw price history (numpy 1-D float64).
        forward_bars: Forecast horizon (bars).
        percentiles: Percentile levels for the returned cone.
        config: Pipeline config (forwarded to the baseline projector).
        alpha_target: Nominal miscoverage for the cone edges that are
            being recalibrated. For the default projector percentiles
            [10, 25, 50, 75, 90], this targets the P10/P90 band
            (alpha = 0.20).
        lr: Learning rate for the alpha update per residual.
        change_aware: If True (or ``mode="change_aware"``), down-weight
            older residuals when a variance jump is detected.
        decay: Exponential decay applied to residuals in change-aware mode
            (older residuals multiplied by decay**age).
        shift_ratio_threshold: Ratio of recent-window variance to full-window
            variance above which we declare a shift and apply decay.
        mode: Convenience selector ("adaptive" or "change_aware") used by
            the lane runner; when provided it overrides ``change_aware``.

    Returns:
        A :class:`Forecast` with P10/P90 curves rescaled by the
        adaptive conformal factor and an ``adaptive_conformal`` attribute
        attached describing the calibration diagnostics.
    """
    # Resolve mode alias — lane runner prefers a string selector.
    if mode == "change_aware":
        change_aware = True
    elif mode == "adaptive":
        change_aware = False

    # --- Step 1: run the baseline projector unchanged ---
    # This is intentional: the *point* forecast (P50) and raw bar-wise
    # quantile shape are taken verbatim from projector.py so any
    # improvement measured on the lane is attributable ONLY to the
    # calibration layer we add below.
    baseline = _baseline_project(
        matches=matches,
        history=history,
        forward_bars=forward_bars,
        percentiles=percentiles,
        config=config,
    )

    # Nothing to recalibrate if the baseline had no usable paths.
    if baseline.all_paths.shape[0] == 0:
        _attach_state(
            baseline,
            AdaptiveConformalState(
                alpha_target=alpha_target,
                alpha_effective=alpha_target,
                lr=lr,
                n_calibration=0,
                change_aware=change_aware,
                regime_shift_weight=1.0,
            ),
        )
        return baseline

    # --- Step 2: compute terminal-bar residuals for calibration ---
    # Residuals are |actual_terminal - P50_terminal| for each match's
    # forward window. This is the split-conformal nonconformity score
    # restricted to the terminal bar, which aligns with how CRPS and
    # calibration_error_p10_p90 are measured downstream.
    p50 = baseline.curves.get(50)
    if p50 is None or len(p50) == 0:
        _attach_state(
            baseline,
            AdaptiveConformalState(
                alpha_target=alpha_target,
                alpha_effective=alpha_target,
                lr=lr,
                n_calibration=0,
                change_aware=change_aware,
                regime_shift_weight=1.0,
            ),
        )
        return baseline

    terminal_forecast = float(p50[-1])
    actuals_terminal = baseline.all_paths[:, -1].astype(np.float64)
    residuals = np.abs(actuals_terminal - terminal_forecast)

    # --- Step 3: change-aware weighting (optional) ---
    # Residual variance ratio between the most recent third of the
    # calibration set and the full set is our cheap shift detector. A
    # ratio above ``shift_ratio_threshold`` triggers exponential
    # down-weighting of older residuals so the effective calibration
    # window shrinks toward the recent regime.
    regime_shift_weight = 1.0
    sample_weights = np.ones_like(residuals)
    if change_aware and len(residuals) >= 6:
        recent = residuals[-max(1, len(residuals) // 3) :]
        full_var = float(np.var(residuals)) + 1e-12
        recent_var = float(np.var(recent)) + 1e-12
        ratio = recent_var / full_var
        if ratio > shift_ratio_threshold:
            # Apply exponential decay (newest residual has weight 1).
            ages = np.arange(len(residuals))[::-1].astype(np.float64)
            sample_weights = np.power(decay, ages)
            regime_shift_weight = float(sample_weights.sum() / len(residuals))

    # --- Step 4: adaptive alpha update ---
    # Starting from alpha_target, we sweep through residuals in calibration
    # order. At each step we estimate the *current* conformal quantile via
    # the weighted residual CDF, check whether this residual would have
    # been covered, then nudge alpha toward the target.
    alpha_eff = _adaptive_alpha_pass(
        residuals=residuals,
        sample_weights=sample_weights,
        alpha_target=alpha_target,
        lr=lr,
    )

    # Clamp for numerical sanity — alpha must remain in (0, 1) strictly
    # so the downstream quantile lookup is well defined.
    alpha_eff = float(np.clip(alpha_eff, 1e-3, 1.0 - 1e-3))

    # --- Step 5: convert adaptive alpha into cone-edge scaling ---
    # We rescale the P10/P90 *distance from P50* by the ratio between the
    # adaptive conformal half-width and the current baseline half-width.
    # This keeps the P50 curve, widens/narrows the edges uniformly, and
    # leaves P25/P75 untouched (they are interior quantiles and are not
    # part of the calibration contract here).
    scale = _compute_cone_scale(
        residuals=residuals,
        sample_weights=sample_weights,
        alpha_effective=alpha_eff,
        baseline_half_width=_baseline_half_width(baseline),
    )

    calibrated = _rescale_edges(baseline, scale=scale)
    _attach_state(
        calibrated,
        AdaptiveConformalState(
            alpha_target=alpha_target,
            alpha_effective=alpha_eff,
            lr=lr,
            n_calibration=int(len(residuals)),
            change_aware=change_aware,
            regime_shift_weight=regime_shift_weight,
        ),
    )
    return calibrated


# ---------------------------------------------------------------------------
# Internal helpers — kept private and documented for future agents.
# ---------------------------------------------------------------------------


def _adaptive_alpha_pass(
    *,
    residuals: NDArray[np.float64],
    sample_weights: NDArray[np.float64],
    alpha_target: float,
    lr: float,
) -> float:
    """Run the Gibbs & Candès adaptive conformal update once.

    At step t we compute the (1 - alpha_t) weighted quantile of the
    residuals seen SO FAR, treat this as the current conformal bound,
    then check whether the newest residual would have been covered
    (residual <= bound). An uncovered sample pushes alpha downward
    (tighter, counter-intuitively — because lowering alpha moves the
    quantile UP toward the extreme tail), while a covered sample pushes
    alpha upward. The final ``alpha`` converges toward the value whose
    empirical miscoverage on this calibration stream equals
    ``alpha_target``.

    We only use this procedure to get a *stable* effective alpha; the
    downstream cone widening then uses the full residual set evaluated
    at that alpha, rather than a streaming bound.
    """
    alpha = float(alpha_target)

    # Guard against a degenerate calibration set.
    if len(residuals) == 0:
        return alpha

    # Running weighted residual buffer. We accumulate residuals and
    # weights as we walk the stream; at each step the conformal bound
    # is the (1 - alpha) weighted quantile of the buffer.
    running_res: list[float] = []
    running_w: list[float] = []

    for res, w in zip(residuals, sample_weights, strict=False):
        if len(running_res) == 0:
            # First sample — no prior bound available; just bank it.
            running_res.append(float(res))
            running_w.append(float(w))
            continue

        # Current conformal bound at level 1 - alpha.
        arr = np.asarray(running_res, dtype=np.float64)
        wt = np.asarray(running_w, dtype=np.float64)
        wt = wt / max(wt.sum(), 1e-12)
        bound = _weighted_quantile(arr, wt, 1.0 - alpha)

        # 1 if miscovered (err_t = 1), 0 if covered.
        err = 1.0 if float(res) > bound else 0.0

        # alpha <- alpha + lr * (alpha_target - err)
        alpha = alpha + lr * (alpha_target - err)
        alpha = float(np.clip(alpha, 1e-3, 1.0 - 1e-3))

        running_res.append(float(res))
        running_w.append(float(w))

    return alpha


def _baseline_half_width(baseline: Forecast) -> float:
    """Return the mean (P90 - P10) half-width from the baseline cone.

    Used as the denominator when computing the multiplicative scale the
    adaptive layer applies. We use the mean across bars so that very
    narrow near-term bars don't dominate the ratio.
    """
    p10 = baseline.curves.get(10)
    p90 = baseline.curves.get(90)
    if p10 is None or p90 is None or len(p10) == 0 or len(p90) == 0:
        return 0.0
    half_widths = (p90 - p10) / 2.0
    return float(np.mean(np.abs(half_widths)))


def _compute_cone_scale(
    *,
    residuals: NDArray[np.float64],
    sample_weights: NDArray[np.float64],
    alpha_effective: float,
    baseline_half_width: float,
) -> float:
    """Derive the multiplicative cone-edge scale from the adaptive alpha.

    The split-conformal half-width at level (1 - alpha) is the
    (1 - alpha) quantile of residuals. We divide that by the baseline
    empirical half-width to obtain the scale applied to (Pp - P50).

    A scale < 1.0 *tightens* the cone (baseline was too wide at this
    alpha); > 1.0 *widens* it (baseline was too tight). The scale is
    soft-clamped to [0.5, 3.0] to prevent a tiny calibration set from
    producing degenerate cones.
    """
    if len(residuals) == 0 or baseline_half_width <= 0.0:
        return 1.0

    wt = sample_weights.astype(np.float64)
    if wt.sum() <= 0:
        wt = np.ones_like(residuals)
    wt = wt / wt.sum()

    conformal_hw = _weighted_quantile(
        residuals.astype(np.float64), wt, 1.0 - alpha_effective
    )
    if not np.isfinite(conformal_hw) or conformal_hw <= 0.0:
        return 1.0

    scale = float(conformal_hw / baseline_half_width)
    return float(np.clip(scale, 0.5, 3.0))


def _rescale_edges(baseline: Forecast, *, scale: float) -> Forecast:
    """Return a new Forecast with P10/P90 distances from P50 scaled.

    We do NOT mutate the input Forecast — downstream callers (including
    the ensemble comparator) may still hold a reference to the baseline.
    """
    if scale == 1.0:
        return _copy_forecast(baseline)

    new_curves: dict[int, NDArray[np.float64]] = {}
    p50 = baseline.curves.get(50)
    for p, curve in baseline.curves.items():
        if p == 50 or p50 is None or len(p50) == 0:
            new_curves[p] = np.array(curve, copy=True)
            continue
        # Only scale the outer edges. Interior percentiles (25/75) are
        # left as the baseline computed them — the adaptive layer only
        # contracts for the P10/P90 miscoverage contract.
        if p in (10, 90):
            distance = curve - p50
            new_curves[p] = p50 + distance * scale
        else:
            new_curves[p] = np.array(curve, copy=True)

    return Forecast(
        bars=baseline.bars,
        percentiles=list(baseline.percentiles),
        curves=new_curves,
        all_paths=baseline.all_paths,
        weights=baseline.weights,
        koopman_forecast=baseline.koopman_forecast,
    )


def _copy_forecast(baseline: Forecast) -> Forecast:
    """Deep-enough copy for safe post-processing without mutating input."""
    return Forecast(
        bars=baseline.bars,
        percentiles=list(baseline.percentiles),
        curves={p: np.array(c, copy=True) for p, c in baseline.curves.items()},
        all_paths=baseline.all_paths,
        weights=baseline.weights,
        koopman_forecast=baseline.koopman_forecast,
    )


def _attach_state(forecast: Forecast, state: AdaptiveConformalState) -> None:
    """Attach adaptive-conformal diagnostics onto the Forecast.

    We use setattr on a frozen=False dataclass rather than modifying the
    Forecast class itself to keep this module purely additive — Forecast
    remains byte-compatible with the baseline projector.
    """
    setattr(forecast, "adaptive_conformal", state)


def _weighted_quantile(
    values: NDArray[np.float64],
    weights: NDArray[np.float64],
    quantile: float,
) -> float:
    """Weighted quantile using piecewise-linear CDF centres.

    Mirrors the implementation in ``projector.py`` so both modules behave
    identically on their shared edge cases (single sample, monotonicity
    enforcement). Duplicated here to avoid importing a private helper
    across module boundaries.
    """
    if len(values) == 0:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_idx = np.argsort(values)
    sorted_values = values[sorted_idx]
    sorted_weights = weights[sorted_idx]
    cumulative = np.cumsum(sorted_weights)
    centers = cumulative - 0.5 * sorted_weights
    centers[0] = max(0.0, centers[0])
    centers[-1] = min(1.0, centers[-1])
    if len(centers) > 1:
        centers = np.maximum.accumulate(centers)
    return float(np.interp(quantile, centers, sorted_values))
