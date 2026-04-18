"""
In-memory event graph with cosine-similarity analogue search.

``EventGraph`` stores :class:`EventNode` objects keyed by ``event_id`` and
provides two retrieval primitives:

1. **find_analogues** — k-nearest neighbours by cosine similarity on the
   embedded feature vector produced by :func:`features.extract_event_features`.
2. **find_temporal_context** — all nodes within ±*window_days* of a reference
   timestamp.

The graph is intentionally simple (flat list + brute-force scan) so it works
without external dependencies.  For production-scale workloads (>100 k nodes)
swap the inner loop for a FAISS / Annoy index.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np

from the_similarity.events.features import extract_event_features


@dataclass
class EventNode:
    """Single node in the event graph.

    Attributes
    ----------
    event_id : str
        Unique identifier.  Auto-generated (UUID4) if not supplied.
    event_type : str
        Canonical type string (must be in ``features.EVENT_TYPES``).
    timestamp : str
        ISO-8601 date or datetime string.
    features : np.ndarray
        Fixed-length embedding produced by ``extract_event_features``.
    raw : dict
        Original event dict, kept for downstream consumers.
    """

    event_id: str
    event_type: str
    timestamp: str
    features: np.ndarray
    raw: dict = field(default_factory=dict, repr=False)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors, safe against zero-norm.

    Returns 0.0 when either vector has zero magnitude (avoids NaN).
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class EventGraph:
    """In-memory collection of :class:`EventNode` with similarity search.

    Usage::

        graph = EventGraph()
        graph.add_event({"event_type": "rate_decision",
                         "timestamp": "2022-03-16"})
        analogues = graph.find_analogues(
            {"event_type": "rate_decision", "timestamp": "2024-01-31"}, k=3
        )
    """

    def __init__(self) -> None:
        # _nodes is the authoritative store — a dict keyed by event_id for
        # O(1) lookup and de-duplication.
        self._nodes: Dict[str, EventNode] = {}

    # ── Mutation ─────────────────────────────────────────────────────

    def add_event(self, event: dict) -> EventNode:
        """Extract features from *event* and add a node to the graph.

        Parameters
        ----------
        event : dict
            Raw event dict.  Must contain ``event_type`` and ``timestamp``.
            If ``event_id`` is missing a UUID4 is generated.

        Returns
        -------
        EventNode
            The created (or existing) node.
        """
        event_id = event.get("event_id", str(uuid.uuid4()))
        features = extract_event_features(event)
        node = EventNode(
            event_id=event_id,
            event_type=event.get("event_type", "other"),
            timestamp=event["timestamp"],
            features=features,
            raw=event,
        )
        self._nodes[event_id] = node
        return node

    def build_from_series(self, events: List[dict]) -> None:
        """Bulk-load a list of event dicts into the graph.

        Existing nodes with the same ``event_id`` are overwritten.
        """
        for evt in events:
            self.add_event(evt)

    # ── Query ────────────────────────────────────────────────────────

    def find_analogues(
        self, query_event: dict, k: int = 5
    ) -> List[Tuple[EventNode, float]]:
        """Return the *k* most similar nodes by cosine similarity.

        Parameters
        ----------
        query_event : dict
            Event dict to compare against every node in the graph.
        k : int
            Number of neighbours to return.

        Returns
        -------
        list of (EventNode, float)
            Sorted descending by similarity score.
        """
        query_features = extract_event_features(query_event)
        scored: list[tuple[EventNode, float]] = []
        for node in self._nodes.values():
            sim = _cosine_similarity(query_features, node.features)
            scored.append((node, sim))
        # Sort descending by similarity, then take top-k.
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:k]

    def find_temporal_context(
        self, timestamp: str, window_days: int = 30
    ) -> List[EventNode]:
        """Return all nodes within ±*window_days* of *timestamp*.

        Parameters
        ----------
        timestamp : str
            ISO-8601 reference timestamp.
        window_days : int
            Half-window width in calendar days.

        Returns
        -------
        list of EventNode
            Unordered list of nodes falling inside the window.
        """
        ref = datetime.fromisoformat(timestamp)
        delta = timedelta(days=window_days)
        result: list[EventNode] = []
        for node in self._nodes.values():
            node_ts = datetime.fromisoformat(node.timestamp)
            if abs((node_ts - ref).total_seconds()) <= delta.total_seconds():
                result.append(node)
        return result

    # ── Introspection ────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, event_id: str) -> bool:
        return event_id in self._nodes
