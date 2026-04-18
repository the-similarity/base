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

## Dependencies
- numpy + scipy only (no networkx)
- Consumes `StateVector` from [[state_space]] (Agent 1's module)

## Scaling notes
- KNN uses brute-force O(n^2 * d) pairwise distance. For n > 10k, swap to approximate NN.
- Adjacency cache is lazily built and not invalidated — do not mutate edges after first query.

## Tests
21 tests in `the_similarity/tests/test_state_graph.py`.
