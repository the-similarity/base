"""Tests for state_graph module — KNN graph, transition graph, cross-domain bridges, serialization."""

from __future__ import annotations

import json

import numpy as np
import pytest

from the_similarity.core.state_graph import (
    StateGraph,
    StateVector,
    build_knn_graph,
    build_transition_graph,
    find_cross_domain_neighbors,
    from_dict,
    to_dict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_vectors(n: int = 10, dim: int = 4, kind: str = "default", seed: int = 42) -> list[StateVector]:
    """Generate *n* random StateVectors of given dimensionality."""
    rng = np.random.default_rng(seed)
    return [
        StateVector(values=rng.standard_normal(dim), kind=kind, meta={"idx": i})
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# KNN graph
# ---------------------------------------------------------------------------


class TestBuildKNNGraph:
    """Verify KNN graph edge count and structure."""

    def test_knn_edge_count_upper_bound(self):
        """Each of n nodes contributes up to k unique edges; total <= n*k (before dedup)."""
        vectors = _make_vectors(10, dim=3)
        k = 3
        graph = build_knn_graph(vectors, k=k)

        # Each node wants k neighbors, but undirected dedup means the actual
        # count is between k (all overlapping) and n*k/2 + n*k/2 = n*k.
        # Just verify it's > 0 and <= n*k.
        assert len(graph.edges) > 0
        assert len(graph.edges) <= len(vectors) * k

    def test_knn_nodes_preserved(self):
        """Graph nodes list should match input vectors."""
        vectors = _make_vectors(5)
        graph = build_knn_graph(vectors, k=2)
        assert len(graph.nodes) == 5

    def test_knn_k_clamped(self):
        """k larger than n-1 should not crash — it gets clamped."""
        vectors = _make_vectors(3, dim=2)
        graph = build_knn_graph(vectors, k=100)
        # With 3 nodes, each can have at most 2 neighbors
        assert len(graph.edges) > 0

    def test_knn_empty_raises(self):
        with pytest.raises(ValueError):
            build_knn_graph([], k=3)

    def test_knn_k_zero_raises(self):
        with pytest.raises(ValueError):
            build_knn_graph(_make_vectors(3), k=0)


# ---------------------------------------------------------------------------
# Adjacency
# ---------------------------------------------------------------------------


class TestAdjacency:
    """Verify adjacency list correctness."""

    def test_adjacency_returns_neighbors(self):
        vectors = _make_vectors(5, dim=2)
        graph = build_knn_graph(vectors, k=2)
        neighbors = graph.adjacency(0)
        assert isinstance(neighbors, list)
        assert all(isinstance(n, tuple) and len(n) == 2 for n in neighbors)

    def test_adjacency_bidirectional(self):
        """If (i, j) is an edge, j should appear in adjacency(i) and i in adjacency(j)."""
        vectors = _make_vectors(6, dim=3)
        graph = build_knn_graph(vectors, k=2)
        for i, j, d in graph.edges:
            j_neighbors = [idx for idx, _ in graph.adjacency(j)]
            i_neighbors = [idx for idx, _ in graph.adjacency(i)]
            assert i in j_neighbors
            assert j in i_neighbors


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------


class TestClusters:
    """Verify clustering returns at least 1 cluster."""

    def test_clusters_returns_at_least_one(self):
        vectors = _make_vectors(10, dim=3)
        graph = build_knn_graph(vectors, k=3)
        clusters = graph.clusters(method="components")
        assert len(clusters) >= 1
        # All nodes must appear exactly once
        all_nodes = sorted(n for c in clusters for n in c)
        assert all_nodes == list(range(10))

    def test_clusters_disconnected_graph(self):
        """Two isolated clusters should produce 2 components."""
        # Cluster A: near origin
        a = [StateVector(values=np.array([0.0, 0.0]) + np.random.default_rng(i).standard_normal(2) * 0.01) for i in range(3)]
        # Cluster B: far away
        b = [StateVector(values=np.array([100.0, 100.0]) + np.random.default_rng(i + 100).standard_normal(2) * 0.01) for i in range(3)]
        vectors = a + b
        # k=2 within each cluster — should form 2 components
        graph = build_knn_graph(vectors, k=2)
        clusters = graph.clusters()
        assert len(clusters) == 2

    def test_clusters_unknown_method(self):
        graph = StateGraph(nodes=_make_vectors(3))
        with pytest.raises(ValueError, match="Unknown clustering method"):
            graph.clusters(method="unknown")


# ---------------------------------------------------------------------------
# Shortest path
# ---------------------------------------------------------------------------


class TestShortestPath:
    """Verify Dijkstra finds valid paths."""

    def test_shortest_path_self(self):
        vectors = _make_vectors(5)
        graph = build_knn_graph(vectors, k=2)
        path = graph.shortest_path(0, 0)
        assert path == [0]

    def test_shortest_path_valid(self):
        """Path should start at source and end at destination."""
        vectors = _make_vectors(8, dim=3)
        graph = build_knn_graph(vectors, k=3)
        path = graph.shortest_path(0, 7)
        assert len(path) >= 2
        assert path[0] == 0
        assert path[-1] == 7

    def test_shortest_path_no_path(self):
        """Disconnected nodes → empty path."""
        # Manually build a graph with 2 disconnected nodes
        v1 = StateVector(values=np.array([0.0, 0.0]))
        v2 = StateVector(values=np.array([1.0, 1.0]))
        graph = StateGraph(nodes=[v1, v2], edges=[])
        path = graph.shortest_path(0, 1)
        assert path == []


# ---------------------------------------------------------------------------
# Transition graph
# ---------------------------------------------------------------------------


class TestTransitionGraph:
    """Verify transition (temporal chain) graph."""

    def test_transition_edges_count(self):
        """n nodes → n-1 sequential edges."""
        vectors = _make_vectors(5, dim=2)
        graph = build_transition_graph(vectors, time_ordered=True)
        assert len(graph.edges) == 4

    def test_transition_edges_sequential(self):
        """Each edge should connect consecutive indices."""
        vectors = _make_vectors(5, dim=2)
        graph = build_transition_graph(vectors, time_ordered=True)
        for idx, (i, j, d) in enumerate(graph.edges):
            assert i == idx
            assert j == idx + 1
            assert d >= 0.0

    def test_transition_not_time_ordered_uses_knn(self):
        """time_ordered=False should fall back to KNN."""
        vectors = _make_vectors(6, dim=2)
        graph = build_transition_graph(vectors, time_ordered=False)
        # KNN with k=2 will have more than n-1 edges for n=6
        assert len(graph.edges) >= 1


# ---------------------------------------------------------------------------
# Cross-domain neighbors
# ---------------------------------------------------------------------------


class TestCrossDomainNeighbors:
    """Verify cross-domain bridge queries filter by kind."""

    def test_filters_by_kind(self):
        """Only source→target pairs should appear."""
        finance = _make_vectors(4, dim=3, kind="finance", seed=1)
        worlds = _make_vectors(4, dim=3, kind="worlds", seed=2)
        all_vectors = finance + worlds
        graph = build_knn_graph(all_vectors, k=3)

        bridges = find_cross_domain_neighbors(graph, "finance", "worlds", k=2)
        assert len(bridges) > 0
        for src_idx, tgt_idx, dist in bridges:
            assert graph.nodes[src_idx].kind == "finance"
            assert graph.nodes[tgt_idx].kind == "worlds"
            assert dist >= 0.0

    def test_cross_domain_empty_when_no_target(self):
        """No nodes of target kind → empty result."""
        vectors = _make_vectors(5, kind="finance")
        graph = build_knn_graph(vectors, k=2)
        bridges = find_cross_domain_neighbors(graph, "finance", "worlds", k=2)
        assert bridges == []

    def test_cross_domain_k_results_per_source(self):
        """Each source node should get exactly k (or fewer) target neighbors."""
        finance = _make_vectors(3, dim=2, kind="finance", seed=10)
        worlds = _make_vectors(5, dim=2, kind="worlds", seed=20)
        graph = build_knn_graph(finance + worlds, k=3)

        k = 2
        bridges = find_cross_domain_neighbors(graph, "finance", "worlds", k=k)
        # Group by source
        from collections import Counter
        source_counts = Counter(src for src, _, _ in bridges)
        for count in source_counts.values():
            assert count <= k


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    """Verify to_dict / from_dict round-trip."""

    def test_round_trip(self):
        vectors = _make_vectors(6, dim=3)
        graph = build_knn_graph(vectors, k=2)

        d = to_dict(graph)
        # Verify JSON-safe (no numpy types)
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

        restored = from_dict(d)
        assert len(restored.nodes) == len(graph.nodes)
        assert len(restored.edges) == len(graph.edges)

        # Values should be close
        for orig, rest in zip(graph.nodes, restored.nodes):
            np.testing.assert_array_almost_equal(orig.values, rest.values)
            assert orig.kind == rest.kind

    def test_meta_preserved(self):
        v = StateVector(values=np.array([1.0, 2.0]), kind="test", meta={"ticker": "SPY"})
        graph = StateGraph(nodes=[v], edges=[])
        d = to_dict(graph)
        restored = from_dict(d)
        assert restored.nodes[0].meta == {"ticker": "SPY"}
