"""Tests for streaming/progress infrastructure.

Tests the ProgressEvent callback mechanism in the core matcher and the
public search() API. WebSocket endpoint integration tests are separate
(require httpx + uvicorn).
"""
from __future__ import annotations

import numpy as np

from the_similarity import search, Config, ProgressEvent


def _make_synthetic(n: int = 500, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


class TestProgressCallback:
    """Test that progress_fn receives events at each pipeline stage."""

    def test_progress_events_emitted(self):
        """search() with progress_fn should emit prefilter, tier1, done events."""
        prices = _make_synthetic(500)
        query = prices[-60:]
        history = prices[:-60]

        events: list[ProgressEvent] = []
        results = search(
            query=query,
            history=history,
            top_k=5,
            stride=5,
            progress_fn=lambda e: events.append(e),
        )

        assert len(results.matches) > 0

        stages = [e.stage for e in events]
        assert "prefilter" in stages, "should emit prefilter event"
        assert "tier1" in stages, "should emit tier1 event"
        assert "done" in stages, "should emit done event"

    def test_progress_events_with_tier2(self):
        """With tier2 active, should emit tier2 progress events."""
        prices = _make_synthetic(500)
        query = prices[-60:]
        history = prices[:-60]

        events: list[ProgressEvent] = []
        # We only care about the streaming progress side effect here, not the
        # returned matches — leave the return value unbound to keep lint quiet.
        search(
            query=query,
            history=history,
            top_k=5,
            stride=5,
            progress_fn=lambda e: events.append(e),
        )

        stages = [e.stage for e in events]
        assert "tier2" in stages, "should emit tier2 events"

        # Tier2 events should have completed/total
        tier2_events = [e for e in events if e.stage == "tier2"]
        assert all(e.total > 0 for e in tier2_events)
        # Last tier2 event should have completed == total
        assert tier2_events[-1].completed == tier2_events[-1].total

    def test_progress_events_dtw_only(self):
        """With tier2 disabled, should NOT emit tier2 events."""
        prices = _make_synthetic(500)
        query = prices[-60:]
        history = prices[:-60]

        events: list[ProgressEvent] = []
        cfg = Config(
            active_methods=["dtw", "pearson_warped"],
            tier2_candidates=0,
        )
        search(
            query=query,
            history=history,
            top_k=5,
            config=cfg,
            stride=5,
            progress_fn=lambda e: events.append(e),
        )

        stages = [e.stage for e in events]
        assert "tier2" not in stages, "no tier2 events when tier2 disabled"
        assert "done" in stages

    def test_progress_done_has_top_score(self):
        """Done event should report the top match score."""
        prices = _make_synthetic(500)
        query = prices[-60:]
        history = prices[:-60]

        events: list[ProgressEvent] = []
        # We only care about the streaming progress side effect here, not the
        # returned matches — leave the return value unbound to keep lint quiet.
        search(
            query=query,
            history=history,
            top_k=5,
            stride=5,
            progress_fn=lambda e: events.append(e),
        )

        done_events = [e for e in events if e.stage == "done"]
        assert len(done_events) == 1
        done = done_events[0]
        assert done.top_score > 0
        assert done.completed > 0

    def test_progress_no_callback_works(self):
        """search() without progress_fn should work exactly as before."""
        prices = _make_synthetic(500)
        query = prices[-60:]
        history = prices[:-60]

        results = search(query=query, history=history, top_k=5, stride=5)
        assert len(results.matches) > 0

    def test_progress_prefilter_count(self):
        """Prefilter event should report number of surviving candidates."""
        prices = _make_synthetic(500)
        query = prices[-60:]
        history = prices[:-60]

        events: list[ProgressEvent] = []
        search(
            query=query,
            history=history,
            top_k=5,
            stride=5,
            progress_fn=lambda e: events.append(e),
        )

        prefilter_events = [e for e in events if e.stage == "prefilter"]
        assert len(prefilter_events) == 1
        assert prefilter_events[0].completed > 0

    def test_progress_event_fields(self):
        """ProgressEvent should have all expected fields."""
        event = ProgressEvent(
            stage="tier2",
            completed=5,
            total=20,
            message="enriched 5/20 candidates",
            top_score=82.3,
            top_match_idx=150,
        )
        assert event.stage == "tier2"
        assert event.completed == 5
        assert event.total == 20
        assert event.message == "enriched 5/20 candidates"
        assert event.top_score == 82.3
        assert event.top_match_idx == 150

    def test_empty_history_emits_done(self):
        """When no candidates found, should still emit done."""
        query = np.array([1.0, 2.0, 3.0])
        history = np.array([1.0, 2.0])  # too short

        events: list[ProgressEvent] = []
        results = search(
            query=query,
            history=history,
            top_k=5,
            progress_fn=lambda e: events.append(e),
        )

        assert len(results.matches) == 0
        stages = [e.stage for e in events]
        assert "done" in stages
