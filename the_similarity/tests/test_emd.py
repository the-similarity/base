import numpy as np
import pytest

from the_similarity.methods.emd_matcher import (
    decompose_emd,
    emd_match,
    emd_score,
    imf_energy,
)


def test_emd_identical():
    """Same signal should produce a high similarity score."""
    t = np.linspace(0, 1, 200)
    signal = np.sin(2 * np.pi * 5 * t) + 0.5 * np.sin(2 * np.pi * 12 * t)
    score = emd_score(signal, signal.copy())
    assert score > 0.8, f"Expected score > 0.8 for identical signals, got {score}"


def test_emd_different_frequency():
    """Signals with very different frequencies should have lower similarity than identical."""
    t = np.linspace(0, 1, 200)
    signal = np.sin(2 * np.pi * 5 * t) + 0.5 * np.sin(2 * np.pi * 12 * t)
    different = np.sin(2 * np.pi * 20 * t) + 0.5 * np.cos(2 * np.pi * 3 * t)
    score_same = emd_score(signal, signal.copy())
    score_diff = emd_score(signal, different)
    assert score_diff < score_same, (
        f"Different signals ({score_diff}) should score lower than identical ({score_same})"
    )


def test_imf_count():
    """A typical composite signal should decompose into 2-6 IMFs."""
    t = np.linspace(0, 1, 200)
    signal = np.sin(2 * np.pi * 5 * t) + 0.3 * np.sin(2 * np.pi * 20 * t) + t
    imfs = decompose_emd(signal)
    assert 2 <= len(imfs) <= 6, f"Expected 2-6 IMFs, got {len(imfs)}"


def test_emd_short_series():
    """Series shorter than 10 bars should return score = 0.0."""
    short = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    score = emd_score(short, short)
    assert score == 0.0, f"Expected score 0.0 for short series, got {score}"


def test_emd_score_range():
    """Score should always be in [0, 1]."""
    rng = np.random.default_rng(42)
    for _ in range(5):
        a = rng.standard_normal(100)
        b = rng.standard_normal(100)
        score = emd_score(a, b)
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1] range"


def test_imf_energy_zero():
    """Zero array has zero energy."""
    assert imf_energy(np.zeros(50)) == 0.0


def test_imf_energy_known():
    """Energy equals sum of squares."""
    arr = np.array([1.0, 2.0, 3.0])
    assert imf_energy(arr) == pytest.approx(14.0)


def test_imf_energy_positive():
    """Energy is always non-negative."""
    rng = np.random.default_rng(11)
    imf = rng.standard_normal(200)
    assert imf_energy(imf) >= 0.0


def test_emd_match_returns_tuple():
    """emd_match should return (score, distance) tuple."""
    t = np.linspace(0, 1, 200)
    signal = np.sin(2 * np.pi * 5 * t)
    result = emd_match(signal, signal.copy())
    assert isinstance(result, tuple) and len(result) == 2
    score, distance = result
    assert 0.0 <= score <= 1.0
    assert distance >= 0.0


def test_emd_match_identical_score_high():
    """Identical series should produce a high score via emd_match."""
    t = np.linspace(0, 1, 200)
    signal = np.sin(2 * np.pi * 8 * t) + 0.3 * np.cos(2 * np.pi * 3 * t)
    score, dist = emd_match(signal, signal.copy())
    assert score > 0.8, f"Identical signals should score > 0.8, got {score}"
    assert dist < 0.5, f"Identical signals should have small distance, got {dist}"


def test_emd_match_constant_series():
    """Constant series (zero variance) should return score 0 and inf distance."""
    const = np.ones(100)
    score, dist = emd_match(const, const)
    assert score == 0.0
    assert dist == float("inf")


def test_emd_match_short_series():
    """Series shorter than 10 should return (0.0, inf)."""
    short = np.array([1.0, 2.0, 3.0])
    score, dist = emd_match(short, short)
    assert score == 0.0
    assert dist == float("inf")
