"""Structured event ingestion — world events schema, loader, and registry adapter.

This package provides the foundational data model for ingesting structured
world events (rate hikes, pandemics, elections, etc.) with optional market
impact metadata. It is the starting point for the events pillar of the
platform.

Modules
-------
contracts
    Core dataclasses: :class:`Event`, :class:`EventSeries`, :class:`EventType`.
loader
    File I/O: ``load_events``, ``save_events``, ``validate_events``.
registry_adapter
    Platform integration: ``register_event_series`` writes an
    :class:`~the_similarity.platform.artifacts.RunArtifact` with
    ``kind=RunKind.EVENTS``.

Benchmark dataset
-----------------
``the_similarity/events/data/benchmark_events.json`` ships 25 curated
historical events with approximate market impact. Use it for testing
and as a schema reference.
"""

from the_similarity.events.contracts import Event, EventSeries, EventType
from the_similarity.events.loader import load_events, save_events, validate_events

__all__ = [
    "Event",
    "EventSeries",
    "EventType",
    "load_events",
    "save_events",
    "validate_events",
]
