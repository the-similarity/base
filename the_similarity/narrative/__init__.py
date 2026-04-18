"""Narrative — natural-language scenario to time-series pipeline.

This package provides two capabilities:

1. **Trajectory compilation** — converts textual narrative sequences (crash,
   rally, consolidation, breakout, reversal, etc.) into deterministic NumPy
   price arrays and registers them as platform artifacts.

2. **Narrative retrieval** — converts compiled NarrativeSequence objects into
   numeric representations for feature extraction, history retrieval, and
   state-space integration.

Code paths:
    - ``the_similarity/narrative/compiler.py`` — compile_trajectory, compile_and_register
    - ``the_similarity/narrative/retrieval.py`` — feature extraction, history search
    - ``the_similarity/tests/test_narrative_compiler.py`` — compiler unit tests
    - ``the_similarity/tests/test_narrative_retrieval.py`` — retrieval unit tests
"""

from the_similarity.narrative.retrieval import (
    extract_narrative_features,
    extract_nl_ts_state,
    find_similar_histories,
)

__all__ = [
    "extract_narrative_features",
    "extract_nl_ts_state",
    "find_similar_histories",
]
