# State Space Index

The state-space index maps every [[RunRecord]] in the [[RunRegistry]] to a fixed-length numeric vector, then indexes all vectors for nearest-neighbor lookup. It is the core data structure of the [[3D Data Space]].

## Key rule

**"3D is a view, not the model."** The state index is the model. The 3D scatter plot is one rendering surface. The same index supports CLI queries, API lookups, 2D plots, or 3D rendering. Intelligence lives in the index, not the renderer.

## StateVector (extractor)

Converts `RunRecord.summary` → `numpy.ndarray` (shape `(D,)`). Each slot maps to one metric, normalized to `[0, 1]`:

| Slot | Metric | Normalization |
|------|--------|---------------|
| 0 | `score` | identity (already [0,1]) |
| 1 | `n_matches` | `/ 1000`, clamped |
| 2 | `hit_rate` | identity |
| 3 | `n_ticks` | `/ 10000`, clamped |
| 4 | `fidelity_score` | identity |
| 5 | `calibration` | identity |

**Honest limitation**: normalization ranges are hardcoded, not learned. A run with 50k ticks clamps to 1.0, losing information.

## StateIndex

An `(N, D)` numpy matrix + a `run_id` list for provenance.

- **Build**: iterate `registry.list_runs()`, extract vector per run, stack.
- **Query**: brute-force cosine similarity, O(N) per query. Not scalable past ~10k runs.
- **Reduce**: PCA via numpy SVD to 2D or 3D for visualization.

## Cross-pillar similarity

The index connects runs across pillars. A finance backtest with 70% hit rate may be "near" a worlds simulation with similar dynamics, because both produce similar state vectors. This is the core value: **discovering correspondences the user did not search for**.

## What's missing (as of 2026-04-18)

- No ANN index (HNSW / faiss) — brute-force only.
- No temporal dimension — each run is a static point, not a trajectory.
- No learned embeddings — feature extraction is handcrafted.

## Code paths

- `the_similarity/platform/state_space.py` — Agent 1's implementation (may not exist yet)
- `examples/3d_state_space_demo.py` — canonical demo with inline extractors
- `the_similarity/tests/test_3d_state_space.py` — integration tests
- `vision/3d_data_space.md` — vision doc with roadmap

## See also

- [[state_graph]] — KNN graph built on top of the state index
- [[RunRegistry]] — source of RunRecords
- [[platform_spine]] — the registry and contracts layer
