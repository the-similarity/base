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
