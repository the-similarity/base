# State Graph

Graph construction over the shared [[state_space]] vectors.

## Code path
`the_similarity/core/state_graph.py`

## What it does
Builds weighted undirected graphs on top of `StateVector` objects, enabling topology-aware queries over the state space.

## Key APIs

| Function | Purpose |
|----------|---------|
| `build_knn_graph(vectors, k)` | K-nearest-neighbor graph (Euclidean distance) |
| `build_transition_graph(vectors, time_ordered)` | Temporal chain connecting consecutive states |
| `find_cross_domain_neighbors(graph, source_kind, target_kind, k)` | Cross-domain bridge queries ("this finance state looks like that worlds state") |
| `to_dict(graph)` / `from_dict(data)` | JSON-safe serialization for API transport |

## StateGraph class
- `nodes: list[StateVector]` — index position = node id
- `edges: list[tuple[int, int, float]]` — undirected weighted edges
- `adjacency(node_idx)` — lazy-built adjacency list
- `clusters(method="components")` — BFS connected components
- `shortest_path(from_idx, to_idx)` — Dijkstra on edge weights

## Key concepts

### Clusters
Connected components or communities in the graph. Runs that cluster together share similar metric profiles. A cluster may span multiple pillars (e.g. a group of high-fidelity copies runs near high-calibration finance runs).

### Cross-domain bridges
Edges where `source.pillar != target.pillar`. These are the high-value discoveries: a finance run connected to a worlds simulation implies shared dynamics. The UI should highlight bridge edges. Use `find_cross_domain_neighbors()` for explicit cross-domain queries.

### Transitions
Temporal chain connecting consecutive states via `build_transition_graph()`. Turns the graph from a static snapshot into a dynamic trajectory network.

## Dependencies
- numpy + scipy only (no networkx)
- Consumes `StateVector` from [[state_space]] (Agent 1's module)

## Scaling notes
- KNN uses brute-force O(n^2 * d) pairwise distance. For n > 10k, swap to approximate NN.
- Adjacency cache is lazily built and not invalidated — do not mutate edges after first query.
- k is a hyperparameter: too low and the graph is disconnected; too high and every node connects to everything, losing structure.

## Tests
21 tests in `the_similarity/tests/test_state_graph.py`.

## Additional references
- `examples/3d_state_space_demo.py` — demo shows neighbor queries (implicit graph)
- `the_similarity/tests/test_3d_state_space.py` — integration tests for cross-pillar queries
- `vision/3d_data_space.md` — vision doc

## See also
- [[state_space_index]] — the underlying vector index
- [[RunRegistry]] — source of RunRecords
