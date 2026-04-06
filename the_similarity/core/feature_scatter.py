"""Biome-aware feature scattering for terrain.

Places trees, rocks, grass, and other features based on terrain
properties: elevation, slope, moisture, local Hurst exponent, and
biome classification. Uses Poisson disk sampling for natural spacing.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# Feature type constants
FEATURE_TREE_PINE = "tree_pine"
FEATURE_TREE_OAK = "tree_oak"
FEATURE_TREE_PALM = "tree_palm"
FEATURE_BUSH = "bush"
FEATURE_ROCK_SMALL = "rock_small"
FEATURE_ROCK_LARGE = "rock_large"
FEATURE_BOULDER = "boulder"
FEATURE_GRASS_PATCH = "grass_patch"
FEATURE_FLOWER = "flower"


def scatter_features(
    heightmap: NDArray[np.float64],
    hurst_map: NDArray[np.float64],
    moisture_map: NDArray[np.float64],
    biome_map: NDArray[np.int32],
    density: float = 1.0,
    seed: int = 42,
) -> list[dict]:
    """Scatter natural features across terrain based on properties.

    Placement rules:
      - Trees: smooth terrain (H > 0.4), not steep, adequate moisture
      - Rocks: rough terrain (H < 0.4), steep slopes
      - Grass: smooth + moderate moisture
      - Flowers: grass biome, high moisture

    Args:
        heightmap: 2D elevation [0, 1].
        hurst_map: 2D local Hurst exponent.
        moisture_map: 2D moisture [0, 1] from erosion.
        biome_map: 2D biome IDs.
        density: Overall density multiplier (0.0 = none, 1.0 = normal, 2.0 = dense).
        seed: RNG seed.

    Returns:
        List of feature dicts, each with:
          type, x, y, z, scale, rotation, variant
    """
    if density <= 0:
        return []

    H, W = heightmap.shape
    rng = np.random.default_rng(seed)

    # Compute slope
    dy, dx = np.gradient(heightmap)
    slope = np.sqrt(dx**2 + dy**2)

    features: list[dict] = []

    # Target counts based on density and terrain size
    area = H * W
    base_tree_count = int(area * 0.002 * density)
    base_rock_count = int(area * 0.001 * density)
    base_bush_count = int(area * 0.003 * density)
    base_grass_count = int(area * 0.004 * density)

    # --- Trees ---
    tree_candidates = _generate_candidates(
        base_tree_count, H, W, rng, min_spacing=3.0
    )
    for cx, cy in tree_candidates:
        ix, iy = int(cx), int(cy)
        if ix < 0 or ix >= W or iy < 0 or iy >= H:
            continue

        biome = biome_map[iy, ix]
        h_val = hurst_map[iy, ix]
        s_val = slope[iy, ix]
        m_val = moisture_map[iy, ix]
        elev = heightmap[iy, ix]

        # Trees need: forest/grass biome, low slope, moderate roughness
        if biome not in (2, 3):  # grass or forest
            continue
        if s_val > 0.12:  # too steep
            continue
        if h_val < 0.3:  # too rough (rocky)
            continue

        # Tree type based on elevation and moisture
        if elev > 0.6:
            tree_type = FEATURE_TREE_PINE
        elif m_val > 0.5:
            tree_type = FEATURE_TREE_OAK
        else:
            tree_type = FEATURE_TREE_PINE

        features.append(
            _make_feature(
                tree_type, cx, cy, elev, rng,
                base_scale=0.8 + 0.4 * m_val,  # bigger with more moisture
            )
        )

    # --- Rocks ---
    rock_candidates = _generate_candidates(
        base_rock_count, H, W, rng, min_spacing=2.0
    )
    for cx, cy in rock_candidates:
        ix, iy = int(cx), int(cy)
        if ix < 0 or ix >= W or iy < 0 or iy >= H:
            continue

        biome = biome_map[iy, ix]
        h_val = hurst_map[iy, ix]
        s_val = slope[iy, ix]
        elev = heightmap[iy, ix]

        # Rocks need: rock biome or rough terrain
        if biome == 0:  # not in water
            continue
        if h_val > 0.5 and s_val < 0.08:  # too smooth and flat
            continue

        # Rock size based on roughness
        if h_val < 0.25 or s_val > 0.2:
            rock_type = FEATURE_BOULDER
            base_scale = 1.2
        elif h_val < 0.4:
            rock_type = FEATURE_ROCK_LARGE
            base_scale = 0.8
        else:
            rock_type = FEATURE_ROCK_SMALL
            base_scale = 0.4

        features.append(
            _make_feature(rock_type, cx, cy, elev, rng, base_scale=base_scale)
        )

    # --- Bushes ---
    bush_candidates = _generate_candidates(
        base_bush_count, H, W, rng, min_spacing=2.0
    )
    for cx, cy in bush_candidates:
        ix, iy = int(cx), int(cy)
        if ix < 0 or ix >= W or iy < 0 or iy >= H:
            continue

        biome = biome_map[iy, ix]
        m_val = moisture_map[iy, ix]
        s_val = slope[iy, ix]

        if biome not in (2, 3):  # grass or forest only
            continue
        if s_val > 0.15:
            continue
        if m_val < 0.15:
            continue

        features.append(
            _make_feature(FEATURE_BUSH, cx, cy, heightmap[iy, ix], rng, base_scale=0.5)
        )

    # --- Grass patches ---
    grass_candidates = _generate_candidates(
        base_grass_count, H, W, rng, min_spacing=1.5
    )
    for cx, cy in grass_candidates:
        ix, iy = int(cx), int(cy)
        if ix < 0 or ix >= W or iy < 0 or iy >= H:
            continue

        biome = biome_map[iy, ix]
        s_val = slope[iy, ix]

        if biome not in (2, 3):
            continue
        if s_val > 0.1:
            continue

        ftype = FEATURE_FLOWER if moisture_map[iy, ix] > 0.6 else FEATURE_GRASS_PATCH
        features.append(
            _make_feature(ftype, cx, cy, heightmap[iy, ix], rng, base_scale=0.3)
        )

    return features


def _generate_candidates(
    count: int,
    H: int,
    W: int,
    rng: np.random.Generator,
    min_spacing: float = 2.0,
) -> list[tuple[float, float]]:
    """Generate candidate positions with approximate Poisson disk spacing.

    Uses a fast rejection-based approach: generate more candidates than
    needed, then thin based on minimum distance.
    """
    if count <= 0:
        return []

    # Generate 3× candidates, then thin
    n_raw = min(count * 3, H * W)
    xs = rng.uniform(0, W - 1, n_raw)
    ys = rng.uniform(0, H - 1, n_raw)

    # Simple grid-based thinning for O(n) performance
    cell_size = min_spacing
    grid: dict[tuple[int, int], bool] = {}
    result: list[tuple[float, float]] = []

    for x, y in zip(xs, ys):
        gx = int(x / cell_size)
        gy = int(y / cell_size)

        # Check if cell is occupied
        occupied = False
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if (gx + dx, gy + dy) in grid:
                    occupied = True
                    break
            if occupied:
                break

        if not occupied:
            grid[(gx, gy)] = True
            result.append((x, y))
            if len(result) >= count:
                break

    return result


def _make_feature(
    feature_type: str,
    x: float,
    y: float,
    z: float,
    rng: np.random.Generator,
    base_scale: float = 1.0,
) -> dict:
    """Create a feature dict with random variation."""
    return {
        "type": feature_type,
        "x": float(x),
        "y": float(y),
        "z": float(z),
        "scale": base_scale * rng.uniform(0.7, 1.3),
        "rotation": float(rng.uniform(0, 2 * np.pi)),
        "variant": int(rng.integers(0, 4)),
    }
