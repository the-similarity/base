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
    """Distance 0 should produce score 1.0."""
    assert mp_score(0.0, 40) == 1.0


def test_query_profile_single_window():
    """query_profile output has length 1 when history == query."""
    query = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
    distances = query_profile(query, query)
    assert len(distances) == 1
    assert distances[0] < 0.01


def test_mp_score_profile_shape():
    """mp_score_profile output shape must match input distances shape."""
    rng = np.random.default_rng(33)
    distances = rng.uniform(0, 5, size=150)
    scores = mp_score_profile(distances, window_size=40)
    assert scores.shape == distances.shape


def test_query_profile_distances_nonnegative():
    """All distance values in the profile must be >= 0."""
    rng = np.random.default_rng(88)
    history = rng.standard_normal(300)
    query = rng.standard_normal(50)
    distances = query_profile(history, query)
    assert np.all(distances >= 0.0)
