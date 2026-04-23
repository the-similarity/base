import numpy as np

from the_similarity.methods.dtw_matcher import (
    batch_dtw_scores,
    dtw_distance,
    dtw_score,
    rank_candidates,
)


def test_identical_series():
    a = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
    dist = dtw_distance(a, a)
    assert dist == 0.0


def test_score_identical():
    score = dtw_score(0.0, 100)
    assert score == 1.0


def test_score_decreases_with_distance():
    s1 = dtw_score(1.0, 100)
    s2 = dtw_score(10.0, 100)
    assert s1 > s2


def test_rank_candidates():
    query = np.array([0.0, 1.0, 0.0])
    candidates = np.array(
        [
            [0.0, 1.0, 0.0],  # identical
            [0.0, 0.5, 0.0],  # similar
            [1.0, 0.0, 1.0],  # inverted
        ]
    )
    ranked = rank_candidates(query, candidates)
    # First result should be the identical one
    assert ranked[0][0] == 0
    assert ranked[0][2] == 1.0  # perfect score


def test_sakoe_chiba():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    dist = dtw_distance(a, b, sakoe_chiba_radius=1)
    assert dist > 0


def test_batch_dtw_matches_sequential():
    """Batch DTW should produce identical scores to sequential."""
    np.random.seed(42)
    query = np.random.randn(60)
    candidates = [np.random.randn(60) for _ in range(20)]

    # Batch
    batch_scores = batch_dtw_scores(query, candidates, sakoe_chiba_radius=6)

    # Sequential
    seq_scores = []
    for c in candidates:
        d = dtw_distance(query, c, sakoe_chiba_radius=6)
        seq_scores.append(dtw_score(d, 60))

    for b, s in zip(batch_scores, seq_scores):
        assert abs(b - s) < 1e-10, f"Mismatch: batch={b}, sequential={s}"


def test_batch_dtw_empty():
    """Batch DTW with no candidates should return empty list."""
    assert batch_dtw_scores(np.array([1.0, 2.0]), [], sakoe_chiba_radius=1) == []


def test_dtw_score_zero_window():
    """dtw_score with window_size=0 should not raise (uses max(w, 1))."""
    score = dtw_score(1.0, 0)
    assert 0.0 <= score <= 1.0


def test_dtw_integer_input():
    """Integer arrays should be accepted without error."""
    a = np.array([1, 2, 3, 2, 1], dtype=np.int32)
    b = np.array([1, 2, 3, 2, 1], dtype=np.int32)
    dist = dtw_distance(a.astype(np.float64), b.astype(np.float64))
    assert dist == 0.0


def test_dtw_float32_input():
    """float32 arrays should be coerced to float64 without error."""
    rng = np.random.default_rng(0)
    a = rng.standard_normal(30).astype(np.float32)
    b = rng.standard_normal(30).astype(np.float32)
    dist = dtw_distance(a, b)
    assert dist >= 0.0


def test_rank_candidates_empty():
    """rank_candidates with empty candidates array should return empty list."""
    query = np.array([1.0, 2.0, 3.0])
    result = rank_candidates(query, np.empty((0, 3)))
    assert result == []
