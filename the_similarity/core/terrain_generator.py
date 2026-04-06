"""Multi-scale terrain generation driven by TerrainParams.

Replaces uniform midpoint displacement with a pipeline that uses
fractal parameters (Hurst, multifractal width, IMF energies) to
generate terrain with spatially-varying roughness and realistic
multi-scale structure.

Pipeline:
  1. Spectral synthesis base (fBm with spatially-varying H)
  2. Ridge overlay (ridged multifractal, amplitude from IMF2)
  3. Detail injection (high-freq noise from multifractal width)
  4. Hydraulic + thermal erosion
  5. Biome classification
  6. Feature scattering
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from the_similarity.core.terrain_params import TerrainParams, get_preset


@dataclass
class GeneratedTerrain:
    """Output of the terrain generator."""

    heightmap: NDArray[np.float64]  # (H, W) normalized [0, 1]
    moisture_map: NDArray[np.float64]  # (H, W) [0, 1] from erosion
    flow_map: NDArray[np.float64]  # (H, W) water flow accumulation
    biome_map: NDArray[np.int32]  # (H, W) biome IDs
    hurst_map: NDArray[np.float64]  # (H, W) local Hurst used
    features: list[dict] = field(default_factory=list)
    params: TerrainParams | None = None
    seed: int = 42
    size: int = 256

    # Biome ID mapping
    BIOME_WATER: int = 0
    BIOME_SAND: int = 1
    BIOME_GRASS: int = 2
    BIOME_FOREST: int = 3
    BIOME_ROCK: int = 4
    BIOME_SNOW: int = 5


class TerrainGenerator:
    """Parameter-driven terrain generator using self-similarity analysis."""

    def __init__(self, params: TerrainParams | str = "alpine"):
        if isinstance(params, str):
            self.params = get_preset(params)
        else:
            self.params = params

    def generate(self, size: int = 256, seed: int = 42) -> GeneratedTerrain:
        """Generate terrain using the full pipeline.

        Args:
            size: Output heightmap dimensions (size × size).
            seed: RNG seed for reproducibility.

        Returns:
            GeneratedTerrain with heightmap, moisture, flow, biomes, features.
        """
        rng = np.random.default_rng(seed)
        p = self.params

        # 1. Generate spatially-varying Hurst map
        hurst_map = self._generate_hurst_map(size, rng)

        # Broad landform masks make the result feel more geologic and less like
        # "noise at every scale". Real terrain usually has wide basins, plains,
        # shelves, and only localized belts of strong uplift.
        continentalness = self._generate_continentalness(size, rng)
        uplift_mask = self._generate_uplift_mask(size, continentalness, rng)

        # 2. Base layer: fBm with varying roughness
        base = self._spectral_synthesis(size, hurst_map, rng)
        base = 0.55 * base + 0.45 * continentalness

        # 3. Ridge overlay for mountain ridges
        ridges = self._ridged_multifractal(size, rng)
        ridge_weight = p.imf_energies[1] if len(p.imf_energies) > 1 else 0.2
        ridge_weight *= np.clip(1.0 - 0.9 * p.h_mean, 0.15, 0.8)
        ridge_weight *= 0.15 + 0.85 * uplift_mask
        heightmap = base + ridge_weight * ridges

        # 4. Detail injection
        detail = self._fractal_detail(size, rng)
        detail_weight = p.spectrum_width * np.clip(1.0 - 0.75 * p.h_mean, 0.18, 0.8)
        detail_weight *= 0.06 + 0.14 * uplift_mask
        heightmap += detail_weight * detail

        # Favor broad lowlands and coast-like basins so mountains are a
        # minority landform instead of occupying almost the whole map.
        basin_mask = np.clip(1.0 - continentalness, 0.0, 1.0)
        heightmap -= basin_mask * (0.08 + 0.18 * p.water_level)

        # 5. Normalize to [0, 1]
        hmin, hmax = heightmap.min(), heightmap.max()
        if hmax - hmin > 1e-12:
            heightmap = (heightmap - hmin) / (hmax - hmin)
        else:
            heightmap = np.full((size, size), 0.5)

        # Hypsometric shaping:
        # Real terrain is not evenly distributed between sea level and summit.
        # Large areas tend to sit in lowlands or rolling uplands, while sharp
        # relief occupies a smaller fraction of the surface.
        lowland_bias = 1.25 + 1.2 * p.water_level
        heightmap = heightmap ** lowland_bias
        heightmap = 0.7 * heightmap + 0.3 * continentalness

        # 6. Apply elevation range scaling
        heightmap = heightmap * p.elevation_range

        # 7. Erosion — scale iterations to terrain area for interactive speed
        from the_similarity.core.erosion import hydraulic_erosion, thermal_erosion

        area_factor = (size / 256) ** 2  # 128×128 = 0.25× iterations
        erosion_iters = max(500, int(20000 * p.erosion_strength * area_factor))
        heightmap, moisture, flow = hydraulic_erosion(
            heightmap,
            iterations=erosion_iters,
            seed=seed,
        )
        heightmap = thermal_erosion(heightmap, iterations=max(5, int(20 * p.erosion_strength)))
        heightmap = self._relax_heightmap(
            heightmap,
            passes=max(1, int(round(2 + 2 * p.erosion_strength))),
            strength=0.18 if p.terrain_type == "alpine" else 0.24,
        )

        # 8. Renormalize
        hmin, hmax = heightmap.min(), heightmap.max()
        if hmax - hmin > 1e-12:
            heightmap = (heightmap - hmin) / (hmax - hmin)

        # 9. Biome classification
        biome_map = self._classify_biomes(heightmap, moisture, hurst_map)

        # 10. Feature scattering
        from the_similarity.core.feature_scatter import scatter_features

        features = scatter_features(
            heightmap, hurst_map, moisture, biome_map,
            density=p.vegetation_density,
            seed=seed,
        )

        return GeneratedTerrain(
            heightmap=heightmap,
            moisture_map=moisture,
            flow_map=flow,
            biome_map=biome_map,
            hurst_map=hurst_map,
            features=features,
            params=self.params,
            seed=seed,
            size=size,
        )

    def _generate_hurst_map(
        self, size: int, rng: np.random.Generator
    ) -> NDArray[np.float64]:
        """Generate a spatially-varying Hurst exponent map.

        Uses smooth Perlin-like noise to create regions of different roughness.
        Mountains (low H) vs meadows (high H) emerge from this.
        """
        p = self.params
        # Low-frequency noise for smooth spatial variation
        noise = self._smooth_noise(size, octaves=2, rng=rng)
        # Map noise [0,1] to Hurst range [h_min, h_max]
        hurst_map = p.h_min + noise * (p.h_max - p.h_min)
        return hurst_map

    def _generate_continentalness(
        self, size: int, rng: np.random.Generator
    ) -> NDArray[np.float64]:
        """Generate broad-scale land vs basin structure.

        This is our cheap stand-in for plate-scale organization. A low-frequency
        mask ensures the generator produces wide lowlands and coast-like regions
        before it adds local ridges and fine fractal detail.
        """
        raw = self._smooth_noise(size, octaves=1, rng=rng)
        continental = self._relax_heightmap(raw, passes=6, strength=0.35)
        cmin, cmax = continental.min(), continental.max()
        if cmax - cmin > 1e-12:
            continental = (continental - cmin) / (cmax - cmin)
        return continental

    def _generate_uplift_mask(
        self,
        size: int,
        continentalness: NDArray[np.float64],
        rng: np.random.Generator,
    ) -> NDArray[np.float64]:
        """Localize where strong mountain building is allowed to happen."""
        tectonic = self._smooth_noise(size, octaves=2, rng=rng)
        tectonic = self._relax_heightmap(tectonic, passes=3, strength=0.25)
        uplift = continentalness * tectonic
        uplift = np.clip((uplift - 0.35) / 0.65, 0.0, 1.0)
        return uplift

    def _spectral_synthesis(
        self,
        size: int,
        hurst_map: NDArray[np.float64],
        rng: np.random.Generator,
    ) -> NDArray[np.float64]:
        """Generate fBm-like noise with spatially-varying Hurst exponent.

        Uses the spectral synthesis method: generate random phases in
        frequency domain with amplitude ~ f^(-H-1), then blend multiple
        realizations weighted by the local Hurst value.
        """
        # Generate two basis fields: one with low H (rough), one with high H (smooth)
        h_low = max(0.1, self.params.h_min)
        h_high = min(0.95, self.params.h_max)

        field_rough = self._fbm_spectral(size, h_low, rng)
        field_smooth = self._fbm_spectral(size, h_high, rng)

        # Blend based on local Hurst: where H is low → use rough, where high → smooth
        h_norm = hurst_map - hurst_map.min()
        h_range = hurst_map.max() - hurst_map.min()
        if h_range > 1e-12:
            blend = h_norm / h_range
        else:
            blend = np.full_like(hurst_map, 0.5)

        return field_rough * (1 - blend) + field_smooth * blend

    def _fbm_spectral(
        self, size: int, hurst: float, rng: np.random.Generator
    ) -> NDArray[np.float64]:
        """Generate fractional Brownian motion via spectral synthesis.

        Generates random complex amplitudes in frequency domain with
        power spectrum S(f) ~ f^(-(2H+2)), then inverse FFT.
        """
        # Frequency grid
        freq_x = np.fft.fftfreq(size)
        freq_y = np.fft.fftfreq(size)
        fx, fy = np.meshgrid(freq_x, freq_y)
        freq_mag = np.sqrt(fx**2 + fy**2)
        freq_mag[0, 0] = 1.0  # avoid division by zero

        # Power spectrum: amplitude ~ f^(-(H+1))
        amplitude = freq_mag ** (-(hurst + 1))
        amplitude[0, 0] = 0.0  # zero DC component

        # Random phases
        phase = rng.uniform(0, 2 * np.pi, (size, size))
        spectrum = amplitude * np.exp(1j * phase)

        # Force Hermitian symmetry for real output
        result = np.real(np.fft.ifft2(spectrum))

        # Normalize to [0, 1]
        rmin, rmax = result.min(), result.max()
        if rmax - rmin > 1e-12:
            result = (result - rmin) / (rmax - rmin)

        return result

    def _ridged_multifractal(
        self, size: int, rng: np.random.Generator
    ) -> NDArray[np.float64]:
        """Generate ridged multifractal noise for mountain ridges.

        Takes absolute value of fBm and inverts to create sharp ridges.
        """
        h = self.params.h_mean
        fbm = self._fbm_spectral(size, h, rng)
        # Center, take abs, invert → ridges at zero-crossings
        centered = fbm - 0.5
        ridged = 1.0 - np.abs(centered) * 2.0
        ridged = np.clip(ridged, 0, 1)
        return ridged ** 2  # sharpen the ridges

    def _fractal_detail(
        self, size: int, rng: np.random.Generator
    ) -> NDArray[np.float64]:
        """High-frequency fractal detail (rocks, micro-texture)."""
        # Low Hurst = rough detail
        detail_h = max(0.05, self.params.h_min * 0.5)
        detail = self._fbm_spectral(size, detail_h, rng)
        return detail

    def _smooth_noise(
        self, size: int, octaves: int = 2, rng: np.random.Generator | None = None
    ) -> NDArray[np.float64]:
        """Generate smooth low-frequency noise for spatial variation."""
        if rng is None:
            rng = np.random.default_rng()
        # High Hurst = very smooth
        return self._fbm_spectral(size, 0.85, rng)

    def _relax_heightmap(
        self,
        heightmap: NDArray[np.float64],
        passes: int = 1,
        strength: float = 0.2,
    ) -> NDArray[np.float64]:
        """Diffuse sharp one-cell spikes while preserving broad landforms.

        This is a lightweight alternative to a full geomorphology solve. It is
        especially useful after noise synthesis because a tiny amount of local
        diffusion makes the result read more like eroded terrain and less like
        raw procedural facets.
        """
        result = np.array(heightmap, copy=True)
        strength = float(np.clip(strength, 0.0, 1.0))
        for _ in range(max(0, passes)):
            neighbor_mean = (
                np.roll(result, 1, axis=0)
                + np.roll(result, -1, axis=0)
                + np.roll(result, 1, axis=1)
                + np.roll(result, -1, axis=1)
            ) / 4.0
            result = result * (1.0 - strength) + neighbor_mean * strength
        return result

    def _classify_biomes(
        self,
        heightmap: NDArray[np.float64],
        moisture: NDArray[np.float64],
        hurst_map: NDArray[np.float64],
    ) -> NDArray[np.int32]:
        """Classify each pixel into a biome based on height, moisture, roughness.

        Biomes:
            0: water (below water_level)
            1: sand/beach (just above water, low moisture)
            2: grass (moderate elevation, moderate moisture)
            3: forest (moderate elevation, high moisture, smooth terrain)
            4: rock (steep/rough areas, high elevation)
            5: snow (above snow_line)
        """
        p = self.params
        biome = np.full(heightmap.shape, 2, dtype=np.int32)  # default: grass

        # Compute slope magnitude
        dy, dx = np.gradient(heightmap)
        slope = np.sqrt(dx**2 + dy**2)

        # Water
        biome[heightmap < p.water_level] = 0

        # Sand: just above water, low moisture
        sand_zone = (heightmap >= p.water_level) & (heightmap < p.water_level + 0.05)
        biome[sand_zone] = 1

        # Forest: moderate elevation, high moisture, low slope
        forest_zone = (
            (heightmap >= p.water_level + 0.05)
            & (heightmap < p.snow_line * 0.8)
            & (moisture > 0.3)
            & (slope < 0.15)
            & (hurst_map > 0.4)
        )
        biome[forest_zone] = 3

        # Rock: steep slopes or rough terrain at high elevation
        rock_zone = (slope > 0.15) | (
            (heightmap > p.snow_line * 0.6) & (hurst_map < 0.35)
        )
        biome[rock_zone] = 4

        # Snow: above snow line
        biome[heightmap > p.snow_line] = 5

        # Water takes priority
        biome[heightmap < p.water_level] = 0

        return biome
