# Narrative Retrieval

Bridges natural-language scenario descriptions (compiled into 1D price trajectories) with the existing similarity engine and [[state_space|state-space]] infrastructure.

## Code path
`the_similarity/narrative/retrieval.py`

## Three capabilities

### 1. Feature extraction
`extract_narrative_features(sequence: dict) -> np.ndarray`
- Converts a NarrativeSequence dict to a 15-dim feature vector
- Dims 0-9: event type distribution (one per canonical EventType, sorted)
- Dim 10: mean intensity
- Dim 11: mean duration (normalized)
- Dim 12: transition ratio (type changes / total events)
- Dim 13: trend direction (+1/-1/0)
- Dim 14: total duration (normalized)

### 2. History retrieval
`find_similar_histories(trajectory, historical_data, k=5) -> list[dict]`
- Sliding-window normalized cross-correlation against historical price series
- Returns top-k matches with `{symbol, start_idx, end_idx, similarity, window_data}`
- Lightweight alternative to `api.search()` — use the full pipeline when 9-method scoring is needed

### 3. State-space integration
`extract_nl_ts_state(run_summary: dict) -> StateVector`
- Maps NL_TS run summaries to StateVector for the 3D Data Space
- Follows the same pattern as `extract_finance_state`, `extract_copies_state`, `extract_worlds_state`
- NOT yet wired into `build_index_from_registry` — add `"nl_ts": extract_nl_ts_state` to `_PILLAR_EXTRACTORS` when ready

## Integration points
- Depends on: [[state_space]] (`StateVector`, `MAX_DIM`, `_normalize`)
- Consumed by: narrative pipeline (Agents 1/2 build contracts/parser/compiler)
- Does NOT import narrative contracts — operates on plain dicts for parallel-safe development
