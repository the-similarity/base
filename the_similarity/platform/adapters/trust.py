"""Trust artifact — captures the trust decision for a finance run.

UNCALIBRATED PLACEHOLDER — the trust score formula
(0.4*hit_rate + 0.3*coverage + 0.3*(1-crps)) has no empirical basis.
It has not been validated against realized outcomes. Do not use for
production decisions until calibrated against real data.

A :class:`TrustArtifact` evaluates the quality of a backtest run through
a composite ``trust_score`` and a ``calibration_grade``, then renders an
actionable ``decision`` (TRUSTED / REVIEW / REJECTED) so downstream
consumers (UI, alerts, auto-merge gates) can act on it without
re-deriving the same logic.

Decision logic
--------------
::

    trust_score >= 0.7 AND calibration_grade in (A, B) -> TRUSTED
    trust_score >= 0.5 OR  calibration_grade == C      -> REVIEW
    else                                               -> REJECTED

Trust score formula
-------------------
::

    trust_score = 0.4 * hit_rate + 0.3 * coverage + 0.3 * (1 - min(crps, 1))

All three components are in [0, 1]. The weights reflect relative
importance: directional accuracy (40%), interval coverage (30%),
probabilistic calibration quality via CRPS inversion (30%).

Calibration grade (letter contract)
-----------------------------------
Based on mean absolute calibration error across all percentiles. The
finance UX contract is a classic 5-tier letter scale:

- **A**: mean_abs_error < 0.03  (excellent — cone widths match reality)
- **B**: mean_abs_error < 0.06  (good — minor drift, usable)
- **C**: mean_abs_error < 0.10  (fair — cone slightly off, inspect)
- **D**: mean_abs_error < 0.15  (marginal — review before acting)
- **F**: mean_abs_error >= 0.15 (unreliable — do not use)

Rationale: letter grades are the universal finance-UX idiom (S&P bond
ratings, academic scorecards, investor decks). Qualitative labels
(excellent/good/fair/poor) conflate "ok" with "good" in UI copy and
cannot express a 5-tier scale without awkward compound labels. See
``obsidian_thesim/concepts/finance_trust_grades.md`` for the full
decision record.

Serialization
-------------
:meth:`TrustArtifact.to_dict` / :meth:`TrustArtifact.from_dict` provide
JSON round-trip support. The canonical disk filename is ``trust.json``,
written alongside the run's ``artifact.json`` when registration is
enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

from the_similarity.platform.artifacts import iso_now

# The trust score weights and decision thresholds below have NO empirical
# validation. They were chosen to "look reasonable" but have never been
# calibrated against realized trading outcomes.
UNCALIBRATED = True


# ---------------------------------------------------------------------------
# Trust decision enum
# ---------------------------------------------------------------------------


class TrustDecision(str, Enum):
    """Outcome of the trust evaluation gate.

    Inherits from ``str`` for JSON round-trip symmetry with
    :class:`~the_similarity.platform.artifacts.RunKind`.
    """

    TRUSTED = "trusted"
    REVIEW = "review"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Constants — trust score weights + calibration grade thresholds
# ---------------------------------------------------------------------------

# Weights for the composite trust score. Sum to 1.0.
_WEIGHT_HIT_RATE: float = 0.4
_WEIGHT_COVERAGE: float = 0.3
_WEIGHT_CRPS_INV: float = 0.3

# Calibration grade thresholds (mean absolute calibration error).
#
# These upper bounds are EXCLUSIVE — an error equal to the bound rolls
# over to the next grade. The thresholds are locked-in by:
#   * the finance UX contract documented in
#     ``obsidian_thesim/concepts/finance_trust_grades.md``;
#   * the schema expectation in ``tests/test_finance_operating.py``
#     line 233-240 which requires grades to be one of A/B/C/D/F.
#
# Do NOT relax these without updating the concept note AND every
# consumer (UI, signal summary, risk flags, review workflow).
_GRADE_A_MAX: float = 0.03
_GRADE_B_MAX: float = 0.06
_GRADE_C_MAX: float = 0.10
_GRADE_D_MAX: float = 0.15

# Trust decision thresholds.
_TRUST_SCORE_TRUSTED_MIN: float = 0.7
_TRUST_SCORE_REVIEW_MIN: float = 0.5

# Valid calibration grade values — the canonical finance-UX letter set.
# Consumers should reference this constant rather than inlining the
# string literals so a schema change is caught at import time.
VALID_GRADES: tuple[str, ...] = ("A", "B", "C", "D", "F")

# Grade buckets that pass the TRUSTED gate (top tier). Matches the
# "A or B" rule in the module docstring.
_TRUSTED_GRADES: frozenset[str] = frozenset({"A", "B"})

# Grade bucket that qualifies for REVIEW regardless of trust_score.
# Matches the "C triggers review" rule in the module docstring.
_REVIEW_GRADE: str = "C"


# ---------------------------------------------------------------------------
# Computation helpers
# ---------------------------------------------------------------------------


def compute_trust_score(
    hit_rate: float,
    coverage: float,
    crps: float,
) -> float:
    """Compute composite trust score in [0, 1].

    Formula:
        trust_score = 0.4 * hit_rate + 0.3 * coverage + 0.3 * (1 - min(crps, 1))

    Parameters
    ----------
    hit_rate:
        Directional hit rate in [0, 1].
    coverage:
        Empirical interval coverage in [0, 1].
    crps:
        Continuous Ranked Probability Score (lower is better). Clamped to
        [0, 1] before inversion so the trust score stays bounded.

    Returns
    -------
    float
        Composite trust score in [0, 1].
    """
    # Clamp CRPS to [0, 1] for inversion. CRPS can exceed 1 for poorly
    # calibrated forecasts but the trust formula needs a bounded input.
    crps_inv = 1.0 - min(crps, 1.0)
    # WARNING: arbitrary weights, not validated against realized outcomes.
    return (
        _WEIGHT_HIT_RATE * hit_rate
        + _WEIGHT_COVERAGE * coverage
        + _WEIGHT_CRPS_INV * crps_inv
    )


def compute_calibration_grade(calibration: Dict[str, float]) -> str:
    """Assign a calibration letter grade from per-percentile calibration data.

    Letter-grade scale (finance-UX contract):

    - **A**: mean_abs_error < 0.03
    - **B**: mean_abs_error < 0.06
    - **C**: mean_abs_error < 0.10
    - **D**: mean_abs_error < 0.15
    - **F**: mean_abs_error >= 0.15

    Empty or malformed calibration data fail closed to ``"F"`` — the UI
    must never render a missing grade as "pass". See
    ``obsidian_thesim/concepts/finance_trust_grades.md`` for the rationale.

    Parameters
    ----------
    calibration:
        Map from percentile key (e.g. ``"10"``, ``"50"``, ``"90"``) to
        observed coverage rate. The expected coverage for percentile P is
        P/100.

    Returns
    -------
    str
        One of ``"A"``, ``"B"``, ``"C"``, ``"D"``, ``"F"``. See
        :data:`VALID_GRADES`.
    """
    # Fail-closed default: empty or unparseable calibration produces "F".
    # This is intentional — a missing/broken calibration must never be
    # rendered as an A-grade run in a trading UI.
    if not calibration:
        return "F"

    # Compute per-percentile absolute errors: |observed - expected|.
    # Non-numeric keys (e.g. "foo") are silently skipped so malformed
    # payloads degrade gracefully instead of crashing the adapter.
    errors = []
    for p_str, observed in calibration.items():
        try:
            expected = float(p_str) / 100.0
        except (ValueError, TypeError):
            continue
        errors.append(abs(observed - expected))

    if not errors:
        return "F"

    mean_abs_error = sum(errors) / len(errors)

    # Strict less-than comparisons match the EXCLUSIVE upper bounds
    # declared at module scope. A boundary value (e.g. exactly 0.03)
    # rolls over to the next lower grade.
    if mean_abs_error < _GRADE_A_MAX:
        return "A"
    elif mean_abs_error < _GRADE_B_MAX:
        return "B"
    elif mean_abs_error < _GRADE_C_MAX:
        return "C"
    elif mean_abs_error < _GRADE_D_MAX:
        return "D"
    else:
        return "F"


def compute_decision(
    trust_score: float,
    calibration_grade: str,
) -> TrustDecision:
    """Apply the trust decision gate.

    Decision logic::

        trust_score >= 0.7 AND grade in (A, B) -> TRUSTED
        trust_score >= 0.5 OR  grade == C      -> REVIEW
        else                                   -> REJECTED

    The rule is intentionally asymmetric: a top-tier trust_score alone
    is NOT enough for TRUSTED — the cone must also be well-calibrated
    (grade A or B). Conversely, a moderate trust_score (>= 0.5) OR a
    C-grade cone is enough to warrant human REVIEW rather than outright
    REJECTION. This mirrors how a trader would triage signals: check
    the number, then check the envelope.

    Parameters
    ----------
    trust_score:
        Composite score in [0, 1] from :func:`compute_trust_score`.
    calibration_grade:
        Letter grade from :func:`compute_calibration_grade` — one of
        ``"A"``, ``"B"``, ``"C"``, ``"D"``, ``"F"``.

    Returns
    -------
    TrustDecision
    """
    if (
        trust_score >= _TRUST_SCORE_TRUSTED_MIN
        and calibration_grade in _TRUSTED_GRADES
    ):
        return TrustDecision.TRUSTED
    if (
        trust_score >= _TRUST_SCORE_REVIEW_MIN
        or calibration_grade == _REVIEW_GRADE
    ):
        return TrustDecision.REVIEW
    return TrustDecision.REJECTED


def _generate_reasoning(
    trust_score: float,
    calibration_grade: str,
    decision: TrustDecision,
    metrics_snapshot: Dict[str, Any],
) -> str:
    """Auto-generate a human-readable explanation for the trust decision.

    The output is 2-4 sentences explaining the key factors behind the
    decision, suitable for display in a UI or log.
    """
    hit_rate = metrics_snapshot.get("hit_rate", 0.0)
    coverage = metrics_snapshot.get("coverage", 0.0)
    crps_val = metrics_snapshot.get("crps", 0.0)

    parts = [
        f"Trust score {trust_score:.3f} (hit_rate={hit_rate:.1%}, "
        f"coverage={coverage:.1%}, crps={crps_val:.4f}).",
        f"Calibration grade: {calibration_grade}.",
    ]

    if decision == TrustDecision.TRUSTED:
        parts.append("Run meets all quality thresholds and is approved for use.")
    elif decision == TrustDecision.REVIEW:
        # Explain why it needs review. We reference the letter grade
        # directly (A/B/C/D/F) so the reasoning string matches what the
        # UI renders elsewhere — no translation layer between the
        # structured grade and the human-readable reason.
        reasons = []
        if trust_score < _TRUST_SCORE_TRUSTED_MIN:
            reasons.append(
                f"trust score below {_TRUST_SCORE_TRUSTED_MIN:.1f} threshold"
            )
        if calibration_grade not in _TRUSTED_GRADES:
            reasons.append(f"calibration grade is {calibration_grade}")
        parts.append("Run requires manual review: " + "; ".join(reasons) + ".")
    else:
        parts.append(
            "Run is rejected due to insufficient quality. "
            f"Trust score {trust_score:.3f} is below the review threshold "
            f"of {_TRUST_SCORE_REVIEW_MIN:.1f} and calibration grade is {calibration_grade}."
        )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# TrustArtifact
# ---------------------------------------------------------------------------


@dataclass
class TrustArtifact:
    """Structured artifact capturing the trust decision for a finance run.

    Fields
    ------
    run_id:
        FK to the parent :class:`~the_similarity.platform.contracts.RunRecord`.
    trust_score:
        Composite quality score in [0, 1]. See :func:`compute_trust_score`.
    calibration_grade:
        One of ``"A"``, ``"B"``, ``"C"``, ``"D"``, ``"F"``. See
        :data:`VALID_GRADES` for the canonical tuple.
    metrics_snapshot:
        Dict of all metrics at evaluation time (hit_rate, crps, coverage,
        mean_error, etc.). Frozen snapshot — the originating
        ``BacktestReport`` is the source of truth for live re-computation.
    decision:
        :class:`TrustDecision` — the actionable gate output.
    thresholds:
        Dict of cutoff values used in the decision (for audit trail).
    reasoning:
        Auto-generated human-readable explanation of the decision.
    created_at:
        ISO-8601 UTC timestamp.
    """

    run_id: str
    trust_score: float
    calibration_grade: str
    metrics_snapshot: Dict[str, Any]
    decision: TrustDecision
    thresholds: Dict[str, Any]
    reasoning: str
    created_at: str
    uncalibrated: bool = True

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dict. Enum -> string value."""
        return {
            "run_id": self.run_id,
            "trust_score": self.trust_score,
            "calibration_grade": self.calibration_grade,
            "metrics_snapshot": self.metrics_snapshot,
            "decision": self.decision.value,
            "thresholds": self.thresholds,
            "reasoning": self.reasoning,
            "created_at": self.created_at,
            "uncalibrated": self.uncalibrated,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrustArtifact":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            run_id=d["run_id"],
            trust_score=d["trust_score"],
            calibration_grade=d["calibration_grade"],
            metrics_snapshot=d["metrics_snapshot"],
            decision=TrustDecision(d["decision"]),
            thresholds=d["thresholds"],
            reasoning=d["reasoning"],
            created_at=d["created_at"],
            uncalibrated=d.get("uncalibrated", True),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_trust_artifact(
    run_id: str,
    metrics_snapshot: Dict[str, Any],
) -> TrustArtifact:
    """Build a :class:`TrustArtifact` from a metrics snapshot dict.

    This is the primary entry point for callers. It computes the trust
    score, calibration grade, decision, and reasoning from the raw
    metrics, producing a complete artifact ready for serialization.

    Parameters
    ----------
    run_id:
        The run_id of the parent finance run.
    metrics_snapshot:
        Dict containing at least ``hit_rate``, ``coverage``, ``crps``,
        and ``calibration`` (per-percentile dict). Missing keys default
        to 0.0 or empty dict.
    """
    hit_rate = float(metrics_snapshot.get("hit_rate", 0.0))
    coverage = float(metrics_snapshot.get("coverage", 0.0))
    crps_val = float(metrics_snapshot.get("crps", 0.0))
    calibration = metrics_snapshot.get("calibration", {})

    trust_score = compute_trust_score(hit_rate, coverage, crps_val)
    cal_grade = compute_calibration_grade(calibration)
    decision = compute_decision(trust_score, cal_grade)

    # Record the thresholds used for the decision so the artifact is
    # self-describing / auditable. Keys are namespaced with the grade
    # letter so downstream schema consumers can reason about each bucket
    # independently (A/B/C/D boundaries) without parsing the name.
    thresholds = {
        "trust_score_trusted_min": _TRUST_SCORE_TRUSTED_MIN,
        "trust_score_review_min": _TRUST_SCORE_REVIEW_MIN,
        "calibration_grade_a_max": _GRADE_A_MAX,
        "calibration_grade_b_max": _GRADE_B_MAX,
        "calibration_grade_c_max": _GRADE_C_MAX,
        "calibration_grade_d_max": _GRADE_D_MAX,
        "trust_weight_hit_rate": _WEIGHT_HIT_RATE,
        "trust_weight_coverage": _WEIGHT_COVERAGE,
        "trust_weight_crps_inv": _WEIGHT_CRPS_INV,
    }

    reasoning = _generate_reasoning(trust_score, cal_grade, decision, metrics_snapshot)

    return TrustArtifact(
        run_id=run_id,
        trust_score=trust_score,
        calibration_grade=cal_grade,
        metrics_snapshot=metrics_snapshot,
        decision=decision,
        thresholds=thresholds,
        reasoning=reasoning,
        created_at=iso_now(),
        uncalibrated=True,
    )


__all__ = [
    "UNCALIBRATED",
    "VALID_GRADES",
    "TrustArtifact",
    "TrustDecision",
    "build_trust_artifact",
    "compute_calibration_grade",
    "compute_decision",
    "compute_trust_score",
]
