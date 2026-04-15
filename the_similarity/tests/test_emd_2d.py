"""Tests for 2D EMD terrain decomposition (emd_2d.py)."""

import numpy as np
import pytest

# Guard: skip entire module if PyEMD is not installed
pytest.importorskip("PyEMD")

from the_similarity.methods.emd_2d import (
    _bilinear_sample,
    decompose_terrain,
    imf_energy_2d,
    recompose_terrain,
    terrain_scale_analysis,
)


def _flat_heightmap(size: int = 64, seed: int = 0) -> np.ndarray:
    """Simple smooth heightmap: sum of two sine waves."""
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 2 * np.pi, size)
    x = np.linspace(0, 2 * np.pi, size)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    base = np.sin(yy) + np.cos(xx) + 0.1 * rng.standard_normal((size, size))
    return base.astype(np.float64)


def _random_heightmap(size: int = 64, seed: int = 42) -> np.ndarray:
    """Heightmap generated from a seeded RNG for reproducibility."""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((size, size))


# ---------------------------------------------------------------------------
# decompose_terrain
# ---------------------------------------------------------------------------


def test_decompose_terrain_returns_list_of_2d_arrays():
    """Output should be a non-empty list of 2D arrays matching heightmap shape."""
    hm = _flat_heightmap(64)
    imfs = decompose_terrain(hm, max_imfs=4, n_profiles=4)
    assert len(imfs) >= 1
    for imf in imfs:
        assert imf.shape == hm.shape, f"IMF shape {imf.shape} != heightmap {hm.shape}"


def test_decompose_terrain_dtype():
    """All returned IMFs should be float64."""
    hm = _flat_heightmap(64)
    imfs = decompose_terrain(hm, max_imfs=3, n_profiles=4)
    for imf in imfs:
        assert imf.dtype == np.float64


def test_decompose_terrain_requires_2d():
    """Non-2D input must raise ValueError."""
    with pytest.raises(ValueError, match="2D"):
        decompose_terrain(np.ones((4, 4, 4)))


def test_decompose_terrain_multiple_scales():
    """A multi-frequency heightmap should produce more than one IMF layer."""
    hm = _flat_heightmap(128)
    imfs = decompose_terrain(hm, max_imfs=6, n_profiles=8)
    # After decomposition + residue there should be ≥ 2 entries
    assert len(imfs) >= 2, f"Expected ≥ 2 layers, got {len(imfs)}"


def test_decompose_terrain_residue_finite():
    """Every IMF (including the residue) must contain only finite values."""
    hm = _flat_heightmap(64)
    imfs = decompose_terrain(hm, max_imfs=4, n_profiles=4)
    for i, imf in enumerate(imfs):
        assert np.all(np.isfinite(imf)), f"IMF {i} contains non-finite values"


# ---------------------------------------------------------------------------
# imf_energy_2d
# ---------------------------------------------------------------------------


def test_imf_energy_2d_positive():
    """Energy of a non-zero 2D array should be positive."""
    arr = np.ones((32, 32), dtype=np.float64)
    assert imf_energy_2d(arr) > 0.0


def test_imf_energy_2d_zero():
    """Energy of the zero array should be zero."""
    arr = np.zeros((16, 16), dtype=np.float64)
    assert imf_energy_2d(arr) == 0.0


def test_imf_energy_2d_normalized():
    """Energy is normalized by pixel count so a constant-1 field → energy 1.0."""
    arr = np.ones((10, 10), dtype=np.float64)
    assert imf_energy_2d(arr) == pytest.approx(1.0)


def test_imf_energy_2d_larger_amplitude():
    """Higher amplitude should produce higher energy."""
    low = np.ones((20, 20), dtype=np.float64)
    high = np.full((20, 20), 3.0, dtype=np.float64)
    assert imf_energy_2d(high) > imf_energy_2d(low)


# ---------------------------------------------------------------------------
# recompose_terrain
# ---------------------------------------------------------------------------


def test_recompose_terrain_default_weights_sums_imfs():
    """With default weights=1, recompose should equal the element-wise sum of IMFs."""
    hm = _flat_heightmap(64)
    imfs = decompose_terrain(hm, max_imfs=3, n_profiles=4)
    reconstructed = recompose_terrain(imfs)
    expected = sum(imfs)
    np.testing.assert_allclose(reconstructed, expected, atol=1e-12)


def test_recompose_terrain_zero_weights_gives_zeros():
    """Weights of all zero should produce a zero array."""
    hm = _flat_heightmap(64)
    imfs = decompose_terrain(hm, max_imfs=3, n_profiles=4)
    weights = [0.0] * len(imfs)
    result = recompose_terrain(imfs, weights)
    np.testing.assert_array_equal(result, np.zeros_like(imfs[0]))


def test_recompose_terrain_weights_length_mismatch():
    """Mismatched weights length should raise ValueError."""
    hm = _flat_heightmap(64)
    imfs = decompose_terrain(hm, max_imfs=3, n_profiles=4)
    with pytest.raises(ValueError, match="weights"):
        recompose_terrain(imfs, weights=[1.0])  # too short


def test_recompose_terrain_custom_weights():
    """Partial reconstruction: suppress some scales, amplify others."""
    hm = _flat_heightmap(64)
    imfs = decompose_terrain(hm, max_imfs=3, n_profiles=4)
    weights = [1.0 if i == 0 else 0.0 for i in range(len(imfs))]
    result = recompose_terrain(imfs, weights)
    # Should match the first IMF alone
    np.testing.assert_allclose(result, imfs[0], atol=1e-12)


# ---------------------------------------------------------------------------
# terrain_scale_analysis
# ---------------------------------------------------------------------------


def test_terrain_scale_analysis_keys():
    """Return dict must contain all expected keys."""
    hm = _flat_heightmap(64)
    result = terrain_scale_analysis(hm, max_imfs=4, n_profiles=4)
    expected_keys = {
        "imfs",
        "energies",
        "energy_fractions",
        "dominant_scale",
        "scale_count",
    }
    assert expected_keys.issubset(result.keys()), (
        f"Missing keys: {expected_keys - result.keys()}"
    )


def test_terrain_scale_analysis_energy_fractions_sum_to_one():
    """Energy fractions should sum to approximately 1.0."""
    hm = _flat_heightmap(64)
    result = terrain_scale_analysis(hm, max_imfs=4, n_profiles=4)
    total = sum(result["energy_fractions"])
    assert abs(total - 1.0) < 1e-10, f"Energy fractions sum to {total}, expected 1.0"


def test_terrain_scale_analysis_dominant_scale_valid():
    """Dominant scale must be a positive integer index."""
    hm = _flat_heightmap(64)
    result = terrain_scale_analysis(hm, max_imfs=4, n_profiles=4)
    assert isinstance(result["dominant_scale"], int)
    assert result["dominant_scale"] >= 1


def test_terrain_scale_analysis_imfs_shapes():
    """All IMF arrays in the result should match the input heightmap shape."""
    hm = _flat_heightmap(64)
    result = terrain_scale_analysis(hm, max_imfs=4, n_profiles=4)
    for imf in result["imfs"]:
        assert imf.shape == hm.shape


# ---------------------------------------------------------------------------
# _bilinear_sample
# ---------------------------------------------------------------------------


def test_bilinear_sample_at_integer_coords():
    """Bilinear sample at exact integer grid points should match the array values."""
    arr = np.arange(9, dtype=np.float64).reshape(3, 3)
    y = np.array([0.0, 1.0, 2.0])
    x = np.array([0.0, 1.0, 2.0])
    vals = _bilinear_sample(arr, y, x)
    expected = np.array([arr[0, 0], arr[1, 1], arr[2, 2]])
    np.testing.assert_allclose(vals, expected, atol=1e-12)


def test_bilinear_sample_midpoint():
    """Bilinear sample at midpoint of a 2×2 constant should return that constant."""
    arr = np.full((4, 4), 7.0, dtype=np.float64)
    y = np.array([1.5])
    x = np.array([1.5])
    vals = _bilinear_sample(arr, y, x)
    np.testing.assert_allclose(vals, [7.0], atol=1e-12)
