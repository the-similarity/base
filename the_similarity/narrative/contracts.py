"""
Data contracts for the narrative schema.

These dataclasses define the structured representation of market narratives:
- NarrativeType: enum of canonical event types (CRASH, RALLY, etc.)
- NarrativeEvent: a single event with type, intensity, duration, description
- NarrativeTransition: edge between two events with trigger and sharpness
- NarrativeSequence: ordered list of events + transitions, the top-level container

All contracts support round-trip serialization via to_dict / from_dict.

Design invariants:
- intensity is clamped to [0, 1]. 0 = negligible, 1 = extreme.
- sharpness is clamped to [0, 1]. 0 = gradual, 1 = instantaneous.
- duration_bars is an integer >= 1. It represents the number of bars
  (days, hours, etc.) depending on the timeframe context.
- NarrativeSequence.transitions has len(events) - 1 entries when fully
  specified, but MAY be empty if transitions are unknown.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List


class NarrativeType(enum.Enum):
    """
    Canonical event types that a narrative can reference.

    These map to broad market regimes. The parser maps keywords to these
    types; downstream consumers (e.g. projector, synthetic generator)
    translate them into quantitative parameters.
    """

    CRASH = "crash"
    RALLY = "rally"
    CONSOLIDATION = "consolidation"
    BREAKOUT = "breakout"
    REVERSAL = "reversal"
    DRIFT = "drift"
    SPIKE = "spike"
    MEAN_REVERSION = "mean_reversion"


@dataclass
class NarrativeEvent:
    """
    A single narrative event — one phase of market behavior.

    Attributes:
        event_type: The canonical event type (from NarrativeType enum).
        intensity: Strength of the event, 0.0 (negligible) to 1.0 (extreme).
                   Derived from modifier words like "slightly" (0.3) or
                   "sharply" (0.8). Default 0.5 = moderate / unmodified.
        duration_bars: How many bars (time units) this event spans. Default 1.
                       Extracted from time phrases like "for 3 days" -> 3.
        description: Optional free-text description of the event, typically
                     the source sentence or phrase that produced this event.
    """

    event_type: NarrativeType
    intensity: float = 0.5
    duration_bars: int = 1
    description: str = ""

    def __post_init__(self) -> None:
        """Clamp intensity to [0, 1] and enforce duration_bars >= 1."""
        self.intensity = max(0.0, min(1.0, float(self.intensity)))
        self.duration_bars = max(1, int(self.duration_bars))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return {
            "event_type": self.event_type.value,
            "intensity": self.intensity,
            "duration_bars": self.duration_bars,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NarrativeEvent:
        """Deserialize from a plain dict. event_type is resolved by value."""
        return cls(
            event_type=NarrativeType(data["event_type"]),
            intensity=data.get("intensity", 0.5),
            duration_bars=data.get("duration_bars", 1),
            description=data.get("description", ""),
        )


@dataclass
class NarrativeTransition:
    """
    An edge between two consecutive NarrativeEvents.

    Captures *how* the market moved from one regime to the next.

    Attributes:
        from_event: The NarrativeType of the preceding event.
        to_event: The NarrativeType of the following event.
        trigger: Optional free-text description of the catalyst
                 (e.g. "Fed rate decision", "earnings miss").
        sharpness: How abrupt the transition is, 0.0 (gradual) to 1.0
                   (instantaneous). Default 0.5.
    """

    from_event: NarrativeType
    to_event: NarrativeType
    trigger: str = ""
    sharpness: float = 0.5

    def __post_init__(self) -> None:
        """Clamp sharpness to [0, 1]."""
        self.sharpness = max(0.0, min(1.0, float(self.sharpness)))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return {
            "from_event": self.from_event.value,
            "to_event": self.to_event.value,
            "trigger": self.trigger,
            "sharpness": self.sharpness,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NarrativeTransition:
        """Deserialize from a plain dict."""
        return cls(
            from_event=NarrativeType(data["from_event"]),
            to_event=NarrativeType(data["to_event"]),
            trigger=data.get("trigger", ""),
            sharpness=data.get("sharpness", 0.5),
        )


@dataclass
class NarrativeSequence:
    """
    Top-level container: an ordered sequence of narrative events with
    optional transitions between consecutive pairs.

    This is the output of parse_narrative() and the input to downstream
    consumers like the synthetic generator or projector.

    Attributes:
        events: Ordered list of NarrativeEvent objects.
        transitions: Ordered list of NarrativeTransition objects. When fully
                     specified, len(transitions) == len(events) - 1. May be
                     empty if transitions are not extracted.
        source_text: The original free-text narrative that was parsed.
        metadata: Arbitrary key-value metadata (e.g. parser version, model).
    """

    events: List[NarrativeEvent] = field(default_factory=list)
    transitions: List[NarrativeTransition] = field(default_factory=list)
    source_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full sequence to a plain dict."""
        return {
            "events": [e.to_dict() for e in self.events],
            "transitions": [t.to_dict() for t in self.transitions],
            "source_text": self.source_text,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NarrativeSequence:
        """Deserialize from a plain dict."""
        return cls(
            events=[NarrativeEvent.from_dict(e) for e in data.get("events", [])],
            transitions=[
                NarrativeTransition.from_dict(t) for t in data.get("transitions", [])
            ],
            source_text=data.get("source_text", ""),
            metadata=data.get("metadata", {}),
        )
