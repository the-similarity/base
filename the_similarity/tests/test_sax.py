import numpy as np
import pytest

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


def test_sax_transform_output_dtype():
    """SAX transform should return int8 array."""
    series = np.random.default_rng(5).standard_normal(64)
    result = sax_transform(series, n_segments=8, alphabet_size=4)
    assert result.dtype == np.int8


def test_sax_mindist_symmetry():
    """MINDIST must be symmetric: MINDIST(a, b) == MINDIST(b, a)."""
    rng = np.random.default_rng(77)
    a = rng.standard_normal(80)
    b = rng.standard_normal(80)
    sax_a = sax_transform(a, n_segments=16, alphabet_size=8)
    sax_b = sax_transform(b, n_segments=16, alphabet_size=8)
    d_ab = sax_mindist(sax_a, sax_b, original_length=80, alphabet_size=8)
    d_ba = sax_mindist(sax_b, sax_a, original_length=80, alphabet_size=8)
    assert d_ab == pytest.approx(d_ba)


def test_sax_transform_n_segments_exceeds_length():
    """When n_segments >= series length, PAA is an identity copy; output length == series length."""
    series = np.array([1.0, 2.0, 3.0])
    result = sax_transform(series, n_segments=10, alphabet_size=4)
    # PAA returns a copy of the series when n_segments >= len(series),
    # so the SAX output has len(series) symbols, not n_segments.
    assert len(result) == len(series)


def test_sax_score_decreases_with_mindist():
    """Higher MINDIST should produce a lower score."""
    assert sax_score(0.0, 50) > sax_score(1.0, 50) > sax_score(10.0, 50)
