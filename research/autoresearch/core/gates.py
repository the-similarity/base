"""Declarative keep/discard gates for autoresearch lanes.

Before this module each lane hard-coded its decision logic inside its
own ``compare.py`` or sweep runner. That worked with three lanes; at
the Phase 2 target of 5+ lanes it becomes an accountability hole —
there is no one place to read "what thresholds did we decide on?".

This module solves that by making gates *data*, not control flow. Lanes
declare a list of :class:`Gate` instances (threshold + direction +
required flag), call :func:`evaluate_gates` with their deltas, and
receive a :class:`GateDecision` that records which gate passed and
why. The canonical report renderer consumes :class:`GateDecision`
directly so every lane's verdict surface looks identical.

Gate semantics
--------------
* ``required=True`` gates must ALL pass for the decision to ``keep``.
  A single required failure flips the decision to ``discard`` with a
  reason string.
* ``required=False`` (advisory) gates are reported but do not block the
  decision. They surface as "nice-to-have" signals in the report.
* A missing metric in ``deltas`` is treated as a failed gate (we can't
  assert an improvement we didn't measure). If the gate is
  ``required=True`` this discards the run.

Why thresholds are signed deltas, not absolute metric values
------------------------------------------------------------
The delta convention is ``candidate − baseline``. Threshold conventions:

* ``direction="lower_is_better"``: gate passes iff
  ``raw_delta <= threshold`` (e.g. CRPS must improve by at least
  ``-0.01``).
* ``direction="higher_is_better"``: gate passes iff
  ``raw_delta >= threshold`` (e.g. hit rate must improve by at least
  ``+0.02``).

This mirrors the invariant used in
``research/autoresearch/core/metrics_delta.py`` so a reader never has to
flip signs in their head.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal


Direction = Literal["lower_is_better", "higher_is_better"]


@dataclass(frozen=True)
class Gate:
    """One keep/discard gate.

    Fields
    ------
    name:
        Human-readable identifier. Used as the key in
        :attr:`GateDecision.gate_results` and as the heading in the
        report renderer. Must be unique within a gate list.
    metric:
        Key into the ``deltas`` dict supplied to :func:`evaluate_gates`.
    threshold:
        Signed delta threshold. See the module docstring for semantics.
    direction:
        ``"lower_is_better"`` or ``"higher_is_better"``.
    required:
        If True, failing this gate forces ``keep=False``.
    description:
        Optional free-text explanation rendered in reports.
    """

    name: str
    metric: str
    threshold: float
    direction: Direction
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class GateResult:
    """Result of evaluating one :class:`Gate`."""

    gate: Gate
    observed_delta: float | None
    passed: bool
    reason: str


@dataclass
class GateDecision:
    """Aggregate keep/discard decision across a gate list.

    ``keep`` is ``True`` iff all ``required=True`` gates passed.
    ``reasons`` enumerates the *failing* gate reasons (empty on a clean
    keep). ``gate_results`` maps gate name -> :class:`GateResult` for
    the full audit trail.
    """

    keep: bool
    reasons: list[str] = field(default_factory=list)
    gate_results: dict[str, GateResult] = field(default_factory=dict)


def _check_direction(direction: str) -> None:
    if direction not in {"lower_is_better", "higher_is_better"}:
        raise ValueError(
            f"Gate.direction must be 'lower_is_better' or 'higher_is_better'; "
            f"got {direction!r}"
        )


def _evaluate_single(gate: Gate, deltas: dict[str, float]) -> GateResult:
    _check_direction(gate.direction)
    observed = deltas.get(gate.metric)
    if observed is None:
        return GateResult(
            gate=gate,
            observed_delta=None,
            passed=False,
            reason=(
                f"Gate '{gate.name}' has no observed delta for metric "
                f"'{gate.metric}' — treated as failure."
            ),
        )

    observed = float(observed)
    if gate.direction == "lower_is_better":
        passed = observed <= gate.threshold
        cmp_str = f"Δ={observed:+.5f} <= {gate.threshold:+.5f}"
    else:
        passed = observed >= gate.threshold
        cmp_str = f"Δ={observed:+.5f} >= {gate.threshold:+.5f}"

    reason = (
        f"Gate '{gate.name}' on '{gate.metric}' ({gate.direction}): "
        f"{cmp_str} -> {'PASS' if passed else 'FAIL'}"
    )
    return GateResult(
        gate=gate, observed_delta=observed, passed=passed, reason=reason
    )


def evaluate_gates(
    *,
    deltas: dict[str, float],
    gates: Iterable[Gate],
) -> GateDecision:
    """Run every ``gate`` against ``deltas`` and aggregate a :class:`GateDecision`.

    ``deltas`` keys should match :attr:`Gate.metric`. Values are
    ``candidate − baseline`` floats (use
    ``research.autoresearch.core.metrics_delta.compute_delta`` to build
    them).

    Semantics
    ---------
    * An empty gate list yields ``keep=True`` (no gates = no constraints).
      Lanes that want "default-discard until proven otherwise" behaviour
      should always declare at least one required gate.
    * Required failures accumulate into ``reasons``. Advisory failures
      are recorded in ``gate_results`` but don't populate ``reasons``.
    """
    results: dict[str, GateResult] = {}
    reasons: list[str] = []
    required_failures = 0
    total_required = 0

    for gate in gates:
        res = _evaluate_single(gate, deltas)
        if gate.name in results:
            raise ValueError(f"Duplicate gate name in list: {gate.name!r}")
        results[gate.name] = res
        if gate.required:
            total_required += 1
            if not res.passed:
                required_failures += 1
                reasons.append(res.reason)

    # keep=True when no required gate exists (empty list) OR all required
    # gates passed. Advisory gates never flip this.
    keep = required_failures == 0
    return GateDecision(keep=keep, reasons=reasons, gate_results=results)


# ---------------------------------------------------------------------------
# Conveniences
# ---------------------------------------------------------------------------


def standard_forecast_gates() -> list[Gate]:
    """Return the default gate list for a forecast-quality lane.

    Encodes the thresholds used by the projector-v2 lane:

    * CRPS must improve by at least 0.005 (required)
    * Hit rate must not regress below 0.45 absolute (required via an
      auxiliary delta ``hit_rate_floor_margin`` the caller computes)
    * Calibration error improves by at least 0.005 (advisory)

    Callers needing different thresholds should declare their own list
    rather than mutating this one — :class:`Gate` is frozen.
    """
    return [
        Gate(
            name="crps_improvement",
            metric="crps",
            threshold=-0.005,
            direction="lower_is_better",
            required=True,
            description="Mean CRPS must drop by at least 0.005 vs baseline.",
        ),
        Gate(
            name="calibration_improvement",
            metric="calibration_error_p10_p90",
            threshold=-0.005,
            direction="lower_is_better",
            required=False,
            description="P10/P90 calibration error should drop by 0.005+.",
        ),
    ]


__all__ = [
    "Direction",
    "Gate",
    "GateResult",
    "GateDecision",
    "evaluate_gates",
    "standard_forecast_gates",
]
