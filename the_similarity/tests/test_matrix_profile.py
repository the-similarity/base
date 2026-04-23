import numpy as np

from the_similarity.methods.matrix_profile_filter import (
    mp_score,
    mp_score_profile,
    query_profile,
)


def test_embedded_pattern_top_ranked():
    """Embed a pattern in noise; MP should rank that position #1."""
    rng = np.random.default_rng(42)
    history = rng.standard_normal(500)
    pattern = np.sin(np.linspace(0, 4 * np.pi, 40))
    history[200:240] = pattern
    query = pattern.copy()

    distances = query_profile(history, query)
    best_pos = int(np.argmin(distances))
    assert best_pos == 200


def test_mp_score_identical():
    """Identical subsequence should have distance ≈ 0 and score ≈ 1."""
    rng = np.random.default_rng(7)
    history = rng.standard_normal(300)
    query = history[100:140].copy()

    distances = query_profile(history, query)
    best_dist = distances[100]
    score = mp_score(best_dist, len(query))
    assert best_dist < 0.01, f"Expected near-zero distance, got {best_dist}"
    assert score > 0.99


def test_mass_returns_correct_length():
    """Output length should be len(history) - len(query) + 1."""
    rng = np.random.default_rng(99)
    history = rng.standard_normal(200)
    query = rng.standard_normal(30)

    distances = query_profile(history, query)
    expected_length = len(history) - len(query) + 1
    assert len(distances) == expected_length


def test_mp_score_profile_range():
    """All scores from mp_score_profile should be in [0, 1]."""
    rng = np.random.default_rng(55)
    history = rng.standard_normal(300)
    query = rng.standard_normal(40)

    distances = query_profile(history, query)
    scores = mp_score_profile(distances, len(query))
    assert scores.min() >= 0.0
    assert scores.max() <= 1.0


def test_mp_score_decreases_with_distance():
    """Higher distance should produce lower score."""
    score_near = mp_score(0.5, 40)
    score_far = mp_score(5.0, 40)
    assert score_near > score_far


def test_mp_score_zero_distance():
    """Distance of 0 should return score of 1.0."""
    assert mp_score(0.0, 40) == 1.0


def test_mp_score_zero_window():
    """mp_score with window_size=0 should not raise (uses max(sqrt(w), 1))."""
    score = mp_score(1.0, 0)
    assert 0.0 <= score <= 1.0


def test_query_profile_list_input():
    """query_profile should accept Python lists as well as ndarrays."""
    history = list(np.sin(np.linspace(0, 4 * np.pi, 100)))
    query = list(np.sin(np.linspace(0, 4 * np.pi, 20)))
    distances = query_profile(history, query)
    assert len(distances) == len(history) - len(query) + 1
    assert np.all(distances >= 0.0)


def test_query_profile_constant_query():
    """Constant query (std≈0) should not raise; distances are finite."""
    history = np.random.default_rng(1).standard_normal(100)
    query = np.ones(20)
    distances = query_profile(history, query)
    assert np.all(np.isfinite(distances))
