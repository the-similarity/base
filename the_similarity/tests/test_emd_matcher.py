import math

import numpy as np
import pytest

from the_similarity.methods.emd_matcher import (
    decompose_emd,
    emd_match,
    emd_score,
    imf_energy,
)


# ---------------------------------------------------------------------------
# decompose_emd
# ---------------------------------------------------------------------------


def test_decompose_emd_returns_list_of_arrays():
    """decompose_emd should return a non-empty list of 1D numpy arrays."""
    t = np.linspace(0, 1, 200)
    signal = np.sin(2 * np.pi * 5 * t) + 0.3 * np.sin(2 * np.pi * 20 * t)
    imfs = decompose_emd(signal)
    assert isinstance(imfs, list)
    assert len(imfs) >= 1
    for imf in imfs:
        assert isinstance(imf, np.ndarray)
        assert imf.ndim == 1


def test_decompose_emd_respects_max_imfs():
    """max_imfs caps the number of returned components."""
    t = np.linspace(0, 1, 256)
    signal = sum(np.sin(2 * np.pi * f * t) for f in [3, 7, 15, 30, 60])
    imfs_full = decompose_emd(signal, max_imfs=6)
    imfs_limited = decompose_emd(signal, max_imfs=2)
    assert len(imfs_limited) <= 2
    assert len(imfs_full) <= 6


def test_decompose_emd_fallback_on_constant_series():
    """Constant (zero-variance) series falls back gracefully to a list with one entry."""
    constant = np.ones(50)
    imfs = decompose_emd(constant)
    # Must not raise; result is a non-empty list regardless of PyEMD internals.
    assert isinstance(imfs, list)
    assert len(imfs) >= 1


def test_decompose_emd_accepts_integer_input():
    """Integer-typed arrays should be coerced to float64 without error."""
    signal = np.arange(100, dtype=np.int32)
    imfs = decompose_emd(signal)
    assert isinstance(imfs, list)
    assert len(imfs) >= 1


# ---------------------------------------------------------------------------
# imf_energy
# ---------------------------------------------------------------------------


def test_imf_energy_zero_array():
    """Zero array must have energy 0."""
    assert imf_energy(np.zeros(50)) == 0.0


def test_imf_energy_known_value():
    """Energy of [1, 2, 3] = 1² + 2² + 3² = 14."""
    assert imf_energy(np.array([1.0, 2.0, 3.0])) == pytest.approx(14.0)


def test_imf_energy_nonnegative():
    """Energy is always ≥ 0 for any input."""
    rng = np.random.default_rng(0)
    for _ in range(10):
        arr = rng.standard_normal(64)
        assert imf_energy(arr) >= 0.0


def test_imf_energy_scales_with_amplitude():
    """Doubling amplitude quadruples energy (sum-of-squares property)."""
    arr = np.array([1.0, -1.0, 1.0, -1.0])
    e1 = imf_energy(arr)
    e2 = imf_energy(arr * 2)
    assert e2 == pytest.approx(4 * e1)


# ---------------------------------------------------------------------------
# emd_match — return type and structure
# ---------------------------------------------------------------------------


def test_emd_match_returns_tuple():
    """emd_match should return a (float, float) tuple."""
    t = np.linspace(0, 1, 100)
    s = np.sin(2 * np.pi * 5 * t)
    result = emd_match(s, s)
    assert isinstance(result, tuple)
    assert len(result) == 2
    score, dist = result
    assert isinstance(score, float)
    assert isinstance(dist, float)


# ---------------------------------------------------------------------------
# emd_match — edge cases that must return (0.0, inf)
# ---------------------------------------------------------------------------


def test_emd_match_short_query_returns_zero():
    """Query shorter than 10 bars must return (0.0, inf)."""
    short = np.array([1.0, 2.0, 3.0])
    long_enough = np.linspace(0, 1, 50)
    score, dist = emd_match(short, long_enough)
    assert score == 0.0
    assert math.isinf(dist)


def test_emd_match_short_candidate_returns_zero():
    """Candidate shorter than 10 bars must return (0.0, inf)."""
    long_enough = np.linspace(0, 1, 50)
    short = np.array([1.0, 2.0])
    score, dist = emd_match(long_enough, short)
    assert score == 0.0
    assert math.isinf(dist)


def test_emd_match_zero_variance_query_returns_zero():
    """Constant query (std == 0) must return (0.0, inf)."""
    constant = np.ones(50)
    varying = np.linspace(0, 1, 50)
    score, dist = emd_match(constant, varying)
    assert score == 0.0
    assert math.isinf(dist)


def test_emd_match_zero_variance_candidate_returns_zero():
    """Constant candidate (std == 0) must return (0.0, inf)."""
    varying = np.linspace(0, 1, 50)
    constant = np.ones(50)
    score, dist = emd_match(varying, constant)
    assert score == 0.0
    assert math.isinf(dist)


# ---------------------------------------------------------------------------
# emd_match — correctness properties
# ---------------------------------------------------------------------------


def test_emd_match_identical_series_score_near_one():
    """Identical series produce distance ≈ 0 and score ≈ 1."""
    t = np.linspace(0, 1, 200)
    signal = np.sin(2 * np.pi * 5 * t) + 0.5 * np.sin(2 * np.pi * 12 * t)
    score, dist = emd_match(signal, signal.copy())
    assert score >= 0.99, f"Expected score ≈ 1 for identical series, got {score}"
    assert dist < 1e-10, f"Expected distance ≈ 0 for identical series, got {dist}"


def test_emd_match_score_equals_exp_neg_distance():
    """score must exactly equal exp(-distance) per the implementation contract."""
    rng = np.random.default_rng(7)
    a = rng.standard_normal(150)
    b = rng.standard_normal(150)
    score, dist = emd_match(a, b)
    assert score == pytest.approx(math.exp(-dist), rel=1e-9)


def test_emd_match_score_in_range():
    """Score must always be in [0, 1]."""
    rng = np.random.default_rng(13)
    for _ in range(8):
        a = rng.standard_normal(120)
        b = rng.standard_normal(120)
        score, _ = emd_match(a, b)
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1]"


def test_emd_match_distance_nonnegative():
    """Total distance must be ≥ 0 for valid inputs."""
    rng = np.random.default_rng(21)
    for _ in range(8):
        a = rng.standard_normal(100)
        b = rng.standard_normal(100)
        _, dist = emd_match(a, b)
        assert dist >= 0.0, f"Distance {dist} is negative"


def test_emd_match_similar_series_higher_score_than_different():
    """Series drawn from the same process should score higher than unrelated series."""
    rng = np.random.default_rng(42)
    t = np.linspace(0, 2 * np.pi, 200)
    query = np.sin(t) + 0.1 * rng.standard_normal(200)
    similar = np.sin(t) + 0.1 * rng.standard_normal(200)
    unrelated = rng.standard_normal(200)

    score_sim, _ = emd_match(query, similar)
    score_diff, _ = emd_match(query, unrelated)
    assert score_sim > score_diff, (
        f"Similar score {score_sim} should exceed unrelated score {score_diff}"
    )


def test_emd_match_max_imfs_param_accepted():
    """Non-default max_imfs values should not raise and should return valid results."""
    t = np.linspace(0, 1, 200)
    s = np.sin(2 * np.pi * 5 * t) + 0.5 * np.cos(2 * np.pi * 10 * t)
    for max_imfs in (1, 2, 3, 10):
        score, dist = emd_match(s, s.copy(), max_imfs=max_imfs)
        assert 0.0 <= score <= 1.0
        assert dist >= 0.0


# ---------------------------------------------------------------------------
# emd_score — wrapper consistency
# ---------------------------------------------------------------------------


def test_emd_score_matches_emd_match_first_element():
    """emd_score must return exactly emd_match(...)[0]."""
    rng = np.random.default_rng(99)
    a = rng.standard_normal(100)
    b = rng.standard_normal(100)
    assert emd_score(a, b) == emd_match(a, b)[0]


def test_emd_score_range_random_pairs():
    """emd_score must stay in [0, 1] across random inputs."""
    rng = np.random.default_rng(55)
    for _ in range(10):
        a = rng.standard_normal(100)
        b = rng.standard_normal(100)
        score = emd_score(a, b)
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1]"


def test_emd_score_short_returns_zero():
    """Short series convenience wrapper should return 0.0 directly."""
    short = np.array([1.0, 2.0, 3.0, 4.0])
    assert emd_score(short, short) == 0.0
