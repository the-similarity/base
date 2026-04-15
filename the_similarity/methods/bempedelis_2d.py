"""2D Bempedelis self-similarity transform for terrain patches.

Extends the 1D bempedelis.py to 2D heightfield patches. Asks: does this
terrain look the same at different scales? Real terrain should score high
because fractal geometry is scale-invariant.

Given a 2D heightmap, extracts patches at multiple scales (zoom levels),
then optimizes alpha(s), beta(s) to collapse them onto a common surface.
High R² = terrain has genuine self-similarity across scales.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.interpolate import RegularGridInterpolator


@dataclass
class BempedelisResult2D:
    """Result of 2D self-similarity transform."""

    alpha: NDArray[np.float64]  # spatial-scaling per scale, shape (n_scales,)
    beta: NDArray[np.float64]  # value-scaling per scale, shape (n_scales,)
    power_law_r2: float  # R² of power law fit to alpha, beta
    alpha_r2: float  # R² of power law fit to alpha alone
    beta_r2: float  # R² of power law fit to beta alone
    smoothness: float  # 1 - normalized total variation
    residual: float  # optimization residual
    score: float  # combined self-similarity score in [0, 1]


def terrain_self_similarity(
    heightmap: NDArray[np.float64],
    n_scales: int = 5,
    patch_size: int = 64,
    n_restarts: int = 3,
) -> BempedelisResult2D:
    """Compute self-similarity transform on a 2D heightmap.

    Extracts concentric patches of increasing size from the center,
    downsamples each to patch_size×patch_size, and optimizes alpha/beta
    to collapse them into a common surface.

    Args:
        heightmap: 2D elevation array (must be at least patch_size×n_scales).
        n_scales: Number of scale levels to extract.
        patch_size: Common size to resample each patch to.
        n_restarts: Optimization restarts.

    Returns:
        BempedelisResult2D with alpha, beta, R², smoothness, score.
    """
    heightmap = np.asarray(heightmap, dtype=np.float64)
    if heightmap.ndim != 2:
        raise ValueError(f"Expected 2D heightmap, got shape {heightmap.shape}")

    H, W = heightmap.shape
    min_dim = min(H, W)

    if min_dim < patch_size:
        raise ValueError(f"Heightmap too small ({H}×{W}) for patch_size={patch_size}")

    # Extract patches at increasing scales from center
    cy, cx = H // 2, W // 2
    patches = _extract_multiscale_patches(
        heightmap, cy, cx, n_scales, patch_size, min_dim
    )

    n_patches = len(patches)
    if n_patches < 2:
        return BempedelisResult2D(
            alpha=np.ones(1),
            beta=np.ones(1),
            power_law_r2=0.0,
            alpha_r2=0.0,
            beta_r2=0.0,
            smoothness=0.0,
            residual=float("inf"),
            score=0.0,
        )

    # Optimize: find alpha_k, beta_k for each scale
    # Fix alpha[0] = 1, beta[0] = 1 to remove ambiguity
    n_free = n_patches - 1
    n_params = 2 * n_free

    ref_grid = np.linspace(0, 1, patch_size)

    def objective(params: NDArray) -> float:
        alpha = np.empty(n_patches)
        beta = np.empty(n_patches)
        alpha[0] = 1.0
        beta[0] = 1.0
        alpha[1:] = params[:n_free]
        beta[1:] = params[n_free:]

        rescaled = _rescale_patches(patches, ref_grid, alpha, beta)
        return _pairwise_collapse_error_2d(rescaled)

    bounds = [(0.1, 10.0)] * n_free + [(-10.0, 10.0)] * n_free

    best_result = None
    best_cost = np.inf

    for restart in range(n_restarts):
        if restart == 0:
            x0 = np.ones(n_params)
        else:
            rng = np.random.default_rng(seed=restart)
            x0 = np.concatenate(
                [
                    rng.uniform(0.5, 2.0, n_free),
                    rng.uniform(0.5, 2.0, n_free),
                ]
            )

        result = minimize(
            objective,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 300, "ftol": 1e-9},
        )

        if result.fun < best_cost:
            best_cost = result.fun
            best_result = result

    # Extract best alpha, beta
    alpha = np.empty(n_patches)
    beta = np.empty(n_patches)
    alpha[0] = 1.0
    beta[0] = 1.0
    alpha[1:] = best_result.x[:n_free]
    beta[1:] = best_result.x[n_free:]

    # Score
    t = np.arange(1, n_patches + 1, dtype=np.float64)
    alpha_r2 = _power_law_r2(t, np.abs(alpha))
    beta_r2 = _power_law_r2(t, np.abs(beta))
    power_law_r2 = (alpha_r2 + beta_r2) / 2.0

    smoothness = _smoothness_score(alpha, beta)
    residual_score = float(np.exp(-best_cost))
    score = 0.5 * power_law_r2 + 0.3 * smoothness + 0.2 * residual_score

    return BempedelisResult2D(
        alpha=alpha,
        beta=beta,
        power_law_r2=power_law_r2,
        alpha_r2=alpha_r2,
        beta_r2=beta_r2,
        smoothness=smoothness,
        residual=best_cost,
        score=score,
    )


def patch_similarity(
    patch_a: NDArray[np.float64],
    patch_b: NDArray[np.float64],
    n_scales: int = 4,
    n_restarts: int = 2,
) -> float:
    """Compare two terrain patches via self-similarity.

    Runs the transform on each patch and compares their alpha/beta profiles.

    Args:
        patch_a: 2D patch.
        patch_b: 2D patch (can be different size).
        n_scales: Sub-scales to analyze within each patch.
        n_restarts: Optimization restarts.

    Returns:
        Similarity score in [0, 1].
    """
    patch_size = min(min(patch_a.shape), min(patch_b.shape), 64)

    try:
        result_a = terrain_self_similarity(
            patch_a, n_scales=n_scales, patch_size=patch_size, n_restarts=n_restarts
        )
        result_b = terrain_self_similarity(
            patch_b, n_scales=n_scales, patch_size=patch_size, n_restarts=n_restarts
        )
    except (ValueError, Exception):
        return 0.5

    # Compare alpha/beta profiles
    transform_sim = _transform_similarity_2d(result_a, result_b)
    r2_score = float(
        np.sqrt(max(0, result_a.power_law_r2) * max(0, result_b.power_law_r2))
        * transform_sim
    )

    return float(np.clip(r2_score, 0.0, 1.0))


def scale_invariance_score(
    heightmap: NDArray[np.float64],
    n_scales: int = 5,
    patch_size: int = 64,
) -> float:
    """Quick scalar: how fractal/self-similar is this terrain?

    Args:
        heightmap: 2D elevation array.
        n_scales: Number of scales to check.
        patch_size: Common patch size.

    Returns:
        Score in [0, 1] where 1 = perfectly self-similar across scales.
    """
    try:
        result = terrain_self_similarity(
            heightmap, n_scales=n_scales, patch_size=patch_size
        )
        return result.score
    except (ValueError, Exception):
        return 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_multiscale_patches(
    heightmap: NDArray[np.float64],
    cy: int,
    cx: int,
    n_scales: int,
    patch_size: int,
    min_dim: int,
) -> list[NDArray[np.float64]]:
    """Extract concentric patches at increasing scale, resample to common size."""
    H, W = heightmap.shape
    patches = []

    # Scale sizes: from patch_size to min_dim, log-spaced
    sizes = np.logspace(
        np.log2(patch_size),
        np.log2(min_dim * 0.9),
        n_scales,
        base=2,
    ).astype(int)
    sizes = np.unique(np.clip(sizes, patch_size, min_dim))

    for size in sizes:
        half = size // 2
        y0 = max(0, cy - half)
        y1 = min(H, cy + half)
        x0 = max(0, cx - half)
        x1 = min(W, cx + half)

        patch = heightmap[y0:y1, x0:x1]
        if patch.shape[0] < 4 or patch.shape[1] < 4:
            continue

        # Resample to common patch_size × patch_size
        resampled = _resample_patch(patch, patch_size)
        # Normalize to [0, 1]
        pmin, pmax = resampled.min(), resampled.max()
        if pmax - pmin > 1e-12:
            resampled = (resampled - pmin) / (pmax - pmin)
        patches.append(resampled)

    return patches


def _resample_patch(
    patch: NDArray[np.float64], target_size: int
) -> NDArray[np.float64]:
    """Resample a 2D patch to target_size × target_size."""
    h, w = patch.shape
    y_orig = np.linspace(0, 1, h)
    x_orig = np.linspace(0, 1, w)

    interp = RegularGridInterpolator(
        (y_orig, x_orig), patch, method="linear", bounds_error=False
    )

    y_new = np.linspace(0, 1, target_size)
    x_new = np.linspace(0, 1, target_size)
    yy, xx = np.meshgrid(y_new, x_new, indexing="ij")
    points = np.stack([yy.ravel(), xx.ravel()], axis=-1)

    return interp(points).reshape(target_size, target_size)


def _rescale_patches(
    patches: list[NDArray[np.float64]],
    ref_grid: NDArray[np.float64],
    alpha: NDArray[np.float64],
    beta: NDArray[np.float64],
) -> list[NDArray[np.float64]]:
    """Apply alpha/beta rescaling to each 2D patch."""
    rescaled = []
    for k, patch in enumerate(patches):
        size = patch.shape[0]
        grid = np.linspace(0, 1, size)

        s_query = np.clip(alpha[k] * ref_grid, 0, 1)
        interp = RegularGridInterpolator(
            (grid, grid), patch, method="linear", bounds_error=False, fill_value=0.0
        )

        yy, xx = np.meshgrid(s_query, s_query, indexing="ij")
        points = np.stack([yy.ravel(), xx.ravel()], axis=-1)
        rescaled_patch = beta[k] * interp(points).reshape(len(ref_grid), len(ref_grid))
        rescaled.append(rescaled_patch)

    return rescaled


def _pairwise_collapse_error_2d(patches: list[NDArray[np.float64]]) -> float:
    """Sum of squared pairwise differences between rescaled 2D patches."""
    n = len(patches)
    total = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            diff = patches[i] - patches[j]
            total += float(np.sum(diff**2))
    n_pairs = n * (n - 1) / 2
    n_pixels = patches[0].size
    return total / (n_pairs * n_pixels)


def _power_law_r2(t: NDArray[np.float64], values: NDArray[np.float64]) -> float:
    """R² of power law fit in log-log space."""
    v = np.maximum(np.abs(values), 1e-12)
    log_t = np.log(t)
    log_v = np.log(v)

    n = len(t)
    if n < 2:
        return 0.0

    mean_lt = np.mean(log_t)
    mean_lv = np.mean(log_v)
    ss_tot = np.sum((log_v - mean_lv) ** 2)
    if ss_tot < 1e-15:
        return 1.0

    ss_xy = np.sum((log_t - mean_lt) * (log_v - mean_lv))
    ss_xx = np.sum((log_t - mean_lt) ** 2)
    if ss_xx < 1e-15:
        return 0.0

    slope = ss_xy / ss_xx
    intercept = mean_lv - slope * mean_lt
    predicted = intercept + slope * log_t
    ss_res = np.sum((log_v - predicted) ** 2)

    r2 = 1.0 - ss_res / ss_tot
    return float(np.clip(r2, 0.0, 1.0))


def _smoothness_score(alpha: NDArray, beta: NDArray) -> float:
    """Score how smooth alpha(t) and beta(t) are."""

    def _tv(v: NDArray) -> float:
        if len(v) < 2:
            return 1.0
        tv = np.sum(np.abs(np.diff(v)))
        rng = np.max(np.abs(v)) - np.min(np.abs(v))
        if rng < 1e-12:
            return 1.0
        normalized = tv / (rng * (len(v) - 1))
        return float(np.clip(1.0 - normalized, 0.0, 1.0))

    return (_tv(alpha) + _tv(beta)) / 2.0


def _transform_similarity_2d(a: BempedelisResult2D, b: BempedelisResult2D) -> float:
    """Compare alpha/beta transform profiles between two results."""
    alpha_sim = _profile_sim(a.alpha, b.alpha)
    beta_sim = _profile_sim(np.abs(a.beta), np.abs(b.beta))
    return 0.5 * alpha_sim + 0.5 * beta_sim


def _profile_sim(left: NDArray, right: NDArray) -> float:
    """Similarity between two 1D profiles."""
    size = min(len(left), len(right))
    left = left[:size]
    right = right[:size]

    left_std = np.std(left)
    right_std = np.std(right)
    if left_std < 1e-12 or right_std < 1e-12:
        mse = float(np.mean((left - right) ** 2))
        return float(np.exp(-mse))

    left_n = (left - np.mean(left)) / left_std
    right_n = (right - np.mean(right)) / right_std
    corr = np.corrcoef(left_n, right_n)[0, 1]
    if np.isnan(corr):
        corr = 0.0
    mse = float(np.mean((left_n - right_n) ** 2))
    return 0.5 * max(0, (corr + 1) / 2) + 0.5 * float(np.exp(-mse))
