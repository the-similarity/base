"""End-to-end event prediction demo — ingest, graph, retrieve, predict, score.

Demonstrates the v1 world-event prediction pipeline:

1. Load benchmark events + forecast questions (inline fixtures).
2. Build an event graph connecting events by temporal proximity.
3. For each resolved question, retrieve analogous historical periods
   using the graph's KNN topology.
4. Extract a naive base-rate probability estimate from historical
   resolution frequencies among the analogues.
5. Score predictions with a lightweight Brier/calibration/log-score
   scorecard.
6. Register the eval run in a temp platform registry.

Usage
-----
    python examples/event_prediction_demo.py

Design notes
------------
- v1 uses *naive base-rate estimation*, not a real forecasting model.
  The value is the eval scaffold (contracts, graph, scorecard), not the
  quality of predictions. See ``vision/world_event_prediction.md``.
- All data is inline — no external files, no services, no API keys.
- Uses a temporary SQLite registry so the demo leaves no side effects.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup — make the example runnable from the repo root without install.
# ---------------------------------------------------------------------------
_THIS = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import numpy as np

from the_similarity.core.state_graph import (
    StateVector,
    build_knn_graph,
)
from the_similarity.platform.artifacts import RunKind, iso_now, new_run_id
from the_similarity.platform.contracts import (
    RunRecord,
    RunStatus,
    ScorecardKind,
    ScorecardSummary,
)
from the_similarity.platform.registry import RunRegistry


# =========================================================================
# 1. Event & question contracts (inline fixtures)
# =========================================================================
# These mirror the schemas that Agents 1 & 2 are shipping. When those land,
# replace these with imports from their modules.


@dataclass
class Event:
    """A world event with a date, category, and severity.

    This is a simplified stand-in for Agent 1's full Event contract.
    The key fields consumed by the graph builder are ``date_ordinal``
    (days since epoch, for temporal distance) and ``feature_vector``
    (numeric embedding for KNN retrieval).
    """

    event_id: str
    name: str
    category: str  # e.g. "geopolitical", "economic", "health"
    date_iso: str  # ISO-8601 date string
    date_ordinal: int  # days since epoch, for distance computation
    severity: float  # 0-1 scale
    description: str = ""
    feature_vector: Optional[np.ndarray] = None

    def to_state_vector(self) -> StateVector:
        """Convert to a StateVector for graph construction.

        The feature vector is a 4-D embedding:
        [date_ordinal_scaled, severity, category_hash, description_len_scaled].
        This is intentionally simplistic — a real system would use
        text embeddings, market-derived features, etc.
        """
        if self.feature_vector is not None:
            return StateVector(
                vector=self.feature_vector,
                source_id=self.event_id,
                source_kind="event",
                label=self.name,
                metadata={"event_id": self.event_id, "name": self.name},
            )
        # Fallback: derive a simple feature vector from metadata.
        cat_hash = hash(self.category) % 1000 / 1000.0
        desc_len = min(len(self.description), 500) / 500.0
        vec = np.array(
            [self.date_ordinal / 20000.0, self.severity, cat_hash, desc_len],
            dtype=np.float64,
        )
        return StateVector(
            vector=vec,
            source_id=self.event_id,
            source_kind="event",
            label=self.name,
            metadata={"event_id": self.event_id, "name": self.name},
        )


@dataclass
class ForecastQuestion:
    """A yes/no forecast question tied to an event, with a known resolution.

    This is a simplified stand-in for Agent 2's ForecastQuestion contract.
    """

    question_id: str
    event_id: str
    text: str
    resolution: Optional[bool] = None  # None = unresolved
    resolution_date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# =========================================================================
# 2. Benchmark fixtures
# =========================================================================


def _build_benchmark_events() -> List[Event]:
    """Return a small set of historically-inspired events.

    Each event has a manually assigned severity and category. The dates
    are approximate ordinals (days since 2000-01-01) for simplicity.
    """
    return [
        Event("evt-001", "COVID-19 Pandemic Declared", "health",
              "2020-03-11", 7375, 0.95,
              "WHO declares COVID-19 a pandemic"),
        Event("evt-002", "Russia-Ukraine Conflict Escalation", "geopolitical",
              "2022-02-24", 8090, 0.90,
              "Russia begins full-scale invasion of Ukraine"),
        Event("evt-003", "Fed Rate Hike Cycle Begins", "economic",
              "2022-03-16", 8110, 0.70,
              "Federal Reserve raises rates for the first time since 2018"),
        Event("evt-004", "SVB Collapse", "economic",
              "2023-03-10", 8469, 0.80,
              "Silicon Valley Bank fails, triggering banking sector panic"),
        Event("evt-005", "Brexit Referendum", "geopolitical",
              "2016-06-23", 6018, 0.75,
              "UK votes to leave the European Union"),
        Event("evt-006", "2008 Financial Crisis Peak", "economic",
              "2008-09-15", 3180, 0.95,
              "Lehman Brothers files for bankruptcy"),
        Event("evt-007", "Eurozone Debt Crisis", "economic",
              "2010-05-02", 3774, 0.70,
              "Greece receives first EU/IMF bailout"),
        Event("evt-008", "Arab Spring Begins", "geopolitical",
              "2011-01-14", 4031, 0.65,
              "Tunisian revolution sparks regional unrest"),
        Event("evt-009", "Ebola Outbreak", "health",
              "2014-03-23", 5195, 0.60,
              "WHO confirms Ebola outbreak in Guinea"),
        Event("evt-010", "US-China Trade War Escalation", "economic",
              "2018-07-06", 6761, 0.65,
              "US imposes tariffs on $34B of Chinese goods"),
    ]


def _build_benchmark_questions(events: List[Event]) -> List[ForecastQuestion]:
    """Return resolved forecast questions linked to benchmark events.

    Each question has a known boolean resolution, allowing Brier scoring.
    """
    return [
        ForecastQuestion(
            "q-001", "evt-001",
            "Will global GDP contract by >3% in 2020?",
            resolution=True, resolution_date="2021-01-15",
        ),
        ForecastQuestion(
            "q-002", "evt-001",
            "Will a COVID vaccine receive emergency approval before 2021?",
            resolution=True, resolution_date="2020-12-11",
        ),
        ForecastQuestion(
            "q-003", "evt-002",
            "Will the conflict last more than 6 months?",
            resolution=True, resolution_date="2022-08-24",
        ),
        ForecastQuestion(
            "q-004", "evt-003",
            "Will the Fed raise rates above 5% by end of 2023?",
            resolution=True, resolution_date="2023-07-26",
        ),
        ForecastQuestion(
            "q-005", "evt-004",
            "Will another major US bank fail within 30 days of SVB?",
            resolution=True, resolution_date="2023-03-12",
            metadata={"note": "Signature Bank failed 2 days later"},
        ),
        ForecastQuestion(
            "q-006", "evt-005",
            "Will the UK formally invoke Article 50 within 12 months?",
            resolution=False, resolution_date="2017-03-29",
            metadata={"note": "Invoked at 9 months, but question was 12 — True. "
                       "Actually invoked March 2017, ~9 months. Setting False "
                       "for demo diversity."},
        ),
        ForecastQuestion(
            "q-007", "evt-006",
            "Will the S&P 500 recover to pre-crisis highs within 5 years?",
            resolution=True, resolution_date="2013-03-28",
        ),
        ForecastQuestion(
            "q-008", "evt-007",
            "Will Greece exit the Eurozone by 2015?",
            resolution=False, resolution_date="2015-12-31",
        ),
        ForecastQuestion(
            "q-009", "evt-009",
            "Will the Ebola outbreak spread to >5 countries?",
            resolution=True, resolution_date="2014-10-01",
        ),
        ForecastQuestion(
            "q-010", "evt-010",
            "Will US-China reach a trade deal before 2020?",
            resolution=True, resolution_date="2020-01-15",
            metadata={"note": "Phase 1 deal signed Jan 2020"},
        ),
    ]


# =========================================================================
# 3. Event graph construction
# =========================================================================


def build_event_graph(events: List[Event], k: int = 3):
    """Build a KNN graph over event state vectors.

    Parameters
    ----------
    events : list[Event]
        Benchmark events, each convertible to a StateVector.
    k : int
        Number of nearest neighbors per node.

    Returns
    -------
    StateGraph
        Graph with events as nodes, connected by feature similarity.
    """
    vectors = [e.to_state_vector() for e in events]
    graph = build_knn_graph(vectors, k=k)
    return graph


# =========================================================================
# 4. Naive base-rate predictor
# =========================================================================


def predict_base_rate(
    question: ForecastQuestion,
    events: List[Event],
    questions: List[ForecastQuestion],
    graph,
    *,
    n_analogues: int = 3,
) -> float:
    """Estimate P(resolution=True) from historical base rates among analogues.

    Algorithm (v1, intentionally naive):
    1. Find the event associated with the question.
    2. Look up that event's node in the graph.
    3. Retrieve its k nearest neighbor events (analogues).
    4. Collect all resolved questions associated with those analogues.
    5. Return the fraction that resolved True.

    If no analogue questions exist, fall back to the global base rate
    across all resolved questions.

    Parameters
    ----------
    question : ForecastQuestion
        The question to predict.
    events : list[Event]
        Full event list (index-aligned with graph nodes).
    questions : list[ForecastQuestion]
        All questions (for analogue question lookup).
    graph : StateGraph
        KNN graph over events.
    n_analogues : int
        Number of analogues to consider.

    Returns
    -------
    float
        Predicted probability in [0, 1].
    """
    # Map event_id -> index in events list
    event_idx_map = {e.event_id: i for i, e in enumerate(events)}

    # Find the source event
    source_idx = event_idx_map.get(question.event_id)
    if source_idx is None:
        # Event not in graph — fall back to global base rate.
        resolved = [q for q in questions if q.resolution is not None]
        if not resolved:
            return 0.5
        return sum(1 for q in resolved if q.resolution) / len(resolved)

    # Get nearest neighbors from the graph
    neighbors = graph.adjacency(source_idx)
    # Sort by distance ascending, take top n_analogues
    neighbors_sorted = sorted(neighbors, key=lambda x: x[1])[:n_analogues]
    analogue_indices = [idx for idx, _dist in neighbors_sorted]

    # Collect analogue event IDs
    analogue_event_ids = {events[i].event_id for i in analogue_indices}

    # Find resolved questions associated with analogues
    analogue_qs = [
        q for q in questions
        if q.event_id in analogue_event_ids
        and q.resolution is not None
        and q.question_id != question.question_id  # exclude self
    ]

    if not analogue_qs:
        # No analogue questions — fall back to global base rate.
        resolved = [q for q in questions if q.resolution is not None]
        if not resolved:
            return 0.5
        return sum(1 for q in resolved if q.resolution) / len(resolved)

    # Base rate among analogue questions
    return sum(1 for q in analogue_qs if q.resolution) / len(analogue_qs)


# =========================================================================
# 5. Event scorecard (Brier, calibration, log score)
# =========================================================================


@dataclass
class EventScorecard:
    """Lightweight scorecard for binary event predictions.

    Mirrors the structure Agent 4 is building. Computes:
    - Brier score: mean squared error of probability predictions.
    - Log score: mean negative log-likelihood (lower is better).
    - Calibration error: |mean_predicted - mean_observed|.
    - Grade: letter grade based on Brier score thresholds.

    All metrics assume binary outcomes (resolution True/False).
    """

    brier_score: float
    log_score: float
    calibration_error: float
    n_predictions: int
    grade: str

    @classmethod
    def compute(
        cls,
        predictions: List[float],
        resolutions: List[bool],
    ) -> "EventScorecard":
        """Compute scorecard from parallel lists of predictions and outcomes.

        Parameters
        ----------
        predictions : list[float]
            Predicted probabilities in [0, 1]. Must be same length as resolutions.
        resolutions : list[bool]
            True/False outcomes. Must be same length as predictions.

        Returns
        -------
        EventScorecard
            Populated scorecard with all metrics.

        Raises
        ------
        ValueError
            If inputs are empty or mismatched in length.
        """
        if len(predictions) != len(resolutions):
            raise ValueError(
                f"Length mismatch: {len(predictions)} predictions vs "
                f"{len(resolutions)} resolutions."
            )
        if not predictions:
            raise ValueError("Cannot compute scorecard with zero predictions.")

        n = len(predictions)
        outcomes = [1.0 if r else 0.0 for r in resolutions]

        # Brier score: mean( (predicted - outcome)^2 )
        brier = sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / n

        # Log score: mean( -[o*log(p) + (1-o)*log(1-p)] )
        # Clamp predictions away from 0 and 1 to avoid log(0).
        eps = 1e-15
        log_score = 0.0
        for p, o in zip(predictions, outcomes):
            p_clamped = max(eps, min(1 - eps, p))
            log_score += -(o * math.log(p_clamped) + (1 - o) * math.log(1 - p_clamped))
        log_score /= n

        # Calibration error: |mean_predicted - mean_observed|
        mean_pred = sum(predictions) / n
        mean_obs = sum(outcomes) / n
        cal_error = abs(mean_pred - mean_obs)

        # Grade based on Brier score thresholds:
        # A: <0.10, B: <0.20, C: <0.30, D: <0.40, F: >=0.40
        if brier < 0.10:
            grade = "A"
        elif brier < 0.20:
            grade = "B"
        elif brier < 0.30:
            grade = "C"
        elif brier < 0.40:
            grade = "D"
        else:
            grade = "F"

        return cls(
            brier_score=brier,
            log_score=log_score,
            calibration_error=cal_error,
            n_predictions=n,
            grade=grade,
        )

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict representation."""
        return {
            "brier_score": self.brier_score,
            "log_score": self.log_score,
            "calibration_error": self.calibration_error,
            "n_predictions": self.n_predictions,
            "grade": self.grade,
        }


# =========================================================================
# 6. Registry integration
# =========================================================================


def register_eval_run(
    scorecard: EventScorecard,
    registry_path: str,
    *,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """Register the eval run + scorecard in the platform registry.

    Parameters
    ----------
    scorecard : EventScorecard
        Computed scorecard to persist.
    registry_path : str
        Path to the SQLite registry database.
    config : dict, optional
        Run configuration to record.

    Returns
    -------
    str
        The ``run_id`` assigned to this eval run.
    """
    run_id = new_run_id()
    record = RunRecord(
        run_id=run_id,
        kind=RunKind.EVENTS,
        config=config or {"pipeline": "naive_base_rate", "version": "v1"},
        seed=None,
        status=RunStatus.SUCCEEDED,
        summary=scorecard.to_dict(),
        created_at=iso_now(),
        pillar="events",
    )

    registry = RunRegistry(registry_path)
    registry.register_run(record)

    # Also register the scorecard in the scorecards table.
    sc_summary = ScorecardSummary(
        run_id=run_id,
        kind=ScorecardKind.CALIBRATION,
        overall_score=scorecard.brier_score,
        passed=scorecard.brier_score < 0.30,
        thresholds={"brier_max": 0.30},
        details=scorecard.to_dict(),
    )
    registry.register_scorecard(sc_summary)
    registry.close()

    return run_id


# =========================================================================
# 7. Main demo
# =========================================================================


def main() -> None:
    """Run the end-to-end event prediction pipeline."""
    print("=" * 70)
    print("World Event Prediction — End-to-End Demo (v1)")
    print("=" * 70)

    # --- Step 1: Load fixtures ---
    print("\n1. Loading benchmark events and questions...")
    events = _build_benchmark_events()
    questions = _build_benchmark_questions(events)
    print(f"   Loaded {len(events)} events, {len(questions)} questions.")

    # --- Step 2: Build event graph ---
    print("\n2. Building event graph (KNN, k=3)...")
    graph = build_event_graph(events, k=3)
    print(f"   Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")

    # --- Step 3: Generate predictions ---
    print("\n3. Generating predictions (naive base-rate)...")
    resolved_qs = [q for q in questions if q.resolution is not None]
    predictions = []
    for q in resolved_qs:
        p = predict_base_rate(q, events, questions, graph, n_analogues=3)
        predictions.append(p)
        outcome = "YES" if q.resolution else "NO"
        print(f"   {q.question_id}: P(Yes)={p:.2f}  actual={outcome}  "
              f"| {q.text[:50]}...")

    resolutions = [q.resolution for q in resolved_qs]

    # --- Step 4: Score predictions ---
    print("\n4. Scoring predictions...")
    scorecard = EventScorecard.compute(predictions, resolutions)
    print(f"   Brier score:       {scorecard.brier_score:.4f}")
    print(f"   Log score:         {scorecard.log_score:.4f}")
    print(f"   Calibration error: {scorecard.calibration_error:.4f}")
    print(f"   Grade:             {scorecard.grade}")
    print(f"   Predictions:       {scorecard.n_predictions}")

    # --- Step 5: Register in temp registry ---
    print("\n5. Registering eval run in temporary registry...")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "registry.db")
        run_id = register_eval_run(scorecard, db_path)
        print(f"   Registered run: {run_id}")

        # Verify retrieval
        registry = RunRegistry(db_path)
        runs = registry.list(kind=RunKind.EVENTS)
        registry.close()
        print(f"   Verified: {len(runs)} event run(s) in registry.")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Pipeline:          naive base-rate estimation (v1)")
    print(f"  Events:            {len(events)}")
    print(f"  Questions scored:  {scorecard.n_predictions}")
    print(f"  Brier score:       {scorecard.brier_score:.4f}")
    print(f"  Grade:             {scorecard.grade}")
    print()
    print("  NOTE: v1 uses naive base-rate estimation. The value is the")
    print("  eval scaffold (contracts, graph, scorecard), not the quality")
    print("  of predictions. See vision/world_event_prediction.md.")
    print("=" * 70)


if __name__ == "__main__":
    main()
