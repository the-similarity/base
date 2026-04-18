"""Narrative retrieval — bridging natural-language scenarios to historical data.

This package converts compiled NarrativeSequence objects (from the parser/compiler
pipeline built by Agents 1/2) into numeric representations suitable for:

1. **Feature extraction** — fixed-length vectors summarizing narrative structure
   (event type distribution, intensity, duration, transitions, trend).
2. **History retrieval** — finding the k most similar windows in real historical
   price data for a compiled narrative trajectory.
3. **State-space integration** — mapping NL_TS runs into :class:`StateVector`
   objects for the 3D Data Space visualization.

Code paths:
    - ``the_similarity/narrative/retrieval.py`` — all three capabilities
    - ``the_similarity/tests/test_narrative_retrieval.py`` — unit tests
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
