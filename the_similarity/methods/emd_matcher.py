"""Empirical Mode Decomposition (EMD) matcher.

Decomposes a time series into Intrinsic Mode Functions (IMFs).
Used as a Tier 2 enrichment method to compare multi-scale characteristics.

Spectral Decomposition & Matching Architecture:
- Data-driven Basis: Unlike Fourier or Wavelet transforms relying on fixed
  rigid mathematical dictionaries, EMD empirically derives basis functions
  (Intrinsic Mode Functions, IMFs) strictly from the target data via sifting.
- Dimensionality Alignment: `n_q` and `n_c` are not guaranteed to match due to
  the empirical generation process. The shorter spectrum is padded with zero arrays.
- Distance Metric: Final score computes the energy-weighted L2 distance mapped
  exponentially. High energy components in the query firmly dictate distance penalties.
"""

import numpy as np
from numpy.typing import NDArray
from PyEMD import EMD


def decompose_emd(series: NDArray[np.float64], max_imfs: int = 6) -> list[NDArray]:
    """Decompose a 1D series into Intrinsic Mode Functions using EMD.

    Args:
        series: 1D time series array.
        max_imfs: Maximum number of IMFs to return.

    Returns:
        List of IMF arrays, truncated to max_imfs.
    """
    emd = EMD()
    try:
        imfs = emd(series.astype(np.float64))
    except Exception:
        return [series]

    if imfs is None or len(imfs) == 0:
        return [series]

    return list(imfs[:max_imfs])


def imf_energy(imf: NDArray[np.float64]) -> float:
    """Compute the energy of an IMF.

    Args:
        imf: 1D IMF array.

    Returns:
        Sum of squared values.
    """
    return float(np.sum(imf**2))


def emd_match(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    max_imfs: int = 6,
) -> tuple[float, float]:
    """Match two series using EMD multi-scale decomposition.

    Decomposes both series into IMFs, aligns them, and computes an
    energy-weighted distance across corresponding IMF pairs.

    Args:
        query: 1D query series.
        candidate: 1D candidate series.
        max_imfs: Maximum number of IMFs to use.

    Returns:
        Tuple of (score, distance) where score is in [0, 1].
    """
    if len(query) < 10 or len(candidate) < 10:
        return (0.0, float("inf"))

    if np.std(query) == 0.0 or np.std(candidate) == 0.0:
        return (0.0, float("inf"))

    try:
        q_imfs = decompose_emd(query, max_imfs)
        c_imfs = decompose_emd(candidate, max_imfs)
    except Exception:
        return (0.0, float("inf"))

    # Align IMF count by padding with zeros
    n_q, n_c = len(q_imfs), len(c_imfs)
    n_max = max(n_q, n_c)
    length = len(query)

    while len(q_imfs) < n_max:
        q_imfs.append(np.zeros(length))
    while len(c_imfs) < n_max:
        c_imfs.append(np.zeros(len(candidate)))

    # Compute energy weights from query IMFs
    energies = [imf_energy(q) for q in q_imfs]
    total_energy = sum(energies)
    if total_energy == 0.0:
        return (0.0, float("inf"))

    weights = [e / total_energy for e in energies]

    # Weighted sum of per-IMF normalized L2 distances
    total_distance = 0.0
    for q_imf, c_imf, w in zip(q_imfs, c_imfs, weights):
        # Use shorter length for comparison
        min_len = min(len(q_imf), len(c_imf))
        diff = q_imf[:min_len] - c_imf[:min_len]
        l2 = float(np.sqrt(np.sum(diff**2)))
        normalized = l2 / max(min_len, 1)
        total_distance += w * normalized

    score = float(np.exp(-total_distance))
    return (score, total_distance)


def emd_score(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    max_imfs: int = 6,
) -> float:
    """Convenience wrapper returning just the similarity score.

    Args:
        query: 1D query series.
        candidate: 1D candidate series.
        max_imfs: Maximum number of IMFs to use.

    Returns:
        Similarity score in [0, 1].
    """
    score, _ = emd_match(query, candidate, max_imfs)
    return score
