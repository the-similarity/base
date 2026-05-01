"""Calibration-aware decision rules for strategies consuming a projection.

This module is the *decision layer* on top of ``strategy.py``. A plain
``Strategy`` converts matches + forecast into ``Signal`` objects that
express direction and target levels. A ``CalibrationAwareStrategy`` adds
three things on top:

1. **Trust-aware gating**: a ``TrustFilter`` evaluates the cone and can
   veto a signal entirely (``signal_type=FLAT`` with reason).
2. **Percentile-threshold entries**: entries require
   ``P_{percentile} * direction > threshold``. Defaults check the
   conservative tail (P25 for longs, P75 for shorts) rather than the
   median — "does the 25th-percentile outcome still clear our minimum
   expected return?"
3. **Confidence-scaled position sizing**: the engine emits a
   ``position_size`` field in [0, 1] that scales with
   ``trust_score * confidence_weight``. Downstream execution can
   multiply this by the operator's risk budget.

The module stays purely additive: existing ``evaluate_strategy`` and
``validate_strategy_backtest`` are untouched; callers opt in by using
the ``CalibrationAwareStrategy`` wrapper or ``evaluate_with_trust``
function.

Invariants
----------
- ``evaluate_with_trust`` is pure: no I/O, no mutation of inputs.
- A FLAT signal is always emitted when the trust filter vetoes — this
  makes the audit trail explicit rather than silently suppressing the
  signal.
- ``position_size`` is clamped to [0, 1]. Callers must scale by their
  capital allocation; this module NEVER references dollar amounts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from the_similarity.core.projector import Forecast
from the_similarity.core.ensemble import EnsembleForecast
from the_similarity.core.dynamic_sizing import DynamicSizingPolicy, SizingState
from the_similarity.core.scorer import MatchResult
from the_similarity.core.strategy import (
    Signal,
    SignalType,
    Strategy,
    evaluate_strategy,
)
from the_similarity.core.trust_filter import (
    TrustDecision,
    TrustFilter,
)


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------


@dataclass
class CalibrationAwareSignal:
    """Trust-aware wrapper around a base ``Signal``.

    Fields:
        base: The underlying Signal produced by the wrapped Strategy.
            For a vetoed trade this is synthesized with FLAT direction
            and a ``reason`` documenting the veto.
        trust: The ``TrustDecision`` from the trust filter for this
            decision point. Always populated (even on FLAT).
        position_size: Suggested position size in [0, 1], where 1.0
            means "full risk budget". Always 0.0 when trust.trust is
            False.
        threshold_met: Whether the percentile threshold (e.g. P25>0 for
            long) was satisfied at decision time. Included so the
            caller can distinguish "thresholds failed" from "trust
            failed".
        review_notes: Free-form strings that combine the Strategy rule
            name, trust reasons, and threshold outcome. This is the
            audit artifact for the review step of the workflow.
    """

    base: Signal
    trust: TrustDecision
    position_size: float
    threshold_met: bool
    review_notes: list[str] = field(default_factory=list)

    # -- Convenience accessors ---------------------------------------------

    @property
    def signal_type(self) -> SignalType:
        """Pass-through to the wrapped Signal's type."""
        return self.base.signal_type

    @property
    def confidence(self) -> float:
        """Match confidence [0, 100] from the base signal."""
        return self.base.confidence

    @property
    def trusted(self) -> bool:
        """Shortcut: trust decision's binary flag."""
        return self.trust.trust


@dataclass
class DecisionRuleConfig:
    """Parameters controlling calibration-aware rule behavior.

    Separate from Strategy so users can reuse one config across many
    strategies and change gating behavior without touching rules.

    Fields:
        entry_percentile: Which percentile level must clear the
            threshold for a LONG entry (e.g. 25 = "the P25 outcome must
            still be above threshold"). For SHORT entries the symmetric
            percentile (100 - entry_percentile) is used.
        entry_threshold: Minimum return magnitude at the entry
            percentile. E.g. 0.01 = "P25 cumulative return must be at
            least +1% to go long, or -1% to go short".
        min_position_size: Floor on position size for trusted trades.
            Prevents the trust score from producing effectively-zero
            size on edge-of-threshold setups.
        max_position_size: Ceiling on position size.
        veto_on_distrust: If True (default), a ``trust=False`` decision
            replaces any LONG/SHORT signal with FLAT. If False, the
            signal is preserved but ``position_size`` is set to 0.
        dynamic_sizing_policy: Optional finite-action policy. When present,
            trusted signals use the policy's utility maximization instead of
            the legacy linear trust-confidence size formula.
    """

    entry_percentile: int = 25
    entry_threshold: float = 0.005
    min_position_size: float = 0.1
    max_position_size: float = 1.0
    veto_on_distrust: bool = True
    dynamic_sizing_policy: DynamicSizingPolicy | None = None
    current_position_size: float = 0.0
    drawdown: float = 0.0
    calibration_error: float = 0.0


# ---------------------------------------------------------------------------
# Core rule evaluator
# ---------------------------------------------------------------------------


def evaluate_with_trust(
    strategy: Strategy,
    matches: list[MatchResult],
    history: NDArray[np.float64],
    forecast: Forecast | EnsembleForecast | None = None,
    current_price: float | None = None,
    trust_filter: TrustFilter | None = None,
    calibration_report: Any | None = None,
    regime_state: dict[str, Any] | None = None,
    decision_config: DecisionRuleConfig | None = None,
) -> list[CalibrationAwareSignal]:
    """Run a Strategy and then gate its signals with the trust filter.

    The algorithm:
      1. Call the plain ``evaluate_strategy`` to get base signals.
      2. Evaluate the trust filter against the match pool + projection.
      3. For each base signal:
           a. Check the percentile threshold (``P_k * dir > threshold``).
           b. If the trust gate vetoed OR the percentile threshold
              failed, the output is either a FLAT signal (veto_on_distrust)
              or the original signal with position_size=0.
           c. Otherwise, compute position_size =
              min_position_size + (max - min) * trust.score * (confidence/100).
      4. Emit a CalibrationAwareSignal per input signal, always
         including the full trust.reasons + threshold outcome.

    Args:
        strategy: Base Strategy (any Rule list; see strategy.py).
        matches: Ranked match results.
        history: Full raw price history.
        forecast: Optional projection to evaluate threshold against.
        current_price: Optional override; defaults to history[-1].
        trust_filter: Injected TrustFilter. If None, a default is used.
        calibration_report: Optional BacktestReport-like for the
            calibration signal.
        regime_state: Optional {"regime": "..."} for regime novelty.
        decision_config: Threshold + sizing config. Defaults applied
            if None.

    Returns:
        One ``CalibrationAwareSignal`` per base signal. Empty list if
        the base strategy emits nothing.
    """
    if trust_filter is None:
        trust_filter = TrustFilter()
    if decision_config is None:
        decision_config = DecisionRuleConfig()

    base_signals = evaluate_strategy(
        strategy=strategy,
        matches=matches,
        history=history,
        forecast=forecast,
        current_price=current_price,
    )
    if not base_signals:
        # No signals from the underlying strategy — the filter is moot,
        # return an empty list (callers can short-circuit).
        return []

    trust = trust_filter.evaluate(
        match_pool=matches,
        projection=forecast,
        regime_state=regime_state,
        calibration_report=calibration_report,
    )

    curves = getattr(forecast, "curves", {}) if forecast is not None else {}

    wrapped: list[CalibrationAwareSignal] = []
    for sig in base_signals:
        threshold_met, threshold_note = _check_percentile_threshold(
            signal_type=sig.signal_type,
            curves=curves,
            entry_percentile=decision_config.entry_percentile,
            entry_threshold=decision_config.entry_threshold,
        )

        review_notes = [
            f"rule={sig.reason}",
            threshold_note,
            f"trust.score={trust.score:.3f}",
        ]
        review_notes.extend(trust.reasons)

        size = _compute_position_size(
            trust=trust,
            confidence=sig.confidence,
            threshold_met=threshold_met,
            decision_config=decision_config,
            signal_type=sig.signal_type,
            forecast=forecast,
        )

        # Apply the veto policy: trust failure OR threshold failure
        # collapses a directional signal to FLAT (or size=0 if
        # veto_on_distrust is False).
        effective_signal = sig
        if not trust.trust or not threshold_met:
            size = 0.0
            if decision_config.veto_on_distrust:
                effective_signal = Signal(
                    signal_type=SignalType.FLAT,
                    confidence=sig.confidence,
                    entry_price=sig.entry_price,
                    stop_loss=None,
                    take_profit=None,
                    reason=(
                        f"vetoed: trust={trust.trust}, "
                        f"threshold_met={threshold_met} (orig rule: {sig.reason})"
                    ),
                    match=sig.match,
                    forecast=sig.forecast,
                )

        wrapped.append(
            CalibrationAwareSignal(
                base=effective_signal,
                trust=trust,
                position_size=size,
                threshold_met=threshold_met,
                review_notes=review_notes,
            )
        )

    return wrapped


# ---------------------------------------------------------------------------
# Calibration-aware strategy wrapper
# ---------------------------------------------------------------------------


@dataclass
class CalibrationAwareStrategy:
    """Strategy adapter that forces all evaluations through the trust filter.

    Lifecycle:
        Construct once per strategy / session, passing a ``Strategy``,
        a pre-configured ``TrustFilter`` (or accept defaults), and an
        optional ``calibration_report``. Call ``evaluate(...)`` per
        decision point.

    This is intentionally thin. It holds configuration, not state —
    there is nothing to "reset", and instances are safe to share across
    threads.

    Fields:
        base_strategy: Underlying rule-based ``Strategy``.
        trust_filter: The filter to gate each evaluation.
        decision_config: Threshold + sizing parameters.
        calibration_report: Optional report for the trust filter's
            calibration signal. May be None during cold start.
    """

    base_strategy: Strategy
    trust_filter: TrustFilter = field(default_factory=TrustFilter)
    decision_config: DecisionRuleConfig = field(default_factory=DecisionRuleConfig)
    calibration_report: Any | None = None

    def evaluate(
        self,
        matches: list[MatchResult],
        history: NDArray[np.float64],
        forecast: Forecast | EnsembleForecast | None = None,
        current_price: float | None = None,
        regime_state: dict[str, Any] | None = None,
    ) -> list[CalibrationAwareSignal]:
        """Delegate to ``evaluate_with_trust`` with the stored config."""
        return evaluate_with_trust(
            strategy=self.base_strategy,
            matches=matches,
            history=history,
            forecast=forecast,
            current_price=current_price,
            trust_filter=self.trust_filter,
            calibration_report=self.calibration_report,
            regime_state=regime_state,
            decision_config=self.decision_config,
        )

    def with_report(self, calibration_report: Any) -> "CalibrationAwareStrategy":
        """Return a copy bound to a new calibration report.

        Use after running a fresh backtest to rebind the filter to the
        latest empirical calibration without mutating the original
        instance (preserves immutability semantics).
        """
        return CalibrationAwareStrategy(
            base_strategy=self.base_strategy,
            trust_filter=self.trust_filter,
            decision_config=self.decision_config,
            calibration_report=calibration_report,
        )


# ---------------------------------------------------------------------------
# Review summary
# ---------------------------------------------------------------------------


@dataclass
class ReviewSummary:
    """Human-readable summary of a decision point.

    This is the "review" step in the workflow: search -> projection ->
    decision -> review. Emit one per evaluation; persist alongside
    executions for audit.
    """

    signals: list[CalibrationAwareSignal]
    n_matches: int
    trust_score: float
    trust: bool
    top_reasons: list[str]

    def to_text(self) -> str:
        """Render to a plain-text block suitable for logs / tickets."""
        direction_counts = {"long": 0, "short": 0, "flat": 0}
        sized = 0.0
        for s in self.signals:
            direction_counts[s.signal_type.value] += 1
            sized += s.position_size
        lines = [
            "ReviewSummary",
            f"  n_matches = {self.n_matches}",
            f"  trust = {self.trust}  score = {self.trust_score:.3f}",
            f"  signals: long={direction_counts['long']} "
            f"short={direction_counts['short']} flat={direction_counts['flat']}",
            f"  aggregate position size = {sized:.3f}",
            "  reasons:",
        ]
        for r in self.top_reasons:
            lines.append(f"    - {r}")
        return "\n".join(lines)


def summarise_review(
    signals: list[CalibrationAwareSignal],
    n_matches: int,
) -> ReviewSummary:
    """Build a ReviewSummary from a list of CalibrationAwareSignals.

    If no signals were produced (empty list), returns a summary with
    trust inferred as False and a single explanatory reason.
    """
    if not signals:
        return ReviewSummary(
            signals=[],
            n_matches=n_matches,
            trust_score=0.0,
            trust=False,
            top_reasons=["no base signals emitted by strategy"],
        )

    # All signals share the same trust decision (single evaluation per
    # call), so read from the first.
    primary = signals[0].trust
    return ReviewSummary(
        signals=signals,
        n_matches=n_matches,
        trust_score=primary.score,
        trust=primary.trust,
        top_reasons=list(primary.reasons),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _check_percentile_threshold(
    signal_type: SignalType,
    curves: dict[int, NDArray[np.float64]] | dict,
    entry_percentile: int,
    entry_threshold: float,
) -> tuple[bool, str]:
    """Check whether the configured tail percentile clears the threshold.

    Semantics:
        LONG:  P{entry_percentile}[-1] >= +entry_threshold
        SHORT: P{100-entry_percentile}[-1] <= -entry_threshold
        FLAT:  always True (nothing to gate).

    If the requested percentile is not in ``curves``, the threshold is
    treated as FAILED (fail-closed) — we cannot verify the tail, so we
    do not permit the entry.
    """
    if signal_type == SignalType.FLAT:
        return True, "threshold: FLAT signal (gate skipped)"

    p_key: int
    direction: int
    if signal_type == SignalType.LONG:
        p_key = entry_percentile
        direction = 1
    else:
        p_key = 100 - entry_percentile
        direction = -1

    curve = curves.get(p_key) if curves else None
    if curve is None or len(curve) == 0:
        return (
            False,
            f"threshold: P{p_key} unavailable in forecast (fail-closed)",
        )

    endpoint = float(curve[-1])
    effective = endpoint * direction
    met = effective >= entry_threshold
    return (
        met,
        f"threshold: P{p_key} endpoint={endpoint:+.4f}, "
        f"direction={direction}, required>={entry_threshold}, met={met}",
    )


def _compute_position_size(
    trust: TrustDecision,
    confidence: float,
    threshold_met: bool,
    decision_config: DecisionRuleConfig,
    signal_type: SignalType = SignalType.FLAT,
    forecast: Forecast | EnsembleForecast | None = None,
) -> float:
    """Scale position size by trust score * (confidence/100).

    Semantics:
        size = min + (max - min) * trust.score * (confidence / 100)

    If trust is False or threshold is not met, size is 0 (the calling
    code applies this policy; this helper computes the POSITIVE size).
    The formula is deliberately multiplicative so that either a weak
    trust score OR a weak match confidence suppresses the size
    proportionally.
    """
    if not trust.trust or not threshold_met:
        return 0.0

    if decision_config.dynamic_sizing_policy is not None:
        decision = decision_config.dynamic_sizing_policy.choose_size(
            signal_type=signal_type,
            forecast=forecast,
            state=SizingState(
                trust_score=trust.score,
                confidence=confidence,
                current_position_size=decision_config.current_position_size,
                drawdown=decision_config.drawdown,
                calibration_error=decision_config.calibration_error,
            ),
            min_position_size=decision_config.min_position_size,
            max_position_size=decision_config.max_position_size,
        )
        return decision.size

    conf01 = max(0.0, min(1.0, float(confidence) / 100.0))
    raw = (
        decision_config.min_position_size
        + (decision_config.max_position_size - decision_config.min_position_size)
        * float(trust.score)
        * conf01
    )
    return float(
        max(
            decision_config.min_position_size
            if (trust.trust and threshold_met)
            else 0.0,
            min(decision_config.max_position_size, raw),
        )
    )


__all__ = [
    "CalibrationAwareSignal",
    "CalibrationAwareStrategy",
    "DecisionRuleConfig",
    "DynamicSizingPolicy",
    "ReviewSummary",
    "SizingState",
    "evaluate_with_trust",
    "summarise_review",
]
