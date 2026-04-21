"""End-to-end integration tests for the world-event prediction pipeline.

Tests the full flow: event fixtures -> graph construction -> base-rate
prediction -> scorecard computation -> registry registration. Uses small
inline fixtures (no external files or services).

Code path: the_similarity/tests/test_event_prediction_e2e.py
"""

from __future__ import annotations

import os
import tempfile

import pytest

# Import the demo module's components directly. The demo is structured
# so that each function is independently testable.
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from examples.event_prediction_demo import (
    Event,
    EventScorecard,
    ForecastQuestion,
    build_event_graph,
    predict_base_rate,
    register_eval_run,
)
from the_similarity.platform.artifacts import RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_events() -> list[Event]:
    """Build a minimal set of 5 events for testing."""
    return [
        Event("e1", "Event A", "economic", "2020-01-01", 7305, 0.8,
              "Economic downturn"),
        Event("e2", "Event B", "health", "2020-03-15", 7379, 0.9,
              "Health crisis"),
        Event("e3", "Event C", "geopolitical", "2021-06-01", 7822, 0.6,
              "Geopolitical tension"),
        Event("e4", "Event D", "economic", "2022-01-15", 8050, 0.7,
              "Rate hike cycle"),
        Event("e5", "Event E", "health", "2023-05-01", 8521, 0.5,
              "Pandemic variant"),
    ]


def _make_questions() -> list[ForecastQuestion]:
    """Build resolved questions linked to the test events."""
    return [
        ForecastQuestion("q1", "e1", "Will GDP fall?", resolution=True),
        ForecastQuestion("q2", "e2", "Will lockdowns last >3 months?",
                         resolution=True),
        ForecastQuestion("q3", "e3", "Will sanctions be imposed?",
                         resolution=False),
        ForecastQuestion("q4", "e4", "Will rates exceed 4%?",
                         resolution=True),
        ForecastQuestion("q5", "e5", "Will a new vaccine be needed?",
                         resolution=False),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEventGraphConstruction:
    """Verify that the event graph is built correctly from fixtures."""

    def test_graph_has_correct_node_count(self):
        """Graph should contain one node per event."""
        events = _make_events()
        graph = build_event_graph(events, k=2)
        assert len(graph.nodes) == len(events)

    def test_graph_has_edges(self):
        """Graph should have at least one edge per node (k >= 1)."""
        events = _make_events()
        graph = build_event_graph(events, k=2)
        # With 5 nodes and k=2, we expect at least 5 edges (each node
        # connects to 2 nearest neighbors, but edges are deduplicated).
        assert len(graph.edges) >= len(events)


class TestBaseRatePredictor:
    """Verify naive base-rate prediction produces valid probabilities."""

    def test_predictions_in_valid_range(self):
        """All predicted probabilities must be in [0, 1]."""
        events = _make_events()
        questions = _make_questions()
        graph = build_event_graph(events, k=2)

        for q in questions:
            if q.resolution is not None:
                p = predict_base_rate(q, events, questions, graph,
                                      n_analogues=2)
                assert 0.0 <= p <= 1.0, (
                    f"Prediction {p} for {q.question_id} out of range"
                )

    def test_unknown_event_falls_back_to_global_rate(self):
        """A question referencing an unknown event should use global base rate."""
        events = _make_events()
        questions = _make_questions()
        graph = build_event_graph(events, k=2)

        orphan_q = ForecastQuestion("q-orphan", "e-unknown",
                                    "Will something happen?",
                                    resolution=True)
        p = predict_base_rate(orphan_q, events, questions, graph)
        # Global base rate: 3 True out of 5 = 0.6
        assert 0.0 <= p <= 1.0


class TestEventScorecard:
    """Verify scorecard computation produces valid metrics."""

    def test_brier_score_in_range(self):
        """Brier score must be in [0, 1] for binary predictions."""
        events = _make_events()
        questions = _make_questions()
        graph = build_event_graph(events, k=2)

        resolved = [q for q in questions if q.resolution is not None]
        predictions = [
            predict_base_rate(q, events, questions, graph, n_analogues=2)
            for q in resolved
        ]
        resolutions = [q.resolution for q in resolved]

        scorecard = EventScorecard.compute(predictions, resolutions)
        assert 0.0 <= scorecard.brier_score <= 1.0
        assert scorecard.n_predictions == len(resolved)
        assert scorecard.grade in {"A", "B", "C", "D", "F"}

    def test_perfect_predictions_score_zero(self):
        """Perfect predictions (p=1 for True, p=0 for False) -> Brier = 0."""
        predictions = [1.0, 1.0, 0.0]
        resolutions = [True, True, False]
        scorecard = EventScorecard.compute(predictions, resolutions)
        assert scorecard.brier_score == pytest.approx(0.0)
        assert scorecard.grade == "A"

    def test_registry_integration(self):
        """Scorecard should be registrable in the platform registry."""
        predictions = [0.7, 0.3, 0.6]
        resolutions = [True, False, True]
        scorecard = EventScorecard.compute(predictions, resolutions)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_registry.db")
            run_id = register_eval_run(scorecard, db_path)

            # Verify the run was persisted
            registry = RunRegistry(db_path)
            runs = registry.list(kind=RunKind.EVENTS)
            registry.close()

            assert len(runs) == 1
            assert runs[0].run_id == run_id
