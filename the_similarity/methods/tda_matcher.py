"""Topological Data Analysis (TDA) pattern matcher.

Computes persistent homology on delay-embedded time series and compares
persistence diagrams via Wasserstein distance.

Topological State Space Definitions:
- Point Cloud Lifting: Employs Takens Delay Embedding to lift 1D temporal series
  into structured multi-dimensional phase-space point clouds.
- Persistent Homology: Analyzes topological evolution (H0 connected components,
  H1 loops). Features robustly spaced from the Birth=Death diagonal represent
  structural manifold properties, while proximate features are ephemeral stochastic noise.
- Metric Algebra: Compares multi-set Persistence Diagrams directly via Wasserstein
  Metric mapping, computing the optimal transport cost required to structurally
  align two dynamic attractors.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from the_similarity.core.embedding import delay_embed

# Optional heavy dependencies --------------------------------------------------
try:
    from ripser import ripser
    from persim import wasserstein

    HAS_TDA = True
except ImportError:
    HAS_TDA = False

# Minimum series length for meaningful TDA
TDA_MIN_WINDOW = 40


def _require_tda() -> None:
    if not HAS_TDA:
        raise RuntimeError(
            "TDA dependencies not installed. Run:\n  pip install ripser persim"
        )


def compute_persistence(
    series: NDArray[np.float64],
    dim: int = 4,
    lag: int = 3,
) -> dict[str, NDArray[np.float64]]:
    """Compute persistence diagrams (H0, H1) for a 1-D time series.

    Args:
        series: 1-D time series array.
        dim: Embedding dimension for Takens delay embedding.
        lag: Time delay for embedding.

    Returns:
        Dict with keys ``"H0"`` and ``"H1"``, each an (n, 2) array of
        birth-death pairs.
    """
    _require_tda()
    series = np.asarray(series, dtype=np.float64).ravel()

    if len(series) < TDA_MIN_WINDOW:
        return {
            "H0": np.empty((0, 2), dtype=np.float64),
            "H1": np.empty((0, 2), dtype=np.float64),
        }

    # Constant series → trivial topology
    if np.ptp(series) < 1e-12:
        return {
            "H0": np.empty((0, 2), dtype=np.float64),
            "H1": np.empty((0, 2), dtype=np.float64),
        }

    embedded = delay_embed(series, dim, lag)
    result = ripser(embedded, maxdim=1)

    dgm_h0 = result["dgms"][0]
    dgm_h1 = result["dgms"][1]

    # Remove infinite-death features from H0 (the single connected component)
    finite_mask = np.isfinite(dgm_h0[:, 1])
    dgm_h0 = dgm_h0[finite_mask]

    return {"H0": dgm_h0, "H1": dgm_h1}


def persistence_distance(
    diag_a: dict[str, NDArray[np.float64]],
    diag_b: dict[str, NDArray[np.float64]],
) -> float:
    """Wasserstein distance between two persistence diagram dicts.

    H1 (loops) is weighted higher than H0 (connected components) because
    loop structure carries more information about the dynamics.

    Args:
        diag_a: Output of :func:`compute_persistence`.
        diag_b: Output of :func:`compute_persistence`.

    Returns:
        Combined distance (>= 0).
    """
    _require_tda()

    h0_a, h0_b = diag_a["H0"], diag_b["H0"]
    h1_a, h1_b = diag_a["H1"], diag_b["H1"]

    # Empty diagrams → distance 0
    if h0_a.size == 0 and h0_b.size == 0:
        d_h0 = 0.0
    else:
        d_h0 = wasserstein(h0_a, h0_b)

    if h1_a.size == 0 and h1_b.size == 0:
        d_h1 = 0.0
    else:
        d_h1 = wasserstein(h1_a, h1_b)

    return 0.4 * d_h0 + 0.6 * d_h1


def tda_score(distance: float) -> float:
    """Map a persistence distance to a [0, 1] similarity score.

    Uses exponential decay: ``exp(-distance * 2)``.

    Args:
        distance: Non-negative persistence distance.

    Returns:
        Similarity in [0, 1], where 1 = identical topology.
    """
    return float(np.exp(-distance * 2))


def compare(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    dim: int = 4,
    lag: int = 3,
) -> float:
    """End-to-end TDA similarity score between two series.

    Convenience wrapper that embeds, computes persistence, measures
    distance, and returns a [0, 1] score.

    Args:
        query: 1-D query series.
        candidate: 1-D candidate series.
        dim: Embedding dimension.
        lag: Time delay.

    Returns:
        Similarity score in [0, 1].
    """
    query = np.asarray(query, dtype=np.float64).ravel()
    candidate = np.asarray(candidate, dtype=np.float64).ravel()

    if len(query) < TDA_MIN_WINDOW or len(candidate) < TDA_MIN_WINDOW:
        return 0.0

    diag_q = compute_persistence(query, dim, lag)
    diag_c = compute_persistence(candidate, dim, lag)

    # Both constant → identical (trivial) topology
    if (
        diag_q["H0"].size == 0
        and diag_q["H1"].size == 0
        and diag_c["H0"].size == 0
        and diag_c["H1"].size == 0
    ):
        return 0.0

    dist = persistence_distance(diag_q, diag_c)
    return tda_score(dist)
