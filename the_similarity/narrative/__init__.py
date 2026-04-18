"""
Narrative schema and text extraction for natural-language-to-timeseries.

This package provides:
- Data contracts for narrative events, transitions, and sequences
- A rule-based keyword parser that converts free-text market narratives
  into structured NarrativeSequence objects

The parser is a **baseline** implementation using keyword matching and
modifier-based intensity scoring. It is NOT an NLU system — it exists
to validate the schema and provide a deterministic fallback before any
ML-based parser is built.
"""

from the_similarity.narrative.contracts import (
    NarrativeEvent,
    NarrativeSequence,
    NarrativeTransition,
    NarrativeType,
)
from the_similarity.narrative.parser import parse_narrative

__all__ = [
    "NarrativeEvent",
    "NarrativeSequence",
    "NarrativeTransition",
    "NarrativeType",
    "parse_narrative",
]
