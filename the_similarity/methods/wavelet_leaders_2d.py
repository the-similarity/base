"""2D Wavelet Leaders multifractal analysis for heightmaps.

Extends the 1D wavelet_leaders.py to 2D heightfields using pywt.wavedec2.
Produces local Hurst exponent maps and f(α) singularity spectra that
capture how terrain roughness varies spatially — mountains vs valleys vs plains.

Reference: Jaffard, Lashermes, Abry, "Wavelet Leaders in Multifractal
Analysis" (2006), extended to 2D via separable wavelet decomposition.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

try:
    import pywt

    HAS_PYWT = True
except ImportError:
    HAS_PYWT = False


def compute_wavelet_leaders_2d(
    heightmap: NDArray[np.float64],
    wavelet: str = "db4",
    max_level: int | None = None,
) -> list[list[NDArray[np.float64]]]:
    """Compute 2D wavelet leaders at each scale.

    For each scale, returns three leader arrays (LH, HL, HH) corresponding
    to horizontal, vertical, and diagonal detail. Leaders are the local
    supremum of coefficient magnitudes over 3×3 neighborhoods.

    Args:
        heightmap: 2D array (H, W).
        wavelet: Wavelet name (default: Daubechies-4).
        max_level: Max decomposition level. None = auto.

    Returns:
        List of [LH_leaders, HL_leaders, HH_leaders] per scale (coarse→fine).
    """
    if not HAS_PYWT:
        raise RuntimeError("PyWavelets required. Install with: pip install PyWavelets")

    heightmap = np.asarray(heightmap, dtype=np.float64)
    if heightmap.ndim != 2:
        raise ValueError(f"Expected 2D array, got shape {heightmap.shape}")

    if max_level is None:
        min_dim = min(heightmap.shape)
        max_level = pywt.dwt_max_level(min_dim, pywt.Wavelet(wavelet).dec_len)
        max_level = max(1, min(max_level, 8))

    coeffs = pywt.wavedec2(heightmap, wavelet, level=max_level)
    # coeffs[0] = approximation (2D)
    # coeffs[1:] = list of (LH, HL, HH) tuples, coarse→fine

    all_leaders: list[list[NDArray[np.float64]]] = []
    for detail_tuple in coeffs[1:]:
        level_leaders = []
        for subband in detail_tuple:  # LH, HL, HH
            abs_coeffs = np.abs(subband)
            leader_vals = _local_supremum_2d(abs_coeffs)
            level_leaders.append(leader_vals)
        all_leaders.append(level_leaders)

    return all_leaders


def _local_supremum_2d(arr: NDArray[np.float64]) -> NDArray[np.float64]:
    """Compute local supremum over 3×3 neighborhoods.

    For edge pixels, uses available neighbors (edge-padded).
    """
    if arr.shape[0] < 2 or arr.shape[1] < 2:
        return arr.copy()

    padded = np.pad(arr, 1, mode="edge")
    result = np.zeros_like(arr)
    for di in range(3):
        for dj in range(3):
            result = np.maximum(
                result,
                padded[di : di + arr.shape[0], dj : dj + arr.shape[1]],
            )
    return result


def multifractal_spectrum_2d(
    leaders: list[list[NDArray[np.float64]]],
    q_range: tuple[float, float, float] = (-5, 5.5, 0.5),
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Compute f(α) singularity spectrum from 2D wavelet leaders.

    Averages structure functions across all three subbands (LH, HL, HH)
    at each scale before performing the Legendre transform.

    Args:
        leaders: Output of compute_wavelet_leaders_2d.
        q_range: (start, stop, step) for moment orders q.

    Returns:
        (alpha, f_alpha) arrays defining the singularity spectrum.
    """
    q_values = np.arange(*q_range)
    n_scales = len(leaders)

    if n_scales < 2:
        return np.array([0.5]), np.array([1.0])

    scales = np.arange(1, n_scales + 1, dtype=np.float64)
    log_scales = np.log2(scales)

    h_q = np.zeros(len(q_values))
    for qi, q in enumerate(q_values):
        log_sq = np.zeros(n_scales)
        for j, level_leaders in enumerate(leaders):
            # Average across LH, HL, HH subbands
            subband_vals = []
            for subband_leaders in level_leaders:
                flat = subband_leaders.ravel()
                safe = np.maximum(flat, 1e-15)
                if q == 0:
                    subband_vals.append(np.mean(np.log(safe)))
                else:
                    subband_vals.append(
                        np.log2(np.mean(safe**q) + 1e-30) / max(abs(q), 1e-10)
                    )
            log_sq[j] = np.mean(subband_vals)

        if np.std(log_scales) > 0 and np.std(log_sq) > 0:
            slope, _ = np.polyfit(log_scales, log_sq, 1)
            h_q[qi] = slope
        else:
            h_q[qi] = 0.5

    # Scaling exponent τ(q) = q·h(q) − 1
    tau_q = q_values * h_q - 1

    # Legendre transform: α = dτ/dq, f(α) = q·α − τ
    alpha = np.gradient(tau_q, q_values)
    f_alpha = q_values * alpha - tau_q

    valid = np.isfinite(alpha) & np.isfinite(f_alpha)
    if not np.any(valid):
        return np.array([0.5]), np.array([1.0])

    return alpha[valid], f_alpha[valid]


def local_hurst_map(
    heightmap: NDArray[np.float64],
    block_size: int = 32,
    wavelet: str = "db4",
    overlap: float = 0.5,
) -> NDArray[np.float64]:
    """Compute spatially-varying Hurst exponent map.

    Divides the heightmap into overlapping blocks and estimates the local
    Hurst exponent for each block via structure function regression on
    1D profiles extracted from the block.

    Args:
        heightmap: 2D elevation array.
        block_size: Size of each analysis block.
        wavelet: Wavelet for DWT.
        overlap: Fraction of overlap between blocks (0-0.9).

    Returns:
        2D array of local Hurst exponents (same shape as heightmap,
        interpolated from block centers).
    """
    heightmap = np.asarray(heightmap, dtype=np.float64)
    H, W = heightmap.shape

    step = max(1, int(block_size * (1 - overlap)))
    # Block centers
    cy_list = list(range(block_size // 2, H - block_size // 2 + 1, step))
    cx_list = list(range(block_size // 2, W - block_size // 2 + 1, step))

    if not cy_list or not cx_list:
        return np.full_like(heightmap, 0.5)

    hurst_grid = np.zeros((len(cy_list), len(cx_list)))

    for i, cy in enumerate(cy_list):
        for j, cx in enumerate(cx_list):
            y0 = cy - block_size // 2
            x0 = cx - block_size // 2
            block = heightmap[y0 : y0 + block_size, x0 : x0 + block_size]
            hurst_grid[i, j] = _estimate_block_hurst(block)

    # Interpolate to full resolution
    from scipy.interpolate import RegularGridInterpolator

    cy_arr = np.array(cy_list, dtype=np.float64)
    cx_arr = np.array(cx_list, dtype=np.float64)

    interp = RegularGridInterpolator(
        (cy_arr, cx_arr),
        hurst_grid,
        method="linear",
        bounds_error=False,
        fill_value=None,
    )

    yy, xx = np.meshgrid(
        np.arange(H, dtype=np.float64),
        np.arange(W, dtype=np.float64),
        indexing="ij",
    )
    points = np.stack([yy.ravel(), xx.ravel()], axis=-1)
    hurst_full = interp(points).reshape(H, W)

    return np.clip(hurst_full, 0.0, 1.0)


def _estimate_block_hurst(block: NDArray[np.float64]) -> float:
    """Estimate Hurst exponent for a small 2D block.

    Uses structure function on horizontal and vertical profiles,
    averaged for isotropy.
    """
    h_vals = []
    # Horizontal profiles
    for row in block:
        h = _hurst_structure_function(row)
        if h is not None:
            h_vals.append(h)
    # Vertical profiles
    for col in block.T:
        h = _hurst_structure_function(col)
        if h is not None:
            h_vals.append(h)

    if not h_vals:
        return 0.5
    return float(np.clip(np.median(h_vals), 0.0, 1.0))


def _hurst_structure_function(series: NDArray[np.float64]) -> float | None:
    """Estimate Hurst exponent via structure function (variogram).

    S(τ) = <|x(t+τ) - x(t)|²> ~ τ^(2H)
    """
    n = len(series)
    if n < 8:
        return None

    max_lag = min(n // 4, 16)
    lags = np.arange(1, max_lag + 1)
    structure = np.zeros(len(lags))

    for i, lag in enumerate(lags):
        diffs = series[lag:] - series[:-lag]
        structure[i] = np.mean(diffs**2)

    # Filter valid
    valid = structure > 0
    if np.sum(valid) < 2:
        return None

    log_lags = np.log(lags[valid].astype(np.float64))
    log_struct = np.log(structure[valid])

    try:
        slope = np.polyfit(log_lags, log_struct, 1)[0]
        h = slope / 2.0  # S(τ) ~ τ^(2H)
        return float(np.clip(h, 0.0, 1.0))
    except Exception:
        return None


def extract_terrain_spectrum(
    heightmap: NDArray[np.float64],
    wavelet: str = "db4",
) -> dict:
    """Extract full multifractal characterization of a heightmap.

    Returns a dictionary with spectrum, width, dominant scale,
    and local Hurst statistics — everything needed to parameterize
    terrain generation.

    Args:
        heightmap: 2D elevation array.
        wavelet: Wavelet name.

    Returns:
        Dict with keys: alpha, f_alpha, spectrum_width, h_mean, h_std,
        dominant_scale.
    """
    leaders = compute_wavelet_leaders_2d(heightmap, wavelet=wavelet)
    alpha, f_alpha = multifractal_spectrum_2d(leaders)
    hurst = local_hurst_map(heightmap, wavelet=wavelet)

    # Spectrum width = range of α values (wider = more multifractal)
    spectrum_width = float(alpha.max() - alpha.min()) if len(alpha) > 1 else 0.0

    # Dominant scale: which decomposition level has the most energy?
    scale_energies = []
    for level_leaders in leaders:
        energy = sum(float(np.sum(s**2)) for s in level_leaders)
        scale_energies.append(energy)
    dominant_scale = int(np.argmax(scale_energies)) + 1 if scale_energies else 1

    return {
        "alpha": alpha,
        "f_alpha": f_alpha,
        "spectrum_width": spectrum_width,
        "h_mean": float(np.mean(hurst)),
        "h_std": float(np.std(hurst)),
        "h_min": float(np.min(hurst)),
        "h_max": float(np.max(hurst)),
        "dominant_scale": dominant_scale,
        "scale_energies": scale_energies,
        "hurst_map": hurst,
    }
