# State Graph

The state graph is a KNN graph built on top of the [[state_space_index]]. Nodes are runs, edges connect nearest neighbors by cosine similarity.

## Structure

- **Nodes**: one per [[RunRecord]] in the [[RunRegistry]].
- **Edges**: directed, from each node to its k nearest neighbors (default k=5). Edge weight = cosine similarity.
- **Construction**: for each run, query the [[state_space_index]] for k nearest, add edges.

## Key concepts

### Clusters

Connected components or communities in the graph. Runs that cluster together share similar metric profiles. A cluster may span multiple pillars (e.g. a group of high-fidelity copies runs near high-calibration finance runs).

### Cross-domain bridges

Edges where `source.pillar != target.pillar`. These are the high-value discoveries: a finance run connected to a worlds simulation implies shared dynamics. The UI should highlight bridge edges.

### Transitions (future)

If temporal state evolution is implemented, edges between successive states of the same run. This turns the graph from a static snapshot into a dynamic trajectory network.

## Honest limitations

- **No graph library dependency**: the initial implementation uses adjacency lists in plain Python. No networkx, no graph-tool. This keeps the dependency footprint minimal but limits available algorithms (no spectral clustering, no PageRank out of the box).
- **k is a hyperparameter**: too low and the graph is disconnected; too high and every node connects to everything, losing structure. No principled selection method yet.
- **Static only**: the graph is rebuilt from scratch on every query. No incremental updates, no streaming.

## Code paths

- `the_similarity/platform/state_graph.py` — Agent 1's implementation (may not exist yet)
- `examples/3d_state_space_demo.py` — demo shows neighbor queries (implicit graph)
- `the_similarity/tests/test_3d_state_space.py` — tests cross-pillar neighbor queries

## See also

- [[state_space_index]] — the underlying vector index
- [[RunRegistry]] — source of RunRecords
