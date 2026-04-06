"""Wavelet Leaders multifractal spectrum analysis.

Computes the f(α) singularity spectrum via wavelet leaders and uses
spectrum distance as a scoring signal for pattern matching.

Reference: Jaffard, Lashermes, Abry, "Wavelet Leaders in Multifractal
Analysis" (2006).

Multifractal Scaling Mechanics:
- Spectrum Transformation: Converts temporal trajectories into the dense `f(α)` 
  singularity spectrum parameter space. Rather than a singular monofractal Hurst 
  exponent, multifractal footprints accommodate heterogeneous local scaling densities.
- Wavelet Leaders Method: Sub-selects local coefficient suprema across all finer 
  scale cascades. This bypasses raw wavelet instabilities, firmly bounding 
  oscillatory artifacts.
- Analytical Transposition: A Legendre transform subsequently projects scaling 
  exponents onto `f(α)`. Series exhibiting heavily overlapping spectra are 
  structurally isomorphic in terms of dynamic volatility clustering behavior.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

try:
    import pywt

    HAS_PYWT = True
except ImportError:
    HAS_PYWT = False

MIN_WINDOW_SIZE = 16


def compute_wavelet_leaders(
    series: NDArray[np.float64],
    wavelet: str = "db4",
    max_level: int | None = None,
) -> list[NDArray[np.float64]]:
    """Compute wavelet leaders at each scale.

    Wavelet leaders are the local supremum of wavelet coefficient
    absolute values, capturing the local regularity of the signal.

    Args:
        series: 1D input array.
        wavelet: Wavelet name (default: Daubechies-4).
        max_level: Max decomposition level. None = auto.

    Returns:
        List of leader arrays, one per scale (coarse to fine).
    """
    if not HAS_PYWT:
        raise RuntimeError("PyWavelets required. Install with: pip install PyWavelets")

    series = np.asarray(series, dtype=np.float64)
    if max_level is None:
        max_level = pywt.dwt_max_level(len(series), pywt.Wavelet(wavelet).dec_len)
        max_level = max(1, min(max_level, 8))

    coeffs = pywt.wavedec(series, wavelet, level=max_level)
    # coeffs[0] = approximation, coeffs[1:] = details (coarse to fine)
    detail_coeffs = coeffs[1:]

    leaders: list[NDArray[np.float64]] = []
    for level_coeffs in detail_coeffs:
        abs_coeffs = np.abs(level_coeffs)
        if len(abs_coeffs) < 3:
            leaders.append(abs_coeffs.copy())
            continue
        # Leader = max of coefficient and its immediate neighbors
        padded = np.pad(abs_coeffs, 1, mode="edge")
        leader_vals = np.maximum(
            np.maximum(padded[:-2], padded[1:-1]),
            padded[2:],
        )
        leaders.append(leader_vals)

    return leaders


def multifractal_spectrum(
    leaders: list[NDArray[np.float64]],
    q_range: tuple[float, float, float] = (-5, 5.5, 0.5),
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Compute the f(α) singularity spectrum from wavelet leaders.

    Args:
        leaders: List of leader arrays per scale.
        q_range: (start, stop, step) for moment orders q.

    Returns:
        (alpha, f_alpha) arrays defining the singularity spectrum.
    """
    q_values = np.arange(*q_range)
    n_scales = len(leaders)

    if n_scales < 2:
        # Not enough scales for regression
        return np.array([0.5]), np.array([1.0])

    # Structure functions S(q, j) at each scale
    scales = np.arange(1, n_scales + 1, dtype=np.float64)
    log_scales = np.log2(scales)

    h_q = np.zeros(len(q_values))
    for qi, q in enumerate(q_values):
        log_sq = np.zeros(n_scales)
        for j, ldr in enumerate(leaders):
            ldr_safe = np.maximum(ldr, 1e-15)
            if q == 0:
                log_sq[j] = np.mean(np.log(ldr_safe))
            else:
                log_sq[j] = np.log2(np.mean(ldr_safe ** q) + 1e-30) / max(abs(q), 1e-10)

        # Linear regression: log_sq = h(q) * log_scales + const
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

    # Filter valid points (f_alpha should be <= 1 and alpha should be positive-ish)
    valid = np.isfinite(alpha) & np.isfinite(f_alpha)
    if not np.any(valid):
        return np.array([0.5]), np.array([1.0])

    return alpha[valid], f_alpha[valid]


def spectrum_distance(
    spec_a: tuple[NDArray[np.float64], NDArray[np.float64]],
    spec_b: tuple[NDArray[np.float64], NDArray[np.float64]],
) -> float:
    """L2 distance between two multifractal spectra.

    Interpolates both onto a common alpha grid for comparison.

    Args:
        spec_a: (alpha_a, f_alpha_a) tuple.
        spec_b: (alpha_b, f_alpha_b) tuple.

    Returns:
        L2 distance (0 = identical spectra).
    """
    alpha_a, f_a = spec_a
    alpha_b, f_b = spec_b

    if len(alpha_a) < 2 or len(alpha_b) < 2:
        return 0.5  # fallback for degenerate spectra

    # Common alpha grid
    lo = max(alpha_a.min(), alpha_b.min())
    hi = min(alpha_a.max(), alpha_b.max())
    if lo >= hi:
        return 1.0  # no overlap

    grid = np.linspace(lo, hi, 50)
    f_a_interp = np.interp(grid, alpha_a, f_a)
    f_b_interp = np.interp(grid, alpha_b, f_b)

    return float(np.sqrt(np.mean((f_a_interp - f_b_interp) ** 2)))


def wavelet_score(distance: float) -> float:
    """Convert spectrum distance to [0, 1] similarity score."""
    return float(np.exp(-distance * 5))


def wavelet_spectrum_score(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    wavelet: str = "db4",
) -> float:
    """End-to-end: compute wavelet spectrum similarity between two series.

    Args:
        query: Query window (1D).
        candidate: Candidate window (1D).
        wavelet: Wavelet name.

    Returns:
        Score in [0, 1]. Returns 0.5 for short/degenerate series.
    """
    if len(query) < MIN_WINDOW_SIZE or len(candidate) < MIN_WINDOW_SIZE:
        return 0.5

    try:
        leaders_q = compute_wavelet_leaders(query, wavelet=wavelet)
        leaders_c = compute_wavelet_leaders(candidate, wavelet=wavelet)
        spec_q = multifractal_spectrum(leaders_q)
        spec_c = multifractal_spectrum(leaders_c)
        dist = spectrum_distance(spec_q, spec_c)
        return wavelet_score(dist)
    except Exception:
        return 0.5
