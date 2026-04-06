"""Unified terrain parameter extraction combining all 2D methods.

TerrainParams captures the full multifractal characterization of a
heightmap — roughness distribution (from Wavelet Leaders), scale
structure (from EMD), and self-similarity quality (from Bempedelis).
These drive the terrain generator.

Also provides curated presets extracted from analysis of real terrain
types, so generation can work without real DEM data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass
class TerrainParams:
    """Full terrain characterization from 2D analysis methods."""

    # --- From Wavelet Leaders 2D ---
    h_mean: float = 0.5  # mean Hurst exponent
    h_std: float = 0.1  # Hurst spatial variation
    h_min: float = 0.3  # minimum local Hurst
    h_max: float = 0.8  # maximum local Hurst
    spectrum_width: float = 0.5  # multifractal width (0=mono, 1+=rich)
    dominant_scale: int = 3  # primary feature scale (wavelet level)

    # --- From EMD 2D ---
    imf_energies: list[float] = field(default_factory=lambda: [0.4, 0.25, 0.15, 0.1, 0.05, 0.05])
    scale_count: int = 5  # number of meaningful IMFs

    # --- From Bempedelis 2D ---
    self_similarity_r2: float = 0.7  # overall self-similarity score
    scale_invariance: float = 0.6  # Bempedelis combined score

    # --- Derived / User-set ---
    terrain_type: str = "alpine"  # classification label
    base_elevation: float = 0.0  # base elevation offset
    elevation_range: float = 1.0  # peak-to-valley range

    # --- Generation hints ---
    erosion_strength: float = 0.5  # how eroded the terrain should look
    water_level: float = 0.2  # normalized water level (0=dry, 1=flooded)
    vegetation_density: float = 0.5  # tree/grass density multiplier
    snow_line: float = 0.8  # normalized elevation above which snow appears


# ---------------------------------------------------------------------------
# Presets — derived from known terrain morphology
# ---------------------------------------------------------------------------

TERRAIN_PRESETS: dict[str, TerrainParams] = {
    "alpine": TerrainParams(
        h_mean=0.45,
        h_std=0.12,
        h_min=0.25,
        h_max=0.72,
        spectrum_width=0.55,
        dominant_scale=3,
        imf_energies=[0.42, 0.20, 0.16, 0.10, 0.07, 0.05],
        scale_count=5,
        self_similarity_r2=0.75,
        scale_invariance=0.7,
        terrain_type="alpine",
        elevation_range=1.35,
        erosion_strength=0.8,
        water_level=0.22,
        vegetation_density=0.55,
        snow_line=0.82,
    ),
    "rolling_hills": TerrainParams(
        h_mean=0.75,
        h_std=0.06,
        h_min=0.62,
        h_max=0.88,
        spectrum_width=0.18,
        dominant_scale=4,
        imf_energies=[0.62, 0.12, 0.08, 0.05, 0.03, 0.02],
        scale_count=4,
        self_similarity_r2=0.85,
        scale_invariance=0.8,
        terrain_type="rolling_hills",
        elevation_range=0.6,
        erosion_strength=0.45,
        water_level=0.28,
        vegetation_density=0.8,
        snow_line=0.95,
    ),
    "desert": TerrainParams(
        h_mean=0.7,
        h_std=0.05,
        h_min=0.6,
        h_max=0.85,
        spectrum_width=0.2,
        dominant_scale=5,
        imf_energies=[0.6, 0.2, 0.1, 0.05, 0.03, 0.02],
        scale_count=3,
        self_similarity_r2=0.9,
        scale_invariance=0.85,
        terrain_type="desert",
        elevation_range=0.4,
        erosion_strength=0.15,
        water_level=0.0,
        vegetation_density=0.05,
        snow_line=1.0,
    ),
    "coastal": TerrainParams(
        h_mean=0.55,
        h_std=0.2,
        h_min=0.2,
        h_max=0.9,
        spectrum_width=0.7,
        dominant_scale=3,
        imf_energies=[0.35, 0.25, 0.2, 0.1, 0.05, 0.05],
        scale_count=5,
        self_similarity_r2=0.6,
        scale_invariance=0.55,
        terrain_type="coastal",
        elevation_range=1.0,
        erosion_strength=0.7,
        water_level=0.35,
        vegetation_density=0.6,
        snow_line=0.9,
    ),
    "volcanic": TerrainParams(
        h_mean=0.3,
        h_std=0.12,
        h_min=0.15,
        h_max=0.55,
        spectrum_width=0.9,
        dominant_scale=2,
        imf_energies=[0.5, 0.2, 0.15, 0.08, 0.04, 0.03],
        scale_count=5,
        self_similarity_r2=0.65,
        scale_invariance=0.6,
        terrain_type="volcanic",
        elevation_range=2.5,
        erosion_strength=0.2,
        water_level=0.05,
        vegetation_density=0.15,
        snow_line=0.85,
    ),
    "canyon": TerrainParams(
        h_mean=0.25,
        h_std=0.18,
        h_min=0.1,
        h_max=0.7,
        spectrum_width=1.0,
        dominant_scale=2,
        imf_energies=[0.4, 0.3, 0.15, 0.08, 0.04, 0.03],
        scale_count=5,
        self_similarity_r2=0.55,
        scale_invariance=0.5,
        terrain_type="canyon",
        elevation_range=3.0,
        erosion_strength=0.9,
        water_level=0.1,
        vegetation_density=0.2,
        snow_line=0.95,
    ),
}


def get_preset(name: str) -> TerrainParams:
    """Get a terrain preset by name.

    Args:
        name: Preset name (alpine, rolling_hills, desert, coastal, volcanic, canyon).

    Returns:
        TerrainParams for the preset.

    Raises:
        KeyError: If preset name not found.
    """
    if name not in TERRAIN_PRESETS:
        available = ", ".join(sorted(TERRAIN_PRESETS.keys()))
        raise KeyError(f"Unknown preset '{name}'. Available: {available}")
    # Return a copy to prevent mutation of the global preset
    import copy

    return copy.deepcopy(TERRAIN_PRESETS[name])


def list_presets() -> list[str]:
    """List available terrain preset names."""
    return sorted(TERRAIN_PRESETS.keys())


def analyze_terrain(heightmap: NDArray[np.float64]) -> TerrainParams:
    """Analyze a heightmap with all three 2D methods and produce TerrainParams.

    Runs Wavelet Leaders 2D, profile-based EMD, and Bempedelis 2D,
    then packages results into a TerrainParams for the generator.

    Args:
        heightmap: 2D elevation array.

    Returns:
        TerrainParams populated from analysis.
    """
    from the_similarity.methods.wavelet_leaders_2d import extract_terrain_spectrum
    from the_similarity.methods.emd_2d import terrain_scale_analysis
    from the_similarity.methods.bempedelis_2d import terrain_self_similarity

    heightmap = np.asarray(heightmap, dtype=np.float64)

    # Wavelet Leaders 2D
    try:
        wl = extract_terrain_spectrum(heightmap)
    except Exception:
        wl = {
            "h_mean": 0.5,
            "h_std": 0.1,
            "h_min": 0.3,
            "h_max": 0.8,
            "spectrum_width": 0.5,
            "dominant_scale": 3,
            "scale_energies": [0.2] * 5,
        }

    # EMD 2D
    try:
        emd_result = terrain_scale_analysis(heightmap)
    except Exception:
        emd_result = {
            "energies": [0.3, 0.2, 0.15, 0.1, 0.05],
            "scale_count": 4,
        }

    # Bempedelis 2D
    try:
        patch_size = min(64, min(heightmap.shape) // 2)
        if patch_size >= 16:
            bemp = terrain_self_similarity(heightmap, patch_size=patch_size)
            ss_r2 = bemp.power_law_r2
            ss_score = bemp.score
        else:
            ss_r2 = 0.5
            ss_score = 0.5
    except Exception:
        ss_r2 = 0.5
        ss_score = 0.5

    # Classify terrain type
    terrain_type = classify_terrain_type(
        h_mean=wl["h_mean"],
        h_std=wl["h_std"],
        spectrum_width=wl["spectrum_width"],
    )

    hmap_range = float(heightmap.max() - heightmap.min()) or 1.0

    return TerrainParams(
        h_mean=wl["h_mean"],
        h_std=wl["h_std"],
        h_min=wl["h_min"],
        h_max=wl["h_max"],
        spectrum_width=wl["spectrum_width"],
        dominant_scale=wl["dominant_scale"],
        imf_energies=emd_result["energies"],
        scale_count=emd_result["scale_count"],
        self_similarity_r2=ss_r2,
        scale_invariance=ss_score,
        terrain_type=terrain_type,
        base_elevation=float(heightmap.min()),
        elevation_range=hmap_range,
    )


def classify_terrain_type(
    h_mean: float,
    h_std: float,
    spectrum_width: float,
) -> str:
    """Classify terrain type from multifractal parameters.

    Uses simple thresholds on Hurst and spectrum width.

    Args:
        h_mean: Mean Hurst exponent.
        h_std: Hurst spatial variation.
        spectrum_width: Multifractal spectrum width.

    Returns:
        Terrain type string.
    """
    if h_mean > 0.65:
        return "desert" if h_std < 0.1 else "rolling_hills"
    elif h_mean < 0.3:
        if spectrum_width > 0.8:
            return "canyon"
        return "volcanic"
    elif h_std > 0.15:
        return "coastal"
    else:
        return "alpine"


def params_to_dict(params: TerrainParams) -> dict:
    """Convert TerrainParams to a JSON-serializable dictionary."""
    return {
        "h_mean": params.h_mean,
        "h_std": params.h_std,
        "h_min": params.h_min,
        "h_max": params.h_max,
        "spectrum_width": params.spectrum_width,
        "dominant_scale": params.dominant_scale,
        "imf_energies": params.imf_energies,
        "scale_count": params.scale_count,
        "self_similarity_r2": params.self_similarity_r2,
        "scale_invariance": params.scale_invariance,
        "terrain_type": params.terrain_type,
        "base_elevation": params.base_elevation,
        "elevation_range": params.elevation_range,
        "erosion_strength": params.erosion_strength,
        "water_level": params.water_level,
        "vegetation_density": params.vegetation_density,
        "snow_line": params.snow_line,
    }
