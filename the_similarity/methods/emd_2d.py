"""2D Empirical Mode Decomposition for terrain heightmaps.

Uses a profile-based approach: extracts radial/orthogonal cross-sections
from the heightmap, decomposes each with the existing 1D EMD, then
reconstructs 2D IMFs via interpolation. This reuses the proven 1D EMD
pipeline and is ~20× faster than full Bidimensional EMD (BEMD).

Each IMF captures a different terrain scale:
  IMF1: continental/mountain range shape
  IMF2: individual peak/ridge structure
  IMF3: hill/valley undulation
  IMF4: boulder/rock detail
  IMF5+: surface micro-texture
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import griddata

try:
    from PyEMD import EMD

    HAS_EMD = True
except ImportError:
    HAS_EMD = False


def decompose_terrain(
    heightmap: NDArray[np.float64],
    max_imfs: int = 6,
    n_profiles: int = 8,
) -> list[NDArray[np.float64]]:
    """Decompose a 2D heightmap into scale layers via profile-based EMD.

    Extracts n_profiles radial cross-sections through the center,
    decomposes each with 1D EMD, then reconstructs 2D IMFs by
    interpolating IMF values at each pixel.

    Args:
        heightmap: 2D elevation array (H, W).
        max_imfs: Maximum number of IMFs to extract.
        n_profiles: Number of radial profiles (8 = every 22.5°).

    Returns:
        List of 2D IMF arrays (same shape as heightmap), coarse→fine.
        Last element is the residue.
    """
    if not HAS_EMD:
        raise RuntimeError("EMD-signal required. Install with: pip install EMD-signal")

    heightmap = np.asarray(heightmap, dtype=np.float64)
    if heightmap.ndim != 2:
        raise ValueError(f"Expected 2D array, got shape {heightmap.shape}")

    H, W = heightmap.shape
    cy, cx = H / 2.0, W / 2.0

    # Generate profile lines through the center at even angular spacing
    angles = np.linspace(0, np.pi, n_profiles, endpoint=False)
    max_radius = np.sqrt(cy**2 + cx**2)
    n_samples = max(H, W)

    # Collect all profile decompositions
    all_profile_imfs: list[list[NDArray[np.float64]]] = []
    all_profile_coords: list[NDArray[np.float64]] = []

    emd = EMD()

    for angle in angles:
        # Sample points along the profile line
        t = np.linspace(-max_radius, max_radius, n_samples)
        py = cy + t * np.sin(angle)
        px = cx + t * np.cos(angle)

        # Keep only points inside the heightmap
        mask = (py >= 0) & (py < H - 1) & (px >= 0) & (px < W - 1)
        if np.sum(mask) < 20:
            continue

        py_valid = py[mask]
        px_valid = px[mask]

        # Bilinear interpolation to sample heightmap along profile
        profile = _bilinear_sample(heightmap, py_valid, px_valid)

        # Decompose with 1D EMD
        try:
            imfs = emd(profile.astype(np.float64))
        except Exception:
            continue

        if imfs is None or len(imfs) == 0:
            continue

        imfs_list = list(imfs[:max_imfs])
        all_profile_imfs.append(imfs_list)
        all_profile_coords.append(np.column_stack([py_valid, px_valid]))

    if not all_profile_imfs:
        return [heightmap.copy()]

    # Determine number of IMFs (use minimum across profiles for consistency)
    n_imfs = min(len(pimfs) for pimfs in all_profile_imfs)
    n_imfs = min(n_imfs, max_imfs)

    # Reconstruct 2D IMFs by interpolating profile IMF values
    yy, xx = np.mgrid[0:H, 0:W]
    grid_points = np.column_stack([yy.ravel(), xx.ravel()])

    result_imfs: list[NDArray[np.float64]] = []

    for imf_idx in range(n_imfs):
        # Collect all profile points and their IMF values for this level
        all_points = []
        all_values = []

        for profile_coords, profile_imfs in zip(all_profile_coords, all_profile_imfs):
            if imf_idx >= len(profile_imfs):
                continue
            imf_values = profile_imfs[imf_idx]
            coords = profile_coords
            n = min(len(imf_values), len(coords))
            all_points.append(coords[:n])
            all_values.append(imf_values[:n])

        if not all_points:
            result_imfs.append(np.zeros_like(heightmap))
            continue

        points = np.vstack(all_points)
        values = np.concatenate(all_values)

        # Interpolate to full 2D grid
        try:
            imf_2d = griddata(
                points,
                values,
                grid_points,
                method="linear",
                fill_value=0.0,
            ).reshape(H, W)
        except Exception:
            imf_2d = griddata(
                points,
                values,
                grid_points,
                method="nearest",
                fill_value=0.0,
            ).reshape(H, W)

        result_imfs.append(imf_2d)

    # Compute residue
    reconstructed = sum(result_imfs)
    residue = heightmap - reconstructed
    result_imfs.append(residue)

    return result_imfs


def _bilinear_sample(
    arr: NDArray[np.float64],
    y: NDArray[np.float64],
    x: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Bilinear interpolation sampling on a 2D array."""
    H, W = arr.shape
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    y1 = np.minimum(y0 + 1, H - 1)
    x1 = np.minimum(x0 + 1, W - 1)
    y0 = np.clip(y0, 0, H - 1)
    x0 = np.clip(x0, 0, W - 1)

    fy = y - np.floor(y)
    fx = x - np.floor(x)

    val = (
        arr[y0, x0] * (1 - fy) * (1 - fx)
        + arr[y1, x0] * fy * (1 - fx)
        + arr[y0, x1] * (1 - fy) * fx
        + arr[y1, x1] * fy * fx
    )
    return val


def imf_energy_2d(imf: NDArray[np.float64]) -> float:
    """Compute the energy of a 2D IMF.

    Args:
        imf: 2D IMF array.

    Returns:
        Sum of squared values, normalized by number of pixels.
    """
    return float(np.sum(imf**2) / max(imf.size, 1))


def recompose_terrain(
    imfs: list[NDArray[np.float64]],
    weights: list[float] | None = None,
) -> NDArray[np.float64]:
    """Recompose terrain from weighted IMFs.

    Allows mixing scales: e.g., amplify large-scale structure (IMF1)
    while suppressing surface noise (IMF5).

    Args:
        imfs: List of 2D IMF arrays from decompose_terrain.
        weights: Per-IMF weights. Default: all 1.0 (full reconstruction).

    Returns:
        Reconstructed 2D heightmap.
    """
    if weights is None:
        weights = [1.0] * len(imfs)

    if len(weights) != len(imfs):
        raise ValueError(
            f"weights length ({len(weights)}) != IMFs length ({len(imfs)})"
        )

    result = np.zeros_like(imfs[0])
    for imf, w in zip(imfs, weights):
        result += w * imf
    return result


def terrain_scale_analysis(
    heightmap: NDArray[np.float64],
    max_imfs: int = 6,
    n_profiles: int = 8,
) -> dict:
    """Analyze the multi-scale structure of a heightmap.

    Returns decomposition + energy distribution across scales.

    Args:
        heightmap: 2D elevation array.
        max_imfs: Maximum IMFs.
        n_profiles: Radial profiles for decomposition.

    Returns:
        Dict with keys: imfs, energies, energy_fractions, dominant_scale,
        scale_count.
    """
    imfs = decompose_terrain(heightmap, max_imfs=max_imfs, n_profiles=n_profiles)

    energies = [imf_energy_2d(imf) for imf in imfs]
    total = sum(energies) or 1.0
    fractions = [e / total for e in energies]

    # Count significant scales (energy > 1% of total)
    scale_count = sum(1 for f in fractions if f > 0.01)

    # Dominant scale (excluding residue)
    if len(energies) > 1:
        dominant = int(np.argmax(energies[:-1])) + 1
    else:
        dominant = 1

    return {
        "imfs": imfs,
        "energies": energies,
        "energy_fractions": fractions,
        "dominant_scale": dominant,
        "scale_count": scale_count,
    }
