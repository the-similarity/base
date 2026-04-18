"""Events package — structured ingestion, event graph, retrieval, and prediction markets.

This package provides:

Ingestion layer (this PR):
- ``contracts``: Core dataclasses: Event, EventSeries, EventType.
- ``loader``: File I/O: load_events, save_events, validate_events.
- ``registry_adapter``: Platform integration (EventSeries -> RunArtifact).

Event intelligence:
- ``features``: Convert raw event dicts to fixed-length feature vectors.
- ``event_graph``: In-memory graph of EventNodes with cosine-similarity search.
- ``retrieval``: Sliding-window analogue retrieval over historical event streams.

Prediction markets:
- ``markets``: Core dataclasses: ForecastQuestion, MarketPrice,
  MarketHistory, QuestionSet.
- ``market_loader``: JSON persistence: load_questions / save_questions.
- ``market_adapter``: Platform registry integration: register a
  QuestionSet as a RunRecord with kind=EVENTS.

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
