import numpy as np

from the_similarity.methods.koopman import (
    fit_koopman,
    koopman_eigenvalue_distance,
    koopman_match,
    koopman_score,
)


def _make_sine_mixture(n: int = 200, seed: int = 0) -> np.ndarray:
    """sin(t) + 0.5*sin(2t) with optional tiny noise."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 4 * np.pi, n)
    return np.sin(t) + 0.5 * np.sin(2 * t) + 1e-6 * rng.standard_normal(n)


def _make_random_walk(n: int = 200, seed: int = 99) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.standard_normal(n))


class TestSameSystemLowDistance:
    def test_same_system_low_distance(self):
        """Two windows from the same sine mixture should have low distance."""
        sig_a = _make_sine_mixture(200, seed=0)
        sig_b = _make_sine_mixture(200, seed=1)

        res_a = fit_koopman(sig_a)
        res_b = fit_koopman(sig_b)

        distance = koopman_eigenvalue_distance(res_a.eigenvalues, res_b.eigenvalues)
        assert distance < 1.0, f"Expected distance < 1.0, got {distance}"


class TestDifferentSystemsHighDistance:
    def test_different_systems_high_distance(self):
        """Sine mixture vs random walk should have higher distance."""
        sig_sine = _make_sine_mixture(200, seed=0)
        sig_walk = _make_random_walk(200, seed=99)

        res_sine = fit_koopman(sig_sine)
        res_walk = fit_koopman(sig_walk)

        distance = koopman_eigenvalue_distance(
            res_sine.eigenvalues, res_walk.eigenvalues
        )
        assert distance > 1.0, f"Expected distance > 1.0, got {distance}"


class TestEigenvalueCount:
    def test_eigenvalue_count(self):
        """fit_koopman should return at most n_modes eigenvalues."""
        sig = _make_sine_mixture(200)
        for n_modes in (4, 8):
            result = fit_koopman(sig, n_modes=n_modes)
            assert len(result.eigenvalues) <= n_modes
            assert result.a_tilde.shape[0] <= n_modes
            assert result.a_tilde.shape[1] <= n_modes


class TestHungarianMatchingSymmetric:
    def test_hungarian_matching_symmetric(self):
        """distance(A, B) should equal distance(B, A)."""
        sig_a = _make_sine_mixture(200, seed=10)
        sig_b = _make_random_walk(200, seed=20)

        res_a = fit_koopman(sig_a)
        res_b = fit_koopman(sig_b)

        d_ab = koopman_eigenvalue_distance(res_a.eigenvalues, res_b.eigenvalues)
        d_ba = koopman_eigenvalue_distance(res_b.eigenvalues, res_a.eigenvalues)

        np.testing.assert_allclose(d_ab, d_ba, atol=1e-10)


class TestShortWindowGraceful:
    def test_short_window_returns_zero(self):
        """Windows shorter than 50 bars should yield score 0.0."""
        short = np.sin(np.linspace(0, np.pi, 30))
        score = koopman_match(short, short)
        assert score == 0.0

    def test_constant_series_returns_zero(self):
        """All-constant series should yield score 0.0."""
        const = np.ones(100)
        score = koopman_match(const, const)
        assert score == 0.0


class TestKoopmanScore:
    def test_zero_distance_perfect_score(self):
        assert koopman_score(0.0) == 1.0

    def test_score_decreases_with_distance(self):
        s1 = koopman_score(1.0)
        s2 = koopman_score(5.0)
        assert 0 < s2 < s1 < 1.0

    def test_score_in_unit_interval(self):
        for d in [0.0, 0.5, 1.0, 5.0, 100.0]:
            s = koopman_score(d)
            assert 0.0 <= s <= 1.0


class TestKoopmanMatchEndToEnd:
    def test_identical_signals_high_score(self):
        sig = _make_sine_mixture(200)
        score = koopman_match(sig, sig)
        assert score > 0.8

    def test_similar_higher_than_different(self):
        sig_a = _make_sine_mixture(200, seed=0)
        sig_b = _make_sine_mixture(200, seed=1)
        sig_c = _make_random_walk(200, seed=99)

        score_similar = koopman_match(sig_a, sig_b)
        score_different = koopman_match(sig_a, sig_c)
        assert score_similar > score_different
