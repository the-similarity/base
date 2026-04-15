"""Hydraulic and thermal erosion simulation for terrain heightmaps.

Hydraulic erosion simulates rainfall: droplets flow downhill, pick up
sediment, and deposit it when they slow down. This carves rivers and
valleys naturally from the heightmap geometry.

Thermal erosion simulates rock collapse: when slope exceeds the talus
angle of repose, material slides downhill. This creates scree slopes
and softens sharp ridges.

Reference: Olsen (2004), "Realtime Procedural Terrain Generation."
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class ErosionParams:
    """Parameters for hydraulic erosion simulation."""

    inertia: float = 0.05  # droplet momentum preservation
    capacity: float = 4.0  # sediment carrying capacity multiplier
    deposition_rate: float = 0.3  # fraction of excess sediment deposited per step
    erosion_rate: float = 0.3  # fraction of capacity eroded per step
    evaporation_rate: float = 0.02  # water loss per step
    gravity: float = 4.0  # acceleration due to gravity
    min_slope: float = 0.01  # minimum slope for flow
    max_lifetime: int = 80  # max steps per droplet
    erosion_radius: int = 2  # radius of erosion/deposition brush


def hydraulic_erosion(
    heightmap: NDArray[np.float64],
    iterations: int = 50000,
    params: ErosionParams | None = None,
    seed: int = 42,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Simulate hydraulic erosion on a heightmap.

    Spawns rain droplets at random positions, simulates their flow
    downhill, eroding and depositing sediment along the way.

    Args:
        heightmap: 2D elevation array. Modified in-place and returned.
        iterations: Number of rain droplets to simulate.
        params: Erosion parameters. None = defaults.
        seed: RNG seed.

    Returns:
        (eroded_heightmap, moisture_map, flow_map)
        moisture_map: accumulated water at each pixel (for vegetation)
        flow_map: accumulated flow volume (for river detection)
    """
    if params is None:
        params = ErosionParams()

    heightmap = heightmap.copy().astype(np.float64)
    H, W = heightmap.shape
    rng = np.random.default_rng(seed)

    moisture = np.zeros((H, W), dtype=np.float64)
    flow = np.zeros((H, W), dtype=np.float64)

    for _ in range(iterations):
        # Spawn droplet at random position
        px = rng.uniform(1, W - 2)
        py = rng.uniform(1, H - 2)
        dir_x = 0.0
        dir_y = 0.0
        speed = 1.0
        water = 1.0
        sediment = 0.0

        for step in range(params.max_lifetime):
            ix = int(px)
            iy = int(py)

            if ix < 1 or ix >= W - 2 or iy < 1 or iy >= H - 2:
                break

            # Compute gradient via bilinear interpolation
            fx = px - ix
            fy = py - iy

            # Height at corners
            h00 = heightmap[iy, ix]
            h10 = heightmap[iy, ix + 1]
            h01 = heightmap[iy + 1, ix]
            h11 = heightmap[iy + 1, ix + 1]

            # Gradient
            grad_x = (h10 - h00) * (1 - fy) + (h11 - h01) * fy
            grad_y = (h01 - h00) * (1 - fx) + (h11 - h10) * fx

            # Update direction with inertia
            dir_x = dir_x * params.inertia - grad_x * (1 - params.inertia)
            dir_y = dir_y * params.inertia - grad_y * (1 - params.inertia)

            # Normalize direction
            dir_len = np.sqrt(dir_x**2 + dir_y**2)
            if dir_len < 1e-8:
                # Random direction if stuck
                angle = rng.uniform(0, 2 * np.pi)
                dir_x = np.cos(angle)
                dir_y = np.sin(angle)
                dir_len = 1.0
            else:
                dir_x /= dir_len
                dir_y /= dir_len

            # Move droplet
            new_px = px + dir_x
            new_py = py + dir_y

            new_ix = int(new_px)
            new_iy = int(new_py)
            if new_ix < 0 or new_ix >= W - 1 or new_iy < 0 or new_iy >= H - 1:
                break

            # Height difference
            new_h = _bilinear_height(heightmap, new_px, new_py, W, H)
            old_h = _bilinear_height(heightmap, px, py, W, H)
            delta_h = new_h - old_h

            # Sediment capacity
            capacity = max(-delta_h, params.min_slope) * speed * water * params.capacity

            if sediment > capacity or delta_h > 0:
                # Deposit
                deposit = (sediment - capacity) * params.deposition_rate
                if delta_h > 0:
                    deposit = min(sediment, delta_h)

                _apply_brush(heightmap, ix, iy, deposit, params.erosion_radius, H, W)
                sediment -= deposit
            else:
                # Erode
                erode = min(
                    (capacity - sediment) * params.erosion_rate,
                    -delta_h,
                )
                _apply_brush(heightmap, ix, iy, -erode, params.erosion_radius, H, W)
                sediment += erode

            # Track moisture and flow
            moisture[iy, ix] += water * 0.01
            flow[iy, ix] += water

            # Update droplet state
            speed = np.sqrt(max(speed**2 + delta_h * params.gravity, 0.01))
            water *= 1 - params.evaporation_rate
            px = new_px
            py = new_py

            if water < 0.01:
                break

    # Normalize flow for visualization
    flow_max = flow.max()
    if flow_max > 0:
        flow = flow / flow_max

    moisture_max = moisture.max()
    if moisture_max > 0:
        moisture = moisture / moisture_max

    return heightmap, moisture, flow


def thermal_erosion(
    heightmap: NDArray[np.float64],
    iterations: int = 30,
    talus_angle: float = 0.6,
) -> NDArray[np.float64]:
    """Simulate thermal erosion (material sliding on steep slopes).

    When the height difference between adjacent cells exceeds the
    talus threshold, material is redistributed downhill.

    Args:
        heightmap: 2D elevation array. Modified copy returned.
        iterations: Number of erosion passes.
        talus_angle: Maximum stable slope (height units per cell).

    Returns:
        Eroded heightmap.
    """
    heightmap = heightmap.copy().astype(np.float64)
    H, W = heightmap.shape

    for _ in range(iterations):
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            # Shifted view
            if dy < 0:
                src_y = slice(0, H - 1)
                dst_y = slice(1, H)
            elif dy > 0:
                src_y = slice(1, H)
                dst_y = slice(0, H - 1)
            else:
                src_y = slice(0, H)
                dst_y = slice(0, H)

            if dx < 0:
                src_x = slice(0, W - 1)
                dst_x = slice(1, W)
            elif dx > 0:
                src_x = slice(1, W)
                dst_x = slice(0, W - 1)
            else:
                src_x = slice(0, W)
                dst_x = slice(0, W)

            diff = heightmap[src_y, src_x] - heightmap[dst_y, dst_x]
            excess = np.maximum(diff - talus_angle, 0) * 0.5

            # Transfer half the excess
            if excess.max() > 0:
                heightmap[src_y, src_x] -= excess
                heightmap[dst_y, dst_x] += excess

    return heightmap


def flow_accumulation(heightmap: NDArray[np.float64]) -> NDArray[np.float64]:
    """Compute D8 flow accumulation for river network detection.

    Each cell's flow = 1 + sum of upstream flows.

    Args:
        heightmap: 2D elevation array.

    Returns:
        Flow accumulation map (higher = more upstream area = rivers).
    """
    H, W = heightmap.shape
    flow = np.ones((H, W), dtype=np.float64)

    # D8 neighbors
    dirs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    # Sort cells by elevation (descending) for single-pass accumulation
    flat_idx = np.argsort(heightmap.ravel())[::-1]

    for idx in flat_idx:
        y, x = divmod(idx, W)

        # Find steepest downhill neighbor
        best_drop = 0.0
        best_dy, best_dx = 0, 0

        for dy, dx in dirs:
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W:
                drop = heightmap[y, x] - heightmap[ny, nx]
                if drop > best_drop:
                    best_drop = drop
                    best_dy, best_dx = dy, dx

        if best_drop > 0:
            flow[y + best_dy, x + best_dx] += flow[y, x]

    return flow


def classify_water_bodies(
    flow_map: NDArray[np.float64],
    threshold: float = 0.1,
) -> NDArray[np.bool_]:
    """Identify rivers and lakes from flow accumulation.

    Args:
        flow_map: Normalized flow accumulation [0, 1].
        threshold: Flow threshold for water (0.1 = top 10%).

    Returns:
        Boolean mask where True = water.
    """
    return flow_map > threshold


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bilinear_height(
    heightmap: NDArray[np.float64], px: float, py: float, W: int, H: int
) -> float:
    """Bilinear interpolation of heightmap at (px, py)."""
    ix = int(px)
    iy = int(py)
    ix = max(0, min(ix, W - 2))
    iy = max(0, min(iy, H - 2))
    fx = px - ix
    fy = py - iy

    h00 = heightmap[iy, ix]
    h10 = heightmap[iy, ix + 1]
    h01 = heightmap[iy + 1, ix]
    h11 = heightmap[iy + 1, ix + 1]

    return (
        h00 * (1 - fx) * (1 - fy)
        + h10 * fx * (1 - fy)
        + h01 * (1 - fx) * fy
        + h11 * fx * fy
    )


def _apply_brush(
    heightmap: NDArray[np.float64],
    cx: int,
    cy: int,
    amount: float,
    radius: int,
    H: int,
    W: int,
) -> None:
    """Apply erosion/deposition with a circular brush.

    Uses a Gaussian-weighted kernel for smooth effect.
    """
    if radius <= 0:
        if 0 <= cy < H and 0 <= cx < W:
            heightmap[cy, cx] += amount
        return

    total_weight = 0.0
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            ny = cy + dy
            nx = cx + dx
            if 0 <= ny < H and 0 <= nx < W:
                dist2 = dx * dx + dy * dy
                if dist2 <= radius * radius:
                    weight = max(0, 1 - np.sqrt(dist2) / radius)
                    total_weight += weight

    if total_weight < 1e-8:
        return

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            ny = cy + dy
            nx = cx + dx
            if 0 <= ny < H and 0 <= nx < W:
                dist2 = dx * dx + dy * dy
                if dist2 <= radius * radius:
                    weight = max(0, 1 - np.sqrt(dist2) / radius)
                    heightmap[ny, nx] += amount * (weight / total_weight)
