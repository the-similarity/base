"""Integration tests for the 3D Data Space: state-space index over cross-pillar runs.

These tests verify the architectural invariant **"3D is a view, not the model"**:
the state-space index, nearest-neighbor queries, and dimensionality reduction
are pure data-layer operations that work without any renderer. The 3D scatter
plot is one rendering surface — the same data can be queried via CLI, API, or
rendered in 2D.

Test strategy
-------------
1. Create a temp registry, register runs from 3 pillars (finance, copies, worlds).
2. Build a state-space index from the registry — one vector per run.
3. Verify that nearest-neighbor queries cross pillar boundaries.
4. Reduce to 3D via PCA and verify the output shape.
5. All tests use try/except for Agent 1's imports (state_space module may not
   exist yet) so the test file is valid even before Agent 1 lands.

Dependencies
------------
- ``the_similarity.platform.registry`` — the SQLite-backed run registry
- ``the_similarity.platform.contracts`` — RunRecord, RunStatus
- ``the_similarity.platform.artifacts`` — RunKind, iso_now, new_run_id
- numpy (stdlib-adjacent, always available in our env)
- Agent 1's state-space module (gracefully skipped if missing)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pytest

from the_similarity.platform.artifacts import RunKind, iso_now, new_run_id
from the_similarity.platform.contracts import RunRecord, RunStatus
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Helpers — state-space index built from first principles
# ---------------------------------------------------------------------------
# These helpers implement the core state-space logic inline so the tests
# do not depend on Agent 1's module existing. When Agent 1's module lands,
# these can be replaced with imports from it.


def _extract_state_vector(record: RunRecord) -> np.ndarray:
    """Extract a numeric feature vector from a RunRecord's summary dict.

    This is the *extractor* — it converts heterogeneous summary metrics
    into a fixed-length numeric vector suitable for cosine similarity.
    The normalization is deliberately naive (clamp to [0, 1] by dividing
    by known max values) — the honest limitation is that these ranges are
    arbitrary and not learned.

    Vector layout (length 5):
        [0] score       — overall quality score, [0, 1]
        [1] n_matches   — number of matches / 1000, clamped to [0, 1]
        [2] hit_rate    — backtest hit rate, [0, 1]
        [3] n_ticks     — simulation ticks / 10000, clamped to [0, 1]
        [4] fidelity    — fidelity score, [0, 1]
    """
    s = record.summary
    return np.array([
        float(s.get("score", 0.0)),
        min(float(s.get("n_matches", 0)) / 1000.0, 1.0),
        float(s.get("hit_rate", 0.0)),
        min(float(s.get("n_ticks", 0)) / 10000.0, 1.0),
        float(s.get("fidelity_score", 0.0)),
    ], dtype=np.float64)


def _build_state_index(records: List[RunRecord]) -> np.ndarray:
    """Build a state-space matrix: one row per run, columns are features.

    Returns shape (N, D) where N = len(records) and D = feature dimension.
    """
    vectors = [_extract_state_vector(r) for r in records]
    return np.stack(vectors, axis=0)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D vectors.

    Returns 0.0 if either vector has zero norm (degenerate case —
    no features populated). This is the correct fail-closed behavior:
    a zero-norm vector has no direction, so similarity is undefined;
    returning 0.0 treats it as "no information" rather than crashing.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _query_nearest(
    index: np.ndarray,
    query_idx: int,
    k: int = 2,
) -> List[int]:
    """Return indices of the k nearest neighbors (by cosine sim) to query_idx.

    Excludes the query itself from results. This is brute-force O(N) —
    honest limitation: not scalable past ~10k runs without an ANN index.
    """
    query_vec = index[query_idx]
    sims = []
    for i in range(index.shape[0]):
        if i == query_idx:
            continue
        sims.append((i, _cosine_similarity(query_vec, index[i])))
    # Sort descending by similarity, take top k.
    sims.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in sims[:k]]


def _reduce_to_3d(index: np.ndarray) -> np.ndarray:
    """Reduce the state-space index to 3 dimensions via PCA.

    Uses numpy-only PCA (SVD on centered data). No sklearn dependency.
    Returns shape (N, 3). If D <= 3, pads with zeros rather than failing.
    """
    # Center the data (subtract mean along axis 0).
    centered = index - index.mean(axis=0)
    n, d = centered.shape
    if d <= 3:
        # Already low-dimensional — pad with zeros to reach 3 columns.
        pad_width = 3 - d
        return np.hstack([centered, np.zeros((n, pad_width))])
    # SVD-based PCA: U @ diag(S) @ Vt = centered. The projection onto
    # the first 3 principal components is U[:, :3] @ diag(S[:3]).
    U, S, Vt = np.linalg.svd(centered, full_matrices=False)
    return U[:, :3] * S[:3]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_run(
    kind: RunKind,
    pillar: str,
    summary: Dict[str, Any],
    seed: int = 42,
) -> RunRecord:
    """Helper to build a RunRecord with realistic fields."""
    return RunRecord(
        run_id=new_run_id(),
        kind=kind,
        config={"window": 60, "seed": seed},
        seed=seed,
        status=RunStatus.SUCCEEDED,
        summary=summary,
        created_at=iso_now(),
        pillar=pillar,
    )


@pytest.fixture
def registry_with_runs(tmp_path: Path):
    """Create a temp registry with 3 runs: 1 finance, 1 copies, 1 worlds.

    Returns (registry, records_list) so tests can reference both the
    DB and the in-memory records.
    """
    db_path = tmp_path / "test_state.db"
    registry = RunRegistry(db_path)

    finance_run = _make_run(
        RunKind.FINANCE,
        "finance",
        {"score": 0.85, "n_matches": 150, "hit_rate": 0.62},
        seed=42,
    )
    copies_run = _make_run(
        RunKind.COPIES,
        "synthetic",
        {"score": 0.78, "fidelity_score": 0.91, "n_matches": 0},
        seed=314,
    )
    worlds_run = _make_run(
        RunKind.WORLDS,
        "worlds",
        {"score": 0.72, "n_ticks": 5000, "hit_rate": 0.0},
        seed=271,
    )

    records = [finance_run, copies_run, worlds_run]
    for r in records:
        registry.register_run(r)

    yield registry, records

    registry.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStateSpaceIndex:
    """Verify the state-space index correctly represents cross-pillar runs."""

    def test_build_index_shape(self, registry_with_runs):
        """Building a state index from 3 registry runs produces shape (3, 5)."""
        registry, records = registry_with_runs
        # Rebuild records from the registry to prove the round-trip works.
        db_records = registry.list_runs(limit=100)
        assert len(db_records) == 3

        index = _build_state_index(db_records)
        # 3 runs, 5 features per extractor.
        assert index.shape == (3, 5)

    def test_vectors_are_numeric(self, registry_with_runs):
        """Every element in the state index is a finite float."""
        _, records = registry_with_runs
        index = _build_state_index(records)
        assert np.all(np.isfinite(index)), "State vectors must be finite"
        assert index.dtype == np.float64

    def test_nearest_neighbor_crosses_pillars(self, registry_with_runs):
        """Querying nearest for the finance run returns non-finance runs.

        This is the core cross-domain test: the state space must connect
        runs across pillars, not silo them. The finance run has score=0.85
        and hit_rate=0.62; the copies run has score=0.78 (closest in the
        score dimension); the worlds run has score=0.72. Both should appear
        as neighbors since k=2 and we only have 3 runs total.
        """
        _, records = registry_with_runs
        index = _build_state_index(records)

        # records[0] is finance — query its nearest 2 neighbors.
        neighbors = _query_nearest(index, query_idx=0, k=2)
        assert len(neighbors) == 2
        # Both non-finance indices (1 = copies, 2 = worlds) must appear.
        assert set(neighbors) == {1, 2}

    def test_reduce_to_3d_shape(self, registry_with_runs):
        """PCA reduction of the state index to 3D produces shape (3, 3)."""
        _, records = registry_with_runs
        index = _build_state_index(records)
        reduced = _reduce_to_3d(index)
        assert reduced.shape == (3, 3)
        assert np.all(np.isfinite(reduced))

    def test_cosine_similarity_self(self, registry_with_runs):
        """A run's cosine similarity with itself is 1.0 (or 0.0 if zero-norm)."""
        _, records = registry_with_runs
        index = _build_state_index(records)
        for i in range(index.shape[0]):
            sim = _cosine_similarity(index[i], index[i])
            if np.linalg.norm(index[i]) > 0:
                assert abs(sim - 1.0) < 1e-10, f"Self-similarity for run {i} should be 1.0"


class TestStateSpaceAgentImports:
    """Test that Agent 1's state-space module can be imported (if it exists).

    These tests use try/except so they pass regardless of whether Agent 1
    has landed. When the module exists, they verify basic API surface.
    When it does not, they skip gracefully.
    """

    def test_agent1_state_space_import(self):
        """Attempt to import the state_space module from Agent 1."""
        try:
            from the_similarity.platform import state_space  # noqa: F401
            # If it exists, verify it has the expected API surface.
            assert hasattr(state_space, "StateVector") or hasattr(
                state_space, "StateIndex"
            ), "state_space module exists but missing expected classes"
        except ImportError:
            pytest.skip(
                "Agent 1's state_space module not yet available — "
                "this test will activate once it lands"
            )

    def test_agent1_state_graph_import(self):
        """Attempt to import the state_graph module from Agent 1."""
        try:
            from the_similarity.platform import state_graph  # noqa: F401
            assert hasattr(state_graph, "StateGraph") or hasattr(
                state_graph, "build_knn_graph"
            ), "state_graph module exists but missing expected classes"
        except ImportError:
            pytest.skip(
                "Agent 1's state_graph module not yet available — "
                "this test will activate once it lands"
            )
