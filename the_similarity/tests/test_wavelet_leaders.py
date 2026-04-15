import numpy as np

from the_similarity.methods.wavelet_leaders import (
    compute_wavelet_leaders,
    multifractal_spectrum,
    spectrum_distance,
    wavelet_spectrum_score,
)


def test_spectrum_self_distance_zero():
    """Same series should have spectrum distance ≈ 0."""
    rng = np.random.default_rng(42)
    series = np.cumsum(rng.standard_normal(256))
    leaders = compute_wavelet_leaders(series)
    spec = multifractal_spectrum(leaders)
    dist = spectrum_distance(spec, spec)
    assert dist < 0.01


def test_white_noise_vs_trending():
    """White noise and trending series should have different spectra."""
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(256)
    trend = np.cumsum(rng.standard_normal(256)) + np.linspace(0, 10, 256)

    leaders_n = compute_wavelet_leaders(noise)
    leaders_t = compute_wavelet_leaders(trend)
    spec_n = multifractal_spectrum(leaders_n)
    spec_t = multifractal_spectrum(leaders_t)
    dist = spectrum_distance(spec_n, spec_t)
    assert dist > 0.05


def test_short_series_graceful():
    """Series shorter than 16 bars should return fallback score."""
    short = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    score = wavelet_spectrum_score(short, short)
    assert score == 0.5


def test_wavelet_score_range():
    """Score should always be in [0, 1]."""
    rng = np.random.default_rng(99)
    for _ in range(10):
        a = np.cumsum(rng.standard_normal(128))
        b = np.cumsum(rng.standard_normal(128))
        score = wavelet_spectrum_score(a, b)
        assert 0.0 <= score <= 1.0


def test_similar_series_higher_score():
    """Two segments from the same process should score higher than unrelated."""
    rng = np.random.default_rng(55)
    base = np.cumsum(rng.standard_normal(512))
    seg_a = base[100:228]
    seg_b = base[300:428]
    unrelated = rng.standard_normal(128)

    score_similar = wavelet_spectrum_score(seg_a, seg_b)
    score_different = wavelet_spectrum_score(seg_a, unrelated)
    assert score_similar > score_different
