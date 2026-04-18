#!/usr/bin/env python3
"""Canonical demo for the 3D Data Space — pure Python, no app/API required.

This script demonstrates the core workflow:

    1. Create a temporary registry (SQLite file in /tmp).
    2. Register 10 runs across 3 pillars (5 finance, 3 copies, 2 worlds)
       with varied summary metrics.
    3. Build a state-space index: one numeric vector per run.
    4. Query nearest neighbors for each run — shows cross-domain
       correspondences (e.g. a finance run's nearest neighbor may be a
       worlds simulation with similar dynamics).
    5. Reduce to 3D coordinates via PCA and print them.

Architectural rule: **"3D is a view, not the model."** Everything in this
script operates on the state-space index (the model). The 3D coordinates
are one possible rendering of that index. The same index can be queried
via CLI, API, or rendered as a 2D scatter, a table, or a graph.

Run with:
    python examples/3d_state_space_demo.py

No external services, no API server, no frontend — just Python + numpy.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Ensure the repo root is on sys.path so imports work when running from
# the repo root (``python examples/3d_state_space_demo.py``).
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from the_similarity.platform.artifacts import RunKind, iso_now, new_run_id
from the_similarity.platform.contracts import RunRecord, RunStatus
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# State-space helpers (self-contained — no Agent 1 dependency)
# ---------------------------------------------------------------------------


def extract_state_vector(record: RunRecord) -> np.ndarray:
    """Convert a run's summary metrics into a fixed-length numeric vector.

    Vector layout (length 6):
        [0] score         — overall quality, [0, 1]
        [1] n_matches     — match count / 1000, clamped [0, 1]
        [2] hit_rate      — backtest hit rate, [0, 1]
        [3] n_ticks       — simulation ticks / 10000, clamped [0, 1]
        [4] fidelity      — fidelity score, [0, 1]
        [5] calibration   — calibration score, [0, 1]

    Honest limitation: the normalization ranges are arbitrary, not learned.
    A proper system would learn these from the data distribution.
    """
    s = record.summary
    return np.array([
        float(s.get("score", 0.0)),
        min(float(s.get("n_matches", 0)) / 1000.0, 1.0),
        float(s.get("hit_rate", 0.0)),
        min(float(s.get("n_ticks", 0)) / 10000.0, 1.0),
        float(s.get("fidelity_score", 0.0)),
        float(s.get("calibration", 0.0)),
    ], dtype=np.float64)


def build_state_index(records: List[RunRecord]) -> np.ndarray:
    """Build a state matrix: shape (N, D), one row per run."""
    return np.stack([extract_state_vector(r) for r in records], axis=0)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity, returns 0.0 for zero-norm vectors."""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def query_nearest(
    index: np.ndarray,
    query_idx: int,
    k: int = 3,
) -> List[Tuple[int, float]]:
    """Return (index, similarity) pairs for the k nearest neighbors.

    Brute-force O(N) — not scalable past ~10k runs. Future: HNSW/faiss.
    """
    query = index[query_idx]
    sims = [
        (i, cosine_similarity(query, index[i]))
        for i in range(index.shape[0])
        if i != query_idx
    ]
    sims.sort(key=lambda x: x[1], reverse=True)
    return sims[:k]


def reduce_to_3d(index: np.ndarray) -> np.ndarray:
    """PCA reduction to 3 dimensions using numpy SVD.

    Returns shape (N, 3). Standard PCA — not optimized, but correct.
    """
    centered = index - index.mean(axis=0)
    n, d = centered.shape
    if d <= 3:
        pad = 3 - d
        return np.hstack([centered, np.zeros((n, pad))])
    U, S, Vt = np.linalg.svd(centered, full_matrices=False)
    return U[:, :3] * S[:3]


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def make_run(
    kind: RunKind,
    pillar: str,
    summary: Dict[str, Any],
    seed: int,
) -> RunRecord:
    """Build a RunRecord with realistic fields."""
    return RunRecord(
        run_id=new_run_id(),
        kind=kind,
        config={"window": 60, "seed": seed, "pillar": pillar},
        seed=seed,
        status=RunStatus.SUCCEEDED,
        summary=summary,
        created_at=iso_now(),
        pillar=pillar,
    )


def create_demo_runs() -> List[RunRecord]:
    """Create 10 demo runs across 3 pillars with varied metrics.

    The metrics are chosen so that cross-domain neighbors emerge:
    - Finance run #3 (high score, high hit_rate) should be near
      Worlds run #1 (high score, high n_ticks).
    - Copies run #2 (high fidelity) should be near Copies run #3.
    """
    runs: List[RunRecord] = []

    # 5 finance runs — varied scores and hit rates.
    finance_specs = [
        {"score": 0.92, "n_matches": 200, "hit_rate": 0.71, "calibration": 0.85},
        {"score": 0.65, "n_matches": 50, "hit_rate": 0.48, "calibration": 0.60},
        {"score": 0.88, "n_matches": 180, "hit_rate": 0.68, "calibration": 0.80},
        {"score": 0.45, "n_matches": 30, "hit_rate": 0.35, "calibration": 0.40},
        {"score": 0.78, "n_matches": 120, "hit_rate": 0.58, "calibration": 0.72},
    ]
    for i, s in enumerate(finance_specs):
        runs.append(make_run(RunKind.FINANCE, "finance", s, seed=42 + i))

    # 3 copies runs — fidelity-focused.
    copies_specs = [
        {"score": 0.70, "fidelity_score": 0.85, "calibration": 0.65},
        {"score": 0.82, "fidelity_score": 0.93, "calibration": 0.78},
        {"score": 0.80, "fidelity_score": 0.90, "calibration": 0.75},
    ]
    for i, s in enumerate(copies_specs):
        runs.append(make_run(RunKind.COPIES, "synthetic", s, seed=100 + i))

    # 2 worlds runs — tick-count and score focused.
    worlds_specs = [
        {"score": 0.90, "n_ticks": 8000, "hit_rate": 0.0, "calibration": 0.82},
        {"score": 0.55, "n_ticks": 2000, "hit_rate": 0.0, "calibration": 0.45},
    ]
    for i, s in enumerate(worlds_specs):
        runs.append(make_run(RunKind.WORLDS, "worlds", s, seed=200 + i))

    return runs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full 3D Data Space demo end-to-end."""
    print("=" * 70)
    print("3D Data Space Demo — Cross-Pillar State-Space Index")
    print("=" * 70)
    print()
    print('Architectural rule: "3D is a view, not the model."')
    print("The state-space index is the model. 3D coordinates are one view.")
    print()

    # -- Step 1: Create a temp registry and register runs --
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "demo_registry.db"
        registry = RunRegistry(db_path)

        runs = create_demo_runs()
        for run in runs:
            registry.register_run(run)

        print(f"Registered {len(runs)} runs in temp registry: {db_path}")
        print(f"  - Finance: {sum(1 for r in runs if r.pillar == 'finance')}")
        print(f"  - Synthetic (copies): {sum(1 for r in runs if r.pillar == 'synthetic')}")
        print(f"  - Worlds: {sum(1 for r in runs if r.pillar == 'worlds')}")
        print()

        # -- Step 2: Build state-space index --
        # Read back from registry to prove the round-trip works.
        db_runs = registry.list_runs(limit=100)
        index = build_state_index(db_runs)
        print(f"State-space index shape: {index.shape}  (runs x features)")
        print()

        # -- Step 3: Query nearest neighbors --
        print("Cross-Domain Nearest Neighbors (k=3):")
        print("-" * 60)
        for i, run in enumerate(db_runs):
            neighbors = query_nearest(index, i, k=3)
            label = f"{run.pillar}/{run.kind.value}"
            neighbor_labels = [
                f"{db_runs[j].pillar}/{db_runs[j].kind.value} (sim={sim:.3f})"
                for j, sim in neighbors
            ]
            print(f"  [{i}] {label:20s} -> {', '.join(neighbor_labels)}")
        print()

        # -- Step 4: Reduce to 3D --
        coords_3d = reduce_to_3d(index)
        print(f"3D coordinates (PCA reduction), shape: {coords_3d.shape}")
        print("-" * 60)
        for i, run in enumerate(db_runs):
            x, y, z = coords_3d[i]
            label = f"{run.pillar}/{run.kind.value}"
            print(f"  [{i}] {label:20s} -> ({x:+.4f}, {y:+.4f}, {z:+.4f})")
        print()

        # -- Summary --
        print("Key observations:")
        print("  - Runs from different pillars can be nearest neighbors")
        print("    when they share similar metric profiles.")
        print("  - The 3D coordinates are ONE view of the state space.")
        print("  - The same index supports CLI queries, API lookups,")
        print("    2D plots, or 3D scatter rendering.")
        print()
        print("Honest limitations:")
        print("  - Brute-force cosine sim: O(N^2), not scalable past ~10k runs.")
        print("  - PCA/t-SNE are standard but not optimized for this use case.")
        print("  - Feature extractors use arbitrary normalization ranges.")
        print()
        print("What's next:")
        print("  - Approximate nearest neighbors (HNSW / faiss)")
        print("  - Learned embeddings from run trajectories")
        print("  - Temporal state evolution (how runs move through state space)")
        print("  - Live state tracking for running simulations")

        registry.close()

    print()
    print("Done. Registry cleaned up (temp directory removed).")


if __name__ == "__main__":
    main()
