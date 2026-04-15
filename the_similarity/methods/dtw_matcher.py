"""Dynamic Time Warping (DTW) matcher.

Computes the nonlinear minimum-distance alignment between two series.
Serves a dual role in the pipeline:
1. Tier 1 secondary filter: runs on the ~1000 candidates that pass SAX/MASS.
2. Tier 2 baseline score: its scaled distance becomes the 0.07-weighted `dtw`
   score in the final confidence breakdown.

AI AGENT NOTES:
- Uses `dtaidistance` library which is heavily optimized in C.
- Sakoe-Chiba band: `window` constraint that prevents degenerate warpings
  where one point maps to 50 points. This is essential for financial data
  otherwise DTW just matches the global min/max regardless of shape.
- `batch_dtw_scores` attempts to use the C-level batch matrix function
  which releases the GIL and runs multithreaded.
- Expects inputs to be pre-normalized. Normalizing inside DTW is an anti-pattern
  because it breaks distance comparability across candidates.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from dtaidistance import dtw


def dtw_distance(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    sakoe_chiba_radius: int | None = None,
) -> float:
    """Compute DTW distance between two 1D series.

    Args:
        query: Query window (already normalized).
        candidate: Candidate window (already normalized).
        sakoe_chiba_radius: Sakoe-Chiba band constraint. Limits how far off
                            the diagonal the warping path can stray. None =
                            unconstrained (slow and allows degenerate matches).

    Returns:
        DTW distance (lower distance = more similar). Range is [0, inf).
    """
    kwargs = {}
    if sakoe_chiba_radius is not None:
        kwargs["window"] = sakoe_chiba_radius

    # dtaidistance requires double precision (float64) for its C extensions
    return dtw.distance(query.astype(np.double), candidate.astype(np.double), **kwargs)


def dtw_score(distance: float, window_size: int) -> float:
    """Convert a raw DTW distance to a 0-1 similarity score.

    Uses exponential decay normalized by window size so scores
    are comparable across different window lengths (multi-scale search).

    Args:
        distance: Raw DTW distance.
        window_size: Length of the compared windows.

    Returns:
        Score in [0, 1], where 1 = identical (distance=0).
    """
    normalized = distance / max(window_size, 1)
    return float(np.exp(-normalized))


def batch_dtw_scores(
    query: NDArray[np.float64],
    candidates: list[NDArray[np.float64]],
    sakoe_chiba_radius: int | None = None,
) -> list[float]:
    """Compute DTW scores for query vs all candidates in batch.

    Uses dtaidistance's C-parallelized distance_matrix_fast when available,
    falling back to sequential computation if it fails (e.g. missing OpenMP).

    Args:
        query: Normalized query window.
        candidates: List of normalized candidate windows.
        sakoe_chiba_radius: Sakoe-Chiba band constraint.

    Returns:
        List of DTW scores in [0, 1], one per candidate.
    """
    if not candidates:
        return []

    window_size = len(query)
    n_cands = len(candidates)

    # Try batch computation via C extension
    try:
        series = [query.astype(np.double)] + [c.astype(np.double) for c in candidates]
        kwargs = {"compact": True, "only_triu": False}
        if sakoe_chiba_radius is not None:
            kwargs["window"] = sakoe_chiba_radius

        # Calculate only the distance between the query (index 0) and all
        # candidates (indices 1..N) instead of the full N*N matrix.
        # block=((row_start, row_end), (col_start, col_end))
        kwargs["block"] = ((0, 1), (1, n_cands + 1))

        distances = dtw.distance_matrix_fast(series, **kwargs)
        return [dtw_score(float(d), window_size) for d in distances]
    except Exception:
        # Fallback to sequential pure Python/single-threaded C
        return [
            dtw_score(dtw.distance(
                query.astype(np.double),
                c.astype(np.double),
                **({"window": sakoe_chiba_radius} if sakoe_chiba_radius is not None else {}),
            ), window_size)
            for c in candidates
        ]


def rank_candidates(
    query: NDArray[np.float64],
    candidates: NDArray[np.float64],
    sakoe_chiba_radius: int | None = None,
) -> list[tuple[int, float, float]]:
    """Rank candidate windows by DTW similarity to query.

    Used by the Tier 1 pipeline to re-rank the candidates that survived
    the SAX/MASS pre-filters.

    Args:
        query: Normalized query window, shape (window_size,).
        candidates: 2D array of shape (n_candidates, window_size).
        sakoe_chiba_radius: Sakoe-Chiba band constraint.

    Returns:
        List of (candidate_index, distance, score) sorted by score descending.
    """
    results = []
    window_size = len(query)
    for i, cand in enumerate(candidates):
        dist = dtw_distance(query, cand, sakoe_chiba_radius)
        score = dtw_score(dist, window_size)
        results.append((i, dist, score))

    # Sort descending by score (highest score = most similar)
    results.sort(key=lambda x: x[2], reverse=True)
    return results
