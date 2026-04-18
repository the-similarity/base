"""Tests for the shared state-space embedding and indexing module.

Covers:
- Finance / copies / worlds extractors produce correct-length vectors
- Normalization ranges clamp and map correctly
- Missing fields default to 0.5 (neutral)
- StateIndex nearest query returns correct ordering
- StateIndex radius query filters correctly
- build_index_from_registry works with a populated temp registry
- reduce_to_3d and reduce_to_2d produce correct output shapes
"""

from __future__ import annotations


import numpy as np
import pytest

from the_similarity.core.state_space import (
    MAX_DIM,
    StateIndex,
    StateVector,
    build_index_from_registry,
    extract_copies_state,
    extract_finance_state,
    extract_worlds_state,
    reduce_to_2d,
    reduce_to_3d,
)


# ---------------------------------------------------------------------------
# Extractor tests
# ---------------------------------------------------------------------------


class TestExtractFinanceState:
    """Finance extractor: 5 metrics -> MAX_DIM vector in [0, 1]."""

    def test_full_summary(self):
        summary = {
            "run_id": "fin-001",
            "hit_rate": 0.8,
            "crps": 0.2,
            "coverage": 0.9,
            "trust_score": 0.7,
            "calibration_grade_numeric": 3.0,
        }
        sv = extract_finance_state(summary)
        assert sv.vector.shape == (MAX_DIM,)
        assert sv.source_kind == "finance"
        assert sv.source_id == "fin-001"
        # hit_rate=0.8 in [0,1] -> 0.8
        np.testing.assert_almost_equal(sv.vector[0], 0.8)
        # calibration_grade_numeric=3.0 in [0,4] -> 0.75
        np.testing.assert_almost_equal(sv.vector[4], 0.75)

    def test_missing_fields_default_neutral(self):
        summary = {"run_id": "fin-002"}
        sv = extract_finance_state(summary)
        # All dimensions should be 0.5 (neutral)
        np.testing.assert_array_almost_equal(sv.vector, 0.5)

    def test_values_clamped(self):
        summary = {
            "run_id": "fin-003",
            "hit_rate": 1.5,  # above max
            "crps": -0.3,  # below min
        }
        sv = extract_finance_state(summary)
        np.testing.assert_almost_equal(sv.vector[0], 1.0)  # clamped to max
        np.testing.assert_almost_equal(sv.vector[1], 0.0)  # clamped to min


class TestExtractCopiesState:
    """Copies extractor: 3 metrics -> MAX_DIM vector (padded)."""

    def test_full_summary(self):
        summary = {
            "run_id": "cop-001",
            "fidelity_score": 0.9,
            "privacy_score": 0.8,
            "utility_gap": 0.1,
        }
        sv = extract_copies_state(summary)
        assert sv.vector.shape == (MAX_DIM,)
        assert sv.source_kind == "copies"
        np.testing.assert_almost_equal(sv.vector[0], 0.9)
        np.testing.assert_almost_equal(sv.vector[1], 0.8)
        np.testing.assert_almost_equal(sv.vector[2], 0.1)
        # Padded dimensions should be 0.5 (neutral)
        np.testing.assert_almost_equal(sv.vector[3], 0.5)
        np.testing.assert_almost_equal(sv.vector[4], 0.5)


class TestExtractWorldsState:
    """Worlds extractor: 5 metrics -> MAX_DIM vector."""

    def test_full_summary(self):
        summary = {
            "run_id": "wld-001",
            "alive": 5000,
            "dead": 1000,
            "mean_energy": 100.0,
            "food_count": 2500,
            "population_density": 0.5,
        }
        sv = extract_worlds_state(summary)
        assert sv.vector.shape == (MAX_DIM,)
        assert sv.source_kind == "worlds"
        # alive=5000 in [0, 10000] -> 0.5
        np.testing.assert_almost_equal(sv.vector[0], 0.5)
        # dead=1000 in [0, 10000] -> 0.1
        np.testing.assert_almost_equal(sv.vector[1], 0.1)
        # mean_energy=100 in [0, 200] -> 0.5
        np.testing.assert_almost_equal(sv.vector[2], 0.5)
        # food_count=2500 in [0, 5000] -> 0.5
        np.testing.assert_almost_equal(sv.vector[3], 0.5)
        # population_density=0.5 in [0, 1] -> 0.5
        np.testing.assert_almost_equal(sv.vector[4], 0.5)


# ---------------------------------------------------------------------------
# StateIndex tests
# ---------------------------------------------------------------------------


class TestStateIndex:
    """Brute-force nearest-neighbor index over StateVectors."""

    def _make_sv(self, vec: list, sid: str = "test") -> StateVector:
        """Helper to build a StateVector from a raw list."""
        arr = np.zeros(MAX_DIM, dtype=np.float64)
        for i, v in enumerate(vec):
            arr[i] = v
        return StateVector(
            vector=arr, source_id=sid, source_kind="test", label=sid
        )

    def test_add_and_size(self):
        idx = StateIndex()
        assert idx.size() == 0
        idx.add(self._make_sv([1, 0, 0], "a"))
        assert idx.size() == 1
        idx.add_batch([self._make_sv([0, 1, 0], "b"), self._make_sv([0, 0, 1], "c")])
        assert idx.size() == 3

    def test_query_nearest_ordering(self):
        idx = StateIndex()
        # Three vectors: one close to query, one far, one medium
        close = self._make_sv([0.9, 0.1, 0.0], "close")
        medium = self._make_sv([0.5, 0.5, 0.0], "medium")
        far = self._make_sv([0.0, 0.0, 1.0], "far")
        idx.add_batch([far, medium, close])

        query = np.zeros(MAX_DIM, dtype=np.float64)
        query[0] = 1.0  # query is along first axis

        results = idx.query_nearest(query, k=3)
        assert len(results) == 3
        # Closest should be "close" (most aligned with [1,0,0,...])
        assert results[0][0].source_id == "close"
        # Distances should be monotonically non-decreasing
        for i in range(len(results) - 1):
            assert results[i][1] <= results[i + 1][1]

    def test_query_nearest_k_clamped(self):
        idx = StateIndex()
        idx.add(self._make_sv([1, 0, 0], "only"))
        results = idx.query_nearest(np.ones(MAX_DIM), k=10)
        assert len(results) == 1  # only 1 vector in index

    def test_query_radius(self):
        idx = StateIndex()
        idx.add(self._make_sv([1, 0, 0, 0, 0], "a"))
        idx.add(self._make_sv([0, 1, 0, 0, 0], "b"))

        # Query identical to "a" — should find "a" at distance ~0
        query = np.array([1, 0, 0, 0, 0], dtype=np.float64)
        results = idx.query_radius(query, radius=0.01)
        assert len(results) == 1
        assert results[0][0].source_id == "a"

    def test_empty_index_queries(self):
        idx = StateIndex()
        assert idx.query_nearest(np.ones(MAX_DIM), k=5) == []
        assert idx.query_radius(np.ones(MAX_DIM), radius=1.0) == []

    def test_all_vectors(self):
        idx = StateIndex()
        sv1 = self._make_sv([1, 0, 0], "a")
        sv2 = self._make_sv([0, 1, 0], "b")
        idx.add_batch([sv1, sv2])
        vecs = idx.all_vectors()
        assert len(vecs) == 2
        assert vecs[0].source_id == "a"
        assert vecs[1].source_id == "b"


# ---------------------------------------------------------------------------
# build_index_from_registry test
# ---------------------------------------------------------------------------


class TestBuildIndexFromRegistry:
    """Integration test: registry -> StateIndex."""

    def test_builds_from_populated_registry(self, tmp_path):
        """Register runs across pillars and verify the index contains them."""
        from the_similarity.platform.artifacts import RunKind
        from the_similarity.platform.contracts import RunRecord, RunStatus
        from the_similarity.platform.registry import RunRegistry

        db_path = tmp_path / "test_registry.db"
        with RunRegistry(db_path) as reg:
            # Finance run
            reg.register_run(
                RunRecord(
                    run_id="fin-100",
                    kind=RunKind.FINANCE,
                    config={},
                    seed=42,
                    status=RunStatus.SUCCEEDED,
                    summary={"hit_rate": 0.85, "crps": 0.15},
                    created_at="2026-01-01T00:00:00",
                    pillar="finance",
                )
            )
            # Copies run (pillar="synthetic")
            reg.register_run(
                RunRecord(
                    run_id="cop-100",
                    kind=RunKind.COPIES,
                    config={},
                    seed=42,
                    status=RunStatus.SUCCEEDED,
                    summary={"fidelity_score": 0.9, "privacy_score": 0.8},
                    created_at="2026-01-02T00:00:00",
                    pillar="synthetic",
                )
            )
            # Worlds run
            reg.register_run(
                RunRecord(
                    run_id="wld-100",
                    kind=RunKind.WORLDS,
                    config={},
                    seed=42,
                    status=RunStatus.SUCCEEDED,
                    summary={"alive": 200, "dead": 50, "mean_energy": 80.0},
                    created_at="2026-01-03T00:00:00",
                    pillar="worlds",
                )
            )

            index = build_index_from_registry(reg)

        assert index.size() == 3
        kinds = {sv.source_kind for sv in index.all_vectors()}
        assert kinds == {"finance", "copies", "worlds"}


# ---------------------------------------------------------------------------
# Dimensionality reduction tests
# ---------------------------------------------------------------------------


class TestDimensionalityReduction:
    """reduce_to_3d and reduce_to_2d output shape validation."""

    def _build_index(self, n: int = 10) -> StateIndex:
        """Build a test index with *n* random vectors."""
        rng = np.random.default_rng(42)
        idx = StateIndex()
        for i in range(n):
            sv = StateVector(
                vector=rng.random(MAX_DIM),
                source_id=f"test-{i}",
                source_kind="test",
                label=f"test-{i}",
            )
            idx.add(sv)
        return idx

    def test_reduce_to_3d_pca(self):
        idx = self._build_index(10)
        result = reduce_to_3d(idx, method="pca")
        assert result.shape == (10, 3)

    def test_reduce_to_2d_pca(self):
        idx = self._build_index(10)
        result = reduce_to_2d(idx, method="pca")
        assert result.shape == (10, 2)

    def test_reduce_to_3d_tsne(self):
        idx = self._build_index(10)
        result = reduce_to_3d(idx, method="tsne")
        assert result.shape == (10, 3)

    def test_reduce_empty_index_raises(self):
        idx = StateIndex()
        with pytest.raises(ValueError, match="empty"):
            reduce_to_3d(idx)

    def test_reduce_unknown_method_raises(self):
        idx = self._build_index(5)
        with pytest.raises(ValueError, match="Unknown"):
            reduce_to_3d(idx, method="umap")

    def test_reduce_small_index(self):
        """With fewer samples than components, output is padded."""
        idx = self._build_index(2)
        result = reduce_to_3d(idx, method="pca")
        assert result.shape == (2, 3)
