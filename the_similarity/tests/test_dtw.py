import numpy as np

from the_similarity.methods.dtw_matcher import dtw_distance, dtw_score, rank_candidates


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
    candidates = np.array([
        [0.0, 1.0, 0.0],   # identical
        [0.0, 0.5, 0.0],   # similar
        [1.0, 0.0, 1.0],   # inverted
    ])
    ranked = rank_candidates(query, candidates)
    # First result should be the identical one
    assert ranked[0][0] == 0
    assert ranked[0][2] == 1.0  # perfect score


def test_sakoe_chiba():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([1.5, 2.5, 3.5, 4.5, 5.5])
    dist = dtw_distance(a, b, sakoe_chiba_radius=1)
    assert dist > 0
