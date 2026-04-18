# 3D Data Space — Vision

## The Rule: "3D is a view, not the model"

The state-space index, the KNN graph, and the query engine are the model. The 3D scatter plot is one rendering surface. The same state data can be:

- Queried via CLI (`python -m the_similarity.platform list --nearest <run_id>`)
- Served via API (`GET /state-space/nearest?run_id=...&k=5`)
- Rendered as a 2D scatter, a sortable table, a graph visualization, or a 3D point cloud

**Never couple intelligence to the renderer.** The renderer consumes coordinates; it does not compute similarity, build graphs, or make decisions. If the 3D frontend is offline, every cross-pillar query still works.

## What the state space captures

Every run on the platform — finance retrieval, synthetic copies generation, worlds simulation — produces a `RunRecord` with a `summary` dict of headline metrics. The state-space index converts each summary into a fixed-length numeric vector (the *state vector*) and indexes all vectors for nearest-neighbor lookup.

This creates a **cross-pillar similarity surface**: a finance backtest with 70% hit rate and high calibration may be "near" a worlds simulation with similar dynamics, even though they operate on completely different data. The state space makes these correspondences discoverable.

### The workflow

1. **Register runs** — Runners (finance adapter, copies CLI, worlds headless runner) write `RunRecord`s to the SQLite registry.
2. **Build state index** — An extractor converts each record's `summary` dict into a numeric vector. All vectors are stacked into an (N, D) matrix.
3. **Query neighbors** — Cosine similarity over the matrix finds the k nearest runs to any query, regardless of pillar.
4. **Visualize** — PCA or t-SNE reduces the D-dimensional index to 2D or 3D coordinates for rendering. The visualization is a *derivative* of the index, not the index itself.

## What's honest

This section documents the real limitations — no hedging.

- **Brute-force cosine similarity** — The current implementation computes all-pairs similarity in O(N^2). This works for hundreds of runs. It will not scale past ~10,000 runs without switching to an approximate nearest-neighbor index.
- **PCA / t-SNE are standard, not optimized** — The dimensionality reduction uses textbook PCA via numpy SVD. It produces valid 3D coordinates but does not preserve local structure as well as UMAP or parametric t-SNE would.
- **Arbitrary normalization ranges** — The feature extractor normalizes metrics by dividing by hardcoded constants (e.g. `n_matches / 1000`, `n_ticks / 10000`). These ranges are not learned from the data distribution. A run with 50,000 ticks would be clamped to 1.0, losing information.
- **Fixed feature vector layout** — The extractor produces a fixed-length vector with a predetermined set of slots. Runs that populate different subsets of metrics will have zeros in unused slots, which biases cosine similarity toward runs that populate the same fields.
- **No temporal dimension** — The current index treats each run as a point. It does not track how a run's position evolves over time (e.g. a live simulation moving through state space as it progresses).

## Components

### StateVector (extractor)

Converts a `RunRecord.summary` dict into a `numpy.ndarray` of fixed length. Each slot in the vector corresponds to one metric, normalized to [0, 1].

**Code path**: `the_similarity/platform/state_space.py` (Agent 1)

### StateIndex

An (N, D) numpy matrix plus a list of `run_id`s for provenance. Supports:
- `add(record)` — append a new run's vector
- `query(run_id, k)` — find k nearest neighbors by cosine similarity
- `reduce(dims=3)` — PCA/t-SNE projection for visualization

### StateGraph (KNN graph)

A graph where nodes are runs and edges connect nearest neighbors. Supports:
- **Clusters** — connected components or community detection
- **Cross-domain bridges** — edges that connect runs from different pillars
- **Transitions** — if temporal evolution is added, edges between successive states of the same run

**Code path**: `the_similarity/platform/state_graph.py` (Agent 1)

## What's next

Ordered by impact and feasibility:

1. **Approximate nearest neighbors (HNSW / faiss)** — Replace brute-force with an ANN index. faiss is the obvious choice (battle-tested, numpy-native). This unlocks 100k+ runs without degrading query latency.

2. **Learned embeddings** — Replace the handcrafted feature extractor with a small encoder trained on run trajectories. The encoder maps heterogeneous summary dicts to a shared embedding space where similarity is semantically meaningful, not just metrically close.

3. **Temporal state evolution** — Track how a run's state vector changes over time (for live simulations). This turns the state space from a static snapshot into a dynamic trajectory field.

4. **Live state tracking** — Stream state updates from running simulations into the index in real time. The 3D view becomes a live dashboard showing runs moving through state space.

5. **Graph analytics** — Community detection on the KNN graph to find natural clusters of runs. Bridge edges (cross-pillar connections) become first-class objects the UI highlights.

## References

- `the_similarity/platform/registry.py` — the SQLite-backed run registry
- `the_similarity/platform/contracts.py` — RunRecord, RunStatus, RunKind
- `examples/3d_state_space_demo.py` — canonical demo (pure Python, no dependencies)
- `the_similarity/tests/test_3d_state_space.py` — integration tests
- `obsidian_thesim/concepts/state_space_index.md` — concept note
- `obsidian_thesim/concepts/state_graph.md` — concept note
