"""Platform registry adapter for prediction market question sets.

Registers a :class:`~the_similarity.events.markets.QuestionSet` as a
:class:`~the_similarity.platform.contracts.RunRecord` with
``kind=RunKind.EVENTS`` and ``pillar="events"``.

The adapter follows the same pattern as the finance and copies adapters
in :mod:`the_similarity.platform.adapters` — it coerces domain objects
into the platform's canonical run shape and delegates persistence to the
:class:`~the_similarity.platform.registry.RunRegistry`.

Summary fields
--------------
The ``summary`` dict on the registered :class:`RunRecord` includes:

- ``n_questions`` — total number of questions in the set.
- ``n_resolved`` — count of questions where ``resolved=True``.
- ``mean_brier_score`` — average Brier score across resolved questions
  (only when at least one resolved question has price history). ``None``
  if no resolved questions exist or none have prices.
- ``categories`` — sorted list of distinct question categories.
- ``sources`` — sorted list of distinct platform sources.

Brier score computation
-----------------------
For each resolved question with at least one price observation, the
Brier score is computed from the *last* price in the history (the
terminal market probability before resolution):

    brier = (p_last - outcome)^2

where ``outcome`` is 1.0 if the question resolved True, 0.0 otherwise.
This is the standard Brier score for binary events. A perfect forecaster
scores 0; random guessing (p=0.5) scores 0.25.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from the_similarity.events.markets import MarketHistory, QuestionSet
from the_similarity.platform.artifacts import RunKind, iso_now, new_run_id
from the_similarity.platform.contracts import RunRecord, RunStatus


def _compute_brier_score(history: MarketHistory) -> Optional[float]:
    """Compute Brier score for a single resolved question.

    Returns ``None`` if the question is unresolved, has no resolution
    value, or has no price observations (cannot compute terminal
    probability without data).
    """
    q = history.question
    # Guard: only compute for resolved binary questions with known outcome.
    if not q.resolved or q.resolution is None:
        return None
    # Guard: need at least one price observation.
    if not history.prices:
        return None
    # Use the last price as the terminal probability.
    # Prices are expected sorted ascending by timestamp; take the final one.
    p_last = history.prices[-1].probability
    # Binary outcome: 1.0 if resolved True, 0.0 if resolved False.
    outcome = 1.0 if q.resolution else 0.0
    return (p_last - outcome) ** 2


def _build_summary(qs: QuestionSet) -> Dict[str, Any]:
    """Build the headline summary dict for a question set registration.

    This is the ``summary`` field on the :class:`RunRecord` — small
    enough for UI grid display, no bulk data.
    """
    n_questions = len(qs.questions)
    n_resolved = sum(1 for h in qs.questions if h.question.resolved)

    # Collect Brier scores for resolved questions with price data.
    brier_scores: List[float] = []
    for h in qs.questions:
        bs = _compute_brier_score(h)
        if bs is not None:
            brier_scores.append(bs)

    mean_brier: Optional[float] = None
    if brier_scores:
        mean_brier = sum(brier_scores) / len(brier_scores)

    # Distinct categories and sources, sorted for deterministic output.
    categories = sorted({h.question.category for h in qs.questions})
    sources = sorted({h.question.source for h in qs.questions})

    return {
        "n_questions": n_questions,
        "n_resolved": n_resolved,
        "mean_brier_score": mean_brier,
        "categories": categories,
        "sources": sources,
    }


def register_question_set(
    qs: QuestionSet,
    registry: Any,
) -> str:
    """Register a :class:`QuestionSet` as a :class:`RunRecord` with kind=EVENTS.

    Parameters
    ----------
    qs:
        The question set to register.
    registry:
        A :class:`~the_similarity.platform.registry.RunRegistry` instance
        (or any object with a ``register_run(RunRecord) -> str`` method).
        Typed as ``Any`` to avoid a hard import dependency in lightweight
        test environments.

    Returns
    -------
    str
        The ``run_id`` of the registered run.

    Notes
    -----
    The returned ``run_id`` is a fresh UUID4 hex. Re-registering the same
    question set produces a new run — deterministic IDs are not used here
    because question sets may be edited (prices appended, resolutions
    updated) between registrations.
    """
    summary = _build_summary(qs)

    record = RunRecord(
        run_id=new_run_id(),
        kind=RunKind.EVENTS,
        config={
            "question_set_name": qs.name,
            "question_set_version": qs.version,
        },
        seed=None,
        status=RunStatus.SUCCEEDED,
        summary=summary,
        created_at=iso_now(),
        pillar="events",
    )

    return registry.register_run(record)


__all__ = ["register_question_set"]
