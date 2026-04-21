"""Tests for narrative retrieval — feature extraction, history search, state vectors.

Covers the three public functions in ``the_similarity.narrative.retrieval``:
1. ``extract_narrative_features`` — correct vector shape and values
2. ``find_similar_histories`` — returns ranked matches from synthetic data
3. ``extract_nl_ts_state`` — produces valid StateVector for state-space
"""

from __future__ import annotations

import numpy as np

from the_similarity.narrative.retrieval import (
    NARRATIVE_FEATURE_DIM,
    _CANONICAL_EVENT_TYPES,
    extract_narrative_features,
    extract_nl_ts_state,
    find_similar_histories,
)
from the_similarity.core.state_space import MAX_DIM, StateVector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_sequence(events: list[dict]) -> dict:
    """Helper to build a NarrativeSequence dict for testing."""
    return {"events": events}


def _two_event_sequence() -> dict:
    """A simple 2-event sequence for reuse across tests."""
    return _make_sequence(
        [
            {
                "event_type": "rate_hike",
                "intensity": 0.8,
                "duration": 20,
                "direction": "down",
            },
            {
                "event_type": "pandemic",
                "intensity": 0.9,
                "duration": 30,
                "direction": "down",
            },
        ]
    )


# ---------------------------------------------------------------------------
# 1. extract_narrative_features
# ---------------------------------------------------------------------------


class TestExtractNarrativeFeatures:
    """Tests for the feature extraction function."""

    def test_output_shape(self):
        """Feature vector has the documented fixed length."""
        seq = _two_event_sequence()
        vec = extract_narrative_features(seq)
        assert vec.shape == (NARRATIVE_FEATURE_DIM,)
        assert vec.dtype == np.float64

    def test_empty_events_returns_zeros(self):
        """Empty or missing events produce an all-zero vector."""
        assert np.allclose(extract_narrative_features({"events": []}), 0.0)
        assert np.allclose(extract_narrative_features({}), 0.0)

    def test_event_type_distribution_sums_to_one(self):
        """The event-type distribution dims should sum to 1 for non-empty sequences."""
        seq = _two_event_sequence()
        vec = extract_narrative_features(seq)
        n_types = len(_CANONICAL_EVENT_TYPES)
        dist_sum = vec[:n_types].sum()
        assert abs(dist_sum - 1.0) < 1e-10

    def test_mean_intensity_correct(self):
        """Mean intensity dimension captures the average."""
        seq = _two_event_sequence()
        vec = extract_narrative_features(seq)
        n_types = len(_CANONICAL_EVENT_TYPES)
        expected_mean = (0.8 + 0.9) / 2.0
        assert abs(vec[n_types] - expected_mean) < 1e-10

    def test_trend_direction_negative(self):
        """Two 'down' events should yield trend direction = -1."""
        seq = _two_event_sequence()
        vec = extract_narrative_features(seq)
        n_types = len(_CANONICAL_EVENT_TYPES)
        assert vec[n_types + 3] == -1.0

    def test_trend_direction_positive(self):
        """Two 'up' events should yield trend direction = +1."""
        seq = _make_sequence(
            [
                {"event_type": "earnings", "intensity": 0.5, "duration": 10, "direction": "up"},
                {"event_type": "technology", "intensity": 0.6, "duration": 15, "direction": "up"},
            ]
        )
        vec = extract_narrative_features(seq)
        n_types = len(_CANONICAL_EVENT_TYPES)
        assert vec[n_types + 3] == 1.0

    def test_transition_ratio(self):
        """Two events of different types = 1 transition / 2 events = 0.5."""
        seq = _two_event_sequence()
        vec = extract_narrative_features(seq)
        n_types = len(_CANONICAL_EVENT_TYPES)
        assert abs(vec[n_types + 2] - 0.5) < 1e-10


# ---------------------------------------------------------------------------
# 2. find_similar_histories
# ---------------------------------------------------------------------------


class TestFindSimilarHistories:
    """Tests for the history retrieval function."""

    def test_returns_k_results(self):
        """Given enough data, returns exactly k results."""
        # Create a known pattern and embed it in noise
        np.random.seed(42)
        pattern = np.sin(np.linspace(0, 2 * np.pi, 50))
        # Historical data: noise with the pattern embedded at position 100
        history = np.random.randn(500)
        history[100:150] = pattern * 3.0 + 10.0  # scaled + shifted (shape should match)

        results = find_similar_histories(
            trajectory=pattern,
            historical_data={"SPY": history},
            k=5,
        )
        assert len(results) == 5
        # The best match should be near index 100
        assert results[0]["symbol"] == "SPY"
        assert results[0]["start_idx"] == 100

    def test_result_structure(self):
        """Each result dict has the required keys."""
        pattern = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
        history = np.random.randn(100)

        results = find_similar_histories(
            trajectory=pattern,
            historical_data={"TEST": history},
            k=3,
        )
        assert len(results) > 0
        for r in results:
            assert "symbol" in r
            assert "start_idx" in r
            assert "end_idx" in r
            assert "similarity" in r
            assert "window_data" in r
            assert r["end_idx"] - r["start_idx"] == len(pattern)

    def test_empty_history_returns_empty(self):
        """No historical data -> empty results."""
        pattern = np.array([1.0, 2.0, 3.0])
        assert find_similar_histories(pattern, {}, k=5) == []

    def test_short_trajectory_returns_empty(self):
        """Trajectory of length < 2 cannot produce correlations."""
        assert find_similar_histories(np.array([1.0]), {"SPY": np.ones(100)}, k=5) == []

    def test_multiple_symbols(self):
        """Results can span multiple symbols."""
        np.random.seed(123)
        pattern = np.linspace(0, 1, 20)
        results = find_similar_histories(
            trajectory=pattern,
            historical_data={
                "SPY": np.random.randn(200),
                "QQQ": np.random.randn(200),
            },
            k=10,
        )
        # Should have results from at least one symbol
        assert len(results) > 0
        assert len(results) <= 10


# ---------------------------------------------------------------------------
# 3. extract_nl_ts_state
# ---------------------------------------------------------------------------


class TestExtractNlTsState:
    """Tests for the NL_TS state vector extractor."""

    def test_returns_state_vector(self):
        """Output is a valid StateVector with correct kind."""
        summary = {
            "run_id": "nl-001",
            "mean_intensity": 0.7,
            "mean_duration_norm": 0.3,
            "transition_ratio": 0.5,
            "trend_direction": -0.5,
            "total_duration_norm": 0.6,
        }
        sv = extract_nl_ts_state(summary)
        assert isinstance(sv, StateVector)
        assert sv.source_kind == "nl_ts"
        assert sv.source_id == "nl-001"

    def test_vector_length_matches_max_dim(self):
        """State vector is padded to MAX_DIM for mixed-pillar compatibility."""
        summary = {"run_id": "nl-002", "mean_intensity": 0.5}
        sv = extract_nl_ts_state(summary)
        assert sv.vector.shape == (MAX_DIM,)

    def test_missing_keys_default_to_neutral(self):
        """Missing summary keys produce 0.5 (neutral) in the vector."""
        sv = extract_nl_ts_state({"run_id": "nl-003"})
        # All dims should be 0.5 (neutral) since no metrics were provided
        np.testing.assert_allclose(sv.vector, 0.5)

    def test_normalization_maps_correctly(self):
        """Trend direction -1 maps to 0.0, +1 maps to 1.0, 0 maps to 0.5."""
        sv_neg = extract_nl_ts_state({"run_id": "a", "trend_direction": -1.0})
        sv_pos = extract_nl_ts_state({"run_id": "b", "trend_direction": 1.0})
        sv_mid = extract_nl_ts_state({"run_id": "c", "trend_direction": 0.0})
        # trend_direction is at index 3 in _NL_TS_RANGES
        assert abs(sv_neg.vector[3] - 0.0) < 1e-10
        assert abs(sv_pos.vector[3] - 1.0) < 1e-10
        assert abs(sv_mid.vector[3] - 0.5) < 1e-10

    def test_label_fallback(self):
        """Default label uses run_id when no label is provided."""
        sv = extract_nl_ts_state({"run_id": "test-42"})
        assert "test-42" in sv.label
