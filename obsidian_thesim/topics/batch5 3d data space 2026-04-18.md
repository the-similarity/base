# Batch 5: 3D Data Space — Decision Record (2026-04-18)

## What was decided

Ship the 3D Data Space as a **state-space index over the [[RunRegistry]]** with a strict architectural rule: **"3D is a view, not the model."**

The state-space index, nearest-neighbor queries, and dimensionality reduction are pure data-layer operations. The 3D scatter plot (or any other visualization) is a rendering surface that consumes coordinates, not the source of intelligence.

## Why this rule matters

Without it, the 3D frontend becomes the system of record for cross-pillar similarity. That creates three problems:

1. **Testing requires a browser.** If similarity logic lives in the renderer, you can't unit-test it without spinning up a WebGL context.
2. **CLI and API are second-class.** Power users who want programmatic access must reverse-engineer the frontend's internal state.
3. **Renderer lock-in.** Switching from Three.js to a 2D plot or a table requires reimplementing the intelligence, not just swapping a view.

## What ships in Batch 5

- [[state_space_index]] — StateVector extractor + StateIndex (numpy matrix)
- [[state_graph]] — KNN graph with cross-domain bridge detection
- Integration tests (`test_3d_state_space.py`)
- Canonical demo (`examples/3d_state_space_demo.py`)
- Vision doc (`vision/3d_data_space.md`)
- Smoke script (`scripts/smoke_3d_state_space.sh`)

## Alternatives considered

### 1. Embedding via a learned model (rejected for MVP)

A small encoder trained on run trajectories would produce semantically meaningful embeddings. Rejected because we don't have enough training data yet (need hundreds of diverse runs), and the handcrafted extractor is sufficient to validate the architecture.

### 2. Graph database (Neo4j / ArangoDB) (rejected)

Overkill for the current scale (<1k runs). SQLite + numpy adjacency lists are simpler, dependency-free, and sufficient until we hit ~10k nodes. If we reach that scale, faiss + a graph DB become worth the operational cost.

### 3. Frontend-first approach (rejected)

Build the 3D scatter plot first and add the data layer later. Rejected because it violates the architectural rule and creates the three problems described above. The data layer comes first; the renderer comes when the data layer is proven.

## Honest limitations documented

- Brute-force cosine sim (not scalable past ~10k runs)
- PCA/t-SNE are standard but not optimized
- Feature extractors use arbitrary normalization ranges
- No temporal dimension (runs are static points)
- No learned embeddings

## What's next

1. Approximate nearest neighbors (HNSW / faiss)
2. Learned embeddings from run trajectories
3. Temporal state evolution
4. Live state tracking for running simulations
5. Graph analytics (community detection, bridge highlighting)

## See also

- [[state_space_index]]
- [[state_graph]]
- `vision/3d_data_space.md`
