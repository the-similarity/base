"""Prediction market contracts — the canonical object model for forecast questions.

This module defines the core dataclasses for ingesting prediction market
data from platforms like Polymarket, Metaculus, and Manifold Markets.
Every dataclass carries ``to_dict()`` / ``from_dict()`` for JSON
round-tripping, following the same pattern as
:mod:`the_similarity.platform.contracts`.

Dataclass hierarchy
-------------------
- :class:`ForecastQuestion` — one binary question with resolution metadata.
- :class:`MarketPrice` — one probability observation at a point in time.
- :class:`MarketHistory` — a question + its price time series.
- :class:`QuestionSet` — a named, versioned collection of histories.

Immutability contract
---------------------
Dataclasses are mutable during construction (not ``frozen=True``) so
loaders can build them incrementally. Once serialized (written to JSON,
registered in the registry), consumers MUST treat them as immutable.

Field-name freeze warning
-------------------------
Every field name and type below is part of the events pillar's wire
contract. Changing any of them breaks saved JSON files and any
downstream consumer. Safe changes: add optional fields with defaults.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# ForecastQuestion — one binary prediction market question
# ---------------------------------------------------------------------------


@dataclass
class ForecastQuestion:
    """A single binary forecast question from a prediction market.

    Fields
    ------
    question_id:
        Stable identifier, unique within a :class:`QuestionSet`. Format
        is platform-dependent (e.g. Polymarket slug, Metaculus numeric ID).
    question:
        Human-readable question text (e.g. "Will the Fed raise rates in
        June 2024?").
    category:
        Coarse topic bucket for filtering and grouping. Examples:
        ``"economics"``, ``"geopolitics"``, ``"technology"``,
        ``"climate"``, ``"health"``.
    resolution_date:
        Optional ISO-8601 date (YYYY-MM-DD) when the question resolves.
        ``None`` for open-ended or perpetual markets.
    resolved:
        Whether the question has reached its final resolution. ``False``
        for active markets.
    resolution:
        The binary outcome: ``True`` if the event occurred, ``False`` if
        not. ``None`` if unresolved or if the market was voided.
    source:
        Platform name (``"polymarket"``, ``"metaculus"``, ``"manifold"``).
        Free-form string — no enum because new platforms emerge often.
    metadata:
        Free-form dict for platform-specific fields (market URL, creator,
        liquidity pool size, etc.). Must be JSON-serializable.
    """

    question_id: str
    question: str
    category: str
    source: str
    resolution_date: Optional[str] = None
    resolved: bool = False
    resolution: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dict representation.

        All fields pass through unchanged — no enums to coerce. The
        ``metadata`` dict is NOT deep-copied; callers must not mutate
        it after serialization.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ForecastQuestion":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            question_id=d["question_id"],
            question=d["question"],
            category=d["category"],
            source=d["source"],
            resolution_date=d.get("resolution_date"),
            resolved=d.get("resolved", False),
            resolution=d.get("resolution"),
            metadata=d.get("metadata", {}) or {},
        )


# ---------------------------------------------------------------------------
# MarketPrice — one probability observation
# ---------------------------------------------------------------------------


@dataclass
class MarketPrice:
    """A single probability observation from a prediction market.

    Fields
    ------
    question_id:
        FK to :class:`ForecastQuestion.question_id`. Denormalized here
        so individual price records are self-describing (useful for
        streaming / append-only ingestion).
    timestamp:
        ISO-8601 datetime string (YYYY-MM-DDTHH:MM:SSZ). Prices sort
        lexicographically by timestamp for time-series ordering.
    probability:
        Market-implied probability in ``[0, 1]``. For AMM-based markets
        this is the mid price; for order-book markets this is the last
        trade price normalized.
    volume:
        Optional trading volume for this observation period. Units are
        platform-dependent (USD for Polymarket, mana for Manifold).
        ``None`` when volume data is unavailable.
    """

    question_id: str
    timestamp: str
    probability: float
    volume: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dict representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MarketPrice":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        return cls(
            question_id=d["question_id"],
            timestamp=d["timestamp"],
            probability=d["probability"],
            volume=d.get("volume"),
        )


# ---------------------------------------------------------------------------
# MarketHistory — question + price time series
# ---------------------------------------------------------------------------


@dataclass
class MarketHistory:
    """A forecast question paired with its full price history.

    The ``prices`` list is expected to be sorted by timestamp ascending.
    Loaders enforce this on read; the dataclass does NOT sort internally
    to avoid surprising callers who rely on insertion order during
    incremental construction.

    Fields
    ------
    question:
        The :class:`ForecastQuestion` this history belongs to.
    prices:
        Chronologically ordered list of :class:`MarketPrice` observations.
        Empty list for questions with no price data (e.g. newly created
        markets).
    """

    question: ForecastQuestion
    prices: List[MarketPrice] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe nested dict."""
        return {
            "question": self.question.to_dict(),
            "prices": [p.to_dict() for p in self.prices],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MarketHistory":
        """Reconstruct from a JSON-decoded dict."""
        return cls(
            question=ForecastQuestion.from_dict(d["question"]),
            prices=[MarketPrice.from_dict(p) for p in d.get("prices", [])],
        )


# ---------------------------------------------------------------------------
# QuestionSet — named collection of market histories
# ---------------------------------------------------------------------------


@dataclass
class QuestionSet:
    """A named, versioned collection of :class:`MarketHistory` entries.

    Question sets are the unit of registration on the platform: a set
    is registered as a single ``RunRecord`` with ``kind=EVENTS``.

    Fields
    ------
    questions:
        List of :class:`MarketHistory` entries. Order is preserved but
        not semantically meaningful.
    name:
        Human-readable name (e.g. ``"benchmark-binary-2022"``).
    version:
        Semantic version string (e.g. ``"v1.0"``). Bump when questions
        are added, removed, or price histories are updated.
    """

    questions: List[MarketHistory]
    name: str
    version: str

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe nested dict."""
        return {
            "questions": [q.to_dict() for q in self.questions],
            "name": self.name,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QuestionSet":
        """Reconstruct from a JSON-decoded dict."""
        return cls(
            questions=[MarketHistory.from_dict(q) for q in d.get("questions", [])],
            name=d["name"],
            version=d["version"],
        )


__all__ = [
    "ForecastQuestion",
    "MarketHistory",
    "MarketPrice",
    "QuestionSet",
]
