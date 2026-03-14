"""Tests for TDA persistence-diagram matcher."""
import numpy as np
import pytest

ripser = pytest.importorskip("ripser")
pytest.importorskip("persim")

from the_similarity.methods.tda_matcher import (
    compare,
    compute_persistence,
    persistence_distance,
    tda_score,
    TDA_MIN_WINDOW,
)


def _sine_series(n: int = 200, freq: float = 0.1) -> np.ndarray:
    t = np.arange(n, dtype=np.float64)
    return np.sin(2 * np.pi * freq * t)


def _random_walk(n: int = 200, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.standard_normal(n))


def test_tda_identical():
    """Same series should produce near-zero distance."""
    s = _sine_series()
    diag_a = compute_persistence(s)
    diag_b = compute_persistence(s)
    dist = persistence_distance(diag_a, diag_b)
    assert dist < 0.1, f"Expected < 0.1, got {dist}"


def test_tda_different_dynamics():
    """Sine wave vs random walk should be clearly different."""
    s_sine = _sine_series()
    s_walk = _random_walk()
    diag_sine = compute_persistence(s_sine)
    diag_walk = compute_persistence(s_walk)
    dist = persistence_distance(diag_sine, diag_walk)
    assert dist > 0.5, f"Expected > 0.5, got {dist}"


def test_tda_short_window():
    """Series shorter than TDA_MIN_WINDOW should give score 0."""
    short = np.arange(TDA_MIN_WINDOW - 1, dtype=np.float64)
    score = compare(short, short)
    assert score == 0.0


def test_tda_score_range():
    """Score should always be in [0, 1]."""
    s1 = _sine_series()
    s2 = _random_walk()
    for a, b in [(s1, s1), (s1, s2), (s2, s2)]:
        sc = compare(a, b)
        assert 0.0 <= sc <= 1.0, f"Score {sc} out of range"


def test_tda_score_monotonic():
    """Larger distance should map to lower score."""
    assert tda_score(0.0) > tda_score(1.0) > tda_score(5.0)


def test_tda_constant_series():
    """Constant series should return score 0."""
    c = np.ones(100, dtype=np.float64)
    score = compare(c, c)
    assert score == 0.0
