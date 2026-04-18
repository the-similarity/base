"""Structured event ingestion contracts — the canonical schema for world events.

This module defines the core data model for ingesting, storing, and
validating structured world events (rate hikes, earnings, geopolitical
shocks, pandemics, elections, etc.) and their market impact. These
contracts are the foundation for the events pillar of the platform.

Design decisions
----------------
- **Dataclasses, not Pydantic**: Matches the platform convention
  (``platform.contracts``, ``synthetic.contracts``) where internal
  data models use stdlib dataclasses and only the HTTP boundary uses
  Pydantic (``contracts.api``). Keeps import time fast and avoids
  pulling in Pydantic for batch/offline pipelines.
- **``to_dict`` / ``from_dict``**: Every dataclass round-trips through
  JSON-safe dicts. This is the serialization contract — all persistence
  (JSON, JSONL, registry) goes through these methods.
- **``EventType`` enum**: Provides a controlled vocabulary for common
  event categories while allowing free-form strings via the ``event_type``
  field on :class:`Event` (the enum is advisory, not enforced at the
  dataclass level, so new types don't require a code change).
- **``impact`` dict**: Loosely typed to accommodate varying impact
  schemas (single-asset, multi-asset, sector-level). The benchmark
  dataset demonstrates the canonical shape:
  ``{"asset": "SPY", "direction": "down", "magnitude_pct": -3.2}``.

Immutability
------------
Dataclasses are mutable for construction convenience. Once serialized
(written to JSON, registered in the platform), treat them as immutable.
Mutating a persisted event requires minting a new ``event_id``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# EventType enum
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    """Controlled vocabulary for common world event categories.

    Inherits from ``str`` so values round-trip through JSON without a
    custom encoder (same pattern as ``RunKind``, ``RunStatus``).

    Members cover the major macro-event categories relevant to financial
    markets. The list is intentionally short — extend it when a new
    category appears in production data, not speculatively.

    Members
    -------
    RATE_HIKE:
        Central bank interest rate increase.
    RATE_CUT:
        Central bank interest rate decrease.
    EARNINGS:
        Corporate earnings release (beat, miss, guidance).
    GEOPOLITICAL:
        Wars, sanctions, trade disputes, diplomatic crises.
    PANDEMIC:
        Disease outbreaks with economic impact (COVID, SARS, etc.).
    ELECTION:
        National elections, referendums, political transitions.
    REGULATORY:
        New regulations, antitrust actions, policy changes.
    NATURAL_DISASTER:
        Earthquakes, hurricanes, floods with economic impact.
    FINANCIAL_CRISIS:
        Bank failures, credit events, systemic risk episodes.
    TECHNOLOGY:
        Major tech events (product launches, breakthroughs, outages).
    """

    RATE_HIKE = "rate_hike"
    RATE_CUT = "rate_cut"
    EARNINGS = "earnings"
    GEOPOLITICAL = "geopolitical"
    PANDEMIC = "pandemic"
    ELECTION = "election"
    REGULATORY = "regulatory"
    NATURAL_DISASTER = "natural_disaster"
    FINANCIAL_CRISIS = "financial_crisis"
    TECHNOLOGY = "technology"


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


@dataclass
class Event:
    """A single structured world event with optional market impact.

    This is the atomic unit of the events pillar. Each event captures
    *what happened*, *when*, *where it came from*, and optionally
    *how it moved markets*.

    Fields
    ------
    event_id:
        Unique identifier. For benchmark events, use a descriptive slug
        (e.g. ``"fed-rate-hike-2022-03"``). For production events, use
        a UUID4 hex or source-system ID.
    timestamp:
        ISO-8601 date or datetime string (e.g. ``"2022-03-16"`` or
        ``"2022-03-16T14:00:00Z"``). Must be parseable by
        ``datetime.fromisoformat`` (Python 3.11+).
    event_type:
        Category string. Should match an :class:`EventType` value for
        well-known types, but free-form strings are accepted for novel
        categories.
    title:
        Short human-readable headline (< 120 chars recommended).
    description:
        Longer narrative description. May be empty for terse event feeds.
    source:
        Provenance tag — who/what produced this event record (e.g.
        ``"fed.gov"``, ``"reuters"``, ``"manual_curation"``).
    tags:
        Free-form labels for filtering and grouping (e.g.
        ``["macro", "us", "fomc"]``).
    metadata:
        Arbitrary key-value pairs for source-specific fields that don't
        fit the canonical schema (e.g. ``{"fomc_vote": "unanimous"}``).
    impact:
        Optional market impact record. The canonical shape is::

            {"asset": "SPY", "direction": "down", "magnitude_pct": -3.2}

        Multi-asset impacts use a list under ``"impacts"`` key. The
        schema is deliberately loose — validation is advisory, not
        enforced at the dataclass level.
    """

    event_id: str
    timestamp: str
    event_type: str
    title: str
    description: str = ""
    source: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    impact: Optional[Dict[str, Any]] = None

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dict suitable for ``json.dumps``.

        All fields pass through unchanged — no enum coercion needed
        since ``event_type`` is a plain string. ``impact`` is included
        even when ``None`` so the dict shape is stable for consumers
        that iterate over keys.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Event":
        """Reconstruct an :class:`Event` from a JSON-decoded dict.

        Unknown keys are ignored (forward compatibility). Missing
        optional fields fall back to their dataclass defaults.
        Required fields (``event_id``, ``timestamp``, ``event_type``,
        ``title``) raise ``KeyError`` if absent.
        """
        return cls(
            event_id=d["event_id"],
            timestamp=d["timestamp"],
            event_type=d["event_type"],
            title=d["title"],
            description=d.get("description", ""),
            source=d.get("source", ""),
            tags=d.get("tags", []) or [],
            metadata=d.get("metadata", {}) or {},
            impact=d.get("impact"),
        )


# ---------------------------------------------------------------------------
# EventSeries dataclass
# ---------------------------------------------------------------------------


@dataclass
class EventSeries:
    """An ordered collection of :class:`Event` instances with provenance.

    This is the top-level container for event datasets — benchmark
    fixtures, curated timelines, or production event feeds. The
    ``provenance`` dict follows the same shape as
    :class:`~the_similarity.platform.contracts.Provenance` for
    cross-pillar consistency.

    Fields
    ------
    events:
        Ordered list of events. No uniqueness constraint is enforced
        at this level — callers may have duplicate event_ids across
        different sources.
    name:
        Human-readable dataset name (e.g. ``"benchmark_macro_events"``).
    version:
        Semantic version string (e.g. ``"1.0.0"``). Bump when the
        event list changes.
    provenance:
        Free-form reproducibility record. Expected keys:
        ``generator_name``, ``created_at``, ``source``.
    """

    events: List[Event]
    name: str = ""
    version: str = "1.0.0"
    provenance: Dict[str, Any] = field(default_factory=dict)

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dict with nested events serialized."""
        return {
            "events": [e.to_dict() for e in self.events],
            "name": self.name,
            "version": self.version,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EventSeries":
        """Reconstruct an :class:`EventSeries` from a JSON-decoded dict.

        Each element of the ``"events"`` list is passed through
        :meth:`Event.from_dict`. Unknown top-level keys are ignored.
        """
        return cls(
            events=[Event.from_dict(e) for e in d.get("events", [])],
            name=d.get("name", ""),
            version=d.get("version", "1.0.0"),
            provenance=d.get("provenance", {}) or {},
        )


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "Event",
    "EventSeries",
    "EventType",
]
