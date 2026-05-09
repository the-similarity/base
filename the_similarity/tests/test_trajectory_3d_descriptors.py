"""Unit tests for 3D trajectory shape descriptors.

Verifies the analytical guarantees promised in
``the_similarity/methods/trajectory_3d.py``:

1. Straight line -> kappa = 0, tau = 0.
2. Circular arc in xy-plane (radius r) -> kappa = 1/r, tau = 0.
3. Helix (radius r, pitch param c) -> kappa = r/(r^2+c^2),
   tau = c/(r^2+c^2).
4. Rigid-motion invariance: rotated + translated curves yield the
   same descriptors (up to floating-point tolerance).
5. DTW sanity: distance(x, x) = 0 and is symmetric (commutative).
6. Arc-length resampling preserves endpoints and produces uniform
   spacing.

These tests are the single best safeguard that the formulas are
implemented correctly — every paper on space curves uses these
exact analytical references.
"""

from __future__ import annotations

import numpy as np
import pytest

from the_similarity.methods.trajectory_3d import (
    arc_length_resample,
    dtw_kt_distance,
    frenet_descriptors,
    multiscale_descriptors,
)


# Helper: trim window edges before computing summary stats. The Frenet
# formulas use one-sided differences near the boundary (we replicate
# the last interior value to keep array shapes aligned), so the very
# last few entries are not directly comparable to the analytical
# constants. Trimming 10% from each side is the standard approach in
# the curve-matching literature.
def _interior(arr: np.ndarray, frac: float = 0.1) -> np.ndarray:
    n = len(arr)
    pad = max(1, int(np.ceil(n * frac)))
    return arr[pad:-pad]


# ---------------------------------------------------------------------------
# arc_length_resample
# ---------------------------------------------------------------------------


class TestArcLengthResample:
    def test_straight_line_endpoints_preserved(self):
        # A line from (0,0,0) to (10,0,0). Resampling to 25 points
        # should keep the endpoints exact and place 23 in between.
        line = np.stack([np.linspace(0, 10, 50), np.zeros(50), np.zeros(50)], axis=1)
        out = arc_length_resample(line, 25)
        assert out.shape == (25, 3)
        np.testing.assert_allclose(out[0], line[0], atol=1e-10)
        np.testing.assert_allclose(out[-1], line[-1], atol=1e-10)

    def test_uniform_arc_length_after_resample(self):
        # After resampling, consecutive segment lengths should be
        # near-uniform (deviation < 1% relative to the mean).
        theta = np.linspace(0, 2 * np.pi, 200)
        circle = np.stack([np.cos(theta), np.sin(theta), np.zeros_like(theta)], axis=1)
        out = arc_length_resample(circle, 100)
        seg_lens = np.linalg.norm(np.diff(out, axis=0), axis=1)
        rel_std = float(np.std(seg_lens) / np.mean(seg_lens))
        assert rel_std < 0.01, f"Expected uniform spacing, rel_std={rel_std}"

    def test_zero_length_raises(self):
        # All points identical -> total length = 0 -> ValueError.
        pts = np.zeros((5, 3))
        with pytest.raises(ValueError, match="zero total length"):
            arc_length_resample(pts, 10)

    def test_too_few_samples_raises(self):
        line = np.stack([np.linspace(0, 1, 10), np.zeros(10), np.zeros(10)], axis=1)
        with pytest.raises(ValueError, match="n_samples must be >= 2"):
            arc_length_resample(line, 1)

    def test_wrong_shape_raises(self):
        with pytest.raises(ValueError, match=r"\(N, 3\)"):
            arc_length_resample(np.zeros((5, 2)), 4)


# ---------------------------------------------------------------------------
# frenet_descriptors — analytical references
# ---------------------------------------------------------------------------


class TestFrenetAnalyticalReferences:
    """Verify discrete kappa, tau against closed-form values."""

    def test_straight_line_zero_curvature_zero_torsion(self):
        # A line in 3D has kappa = 0 everywhere. Sample with a slight
        # diagonal so the curve is genuinely 3D and any spurious
        # numerical curvature would surface.
        t = np.linspace(0, 10, 80)
        line = np.stack([t, 2 * t, -3 * t], axis=1)
        resampled = arc_length_resample(line, 80)
        kappa, tau = frenet_descriptors(resampled, sigma=0.0)
        assert np.max(np.abs(kappa)) < 1e-8, (
            f"Line should have kappa=0; got max {kappa.max()}"
        )
        assert np.max(np.abs(tau)) < 1e-8, (
            f"Line should have tau=0; got max {np.abs(tau).max()}"
        )

    def test_circle_curvature_inverse_radius(self):
        # Circle of radius r in the xy-plane. Expected kappa = 1/r.
        # Use a long enough curve (~one full revolution) so we have
        # plenty of interior samples.
        for r in [1.0, 2.0, 5.0]:
            theta = np.linspace(0, 2 * np.pi, 400)
            circle = np.stack(
                [r * np.cos(theta), r * np.sin(theta), np.zeros_like(theta)],
                axis=1,
            )
            resampled = arc_length_resample(circle, 200)
            kappa, tau = frenet_descriptors(resampled, sigma=1.0)
            expected = 1.0 / r
            mid_kappa = float(np.median(_interior(kappa, 0.15)))
            assert abs(mid_kappa - expected) < 0.02, (
                f"Circle r={r}: expected kappa={expected:.4f}, got {mid_kappa:.4f}"
            )
            # Planar curves have tau identically zero.
            mid_tau_abs = float(np.max(np.abs(_interior(tau, 0.15))))
            assert mid_tau_abs < 0.02, (
                f"Circle r={r}: planar curve should have tau=0, got max|tau|={mid_tau_abs}"
            )

    def test_helix_kappa_and_tau_match_analytical(self):
        # Helix: gamma(t) = (r cos t, r sin t, c t).
        # Analytical: kappa = r / (r^2 + c^2), tau = c / (r^2 + c^2).
        for r, c in [(1.0, 0.25), (2.0, 0.5), (1.0, 1.0)]:
            theta = np.linspace(0, 6 * np.pi, 800)
            helix = np.stack([r * np.cos(theta), r * np.sin(theta), c * theta], axis=1)
            resampled = arc_length_resample(helix, 300)
            kappa, tau = frenet_descriptors(resampled, sigma=1.5)
            expected_k = r / (r**2 + c**2)
            expected_t = c / (r**2 + c**2)
            med_k = float(np.median(_interior(kappa, 0.15)))
            med_t = float(np.median(_interior(tau, 0.15)))
            assert abs(med_k - expected_k) < 0.02, (
                f"Helix(r={r},c={c}): expected kappa={expected_k:.4f}, got {med_k:.4f}"
            )
            assert abs(med_t - expected_t) < 0.02, (
                f"Helix(r={r},c={c}): expected tau={expected_t:.4f}, got {med_t:.4f}"
            )


class TestRigidMotionInvariance:
    """Translation + rotation must leave (kappa, tau) unchanged."""

    def _rand_rotation(self, rng: np.random.Generator) -> np.ndarray:
        # Build a random rotation via three Euler angles. Numerically
        # stable enough for the tolerances we test against.
        a, b, c = rng.uniform(-np.pi, np.pi, size=3)
        Rx = np.array(
            [[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]]
        )
        Ry = np.array(
            [[np.cos(b), 0, np.sin(b)], [0, 1, 0], [-np.sin(b), 0, np.cos(b)]]
        )
        Rz = np.array(
            [[np.cos(c), -np.sin(c), 0], [np.sin(c), np.cos(c), 0], [0, 0, 1]]
        )
        return Rz @ Ry @ Rx

    def test_helix_descriptors_invariant_under_rigid_motion(self):
        rng = np.random.default_rng(42)
        theta = np.linspace(0, 4 * np.pi, 500)
        r, c = 1.0, 0.3
        helix = np.stack([r * np.cos(theta), r * np.sin(theta), c * theta], axis=1)
        # Original descriptors
        original = arc_length_resample(helix, 200)
        k0, t0 = frenet_descriptors(original, sigma=1.0)

        # Three random rigid motions
        for trial in range(3):
            R = self._rand_rotation(rng)
            shift = rng.uniform(-10, 10, size=3)
            transformed = helix @ R.T + shift
            resampled = arc_length_resample(transformed, 200)
            k1, t1 = frenet_descriptors(resampled, sigma=1.0)

            # Compare interior portions to avoid edge replication
            # artifacts. Tight tolerance because the formulas are
            # algebraically invariant — any deviation is purely
            # floating-point.
            np.testing.assert_allclose(
                _interior(k0, 0.15),
                _interior(k1, 0.15),
                atol=1e-3,
                err_msg=f"trial {trial}: kappa changed under rigid motion",
            )
            # Torsion is signed; rotation can flip handedness only via
            # a reflection, which a proper rotation (det=+1) does not.
            np.testing.assert_allclose(
                _interior(t0, 0.15),
                _interior(t1, 0.15),
                atol=1e-3,
                err_msg=f"trial {trial}: tau changed under proper rotation",
            )


# ---------------------------------------------------------------------------
# Multiscale + DTW
# ---------------------------------------------------------------------------


class TestMultiscaleDescriptors:
    def test_default_sigmas_returns_three_scales(self):
        theta = np.linspace(0, 4 * np.pi, 200)
        helix = np.stack([np.cos(theta), np.sin(theta), 0.3 * theta], axis=1)
        resampled = arc_length_resample(helix, 100)
        out = multiscale_descriptors(resampled)
        assert set(out.keys()) == {1.0, 4.0, 16.0}
        for sigma, (k, t) in out.items():
            assert k.shape == (100,)
            assert t.shape == (100,)
            # Smoother sigma -> lower variance (the whole point of
            # smoothing). Compare sigma=1 vs sigma=16 variance.
        var_fine = float(np.var(out[1.0][0]))
        var_coarse = float(np.var(out[16.0][0]))
        assert var_coarse <= var_fine + 1e-9

    def test_explicit_sigmas_passes_through(self):
        theta = np.linspace(0, 2 * np.pi, 100)
        circle = np.stack([np.cos(theta), np.sin(theta), np.zeros_like(theta)], axis=1)
        resampled = arc_length_resample(circle, 60)
        out = multiscale_descriptors(resampled, sigmas=[0.5, 2.0])
        assert set(out.keys()) == {0.5, 2.0}


class TestDtwKtDistance:
    def test_self_distance_is_zero(self):
        # A sequence compared with itself must have DTW distance 0.
        rng = np.random.default_rng(0)
        kt = rng.normal(size=(40, 2))
        d = dtw_kt_distance(kt, kt)
        assert d == 0.0

    def test_symmetry(self):
        # Without a band, DTW is symmetric: d(a,b) = d(b,a).
        rng = np.random.default_rng(0)
        a = rng.normal(size=(30, 2))
        b = rng.normal(size=(35, 2))
        d_ab = dtw_kt_distance(a, b)
        d_ba = dtw_kt_distance(b, a)
        assert abs(d_ab - d_ba) < 1e-9

    def test_shifted_helix_descriptors_are_close(self):
        # A helix shifted in time / cropped at different boundaries
        # should warp onto itself with a SMALL DTW distance.
        theta = np.linspace(0, 6 * np.pi, 400)
        r, c = 1.0, 0.3
        helix = np.stack([r * np.cos(theta), r * np.sin(theta), c * theta], axis=1)
        a = arc_length_resample(helix[:300], 100)
        b = arc_length_resample(helix[100:400], 100)
        ka, ta_ = frenet_descriptors(a, sigma=1.0)
        kb, tb = frenet_descriptors(b, sigma=1.0)
        kt_a = np.column_stack([ka, ta_])
        kt_b = np.column_stack([kb, tb])
        d_helix_helix = dtw_kt_distance(kt_a, kt_b)

        # Compare to a line of the same shape — distance should be
        # noticeably larger.
        line = np.stack([np.linspace(0, 1, 300), np.zeros(300), np.zeros(300)], axis=1)
        line_resampled = arc_length_resample(line, 100)
        kl, tl = frenet_descriptors(line_resampled, sigma=1.0)
        kt_l = np.column_stack([kl, tl])
        d_helix_line = dtw_kt_distance(kt_a, kt_l)

        assert d_helix_helix < d_helix_line, (
            f"Helix-helix DTW ({d_helix_helix:.4f}) should be less than "
            f"helix-line DTW ({d_helix_line:.4f})"
        )

    def test_bad_shape_raises(self):
        with pytest.raises(ValueError, match=r"\(N, 2\)"):
            dtw_kt_distance(np.zeros((10, 3)), np.zeros((10, 2)))

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            dtw_kt_distance(np.zeros((0, 2)), np.zeros((5, 2)))

    def test_sakoe_chiba_band_changes_value(self):
        # A tight band can ONLY equal or exceed the unconstrained DTW
        # (it forbids paths the unconstrained version may have used).
        rng = np.random.default_rng(1)
        a = rng.normal(size=(40, 2))
        b = rng.normal(size=(40, 2))
        d_unconstrained = dtw_kt_distance(a, b)
        d_band = dtw_kt_distance(a, b, sakoe_chiba_radius=2)
        # Constrained >= unconstrained, with equality possible if the
        # optimal path was already inside the band.
        assert d_band >= d_unconstrained - 1e-9
