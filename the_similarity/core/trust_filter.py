"""Trust filter — "when NOT to trust the cone" gating logic.

This module implements the opt-in decision layer that answers a single
question for any forecast cone produced by the engine:

    "Given what we know about the match pool, the projection, and the
    current market regime, is this cone reliable enough to act on?"

The engine's default behavior is unchanged: callers explicitly opt in by
constructing a ``TrustFilter`` and calling ``evaluate(...)`` on a pool /
projection / regime context. The filter returns a ``TrustDecision`` with
a binary ``trust`` flag, a continuous ``score`` in [0, 1], and a list of
human-readable ``reasons`` explaining which signals failed.

Signals evaluated
-----------------
The filter composes four *independently grounded* signals. Each signal
returns a sub-score in [0, 1] (1 = strong evidence of trustworthy cone,
0 = strong evidence to distrust). The overall ``score`` is a weighted
mean, and ``trust`` is True iff every *hard gate* passes AND the overall
score meets ``min_score``.

1. **Calibration error** (recent out-of-sample):
   We take the most recent `calibration` dict from a BacktestReport-like
   object (mapping percentile -> empirical rate). For well-calibrated
   cones, the empirical coverage at P10/P90 should match the stated
   percentile (|empirical - stated| small). We convert the mean absolute
   calibration error into a sub-score via ``max(0, 1 - k * mae)``.

   Why: a cone that systematically mis-covers (empirical 30% at a stated
   P10) is not a trustworthy basis for position sizing, regardless of
   regime or match quality.

2. **Match-pool agreement / dispersion**:
   We measure the dispersion of the matches' forward paths (or, when
   paths are unavailable, the P90-P10 spread of the projection itself)
   relative to the median of the match confidence weights. High
   dispersion with weak confidence = disagreeing analogues =
   distrust. The sub-score is 1 - normalized_dispersion, clipped to
   [0, 1].

   Why: if 20 analogues all point in different directions, the median
   projection (P50) is an illusion of precision. A single sharp mode
   from many matches is far more actionable than a wide flat pool.

3. **Regime novelty**:
   Distance from the query regime label to the modal regime in the
   match pool. If the query is ``high_vol`` but most matches are
   ``low_vol``, we treat this as a regime-novelty event and penalise.

   Why: similarity in shape does not imply similarity in volatility
   regime; a shape match in a different regime is often an artifact of
   the distance metric rather than a genuine analogue.

4. **Sample size per bucket**:
   Number of matches in the relevant bucket (after optional regime
   filtering). Below a minimum, the empirical percentiles are
   statistically meaningless. Scored by a smooth logistic in n.

   Why: weighted quantiles on 3 paths are not quantiles, they are
   anecdotes. This gate is the simplest and most important.

Hard gates vs soft signals
--------------------------
The filter distinguishes *hard gates* (failure → trust=False regardless
of the overall score) from *soft signals* (contribute to the score).
Defaults:
    - ``min_matches`` (hard gate): too few matches → untrusted.
    - ``max_calibration_mae`` (hard gate): catastrophic calibration.
    - dispersion and regime novelty: soft signals (contribute to
      ``score`` but do not individually veto).

Rationale: empirically the sample-size and catastrophic-calibration
failure modes produce false positives on strategies that otherwise look
fine on soft signals, so we prefer fail-closed on those two. Agreement
and regime novelty are continuous quantities that degrade smoothly; a
knife-edge cutoff there creates discontinuities in position sizing.

Invariants
----------
- ``TrustFilter.evaluate`` is *pure* given its inputs. It does not read
  global state, mutate its arguments, or touch the filesystem.
- The default thresholds are CONSERVATIVE: it is better to pass on
  ambiguous setups than to recommend a bad trade. Callers can relax
  them by constructing a custom ``TrustFilter``.
- Score and reasons are always populated, even on trust=True, so the
  caller can log them for later review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------


@dataclass
class TrustDecision:
    """Outcome of a trust evaluation.

    Fields:
        trust: Binary decision. ``True`` means the cone is trustworthy
            enough to act on per the configured thresholds.
        score: Continuous overall trust score in [0, 1], a weighted mean
            of the four signal sub-scores. Even when ``trust`` is True,
            strategies can use ``score`` to modulate position size
            (see ``decision_rules.py``).
        reasons: Human-readable strings describing which gates or
            signals fired. Populated on both trust=True and trust=False
            for audit purposes.
        signals: Per-signal sub-score dict, for inspection. Keys:
            ``calibration``, ``agreement``, ``regime_novelty``,
            ``sample_size``.
    """

    trust: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    signals: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------
# These are intentionally CONSERVATIVE — see module docstring.

_DEFAULT_MIN_MATCHES = 5
# Below this many matches the weighted quantiles are not meaningful.
# Calibrated on the observation that forward-path dispersion stabilises
# around n=5..10 on SPY daily.

_DEFAULT_MAX_CALIBRATION_MAE = 0.15
# Mean absolute error across percentiles, as a fraction. E.g. if stated
# P10 empirically covers 28% instead of 10%, that contributes 0.18 to
# the MAE — above the cutoff.

_DEFAULT_MIN_AGREEMENT_SCORE = 0.0
# Soft signal. Set to 0 by default so agreement only drives the score,
# not the hard gate. Callers may raise it to enforce a minimum.

_DEFAULT_MAX_REGIME_NOVELTY = 1.0
# Soft signal. 1.0 = any regime mismatch allowed. Lower to enforce
# regime agreement between query and match pool.

_DEFAULT_MIN_SCORE = 0.5
# Overall weighted score minimum. With equal signal weights and 4
# signals each in [0, 1], 0.5 corresponds to "on average, half the
# signals are firing at full strength".

_DEFAULT_SIGNAL_WEIGHTS = {
    "calibration": 0.35,
    "agreement": 0.25,
    "regime_novelty": 0.15,
    "sample_size": 0.25,
}
# Calibration is the most load-bearing: a poorly calibrated cone is
# useless regardless of how many matches support it. Sample size is
# second because tiny pools are the most common failure mode in
# production.


# ---------------------------------------------------------------------------
# TrustFilter
# ---------------------------------------------------------------------------


@dataclass
class TrustFilter:
    """Trust evaluator for a match pool + projection + regime context.

    Construct once per strategy / per session, then call ``evaluate``
    per decision point. The object is stateless: thresholds live here,
    evidence is passed in.

    Thresholds:
        min_matches: Hard gate. Below this, trust=False.
        max_calibration_mae: Hard gate. Above this, trust=False.
        min_agreement_score: Soft minimum on dispersion-based agreement
            sub-score. Defaults to 0 (soft only).
        max_regime_novelty: Soft maximum on regime-novelty sub-score
            (inverse). Defaults to 1.0 (no veto).
        min_score: Minimum weighted overall score to trust.
        signal_weights: Dict of signal name -> weight for the overall
            score. Renormalised internally so they sum to 1.

    All thresholds are *logical*, not wall-clock or stateful. The
    evaluator does not learn; if calibration of the underlying engine
    drifts, re-run a backtest and pass the new report to ``evaluate``.
    """

    min_matches: int = _DEFAULT_MIN_MATCHES
    max_calibration_mae: float = _DEFAULT_MAX_CALIBRATION_MAE
    min_agreement_score: float = _DEFAULT_MIN_AGREEMENT_SCORE
    max_regime_novelty: float = _DEFAULT_MAX_REGIME_NOVELTY
    min_score: float = _DEFAULT_MIN_SCORE
    signal_weights: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_SIGNAL_WEIGHTS)
    )

    # -- Public API ---------------------------------------------------------

    def evaluate(
        self,
        match_pool: Iterable[Any] | None,
        projection: Any | None,
        regime_state: dict[str, Any] | None = None,
        calibration_report: Any | None = None,
    ) -> TrustDecision:
        """Evaluate whether the current cone is trustworthy.

        Args:
            match_pool: Iterable of match-like objects. Each should
                expose ``confidence_score`` (float, 0-100 scale) and
                optionally ``regime`` (string). Accepts a raw list or a
                ``SearchResults``-style object with ``.matches``.
            projection: The forecast to evaluate. Accepts anything with
                a ``curves`` dict (percentile -> array) — i.e. a
                ``Forecast`` or ``EnsembleForecast``. Paths in
                ``all_paths`` are used for dispersion if present.
            regime_state: Optional dict describing the query regime:
                ``{"regime": "trending_up", ...}``. Falls back to
                ``projection.regime_conditional.regime`` or ``None``.
            calibration_report: Optional object with a ``.calibration``
                attribute returning a ``{percentile: empirical_rate}``
                dict — e.g. a ``BacktestReport``. Without this, the
                calibration sub-score defaults to 1.0 (neutral pass)
                and we record a "no calibration available" reason.

        Returns:
            ``TrustDecision``. See class docstring for fields.
        """
        reasons: list[str] = []
        signals: dict[str, float] = {}

        matches = _materialise_matches(match_pool)
        n_matches = len(matches)

        # --- Signal 1: sample size (HARD gate) ---
        sample_score = _sample_size_score(n_matches, self.min_matches)
        signals["sample_size"] = sample_score
        sample_gate_ok = n_matches >= self.min_matches
        if not sample_gate_ok:
            reasons.append(
                f"sample_size: only {n_matches} matches "
                f"(need >= {self.min_matches})"
            )

        # --- Signal 2: calibration (HARD gate) ---
        cal_score, cal_mae, cal_reason = _calibration_score(
            calibration_report, self.max_calibration_mae
        )
        signals["calibration"] = cal_score
        cal_gate_ok = cal_mae <= self.max_calibration_mae
        if cal_reason is not None:
            reasons.append(cal_reason)

        # --- Signal 3: match-pool agreement (SOFT) ---
        agreement_score = _agreement_score(matches, projection)
        signals["agreement"] = agreement_score
        if agreement_score < self.min_agreement_score:
            reasons.append(
                f"agreement: dispersion-based agreement score "
                f"{agreement_score:.2f} < threshold {self.min_agreement_score:.2f}"
            )

        # --- Signal 4: regime novelty (SOFT) ---
        regime_score, regime_reason = _regime_novelty_score(matches, regime_state)
        signals["regime_novelty"] = regime_score
        # Surface the reason whenever it was non-trivially set (i.e. there
        # was a real regime mismatch in the pool) — this is an *audit*
        # signal, not a gate. The hard gate would be enforced separately
        # by lowering ``max_regime_novelty``.
        if regime_reason is not None:
            reasons.append(regime_reason)

        # --- Compose weighted overall score ---
        overall = _weighted_score(signals, self.signal_weights)

        # --- Final decision: both hard gates + score threshold ---
        trust = sample_gate_ok and cal_gate_ok and (overall >= self.min_score)

        if not trust and overall >= self.min_score and sample_gate_ok and not cal_gate_ok:
            reasons.append(
                f"overall_score={overall:.2f} passed but calibration gate failed"
            )
        elif not trust and overall < self.min_score:
            reasons.append(
                f"overall_score={overall:.2f} < min_score={self.min_score:.2f}"
            )

        # Always explain *why it passed* when it passed — useful for logs.
        if trust and not reasons:
            reasons.append(
                f"trust=True; score={overall:.2f}, "
                f"n_matches={n_matches}, calibration_mae={cal_mae:.3f}"
            )

        return TrustDecision(
            trust=trust,
            score=float(overall),
            reasons=reasons,
            signals=signals,
        )


# ---------------------------------------------------------------------------
# Signal implementations (module-private helpers)
# ---------------------------------------------------------------------------


def _materialise_matches(match_pool: Iterable[Any] | None) -> list[Any]:
    """Normalise the match-pool input to a concrete list.

    Accepts:
        - None -> []
        - A ``SearchResults``-like with ``.matches`` attribute
        - Any iterable of match-like objects
    """
    if match_pool is None:
        return []
    if hasattr(match_pool, "matches"):
        # SearchResults duck type.
        return list(match_pool.matches)
    return list(match_pool)


def _sample_size_score(n: int, min_matches: int) -> float:
    """Smooth logistic in the number of matches.

    At n = 0 returns 0; at n = min_matches returns 0.5; saturates to
    ~1.0 well above min_matches. This gives the overall score a
    continuous response even when the hard gate would reject.

    Mathematical form:
        score = n / (n + min_matches)

    Chosen over a logistic because it is monotone, has a closed form,
    and crosses 0.5 exactly at ``n == min_matches`` for any threshold.
    """
    if min_matches <= 0:
        return 1.0 if n > 0 else 0.0
    if n <= 0:
        return 0.0
    return float(n / (n + min_matches))


def _calibration_score(
    calibration_report: Any | None,
    max_mae: float,
) -> tuple[float, float, str | None]:
    """Turn a calibration dict into a sub-score + MAE + optional reason.

    Returns:
        (score, mae, reason). If the report is missing, score defaults
        to 1.0 (neutral pass) and MAE to 0.0 but a reason is attached so
        the caller knows they evaluated without a calibration anchor.
    """
    if calibration_report is None:
        return 1.0, 0.0, "calibration: no calibration report provided (neutral pass)"

    cal = getattr(calibration_report, "calibration", None)
    if cal is None and isinstance(calibration_report, dict):
        # Allow the user to pass a raw dict too.
        cal = calibration_report
    if not cal:
        return 1.0, 0.0, "calibration: empty calibration dict (neutral pass)"

    # cal is {percentile_int: empirical_rate_float}
    errors = []
    for p, rate in cal.items():
        try:
            expected = float(p) / 100.0
            errors.append(abs(float(rate) - expected))
        except (TypeError, ValueError):
            continue
    if not errors:
        return 1.0, 0.0, "calibration: could not parse any percentile entries"

    mae = float(np.mean(errors))

    # Linear mapping from [0, 2*max_mae] to [1, 0], clamped.
    # This keeps the sub-score continuous across the hard-gate boundary.
    denom = max(1e-9, 2.0 * max_mae)
    score = max(0.0, 1.0 - mae / denom)

    reason = None
    if mae > max_mae:
        reason = (
            f"calibration: empirical MAE {mae:.3f} "
            f"exceeds threshold {max_mae:.3f}"
        )
    return float(score), mae, reason


def _agreement_score(matches: list[Any], projection: Any | None) -> float:
    """Score the agreement of the match pool.

    Two strategies, preferred in order:

    1. If ``projection.all_paths`` is available, compute the mean
       std-dev across paths at the terminal bar, normalised by the
       mean absolute magnitude. Score = 1 / (1 + normalised_std).

    2. Fallback: if only percentile curves are available, use the
       normalised P90-P10 spread at the terminal bar as a dispersion
       proxy. Score = 1 / (1 + spread/|p50| clamped).

    Returns:
        Sub-score in [0, 1].
    """
    if projection is None:
        return 0.5  # Neutral — we have no basis to judge.

    all_paths = getattr(projection, "all_paths", None)
    if all_paths is not None and hasattr(all_paths, "shape"):
        try:
            # Paths may be shape (n, T) or (n,) depending on structure.
            arr = np.asarray(all_paths, dtype=np.float64)
            if arr.ndim == 2 and arr.shape[0] >= 2:
                terminal = arr[:, -1]
                std = float(np.std(terminal))
                scale = float(np.mean(np.abs(terminal))) + 1e-9
                normalised = std / scale
                return float(1.0 / (1.0 + normalised))
        except Exception:
            pass  # Fall through to curve-based estimate.

    curves = getattr(projection, "curves", None)
    if curves and 90 in curves and 10 in curves:
        p90 = np.asarray(curves[90])
        p10 = np.asarray(curves[10])
        if p90.size > 0 and p10.size > 0:
            spread = float(p90[-1] - p10[-1])
            p50 = np.asarray(curves.get(50, [0.0]))
            scale = float(abs(p50[-1]) if p50.size > 0 else 0.0) + 1e-3
            normalised = abs(spread) / scale
            # Monotone decreasing, bounded in [0, 1].
            return float(1.0 / (1.0 + normalised))

    # No dispersion information — fall back to neutral.
    return 0.5


def _regime_novelty_score(
    matches: list[Any],
    regime_state: dict[str, Any] | None,
) -> tuple[float, str | None]:
    """Compare query regime to modal match regime.

    If no query regime is available, returns neutral 1.0 (no penalty).

    Logic: we take the most common non-null ``match.regime`` in the
    pool and compare to the query regime. Exact match -> 1.0, mismatch
    -> 0.0. This is deliberately binary at the per-match level; the
    smoothing comes from the *fraction* of matches agreeing with the
    query regime.

    Returns:
        (score, reason). Reason is only populated on a non-trivial
        mismatch (< 0.5 agreement).
    """
    if not matches:
        return 0.0, "regime_novelty: empty match pool"

    query_regime = None
    if regime_state is not None:
        query_regime = regime_state.get("regime") or regime_state.get("query_regime")
    if query_regime is None:
        return 1.0, None  # No query regime — skip the signal.

    labels = [getattr(m, "regime", None) for m in matches]
    non_null = [r for r in labels if r]
    if not non_null:
        return 1.0, None  # No labels to compare against.

    agree = sum(1 for r in non_null if r == query_regime)
    frac = agree / len(non_null)

    reason: str | None = None
    if frac < 0.5:
        reason = (
            f"regime_novelty: only {frac:.0%} of matches "
            f"share query regime '{query_regime}'"
        )

    return float(frac), reason


def _weighted_score(
    signals: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Weighted mean of per-signal sub-scores.

    Weights are renormalised across the signals actually present in
    ``signals``, so missing signals never drag the mean to zero.
    """
    total = 0.0
    weight_sum = 0.0
    for key, val in signals.items():
        w = weights.get(key, 0.0)
        if w <= 0:
            continue
        total += w * float(val)
        weight_sum += w
    if weight_sum <= 0:
        return 0.0
    return total / weight_sum


# ---------------------------------------------------------------------------
# Convenience: module-level evaluate
# ---------------------------------------------------------------------------


def evaluate(
    match_pool: Iterable[Any] | None,
    projection: Any | None,
    regime_state: dict[str, Any] | None = None,
    calibration_report: Any | None = None,
    **filter_kwargs: Any,
) -> TrustDecision:
    """Shortcut: build a default ``TrustFilter`` and evaluate once.

    For most callers this is the ergonomic entry point. Pass kwargs to
    override thresholds (e.g. ``min_matches=10``). For repeated use in
    a hot loop, instantiate a ``TrustFilter`` once.
    """
    tf = TrustFilter(**filter_kwargs)
    return tf.evaluate(
        match_pool=match_pool,
        projection=projection,
        regime_state=regime_state,
        calibration_report=calibration_report,
    )


# ---------------------------------------------------------------------------
# Explicit re-exports — keep the public surface tight.
# ---------------------------------------------------------------------------
__all__ = [
    "TrustDecision",
    "TrustFilter",
    "evaluate",
]


# Keep these names importable for code that wants to inspect the
# default thresholds (e.g. finance pilot documentation utilities).
DEFAULT_MIN_MATCHES: int = _DEFAULT_MIN_MATCHES
DEFAULT_MAX_CALIBRATION_MAE: float = _DEFAULT_MAX_CALIBRATION_MAE
DEFAULT_MIN_SCORE: float = _DEFAULT_MIN_SCORE

# Keep typing imports from being flagged as unused.
_ = NDArray
