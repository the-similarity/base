import numpy as np

from the_similarity.methods.sax_filter import (
    sax_mindist,
    sax_score,
    sax_transform,
)


def test_sax_identical_series():
    """Same input should produce SAX distance 0."""
    rng = np.random.default_rng(42)
    series = rng.standard_normal(100)
    sax_a = sax_transform(series, n_segments=16, alphabet_size=8)
    sax_b = sax_transform(series, n_segments=16, alphabet_size=8)
    dist = sax_mindist(sax_a, sax_b, original_length=100, alphabet_size=8)
    assert dist == 0.0
    assert sax_score(dist, 100) == 1.0


def test_sax_mindist_lower_bounds_euclidean():
    """For random pairs, MINDIST should be <= Euclidean distance."""
    rng = np.random.default_rng(123)
    for _ in range(50):
        a = rng.standard_normal(64)
        b = rng.standard_normal(64)
        sax_a = sax_transform(a, n_segments=16, alphabet_size=8)
        sax_b = sax_transform(b, n_segments=16, alphabet_size=8)
        mindist = sax_mindist(sax_a, sax_b, original_length=64, alphabet_size=8)
        euclidean = np.linalg.norm(a - b)
        assert mindist <= euclidean + 1e-10, (
            f"MINDIST {mindist} exceeded Euclidean {euclidean}"
        )


def test_sax_embedded_pattern_survives_filter():
    """Embed a known pattern in noise; SAX prefilter should score it highly."""
    rng = np.random.default_rng(7)
    n = 500
    history = rng.standard_normal(n)
    pattern = np.sin(np.linspace(0, 4 * np.pi, 60))
    # Embed pattern at position 200
    history[200:260] = pattern
    query = pattern.copy()

    # Z-normalize both (simulating pipeline normalization)
    query_norm = (query - query.mean()) / query.std()
    query_sax = sax_transform(query_norm, n_segments=16, alphabet_size=8)

    best_score = -1.0
    best_pos = -1
    window_size = 60
    for start in range(0, n - window_size + 1, 5):
        window = history[start : start + window_size]
        w_norm = (window - window.mean()) / max(window.std(), 1e-12)
        w_sax = sax_transform(w_norm, n_segments=16, alphabet_size=8)
        mindist = sax_mindist(query_sax, w_sax, original_length=60, alphabet_size=8)
        score = sax_score(mindist, 60)
        if score > best_score:
            best_score = score
            best_pos = start

    assert best_pos == 200, f"Expected position 200, got {best_pos}"
    assert best_score > 0.8


def test_sax_transform_output_shape():
    """SAX transform returns correct number of segments."""
    series = np.random.default_rng(0).standard_normal(128)
    result = sax_transform(series, n_segments=16, alphabet_size=8)
    assert result.shape == (16,)
    assert result.min() >= 0
    assert result.max() < 8


def test_sax_score_range():
    """SAX score should always be in [0, 1]."""
    rng = np.random.default_rng(99)
    for _ in range(20):
        a = rng.standard_normal(50)
        b = rng.standard_normal(50)
        sax_a = sax_transform(a, n_segments=10, alphabet_size=6)
        sax_b = sax_transform(b, n_segments=10, alphabet_size=6)
        mindist = sax_mindist(sax_a, sax_b, original_length=50, alphabet_size=6)
        score = sax_score(mindist, 50)
        assert 0.0 <= score <= 1.0
