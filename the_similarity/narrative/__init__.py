"""Narrative — natural-language scenario to time-series pipeline.

This package provides three capabilities:

1. **Schema and contracts** — NarrativeType enum, NarrativeEvent,
   NarrativeTransition, NarrativeSequence dataclasses with serialization.

2. **Text extraction** — rule-based keyword parser that converts free-text
   market narratives into structured NarrativeSequence objects.

3. **Trajectory compilation** — converts textual narrative sequences (crash,
   rally, consolidation, breakout, reversal, etc.) into deterministic NumPy
   price arrays and registers them as platform artifacts.

4. **Narrative retrieval** — converts compiled NarrativeSequence objects into
   numeric representations for feature extraction, history retrieval, and
   state-space integration.

Code paths:
    - ``the_similarity/narrative/contracts.py`` — NarrativeType, NarrativeEvent, etc.
    - ``the_similarity/narrative/parser.py`` — parse_narrative keyword parser
    - ``the_similarity/narrative/compiler.py`` — compile_trajectory, compile_and_register
    - ``the_similarity/narrative/retrieval.py`` — feature extraction, history search
    - ``the_similarity/narrative/data/example_narratives.json`` — example fixtures
"""

from the_similarity.narrative.contracts import (
    NarrativeEvent,
    NarrativeSequence,
    NarrativeTransition,
    NarrativeType,
)
from the_similarity.narrative.parser import parse_narrative
from the_similarity.narrative.retrieval import (
    extract_narrative_features,
    extract_nl_ts_state,
    find_similar_histories,
)

__all__ = [
    "NarrativeEvent",
    "NarrativeSequence",
    "NarrativeTransition",
    "NarrativeType",
    "extract_narrative_features",
    "extract_nl_ts_state",
    "find_similar_histories",
    "parse_narrative",
]
