import numpy as np
from numpy.typing import NDArray
from dtaidistance import dtw

from the_similarity.core.normalizer import normalize


def dtw_distance(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    sakoe_chiba_radius: int | None = None,
) -> float:
    """Compute DTW distance between two 1D series.

    Args:
        query: Query window (already normalized).
        candidate: Candidate window (already normalized).
        sakoe_chiba_radius: Sakoe-Chiba band constraint. None = unconstrained.

    Returns:
        DTW distance (lower = more similar).
    """
    kwargs = {}
    if sakoe_chiba_radius is not None:
        kwargs["window"] = sakoe_chiba_radius

    return dtw.distance(query.astype(np.double), candidate.astype(np.double), **kwargs)


def dtw_score(distance: float, window_size: int) -> float:
    """Convert a raw DTW distance to a 0-1 similarity score.

    Uses exponential decay normalized by window size so scores
    are comparable across different window lengths.

    Args:
        distance: Raw DTW distance.
        window_size: Length of the compared windows.

    Returns:
        Score in [0, 1], where 1 = identical.
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
    falling back to sequential computation otherwise.

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

        # block=((0, 1), (1, n_cands+1)) computes only row 0 vs columns 1..N
        kwargs["block"] = ((0, 1), (1, n_cands + 1))

        distances = dtw.distance_matrix_fast(series, **kwargs)
        return [dtw_score(float(d), window_size) for d in distances]
    except Exception:
        # Fallback to sequential
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

    results.sort(key=lambda x: x[2], reverse=True)
    return results
