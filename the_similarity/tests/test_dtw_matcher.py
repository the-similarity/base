"""Tests for the_similarity/methods/dtw_matcher.py.

Covers dtw_distance, dtw_score, batch_dtw_scores, and rank_candidates.
"""

import numpy as np
import pytest

from the_similarity.methods.dtw_matcher import (
    batch_dtw_scores,
    dtw_distance,
    dtw_score,
    rank_candidates,
)


# ---------------------------------------------------------------------------
# dtw_distance
# ---------------------------------------------------------------------------


def test_dtw_distance_identical_returns_zero():
    a = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
    assert dtw_distance(a, a) == 0.0


def test_dtw_distance_positive_for_different():
    a = np.array([0.0, 1.0, 0.0])
    b = np.array([1.0, 0.0, 1.0])
    assert dtw_distance(a, b) > 0.0


def test_dtw_distance_symmetric():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(30)
    b = rng.standard_normal(30)
    assert abs(dtw_distance(a, b) - dtw_distance(b, a)) < 1e-10


def test_dtw_distance_with_sakoe_chiba():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    dist_unconstrained = dtw_distance(a, b, sakoe_chiba_radius=None)
    dist_constrained = dtw_distance(a, b, sakoe_chiba_radius=2)
    # Both should be positive; constrained may be >= unconstrained
    assert dist_unconstrained >= 0.0
    assert dist_constrained >= dist_unconstrained


def test_dtw_distance_sakoe_chiba_none_is_default():
    a = np.array([0.0, 1.0, 2.0, 1.0, 0.0])
    b = np.array([0.1, 1.1, 2.1, 1.1, 0.1])
    d1 = dtw_distance(a, b)
    d2 = dtw_distance(a, b, sakoe_chiba_radius=None)
    assert abs(d1 - d2) < 1e-10


def test_dtw_distance_accepts_float32_input():
    """dtaidistance requires float64; the function should cast silently."""
    a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    b = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    dist = dtw_distance(a, b)
    assert dist == 0.0


def test_dtw_distance_single_element():
    a = np.array([5.0])
    b = np.array([7.0])
    dist = dtw_distance(a, b)
    assert dist == pytest.approx(2.0)


def test_dtw_distance_constant_series():
    a = np.ones(20)
    b = np.ones(20) * 3.0
    dist = dtw_distance(a, b)
    # Each of the 20 pairs contributes |1-3|=2; DTW sums along optimal path
    assert dist > 0.0


# ---------------------------------------------------------------------------
# dtw_score
# ---------------------------------------------------------------------------


def test_dtw_score_zero_distance_gives_one():
    assert dtw_score(0.0, 100) == 1.0


def test_dtw_score_in_unit_interval():
    for dist in [0.0, 0.5, 1.0, 5.0, 100.0]:
        s = dtw_score(dist, 50)
        assert 0.0 <= s <= 1.0, f"score {s} out of [0,1] for dist={dist}"


def test_dtw_score_decreases_with_distance():
    s_small = dtw_score(1.0, 100)
    s_large = dtw_score(10.0, 100)
    assert s_small > s_large


def test_dtw_score_normalized_by_window_size():
    """Same distance over bigger window → lower normalized distance → higher score."""
    s_small_window = dtw_score(10.0, 20)
    s_large_window = dtw_score(10.0, 200)
    assert s_large_window > s_small_window


def test_dtw_score_window_size_one():
    """window_size=1 should not raise (uses max(window_size, 1))."""
    s = dtw_score(0.5, 1)
    assert 0.0 <= s <= 1.0


def test_dtw_score_window_size_zero_safe():
    """window_size=0 should not divide by zero thanks to max guard."""
    s = dtw_score(1.0, 0)
    assert 0.0 <= s <= 1.0


def test_dtw_score_returns_float():
    s = dtw_score(2.0, 50)
    assert isinstance(s, float)


# ---------------------------------------------------------------------------
# batch_dtw_scores
# ---------------------------------------------------------------------------


def test_batch_dtw_empty_candidates():
    q = np.array([1.0, 2.0, 3.0])
    assert batch_dtw_scores(q, []) == []


def test_batch_dtw_single_candidate_identical():
    q = np.array([0.0, 1.0, 0.0])
    scores = batch_dtw_scores(q, [q.copy()])
    assert len(scores) == 1
    assert scores[0] == pytest.approx(1.0)


def test_batch_dtw_all_scores_in_unit_interval():
    rng = np.random.default_rng(7)
    q = rng.standard_normal(40)
    cands = [rng.standard_normal(40) for _ in range(10)]
    for s in batch_dtw_scores(q, cands):
        assert 0.0 <= s <= 1.0


def test_batch_dtw_matches_sequential():
    """Batch scores must agree with per-call dtw_distance up to floating point."""
    rng = np.random.default_rng(42)
    q = rng.standard_normal(60)
    cands = [rng.standard_normal(60) for _ in range(15)]
    radius = 6

    batch = batch_dtw_scores(q, cands, sakoe_chiba_radius=radius)
    seq = [dtw_score(dtw_distance(q, c, sakoe_chiba_radius=radius), len(q)) for c in cands]

    for b, s in zip(batch, seq):
        assert abs(b - s) < 1e-9, f"Mismatch: batch={b}, sequential={s}"


def test_batch_dtw_without_sakoe_chiba():
    rng = np.random.default_rng(99)
    q = rng.standard_normal(20)
    cands = [rng.standard_normal(20) for _ in range(5)]
    scores = batch_dtw_scores(q, cands, sakoe_chiba_radius=None)
    assert len(scores) == 5
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_batch_dtw_accepts_float32():
    q = np.ones(10, dtype=np.float32)
    cands = [np.ones(10, dtype=np.float32)]
    scores = batch_dtw_scores(q, cands)
    assert scores[0] == pytest.approx(1.0)


def test_batch_dtw_length_matches_candidates():
    rng = np.random.default_rng(3)
    q = rng.standard_normal(30)
    n = 7
    cands = [rng.standard_normal(30) for _ in range(n)]
    assert len(batch_dtw_scores(q, cands)) == n


# ---------------------------------------------------------------------------
# rank_candidates
# ---------------------------------------------------------------------------


def test_rank_candidates_identical_top():
    q = np.array([0.0, 1.0, 0.0])
    cands = np.array(
        [
            [0.0, 1.0, 0.0],  # identical → rank 0
            [0.0, 0.5, 0.0],
            [1.0, 0.0, 1.0],  # inverted
        ]
    )
    ranked = rank_candidates(q, cands)
    assert ranked[0][0] == 0
    assert ranked[0][2] == pytest.approx(1.0)


def test_rank_candidates_sorted_descending_by_score():
    q = np.array([0.0, 1.0, 0.0])
    cands = np.array(
        [
            [1.0, 0.0, 1.0],
            [0.0, 0.8, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )
    ranked = rank_candidates(q, cands)
    scores = [r[2] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_candidates_returns_all():
    rng = np.random.default_rng(11)
    q = rng.standard_normal(20)
    cands = rng.standard_normal((8, 20))
    ranked = rank_candidates(q, cands)
    assert len(ranked) == 8


def test_rank_candidates_tuple_structure():
    """Each element should be (index, distance, score)."""
    q = np.array([1.0, 2.0, 3.0])
    cands = np.array([[1.0, 2.0, 3.0]])
    ranked = rank_candidates(q, cands)
    idx, dist, score = ranked[0]
    assert idx == 0
    assert dist == pytest.approx(0.0)
    assert score == pytest.approx(1.0)


def test_rank_candidates_distances_nonnegative():
    rng = np.random.default_rng(55)
    q = rng.standard_normal(25)
    cands = rng.standard_normal((6, 25))
    for _, dist, _ in rank_candidates(q, cands):
        assert dist >= 0.0


def test_rank_candidates_with_sakoe_chiba():
    q = np.array([0.0, 1.0, 2.0, 1.0, 0.0])
    cands = np.array(
        [
            [0.0, 1.0, 2.0, 1.0, 0.0],
            [0.5, 1.5, 2.5, 1.5, 0.5],
        ]
    )
    ranked = rank_candidates(q, cands, sakoe_chiba_radius=2)
    assert len(ranked) == 2
    assert ranked[0][0] == 0  # identical should still rank first


def test_rank_candidates_scores_in_unit_interval():
    rng = np.random.default_rng(77)
    q = rng.standard_normal(30)
    cands = rng.standard_normal((10, 30))
    for _, _, score in rank_candidates(q, cands):
        assert 0.0 <= score <= 1.0


def test_rank_candidates_index_is_original_position():
    """Indices in ranked output must correspond to original row order in candidates."""
    q = np.zeros(5)
    cands = np.array(
        [
            [1.0, 1.0, 1.0, 1.0, 1.0],  # 0: worst
            [0.1, 0.1, 0.1, 0.1, 0.1],  # 1: better
            [0.0, 0.0, 0.0, 0.0, 0.0],  # 2: best (identical)
        ]
    )
    ranked = rank_candidates(q, cands)
    assert ranked[0][0] == 2
    assert ranked[-1][0] == 0
