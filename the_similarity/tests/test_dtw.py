import numpy as np
import pytest

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


def test_batch_dtw_single_candidate():
    """Batch DTW with one identical candidate should return score ≈ 1."""
    query = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
    candidate = [np.array([1.0, 2.0, 3.0, 2.0, 1.0])]
    scores = batch_dtw_scores(query, candidate)
    assert len(scores) == 1
    assert scores[0] == pytest.approx(1.0)


def test_rank_candidates_empty():
    """rank_candidates with empty candidates array should return empty list."""
    query = np.array([1.0, 2.0, 3.0])
    result = rank_candidates(query, np.empty((0, 3)))
    assert result == []


def test_rank_candidates_sorted_descending():
    """rank_candidates result must be sorted by score descending."""
    rng = np.random.default_rng(17)
    query = rng.standard_normal(30)
    candidates = np.array([rng.standard_normal(30) for _ in range(10)])
    ranked = rank_candidates(query, candidates)
    scores = [r[2] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_dtw_score_zero_window():
    """dtw_score with window_size=0 should not raise (uses max(w, 1))."""
    score = dtw_score(1.0, 0)
    assert 0.0 <= score <= 1.0


def test_dtw_score_range():
    """dtw_score should always produce values in (0, 1]."""
    for dist in [0.0, 0.1, 1.0, 10.0, 100.0]:
        s = dtw_score(dist, window_size=50)
        assert 0.0 < s <= 1.0, f"score {s} out of range for dist={dist}"


def test_dtw_float32_input():
    """float32 arrays should be coerced to float64 without error."""
    rng = np.random.default_rng(0)
    a = rng.standard_normal(30).astype(np.float32)
    b = rng.standard_normal(30).astype(np.float32)
    dist = dtw_distance(a, b)
    assert dist >= 0.0


def test_dtw_different_length_series():
    """DTW should handle series of different lengths."""
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    dist = dtw_distance(a, b)
    assert dist >= 0.0
