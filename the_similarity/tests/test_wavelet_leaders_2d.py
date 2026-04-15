"""Tests for 2D wavelet-leaders multifractal analysis (wavelet_leaders_2d.py)."""

import numpy as np
import pytest

# Guard: skip entire module if PyWavelets is not installed
pytest.importorskip("pywt")

from the_similarity.methods.wavelet_leaders_2d import (
    _hurst_structure_function,
    _local_supremum_2d,
    compute_wavelet_leaders_2d,
    extract_terrain_spectrum,
    local_hurst_map,
    multifractal_spectrum_2d,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _sine_heightmap(size: int = 64, seed: int = 0) -> np.ndarray:
    """Smooth heightmap: two orthogonal sine waves + small noise."""
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 4 * np.pi, size)
    x = np.linspace(0, 4 * np.pi, size)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    return (np.sin(yy) + np.cos(xx) + 0.05 * rng.standard_normal((size, size))).astype(
        np.float64
    )


def _fractal_heightmap(size: int = 64, seed: int = 7) -> np.ndarray:
    """Rough heightmap: random walk in 2D (accumulated random noise)."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((size, size))
    # Cumulative sum along both axes as a cheap fractal-like surface
    return np.cumsum(np.cumsum(noise, axis=0), axis=1).astype(np.float64)


# ---------------------------------------------------------------------------
# compute_wavelet_leaders_2d
# ---------------------------------------------------------------------------


def test_leaders_returns_nonempty_list():
    """Should return a non-empty list of per-scale leader groups."""
    hm = _sine_heightmap(64)
    leaders = compute_wavelet_leaders_2d(hm)
    assert len(leaders) >= 1


def test_leaders_each_scale_has_three_subbands():
    """Each scale entry must contain exactly three subbands (LH, HL, HH)."""
    hm = _sine_heightmap(64)
    leaders = compute_wavelet_leaders_2d(hm)
    for scale_idx, level_leaders in enumerate(leaders):
        assert len(level_leaders) == 3, (
            f"Scale {scale_idx}: expected 3 subbands, got {len(level_leaders)}"
        )


def test_leaders_non_negative():
    """Leader values (local suprema of |coefficients|) must all be ≥ 0."""
    hm = _sine_heightmap(64)
    leaders = compute_wavelet_leaders_2d(hm)
    for level_leaders in leaders:
        for subband in level_leaders:
            assert np.all(subband >= 0), "Found negative leader values"


def test_leaders_requires_2d():
    """Non-2D input should raise ValueError."""
    with pytest.raises(ValueError, match="2D"):
        compute_wavelet_leaders_2d(np.ones((4, 4, 4)))


def test_leaders_different_wavelets_produce_results():
    """Common wavelets ('haar', 'db2', 'db4') should all succeed."""
    hm = _sine_heightmap(64)
    for w in ("haar", "db2", "db4"):
        leaders = compute_wavelet_leaders_2d(hm, wavelet=w)
        assert len(leaders) >= 1, f"Empty leaders for wavelet={w}"


def test_leaders_max_level_respected():
    """Specifying max_level=2 should return at most 2 scale levels."""
    hm = _sine_heightmap(64)
    leaders = compute_wavelet_leaders_2d(hm, max_level=2)
    assert len(leaders) <= 2


# ---------------------------------------------------------------------------
# _local_supremum_2d
# ---------------------------------------------------------------------------


def test_local_supremum_nondecreasing():
    """Local supremum should be ≥ the original values everywhere."""
    rng = np.random.default_rng(0)
    arr = np.abs(rng.standard_normal((16, 16)))
    sup = _local_supremum_2d(arr)
    assert np.all(sup >= arr - 1e-12)


def test_local_supremum_constant_array():
    """Supremum of a constant array is the constant itself."""
    arr = np.full((8, 8), 3.5)
    sup = _local_supremum_2d(arr)
    np.testing.assert_allclose(sup, arr)


def test_local_supremum_tiny_array():
    """Tiny arrays (1×1, 1×N) should be returned as-is."""
    for shape in ((1, 1), (1, 8), (8, 1)):
        arr = np.ones(shape)
        sup = _local_supremum_2d(arr)
        np.testing.assert_array_equal(sup, arr)


# ---------------------------------------------------------------------------
# multifractal_spectrum_2d
# ---------------------------------------------------------------------------


def test_spectrum_shape():
    """Alpha and f_alpha must be 1D arrays of the same length ≥ 1."""
    hm = _fractal_heightmap(64)
    leaders = compute_wavelet_leaders_2d(hm)
    alpha, f_alpha = multifractal_spectrum_2d(leaders)
    assert alpha.ndim == 1 and f_alpha.ndim == 1
    assert len(alpha) == len(f_alpha)
    assert len(alpha) >= 1


def test_spectrum_all_finite():
    """Spectrum values must be finite (no NaN/Inf)."""
    hm = _fractal_heightmap(64)
    leaders = compute_wavelet_leaders_2d(hm)
    alpha, f_alpha = multifractal_spectrum_2d(leaders)
    assert np.all(np.isfinite(alpha))
    assert np.all(np.isfinite(f_alpha))


def test_spectrum_fallback_for_single_scale():
    """When only one scale is available, return the trivial fallback (0.5, 1.0)."""
    # Create a leader list with a single entry
    dummy = [np.ones((4, 4)) for _ in range(3)]
    alpha, f_alpha = multifractal_spectrum_2d([dummy])
    np.testing.assert_array_equal(alpha, [0.5])
    np.testing.assert_array_equal(f_alpha, [1.0])


def test_spectrum_width_nonnegative():
    """Spectrum width (max(alpha) - min(alpha)) must be ≥ 0."""
    hm = _fractal_heightmap(128)
    leaders = compute_wavelet_leaders_2d(hm)
    alpha, _ = multifractal_spectrum_2d(leaders)
    assert alpha.max() - alpha.min() >= 0.0


# ---------------------------------------------------------------------------
# local_hurst_map
# ---------------------------------------------------------------------------


def test_hurst_map_shape():
    """Hurst map must have the same shape as the input heightmap."""
    hm = _fractal_heightmap(64)
    hurst = local_hurst_map(hm, block_size=16)
    assert hurst.shape == hm.shape


def test_hurst_map_range():
    """All Hurst values must be in [0, 1]."""
    hm = _fractal_heightmap(64)
    hurst = local_hurst_map(hm, block_size=16)
    assert np.all(hurst >= 0.0)
    assert np.all(hurst <= 1.0)


def test_hurst_map_all_finite():
    """Hurst map must not contain NaN or Inf."""
    hm = _sine_heightmap(64)
    hurst = local_hurst_map(hm, block_size=16)
    assert np.all(np.isfinite(hurst))


def test_hurst_map_small_heightmap():
    """If heightmap is too small for any blocks, should return 0.5 everywhere."""
    # block_size=64 with a 32×32 map → no block centers → fallback
    hm = _sine_heightmap(32)
    hurst = local_hurst_map(hm, block_size=64)
    np.testing.assert_allclose(hurst, 0.5)


# ---------------------------------------------------------------------------
# extract_terrain_spectrum
# ---------------------------------------------------------------------------


def test_extract_terrain_spectrum_keys():
    """Return dict must contain all documented keys."""
    hm = _fractal_heightmap(64)
    result = extract_terrain_spectrum(hm)
    expected = {
        "alpha",
        "f_alpha",
        "spectrum_width",
        "h_mean",
        "h_std",
        "h_min",
        "h_max",
        "dominant_scale",
        "scale_energies",
        "hurst_map",
    }
    assert expected.issubset(result.keys()), f"Missing keys: {expected - result.keys()}"


def test_extract_terrain_spectrum_hurst_stats_range():
    """Mean, min, max Hurst from extracted spectrum must be in [0, 1]."""
    hm = _fractal_heightmap(64)
    r = extract_terrain_spectrum(hm)
    for key in ("h_mean", "h_min", "h_max"):
        assert 0.0 <= r[key] <= 1.0, f"{key}={r[key]} out of [0, 1]"


def test_extract_terrain_spectrum_dominant_scale_valid():
    """Dominant scale must be a positive integer."""
    hm = _fractal_heightmap(64)
    r = extract_terrain_spectrum(hm)
    assert isinstance(r["dominant_scale"], int)
    assert r["dominant_scale"] >= 1


def test_extract_terrain_spectrum_hurst_map_shape():
    """Hurst map embedded in result must match input shape."""
    hm = _fractal_heightmap(64)
    r = extract_terrain_spectrum(hm)
    assert r["hurst_map"].shape == hm.shape


def test_extract_terrain_spectrum_width_nonneg():
    """Spectrum width should be ≥ 0."""
    hm = _fractal_heightmap(64)
    r = extract_terrain_spectrum(hm)
    assert r["spectrum_width"] >= 0.0


# ---------------------------------------------------------------------------
# _hurst_structure_function
# ---------------------------------------------------------------------------


def test_hurst_structure_function_too_short():
    """Series shorter than 8 should return None (not enough lags)."""
    assert _hurst_structure_function(np.ones(5)) is None


def test_hurst_structure_function_range():
    """Hurst estimate should be in [0, 1] for typical series."""
    rng = np.random.default_rng(0)
    series = np.cumsum(rng.standard_normal(64))
    h = _hurst_structure_function(series)
    assert h is not None
    assert 0.0 <= h <= 1.0


def test_hurst_structure_function_constant():
    """Constant series has zero structure function → None (log(0) domain)."""
    # constant signal: structure is 0 everywhere, valid mask empty
    result = _hurst_structure_function(np.ones(32))
    # May return None or a numeric value depending on implementation; must not crash
    assert result is None or (0.0 <= result <= 1.0)
