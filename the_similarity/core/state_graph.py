"""
Graph construction over the shared state space.

Builds KNN graphs, transition graphs, and cross-domain bridge queries
on top of StateVector objects. All graph algorithms use numpy + scipy
(no networkx dependency) to keep the dependency footprint minimal.

Lifecycle:
    1. Create StateVector instances (from state_space.py, the canonical owner).
    2. Call build_knn_graph() or build_transition_graph() to produce a StateGraph.
    3. Query the graph: adjacency(), clusters(), shortest_path().
    4. Serialize with to_dict() / from_dict() for API transport.

Immutability:
    StateGraph.nodes is set at construction and must not be mutated afterward.
    edges is append-only during build and frozen after construction.

Mathematical constraints:
    - KNN graph: O(n^2 * d) brute-force pairwise distance where n = len(vectors),
      d = embedding dimensionality.  For n > ~10k, consider approximate NN.
    - Dijkstra: O((V + E) log V) via scipy.sparse.csgraph or manual heapq.
    - Clustering: connected-components is O(V + E); no iterative methods here.

Code path: the_similarity/core/state_graph.py
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# StateVector — canonical definition lives in state_space.py (Agent 1's module).
# This module re-exports it so existing consumers can still do:
#     from the_similarity.core.state_graph import StateVector
# ---------------------------------------------------------------------------

from the_similarity.core.state_space import StateVector


# ---------------------------------------------------------------------------
# StateGraph
# ---------------------------------------------------------------------------


@dataclass
class StateGraph:
    """Weighted undirected graph over StateVector nodes.

    nodes:  Ordered list of StateVector.  Index position == node id.
    edges:  List of (node_i, node_j, distance) triples.  Undirected:
            if (i, j, d) is present, the reverse is implied by adjacency().
    """

    nodes: list[StateVector] = field(default_factory=list)
    edges: list[tuple[int, int, float]] = field(default_factory=list)

    # -- internal adjacency cache (lazily built) --
    _adj: dict[int, list[tuple[int, float]]] | None = field(
        default=None, repr=False, compare=False
    )

    # ------------------------------------------------------------------ #
    #  Adjacency
    # ------------------------------------------------------------------ #

    def _build_adj(self) -> dict[int, list[tuple[int, float]]]:
        """Build adjacency list from edge list.  O(E)."""
        adj: dict[int, list[tuple[int, float]]] = {i: [] for i in range(len(self.nodes))}
        for i, j, d in self.edges:
            adj[i].append((j, d))
            adj[j].append((i, d))
        return adj

    def adjacency(self, node_idx: int) -> list[tuple[int, float]]:
        """Return neighbors of *node_idx* as [(neighbor_idx, distance), ...].

        Lazily builds and caches the adjacency dict on first call.
        Cache is invalidated if edges change (caller must not mutate edges
        after first adjacency() call — build phase is over).
        """
        if self._adj is None:
            self._adj = self._build_adj()
        return self._adj.get(node_idx, [])

    # ------------------------------------------------------------------ #
    #  Clustering — connected components via BFS
    # ------------------------------------------------------------------ #

    def clusters(self, method: str = "components") -> list[list[int]]:
        """Return clusters of node indices.

        Parameters:
            method: Only "components" is supported (connected components via
                    BFS).  Future: "density" for DBSCAN-like clustering.

        Returns:
            List of clusters, each a list of node indices.  Every node
            appears in exactly one cluster.

        Raises:
            ValueError: If *method* is not recognized.
        """
        if method != "components":
            raise ValueError(f"Unknown clustering method: {method!r}. Supported: 'components'.")

        n = len(self.nodes)
        if n == 0:
            return []

        # Ensure adjacency is built.
        if self._adj is None:
            self._adj = self._build_adj()

        visited: set[int] = set()
        clusters: list[list[int]] = []

        for start in range(n):
            if start in visited:
                continue
            # BFS from *start*
            component: list[int] = []
            queue = [start]
            visited.add(start)
            while queue:
                node = queue.pop(0)
                component.append(node)
                for neighbor, _dist in self._adj.get(node, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            clusters.append(component)

        return clusters

    # ------------------------------------------------------------------ #
    #  Shortest path — Dijkstra
    # ------------------------------------------------------------------ #

    def shortest_path(self, from_idx: int, to_idx: int) -> list[int]:
        """Dijkstra shortest path from *from_idx* to *to_idx*.

        Returns:
            Ordered list of node indices from source to destination
            (inclusive).  Empty list if no path exists.

        Complexity: O((V + E) log V) using a binary heap.
        """
        if from_idx == to_idx:
            return [from_idx]

        if self._adj is None:
            self._adj = self._build_adj()

        n = len(self.nodes)
        # dist[i] = shortest known distance from from_idx to i
        dist = [float("inf")] * n
        dist[from_idx] = 0.0
        # prev[i] = predecessor on shortest path
        prev: list[int | None] = [None] * n
        # Min-heap: (distance, node_idx)
        heap: list[tuple[float, int]] = [(0.0, from_idx)]

        while heap:
            d, u = heapq.heappop(heap)
            if u == to_idx:
                break
            if d > dist[u]:
                # Stale entry — skip.
                continue
            for v, w in self._adj.get(u, []):
                nd = d + w
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))

        # Reconstruct path
        if dist[to_idx] == float("inf"):
            return []  # No path exists

        path: list[int] = []
        cur: int | None = to_idx
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return path


# ---------------------------------------------------------------------------
# Graph builders
# ---------------------------------------------------------------------------


def _pairwise_distances(vectors: list[StateVector]) -> np.ndarray:
    """Compute pairwise Euclidean distance matrix.

    Returns:
        (n, n) float64 array where D[i, j] = ||v_i - v_j||_2.

    Uses vectorized numpy for speed.  Memory: O(n^2).  For n > ~10k
    consider chunked or approximate approaches.
    """
    # Stack all value arrays into (n, d) matrix
    # .vector is the canonical field name from state_space.StateVector
    mat = np.array([v.vector for v in vectors], dtype=np.float64)
    # ||a - b||^2 = ||a||^2 + ||b||^2 - 2 a . b
    sq_norms = np.sum(mat ** 2, axis=1)
    # (n,) + (n,1) - 2*(n,n)  → broadcast to (n,n)
    dist_sq = sq_norms[np.newaxis, :] + sq_norms[:, np.newaxis] - 2.0 * mat @ mat.T
    # Numerical guard: clamp negative values from floating-point error
    np.maximum(dist_sq, 0.0, out=dist_sq)
    return np.sqrt(dist_sq)


def build_knn_graph(vectors: list[StateVector], k: int = 5) -> StateGraph:
    """Build a k-nearest-neighbor graph over *vectors*.

    Each node is a StateVector. For every node, edges connect it to its
    *k* nearest neighbors (by Euclidean distance), with the distance as
    edge weight.  The graph is undirected: if A is a KNN of B, the edge
    (A, B, dist) is stored once but adjacency() returns it from both sides.

    Parameters:
        vectors: List of StateVector with identical dimensionality.
        k:       Number of nearest neighbors per node.  Clamped to
                 len(vectors) - 1 if larger.

    Returns:
        StateGraph with nodes = *vectors* and KNN edges.

    Raises:
        ValueError: If vectors is empty or k < 1.
    """
    if not vectors:
        raise ValueError("vectors must be non-empty.")
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}.")

    n = len(vectors)
    # Clamp k so we don't try to find more neighbors than exist
    k = min(k, n - 1)

    dist_matrix = _pairwise_distances(vectors)

    # For each node, pick k nearest (excluding self)
    # Use a set to deduplicate undirected edges
    edge_set: set[tuple[int, int]] = set()
    edges: list[tuple[int, int, float]] = []

    for i in range(n):
        # argsort row, skip self (distance 0)
        neighbors = np.argsort(dist_matrix[i])
        count = 0
        for j_idx in range(n):
            j = int(neighbors[j_idx])
            if j == i:
                continue
            # Canonical edge key: smaller index first
            edge_key = (min(i, j), max(i, j))
            if edge_key not in edge_set:
                edge_set.add(edge_key)
                edges.append((i, j, float(dist_matrix[i, j])))
            count += 1
            if count >= k:
                break

    return StateGraph(nodes=list(vectors), edges=edges)


def build_transition_graph(
    vectors: list[StateVector], time_ordered: bool = True
) -> StateGraph:
    """Build a sequential transition graph over *vectors*.

    If *time_ordered* is True (default), each vector is connected to the
    next one in list order — representing temporal evolution (e.g.
    sequential backtest windows).

    If *time_ordered* is False, falls back to a KNN graph with k=2 as a
    sensible default for unordered data.

    Parameters:
        vectors:      List of StateVector.
        time_ordered: Whether the input list is chronologically ordered.

    Returns:
        StateGraph with linear chain edges (time_ordered=True) or
        KNN edges (time_ordered=False).
    """
    if not vectors:
        raise ValueError("vectors must be non-empty.")

    if not time_ordered:
        return build_knn_graph(vectors, k=2)

    # Connect each node to the next in sequence
    edges: list[tuple[int, int, float]] = []
    for i in range(len(vectors) - 1):
        # Euclidean distance between consecutive states
        # .vector is the canonical field name from state_space.StateVector
        d = float(np.linalg.norm(
            np.asarray(vectors[i].vector, dtype=np.float64)
            - np.asarray(vectors[i + 1].vector, dtype=np.float64)
        ))
        edges.append((i, i + 1, d))

    return StateGraph(nodes=list(vectors), edges=edges)


# ---------------------------------------------------------------------------
# Cross-domain bridge queries
# ---------------------------------------------------------------------------


def find_cross_domain_neighbors(
    graph: StateGraph,
    source_kind: str,
    target_kind: str,
    k: int = 3,
) -> list[tuple[int, int, float]]:
    """For each node of *source_kind*, find its k nearest neighbors of *target_kind*.

    This is the "this finance state looks like that worlds state" query.
    Uses brute-force pairwise distance between the two subsets.

    Parameters:
        graph:       StateGraph to query.
        source_kind: Domain label of source nodes (e.g. "finance").
        target_kind: Domain label of target nodes (e.g. "worlds").
        k:           Number of nearest cross-domain neighbors per source node.

    Returns:
        List of (source_idx, target_idx, distance) triples, where indices
        are positions in graph.nodes.  Sorted by (source_idx, distance).
    """
    # Partition nodes by kind
    # .source_kind is the canonical field name from state_space.StateVector
    source_indices = [i for i, v in enumerate(graph.nodes) if v.source_kind == source_kind]
    target_indices = [i for i, v in enumerate(graph.nodes) if v.source_kind == target_kind]

    if not source_indices or not target_indices:
        return []

    # Build matrices for vectorized distance computation
    source_mat = np.array(
        [graph.nodes[i].vector for i in source_indices], dtype=np.float64
    )
    target_mat = np.array(
        [graph.nodes[i].vector for i in target_indices], dtype=np.float64
    )

    # Pairwise distances: (|source|, |target|)
    # ||s - t||^2 = ||s||^2 + ||t||^2 - 2 s . t
    s_sq = np.sum(source_mat ** 2, axis=1, keepdims=True)  # (|s|, 1)
    t_sq = np.sum(target_mat ** 2, axis=1, keepdims=True)  # (|t|, 1)
    cross_dist_sq = s_sq + t_sq.T - 2.0 * source_mat @ target_mat.T
    np.maximum(cross_dist_sq, 0.0, out=cross_dist_sq)
    cross_dist = np.sqrt(cross_dist_sq)

    # For each source, pick k nearest targets
    actual_k = min(k, len(target_indices))
    results: list[tuple[int, int, float]] = []

    for si, src_idx in enumerate(source_indices):
        nearest = np.argsort(cross_dist[si])[:actual_k]
        for ti in nearest:
            tgt_idx = target_indices[int(ti)]
            results.append((src_idx, tgt_idx, float(cross_dist[si, int(ti)])))

    return results


# ---------------------------------------------------------------------------
# Serialization — JSON-safe dict round-trip
# ---------------------------------------------------------------------------


def to_dict(graph: StateGraph) -> dict[str, Any]:
    """Serialize a StateGraph to a JSON-safe dictionary.

    Node values (numpy arrays) are converted to plain Python lists.
    Meta dicts are preserved as-is (must already be JSON-serializable).

    Returns:
        Dict with keys "nodes" and "edges", suitable for json.dumps().
    """
    nodes = []
    for v in graph.nodes:
        node_d: dict[str, Any] = {
            # Serialize canonical field names from state_space.StateVector
            "vector": v.vector.tolist() if isinstance(v.vector, np.ndarray) else list(v.vector),
            "source_kind": v.source_kind,
            "source_id": v.source_id,
            "label": v.label,
        }
        if v.metadata:
            node_d["metadata"] = v.metadata
        nodes.append(node_d)

    edges = [{"i": i, "j": j, "distance": d} for i, j, d in graph.edges]

    return {"nodes": nodes, "edges": edges}


def from_dict(data: dict[str, Any]) -> StateGraph:
    """Deserialize a StateGraph from a dict (inverse of to_dict).

    Parameters:
        data: Dict with "nodes" and "edges" keys as produced by to_dict().

    Returns:
        Reconstructed StateGraph.
    """
    nodes = []
    for nd in data["nodes"]:
        nodes.append(StateVector(
            vector=np.array(nd["vector"], dtype=np.float64),
            source_id=nd.get("source_id", ""),
            source_kind=nd.get("source_kind", "default"),
            label=nd.get("label", ""),
            metadata=nd.get("metadata", {}),
        ))

    edges = [(e["i"], e["j"], e["distance"]) for e in data["edges"]]

    return StateGraph(nodes=nodes, edges=edges)
