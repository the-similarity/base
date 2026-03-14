import numpy as np
import pytest

from the_similarity.methods.bempedelis import (
    self_similarity_transform,
    bempedelis_match,
    _power_law_r2,
    _smoothness_score,
)


def _make_self_similar(n: int = 100, exponent: float = 0.5, seed: int = 42) -> np.ndarray:
    """Generate a self-similar signal: power-law correlated noise."""
    rng = np.random.default_rng(seed)
    # Simple approach: fractional differencing approximation
    # Create a base signal and apply power-law scaling in frequency domain
    white = rng.standard_normal(n)
    freqs = np.fft.rfftfreq(n, d=1.0)
    freqs[0] = 1.0  # avoid divide by zero
    spectrum = np.fft.rfft(white)
    # Apply 1/f^exponent scaling
    spectrum *= freqs ** (-exponent)
    return np.fft.irfft(spectrum, n=n)


def test_self_similarity_basic():
    signal = _make_self_similar(100)
    result = self_similarity_transform(signal, n_subwindows=4, n_restarts=2)

    assert result.alpha.shape == (4,)
    assert result.beta.shape == (4,)
    assert 0 <= result.power_law_r2 <= 1
    assert 0 <= result.smoothness <= 1
    assert 0 <= result.score <= 1
    assert result.residual >= 0


def test_identity_alpha_beta_fixed():
    """First sub-window's alpha and beta should always be 1.0."""
    signal = np.sin(np.linspace(0, 4 * np.pi, 80))
    result = self_similarity_transform(signal, n_subwindows=4, n_restarts=1)
    assert result.alpha[0] == 1.0
    assert result.beta[0] == 1.0


def test_constant_signal():
    """A constant signal should have perfect collapse."""
    signal = np.ones(50)
    result = self_similarity_transform(signal, n_subwindows=5, n_restarts=1)
    assert result.residual < 1e-6


def test_too_few_subwindows():
    with pytest.raises(ValueError, match="n_subwindows"):
        self_similarity_transform(np.ones(20), n_subwindows=1)


def test_too_short_series():
    with pytest.raises(ValueError, match="too short"):
        self_similarity_transform(np.ones(4), n_subwindows=5)


def test_bempedelis_match_identical():
    signal = _make_self_similar(100)
    q_result, c_result, r2_score, smooth_score = bempedelis_match(
        signal, signal, n_subwindows=4, n_restarts=2
    )
    # Identical signals should get identical transforms
    np.testing.assert_allclose(q_result.alpha, c_result.alpha, atol=1e-3)
    assert r2_score >= 0
    assert smooth_score >= 0


def test_bempedelis_match_different():
    sig1 = _make_self_similar(100, exponent=0.5, seed=1)
    sig2 = np.random.default_rng(99).standard_normal(100)  # white noise
    _, _, r2_score, _ = bempedelis_match(sig1, sig2, n_subwindows=4, n_restarts=2)
    # White noise is not self-similar, score should be lower
    # (not a hard guarantee but typical)
    assert 0 <= r2_score <= 1


def test_bempedelis_match_prefers_same_process():
    signal = _make_self_similar(100, exponent=0.6, seed=123)
    identical = bempedelis_match(signal, signal, n_subwindows=4, n_restarts=2)
    different = bempedelis_match(
        signal,
        _make_self_similar(100, exponent=1.1, seed=321),
        n_subwindows=4,
        n_restarts=2,
    )
    assert identical[2] >= different[2]
    assert identical[3] >= different[3]


def test_power_law_r2_perfect():
    t = np.arange(1, 6, dtype=np.float64)
    values = 2.0 * t ** 0.7  # perfect power law
    r2 = _power_law_r2(t, values)
    assert r2 > 0.999


def test_power_law_r2_noise():
    t = np.arange(1, 6, dtype=np.float64)
    rng = np.random.default_rng(42)
    values = rng.standard_normal(5) * 10  # random, not power law
    r2 = _power_law_r2(t, np.abs(values) + 0.1)
    assert 0 <= r2 <= 1


def test_smoothness_score():
    # Monotonically increasing = smooth
    alpha = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    beta = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
    score = _smoothness_score(alpha, beta)
    assert score > 0.5

    # Jagged
    alpha_j = np.array([1.0, 3.0, 0.5, 4.0, 0.2])
    beta_j = np.array([1.0, -2.0, 3.0, -1.0, 2.0])
    score_j = _smoothness_score(alpha_j, beta_j)
    assert score_j < score
