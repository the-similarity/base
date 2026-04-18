"""
Tests for event feature extraction, event graph, and analogue retrieval.
"""

from __future__ import annotations


from the_similarity.events.features import FEATURE_DIM, extract_event_features
from the_similarity.events.event_graph import EventGraph
from the_similarity.events.retrieval import retrieve_analogues


# ── Fixture: reusable event dicts ────────────────────────────────────────

RATE_HIKE = {
    "event_id": "rate-2022-03",
    "event_type": "rate_decision",
    "timestamp": "2022-03-16",
    "impact_magnitude": 0.8,
    "impact_direction": "up",
}

COVID_CRASH = {
    "event_id": "covid-2020",
    "event_type": "market_crash",
    "timestamp": "2020-03-12",
    "impact_magnitude": 1.0,
    "impact_direction": "down",
}

EARNINGS = {
    "event_id": "aapl-q4-2023",
    "event_type": "earnings",
    "timestamp": "2023-10-26",
    "impact_magnitude": 0.3,
    "impact_direction": "up",
}

UNKNOWN_TYPE = {
    "event_id": "mystery",
    "event_type": "alien_invasion",
    "timestamp": "2025-01-01",
}

HISTORICAL_EVENTS = [
    {
        "event_type": "rate_decision",
        "timestamp": "2018-06-13",
        "impact_magnitude": 0.5,
        "impact_direction": "up",
    },
    {
        "event_type": "economic_data",
        "timestamp": "2018-06-20",
        "impact_magnitude": 0.2,
        "impact_direction": "down",
    },
    {
        "event_type": "rate_decision",
        "timestamp": "2019-07-31",
        "impact_magnitude": 0.6,
        "impact_direction": "down",
    },
    {
        "event_type": "geopolitical",
        "timestamp": "2019-08-05",
        "impact_magnitude": 0.4,
        "impact_direction": "down",
    },
    {
        "event_type": "market_crash",
        "timestamp": "2020-03-12",
        "impact_magnitude": 1.0,
        "impact_direction": "down",
    },
    {
        "event_type": "policy",
        "timestamp": "2020-03-15",
        "impact_magnitude": 0.9,
        "impact_direction": "up",
    },
    {
        "event_type": "rate_decision",
        "timestamp": "2022-03-16",
        "impact_magnitude": 0.8,
        "impact_direction": "up",
    },
    {
        "event_type": "economic_data",
        "timestamp": "2022-03-30",
        "impact_magnitude": 0.3,
        "impact_direction": "down",
    },
]


# ═════════════════════════════════════════════════════════════════════════
# 1. Feature extraction
# ═════════════════════════════════════════════════════════════════════════


class TestFeatureExtraction:
    """Tests for ``extract_event_features``."""

    def test_output_length(self):
        """Feature vector must have exactly FEATURE_DIM dimensions."""
        vec = extract_event_features(RATE_HIKE)
        assert vec.shape == (FEATURE_DIM,)

    def test_one_hot_correct_position(self):
        """One-hot should activate the correct index for 'rate_decision' (0)."""
        vec = extract_event_features(RATE_HIKE)
        assert vec[0] == 1.0  # rate_decision is index 0
        assert vec[1:8].sum() == 0.0  # all other type slots off

    def test_unknown_type_maps_to_other(self):
        """Unknown event types fall into the 'other' bucket (index 7)."""
        vec = extract_event_features(UNKNOWN_TYPE)
        assert vec[7] == 1.0
        assert vec[0:7].sum() == 0.0

    def test_impact_direction_encoding(self):
        """Direction should be +1 for up, -1 for down, 0 for unknown."""
        assert extract_event_features(RATE_HIKE)[13] == 1.0
        assert extract_event_features(COVID_CRASH)[13] == -1.0
        assert extract_event_features(UNKNOWN_TYPE)[13] == 0.0

    def test_magnitude_clamped(self):
        """Magnitude is clamped to [0, 1]."""
        over = {**RATE_HIKE, "impact_magnitude": 5.0}
        assert extract_event_features(over)[12] == 1.0
        under = {**RATE_HIKE, "impact_magnitude": -2.0}
        assert extract_event_features(under)[12] == 0.0


# ═════════════════════════════════════════════════════════════════════════
# 2. EventGraph
# ═════════════════════════════════════════════════════════════════════════


class TestEventGraph:
    """Tests for ``EventGraph``."""

    def test_add_and_len(self):
        """Adding events increases graph size."""
        g = EventGraph()
        g.add_event(RATE_HIKE)
        g.add_event(COVID_CRASH)
        assert len(g) == 2

    def test_find_analogues_returns_k(self):
        """find_analogues should return exactly k results (or fewer if graph is smaller)."""
        g = EventGraph()
        g.build_from_series(HISTORICAL_EVENTS)
        results = g.find_analogues(RATE_HIKE, k=3)
        assert len(results) == 3
        # Each result is (EventNode, float)
        for node, score in results:
            assert 0.0 <= score <= 1.0

    def test_find_analogues_best_match(self):
        """The top analogue for a rate_decision query should also be a rate_decision."""
        g = EventGraph()
        g.build_from_series(HISTORICAL_EVENTS)
        results = g.find_analogues(RATE_HIKE, k=1)
        best_node, best_score = results[0]
        assert best_node.event_type == "rate_decision"

    def test_temporal_context_filters_by_window(self):
        """find_temporal_context should only return events within ±window_days."""
        g = EventGraph()
        g.build_from_series(HISTORICAL_EVENTS)
        # March 2020 events — window of 10 days around 2020-03-13
        context = g.find_temporal_context("2020-03-13", window_days=10)
        # Should include 2020-03-12 (market_crash) and 2020-03-15 (policy)
        assert len(context) >= 2
        timestamps = [n.timestamp for n in context]
        assert "2020-03-12" in timestamps
        assert "2020-03-15" in timestamps
        # Should NOT include 2022 events
        assert all("2022" not in t for t in timestamps)


# ═════════════════════════════════════════════════════════════════════════
# 3. Retrieval baseline
# ═════════════════════════════════════════════════════════════════════════


class TestRetrieval:
    """Tests for ``retrieve_analogues``."""

    def test_returns_results(self):
        """Retrieval should return at least one window."""
        query = [RATE_HIKE]
        results = retrieve_analogues(query, HISTORICAL_EVENTS, k=3)
        assert len(results) >= 1

    def test_result_schema(self):
        """Each result dict must have the expected keys."""
        results = retrieve_analogues([RATE_HIKE], HISTORICAL_EVENTS, k=1)
        r = results[0]
        assert "window_start" in r
        assert "window_end" in r
        assert "similarity" in r
        assert "events_in_window" in r
        assert "outcomes" in r

    def test_empty_inputs(self):
        """Empty query or historical list returns empty results."""
        assert retrieve_analogues([], HISTORICAL_EVENTS) == []
        assert retrieve_analogues([RATE_HIKE], []) == []
