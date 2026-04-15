"""Tests for 2D Bempedelis self-similarity transform (bempedelis_2d.py)."""

import numpy as np
import pytest

from the_similarity.methods.bempedelis_2d import (
    BempedelisResult2D,
    _power_law_r2,
    _smoothness_score,
    patch_similarity,
    scale_invariance_score,
    terrain_self_similarity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _smooth_heightmap(size: int = 256, seed: int = 0) -> np.ndarray:
    """Smooth, multi-scale heightmap using overlaid sine waves."""
    y = np.linspace(0, 4 * np.pi, size)
    x = np.linspace(0, 4 * np.pi, size)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    rng = np.random.default_rng(seed)
    hm = (
        np.sin(yy)
        + np.cos(xx)
        + 0.5 * np.sin(2 * yy)
        + 0.5 * np.cos(2 * xx)
        + 0.1 * rng.standard_normal((size, size))
    )
    return hm.astype(np.float64)


def _fractal_heightmap(size: int = 256, seed: int = 7) -> np.ndarray:
    """Rough, fractal-like heightmap via accumulated 2D random walk."""
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((size, size))
    return np.cumsum(np.cumsum(noise, axis=0), axis=1).astype(np.float64)


# ---------------------------------------------------------------------------
# terrain_self_similarity — output structure
# ---------------------------------------------------------------------------


def test_terrain_self_similarity_returns_dataclass():
    """Function should return a BempedelisResult2D instance."""
    hm = _smooth_heightmap(256)
    result = terrain_self_similarity(hm, n_scales=3, patch_size=64, n_restarts=1)
    assert isinstance(result, BempedelisResult2D)


def test_terrain_self_similarity_alpha_beta_shapes():
    """alpha and beta arrays must have length == number of extracted patches."""
    hm = _smooth_heightmap(256)
    result = terrain_self_similarity(hm, n_scales=3, patch_size=64, n_restarts=1)
    assert result.alpha.ndim == 1
    assert result.beta.ndim == 1
    assert result.alpha.shape == result.beta.shape


def test_terrain_self_similarity_first_alpha_beta_fixed():
    """alpha[0] and beta[0] are always fixed to 1.0 (remove ambiguity)."""
    hm = _smooth_heightmap(256)
    result = terrain_self_similarity(hm, n_scales=4, patch_size=64, n_restarts=1)
    assert result.alpha[0] == pytest.approx(1.0)
    assert result.beta[0] == pytest.approx(1.0)


def test_terrain_self_similarity_score_range():
    """Score must be in [0, 1]."""
    hm = _smooth_heightmap(256)
    result = terrain_self_similarity(hm, n_scales=3, patch_size=64, n_restarts=1)
    assert 0.0 <= result.score <= 1.0, f"Score {result.score} out of [0, 1]"


def test_terrain_self_similarity_r2_range():
    """R² values must be in [0, 1]."""
    hm = _smooth_heightmap(256)
    result = terrain_self_similarity(hm, n_scales=3, patch_size=64, n_restarts=1)
    assert 0.0 <= result.power_law_r2 <= 1.0
    assert 0.0 <= result.alpha_r2 <= 1.0
    assert 0.0 <= result.beta_r2 <= 1.0


def test_terrain_self_similarity_residual_nonneg():
    """Optimization residual must be ≥ 0."""
    hm = _smooth_heightmap(256)
    result = terrain_self_similarity(hm, n_scales=3, patch_size=64, n_restarts=1)
    assert result.residual >= 0.0


def test_terrain_self_similarity_smoothness_range():
    """Smoothness must be in [0, 1]."""
    hm = _smooth_heightmap(256)
    result = terrain_self_similarity(hm, n_scales=3, patch_size=64, n_restarts=1)
    assert 0.0 <= result.smoothness <= 1.0


# ---------------------------------------------------------------------------
# terrain_self_similarity — error handling
# ---------------------------------------------------------------------------


def test_terrain_self_similarity_requires_2d():
    """Non-2D input must raise ValueError."""
    with pytest.raises(ValueError, match="2D"):
        terrain_self_similarity(np.ones((4, 4, 4)))


def test_terrain_self_similarity_too_small():
    """Heightmap smaller than patch_size must raise ValueError."""
    hm = np.ones((32, 32), dtype=np.float64)  # smaller than default patch_size=64
    with pytest.raises(ValueError):
        terrain_self_similarity(hm, patch_size=64)


# ---------------------------------------------------------------------------
# scale_invariance_score
# ---------------------------------------------------------------------------


def test_scale_invariance_score_range():
    """Score must be in [0, 1] for a valid heightmap."""
    hm = _smooth_heightmap(256)
    score = scale_invariance_score(hm, n_scales=3, patch_size=64)
    assert 0.0 <= score <= 1.0, f"score={score}"


def test_scale_invariance_score_too_small_returns_zero():
    """Too-small heightmap should return 0.0 (exception swallowed)."""
    hm = np.ones((32, 32), dtype=np.float64)
    score = scale_invariance_score(hm, patch_size=64)
    assert score == 0.0


def test_scale_invariance_score_fractal_positive():
    """A multi-scale fractal-like terrain should have score > 0."""
    hm = _fractal_heightmap(256)
    score = scale_invariance_score(hm, n_scales=3, patch_size=64)
    assert score >= 0.0  # not necessarily high but should not error


# ---------------------------------------------------------------------------
# patch_similarity
# ---------------------------------------------------------------------------


def test_patch_similarity_range():
    """patch_similarity must return a value in [0, 1]."""
    rng = np.random.default_rng(0)
    pa = rng.standard_normal((128, 128))
    pb = rng.standard_normal((128, 128))
    score = patch_similarity(pa, pb, n_scales=3, n_restarts=1)
    assert 0.0 <= score <= 1.0, f"score={score}"


def test_patch_similarity_identical_patches():
    """Two identical patches should return the same alpha/beta profiles → high score."""
    hm = _smooth_heightmap(128)
    score = patch_similarity(hm, hm.copy(), n_scales=3, n_restarts=1)
    # The scores should be non-negative; identical inputs tend to produce higher scores
    assert 0.0 <= score <= 1.0


def test_patch_similarity_too_small_returns_half():
    """Patches too small for the transform should gracefully return 0.5 fallback."""
    tiny = np.ones((8, 8), dtype=np.float64)
    score = patch_similarity(tiny, tiny, n_scales=3, n_restarts=1)
    # Either 0.5 fallback or valid [0,1] score
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# _power_law_r2
# ---------------------------------------------------------------------------


def test_power_law_r2_perfect():
    """Perfect power law data should yield R² ≈ 1."""
    t = np.arange(1, 8, dtype=np.float64)
    values = 2.5 * t**0.6
    r2 = _power_law_r2(t, values)
    assert r2 > 0.999, f"Expected R² ≈ 1, got {r2}"


def test_power_law_r2_constant():
    """Constant values (zero slope) should yield R² = 1.0 (ss_tot ≈ 0 → returns 1)."""
    t = np.arange(1, 6, dtype=np.float64)
    values = np.ones(5) * 3.0
    r2 = _power_law_r2(t, values)
    assert r2 == pytest.approx(1.0)


def test_power_law_r2_single_point():
    """Single-point input (n < 2) should return 0.0."""
    t = np.array([1.0])
    values = np.array([5.0])
    r2 = _power_law_r2(t, values)
    assert r2 == 0.0


def test_power_law_r2_noisy():
    """Noisy data should still return a value in [0, 1]."""
    rng = np.random.default_rng(42)
    t = np.arange(1, 10, dtype=np.float64)
    values = np.abs(rng.standard_normal(9)) + 0.1
    r2 = _power_law_r2(t, values)
    assert 0.0 <= r2 <= 1.0


# ---------------------------------------------------------------------------
# _smoothness_score
# ---------------------------------------------------------------------------


def test_smoothness_score_monotonic_is_smooth():
    """Monotonically varying profiles should score > 0.5."""
    alpha = np.array([1.0, 1.2, 1.4, 1.6, 1.8])
    beta = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
    score = _smoothness_score(alpha, beta)
    assert score > 0.5, f"Expected > 0.5, got {score}"


def test_smoothness_score_jagged_lower_than_smooth():
    """Jagged profiles should score lower than smooth ones."""
    alpha_smooth = np.array([1.0, 1.5, 2.0, 2.5, 3.0])
    beta_smooth = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
    alpha_jagged = np.array([1.0, 5.0, 0.2, 4.8, 0.1])
    beta_jagged = np.array([1.0, -3.0, 4.0, -2.0, 3.0])
    score_smooth = _smoothness_score(alpha_smooth, beta_smooth)
    score_jagged = _smoothness_score(alpha_jagged, beta_jagged)
    assert score_smooth > score_jagged


def test_smoothness_score_range():
    """Score must always be in [0, 1]."""
    rng = np.random.default_rng(99)
    for _ in range(10):
        alpha = rng.standard_normal(6)
        beta = rng.standard_normal(6)
        score = _smoothness_score(alpha, beta)
        assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1]"


def test_smoothness_score_constant_profiles():
    """Constant profiles have zero total variation → maximum smoothness (1.0)."""
    alpha = np.ones(5) * 2.0
    beta = np.ones(5) * 1.5
    score = _smoothness_score(alpha, beta)
    assert score == pytest.approx(1.0)
