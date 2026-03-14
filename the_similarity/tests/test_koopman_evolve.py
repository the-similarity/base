import numpy as np
import pytest

from the_similarity.methods.koopman import (
    KoopmanForecast,
    clamp_eigenvalues,
    fit_koopman,
    koopman_evolve,
)


def _make_sine_mixture(n: int = 200, seed: int = 0) -> np.ndarray:
    """sin(t) + 0.5*sin(2t) + offset, ending away from zero."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 3.5 * np.pi, n)  # ends away from zero
    return 5.0 + np.sin(t) + 0.5 * np.sin(2 * t) + 1e-6 * rng.standard_normal(n)


class TestClampEigenvalues:
    def test_stable_eigenvalues_unchanged(self):
        """Eigenvalues with |λ| <= 1 should pass through unchanged."""
        eigs = np.array([0.5 + 0.3j, 0.9 + 0.0j, -0.7 + 0.2j])
        clamped = clamp_eigenvalues(eigs)
        np.testing.assert_allclose(clamped, eigs)

    def test_unstable_eigenvalues_clamped_to_unit_disk(self):
        """Eigenvalues with |λ| > 1 should be scaled to |λ| = 1."""
        eigs = np.array([2.0 + 0.0j, 0.0 + 3.0j, 1.5 + 1.5j])
        clamped = clamp_eigenvalues(eigs)
        mags = np.abs(clamped)
        np.testing.assert_allclose(mags, [1.0, 1.0, 1.0], atol=1e-12)

    def test_phase_preserved_after_clamping(self):
        """Clamping should preserve the phase angle."""
        eigs = np.array([2.0 + 2.0j, -3.0 + 1.0j])
        clamped = clamp_eigenvalues(eigs)
        original_phases = np.angle(eigs)
        clamped_phases = np.angle(clamped)
        np.testing.assert_allclose(clamped_phases, original_phases, atol=1e-12)

    def test_mixed_stable_unstable(self):
        """Only unstable eigenvalues should be modified."""
        eigs = np.array([0.5 + 0.0j, 2.0 + 0.0j])
        clamped = clamp_eigenvalues(eigs)
        assert abs(clamped[0]) == pytest.approx(0.5)
        assert abs(clamped[1]) == pytest.approx(1.0)


class TestKoopmanEvolve:
    def test_returns_forecast_for_valid_series(self):
        """Should return a KoopmanForecast for a well-behaved series."""
        sig = _make_sine_mixture(200)
        result = koopman_evolve(sig, forward_bars=20)
        assert result is not None
        assert isinstance(result, KoopmanForecast)
        assert len(result.trajectory) == 20
        assert len(result.uncertainty) == 20

    def test_short_series_returns_none(self):
        """Series shorter than KOOPMAN_MIN_WINDOW should return None."""
        short = np.sin(np.linspace(0, np.pi, 30))
        result = koopman_evolve(short, forward_bars=10)
        assert result is None

    def test_constant_series_returns_none(self):
        """All-constant series should return None."""
        const = np.ones(100)
        result = koopman_evolve(const, forward_bars=10)
        assert result is None

    def test_trajectory_bounded(self):
        """With clamped eigenvalues, trajectory should not diverge.

        This is the key safety property — without clamping, unstable
        eigenvalues would produce exponentially growing forecasts.
        """
        sig = _make_sine_mixture(200)
        result = koopman_evolve(sig, forward_bars=100)
        assert result is not None
        # Cumulative returns should stay bounded (not blow up to infinity)
        assert np.all(np.isfinite(result.trajectory))
        assert np.max(np.abs(result.trajectory)) < 10.0  # reasonable bound for returns

    def test_uncertainty_grows_with_horizon(self):
        """Uncertainty should increase with forecast horizon."""
        sig = _make_sine_mixture(200)
        result = koopman_evolve(sig, forward_bars=50)
        assert result is not None
        # Uncertainty at bar 50 should be larger than at bar 1
        if result.uncertainty[0] > 0:
            assert result.uncertainty[-1] > result.uncertainty[0]

    def test_known_system_predicts_oscillation(self):
        """A pure sine wave should produce a forecast that continues oscillating.

        The Koopman operator of a periodic system should capture the
        dominant frequency, so the forecast should show oscillatory behavior
        rather than decaying to zero or diverging.
        """
        t = np.linspace(0, 7.5 * np.pi, 300)  # ends away from zero
        sig = 10.0 + np.sin(t)  # offset so last_value >> 0
        result = koopman_evolve(sig, forward_bars=30, dim=4, lag=2)
        assert result is not None
        # The trajectory should have non-trivial variation (oscillation)
        assert np.std(result.trajectory) > 1e-6

    def test_u_r_stored_in_fit_result(self):
        """fit_koopman should now store u_r for projection."""
        sig = _make_sine_mixture(200)
        result = fit_koopman(sig)
        assert result.u_r is not None
        # u_r should have shape (dim, r)
        r = len(result.eigenvalues)
        assert result.u_r.shape[1] == r


class TestKoopmanEvolveIntegration:
    def test_forecast_field_on_projector(self):
        """The Forecast dataclass should accept koopman_forecast."""
        from the_similarity.core.projector import Forecast

        kf = KoopmanForecast(
            trajectory=np.zeros(10),
            uncertainty=np.ones(10) * 0.1,
        )
        forecast = Forecast(
            bars=10,
            percentiles=[50],
            curves={50: np.zeros(10)},
            all_paths=np.zeros((1, 10)),
            weights=np.array([1.0]),
            koopman_forecast=kf,
        )
        assert forecast.koopman_forecast is not None
        assert len(forecast.koopman_forecast.trajectory) == 10
