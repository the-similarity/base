"""Tests for the structured event ingestion package.

Covers:
- Event / EventSeries round-trip serialization (to_dict / from_dict)
- Benchmark dataset loads without error
- Validation catches missing required fields
- Validation catches duplicate event_ids
- Validation catches future timestamps
- JSONL format loading
- Save + load round-trip
- Registry adapter creates a run with kind=EVENTS
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_similarity.events.contracts import Event, EventSeries, EventType
from the_similarity.events.loader import load_events, save_events, validate_events
from the_similarity.events.registry_adapter import register_event_series
from the_similarity.platform.artifacts import RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Path to the benchmark dataset shipped with the package.
_BENCHMARK_PATH = (
    Path(__file__).resolve().parent.parent / "events" / "data" / "benchmark_events.json"
)


def _make_event(**overrides) -> Event:
    """Create a minimal valid Event, applying any field overrides."""
    defaults = {
        "event_id": "test-event-001",
        "timestamp": "2022-03-16",
        "event_type": "rate_hike",
        "title": "Test rate hike event",
        "description": "A test event.",
        "source": "test",
        "tags": ["test"],
        "metadata": {},
        "impact": {"asset": "SPY", "direction": "down", "magnitude_pct": -1.0},
    }
    defaults.update(overrides)
    return Event(**defaults)


def _make_series(events=None, **overrides) -> EventSeries:
    """Create a minimal valid EventSeries."""
    defaults = {
        "events": events or [_make_event()],
        "name": "test_series",
        "version": "1.0.0",
        "provenance": {"generator_name": "test"},
    }
    defaults.update(overrides)
    return EventSeries(**defaults)


# ---------------------------------------------------------------------------
# Event round-trip serialization
# ---------------------------------------------------------------------------


class TestEventSerialization:
    """Verify Event and EventSeries round-trip through dict form."""

    def test_event_round_trip(self) -> None:
        """Event -> to_dict -> from_dict produces an identical Event."""
        original = _make_event(
            tags=["macro", "us"],
            metadata={"vote": "unanimous"},
            impact={"asset": "SPY", "direction": "down", "magnitude_pct": -1.3},
        )
        rebuilt = Event.from_dict(original.to_dict())
        assert rebuilt.event_id == original.event_id
        assert rebuilt.timestamp == original.timestamp
        assert rebuilt.event_type == original.event_type
        assert rebuilt.title == original.title
        assert rebuilt.description == original.description
        assert rebuilt.source == original.source
        assert rebuilt.tags == original.tags
        assert rebuilt.metadata == original.metadata
        assert rebuilt.impact == original.impact

    def test_event_series_round_trip(self) -> None:
        """EventSeries -> to_dict -> from_dict preserves all events."""
        events = [
            _make_event(event_id="e1", title="First"),
            _make_event(event_id="e2", title="Second"),
        ]
        original = _make_series(events=events, name="round_trip_test")
        rebuilt = EventSeries.from_dict(original.to_dict())
        assert rebuilt.name == original.name
        assert rebuilt.version == original.version
        assert len(rebuilt.events) == 2
        assert rebuilt.events[0].event_id == "e1"
        assert rebuilt.events[1].title == "Second"

    def test_event_from_dict_ignores_unknown_keys(self) -> None:
        """Unknown keys in the dict are silently ignored."""
        d = _make_event().to_dict()
        d["unknown_field"] = "should be ignored"
        event = Event.from_dict(d)
        assert event.event_id == "test-event-001"

    def test_event_from_dict_missing_required_raises(self) -> None:
        """Missing required fields raise KeyError."""
        d = {"event_id": "x"}  # missing timestamp, event_type, title
        with pytest.raises(KeyError):
            Event.from_dict(d)


# ---------------------------------------------------------------------------
# Benchmark dataset
# ---------------------------------------------------------------------------


class TestBenchmarkDataset:
    """Verify the shipped benchmark fixture is valid."""

    def test_benchmark_loads(self) -> None:
        """Benchmark JSON loads into a valid EventSeries."""
        series = load_events(_BENCHMARK_PATH)
        assert isinstance(series, EventSeries)
        assert len(series.events) >= 20
        assert series.name == "benchmark_macro_events"

    def test_benchmark_validates_clean(self) -> None:
        """Benchmark dataset passes validation with no warnings."""
        series = load_events(_BENCHMARK_PATH)
        warnings = validate_events(series)
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_benchmark_event_types_match_enum(self) -> None:
        """All event_type values in the benchmark match an EventType enum member."""
        series = load_events(_BENCHMARK_PATH)
        valid_types = {e.value for e in EventType}
        for event in series.events:
            assert event.event_type in valid_types, (
                f"Event {event.event_id!r} has unknown type {event.event_type!r}"
            )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Test validate_events catches various problems."""

    def test_empty_series_warns(self) -> None:
        """An EventSeries with no events produces a warning."""
        series = _make_series(events=[])
        warnings = validate_events(series)
        assert any("no events" in w.lower() for w in warnings)

    def test_missing_required_field_warns(self) -> None:
        """An event with an empty title produces a warning."""
        event = _make_event(title="")
        series = _make_series(events=[event])
        warnings = validate_events(series)
        assert any("title" in w for w in warnings)

    def test_duplicate_event_id_warns(self) -> None:
        """Duplicate event_ids produce a warning."""
        events = [
            _make_event(event_id="dup", title="First"),
            _make_event(event_id="dup", title="Second"),
        ]
        series = _make_series(events=events)
        warnings = validate_events(series)
        assert any("duplicate" in w.lower() for w in warnings)

    def test_invalid_timestamp_warns(self) -> None:
        """A non-ISO-8601 timestamp produces a warning."""
        event = _make_event(timestamp="not-a-date")
        series = _make_series(events=[event])
        warnings = validate_events(series)
        assert any("not valid ISO-8601" in w for w in warnings)

    def test_future_timestamp_warns(self) -> None:
        """A timestamp far in the future produces a warning."""
        event = _make_event(timestamp="2099-01-01")
        series = _make_series(events=[event])
        warnings = validate_events(series)
        assert any("future" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


class TestFileIO:
    """Test save/load round-trip and JSONL format."""

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        """Save then load produces the same EventSeries."""
        original = _make_series(
            events=[_make_event(event_id="rt1"), _make_event(event_id="rt2")]
        )
        out_path = tmp_path / "events.json"
        save_events(original, out_path)
        loaded = load_events(out_path)
        assert loaded.name == original.name
        assert len(loaded.events) == 2
        assert loaded.events[0].event_id == "rt1"

    def test_load_jsonl(self, tmp_path: Path) -> None:
        """JSONL files load correctly (one Event dict per line)."""
        events = [_make_event(event_id="j1"), _make_event(event_id="j2")]
        jsonl_path = tmp_path / "events.jsonl"
        lines = [json.dumps(e.to_dict()) for e in events]
        jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        loaded = load_events(jsonl_path)
        assert len(loaded.events) == 2
        assert loaded.events[0].event_id == "j1"
        # JSONL loader derives name from filename stem.
        assert loaded.name == "events"

    def test_load_missing_file_raises(self) -> None:
        """Loading a nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_events("/nonexistent/path/events.json")


# ---------------------------------------------------------------------------
# Registry adapter
# ---------------------------------------------------------------------------


class TestRegistryAdapter:
    """Test that register_event_series creates a valid EVENTS run."""

    def test_register_creates_events_run(self, tmp_path: Path) -> None:
        """Registering an EventSeries writes a row with kind=EVENTS."""
        db_path = tmp_path / "registry.db"
        series = _make_series(
            events=[_make_event(event_id="r1"), _make_event(event_id="r2")],
            name="adapter_test",
        )
        run_id = register_event_series(series, db_path=str(db_path))

        with RunRegistry(db_path) as registry:
            artifact = registry.get(run_id)
        assert artifact is not None
        assert artifact.kind == RunKind.EVENTS
        assert artifact.summary["n_events"] == 2
        assert artifact.summary["pillar"] == "events"
        assert artifact.config["name"] == "adapter_test"

    def test_register_with_explicit_registry(self, tmp_path: Path) -> None:
        """Passing a pre-opened registry works correctly."""
        db_path = tmp_path / "registry.db"
        series = _make_series()
        with RunRegistry(db_path) as registry:
            run_id = register_event_series(series, registry=registry)
            artifact = registry.get(run_id)
        assert artifact is not None
        assert artifact.kind == RunKind.EVENTS
