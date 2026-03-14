"""Koopman EDMD + eigenvalue matching.

Fits a Koopman operator via Extended Dynamic Mode Decomposition (EDMD)
on delay-embedded windows, extracts eigenvalue spectra, and matches
via the Hungarian algorithm. Weight: 0.20 (highest single method).

The Koopman operator is the infinite-dimensional linear operator that
advances observables of a nonlinear system. EDMD approximates it from
data using least-squares on a dictionary of observables (here: delay
coordinates). The eigenvalues encode the fundamental frequencies and
growth/decay rates of the dynamics — two windows with similar eigenvalue
spectra are governed by similar dynamical processes.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import linear_sum_assignment

from the_similarity.core.embedding import delay_embed

# Minimum window length for meaningful Koopman analysis.
KOOPMAN_MIN_WINDOW = 50


@dataclass
class KoopmanForecast:
    """Forward evolution from a fitted Koopman operator."""
    trajectory: NDArray[np.float64]   # (forward_bars,) predicted cumulative returns
    uncertainty: NDArray[np.float64]  # (forward_bars,) per-step 1-sigma bounds


@dataclass
class KoopmanResult:
    """Result of Koopman EDMD decomposition."""
    eigenvalues: NDArray[np.complex128]
    eigenvectors: NDArray[np.complex128]
    a_tilde: NDArray[np.complex128]
    u_r: NDArray[np.float64] | None = None  # left singular vectors for projection


def fit_koopman(
    series: NDArray[np.float64],
    dim: int = 8,
    lag: int = 3,
    n_modes: int = 8,
) -> KoopmanResult:
    """Fit a Koopman operator via EDMD on delay-embedded snapshots.

    Args:
        series: 1-D time series array.
        dim: Embedding dimension for delay embedding.
        lag: Time delay for delay embedding.
        n_modes: Number of DMD modes to retain (truncation rank).

    Returns:
        KoopmanResult with eigenvalues, eigenvectors, and reduced operator.

    Raises:
        ValueError: If the series is too short for the given dim/lag.
    """
    series = np.asarray(series, dtype=np.float64).ravel()

    # Delay-embed
    embedded = delay_embed(series, dim, lag)  # shape (n_rows, dim)

    # Build snapshot pairs: X = embedded[:-1], Y = embedded[1:]
    x_mat = embedded[:-1].T  # (dim, n_snapshots)
    y_mat = embedded[1:].T   # (dim, n_snapshots)

    # SVD of X
    u, s, vt = np.linalg.svd(x_mat, full_matrices=False)

    # Truncate to n_modes (or fewer if not enough singular values)
    r = min(n_modes, len(s))

    # Guard against zero / near-zero singular values
    nonzero_mask = s[:r] > 1e-12
    r = int(np.sum(nonzero_mask))
    if r == 0:
        # Degenerate case: return trivial result
        return KoopmanResult(
            eigenvalues=np.array([], dtype=np.complex128),
            eigenvectors=np.array([]).reshape(0, 0).astype(np.complex128),
            a_tilde=np.array([]).reshape(0, 0).astype(np.complex128),
            u_r=None,
        )

    u_r = u[:, :r]
    s_r = s[:r]
    vt_r = vt[:r, :]

    # Project: A_tilde = U_r^T @ Y @ V_r @ S_r^{-1}
    a_tilde = u_r.T @ y_mat @ vt_r.T @ np.diag(1.0 / s_r)

    # Eigendecompose
    eigenvalues, eigenvectors = np.linalg.eig(a_tilde)

    return KoopmanResult(
        eigenvalues=eigenvalues.astype(np.complex128),
        eigenvectors=eigenvectors.astype(np.complex128),
        a_tilde=a_tilde.astype(np.complex128),
        u_r=u_r,
    )


def koopman_eigenvalue_distance(
    eigs_a: NDArray[np.complex128],
    eigs_b: NDArray[np.complex128],
    top_k: int = 8,
) -> float:
    """Compute optimal eigenvalue matching distance via Hungarian algorithm.

    Sorts eigenvalues by magnitude, truncates to top-k (above threshold),
    pads the smaller set with zeros, then finds the minimum-cost matching
    in the complex plane.

    Args:
        eigs_a: Eigenvalues from first window.
        eigs_b: Eigenvalues from second window.
        top_k: Maximum number of eigenvalues to compare.

    Returns:
        Total matched distance (sum of |lambda_i - mu_j| over optimal pairs).
    """
    eigs_a = np.asarray(eigs_a, dtype=np.complex128).ravel()
    eigs_b = np.asarray(eigs_b, dtype=np.complex128).ravel()

    # Sort by magnitude descending
    eigs_a = eigs_a[np.argsort(-np.abs(eigs_a))]
    eigs_b = eigs_b[np.argsort(-np.abs(eigs_b))]

    # Truncate to top-k with |lambda| > 0.05
    eigs_a = eigs_a[:top_k]
    eigs_b = eigs_b[:top_k]
    eigs_a = eigs_a[np.abs(eigs_a) > 0.05]
    eigs_b = eigs_b[np.abs(eigs_b) > 0.05]

    if len(eigs_a) == 0 and len(eigs_b) == 0:
        return 0.0

    # Pad smaller set with zeros
    n = max(len(eigs_a), len(eigs_b))
    padded_a = np.zeros(n, dtype=np.complex128)
    padded_b = np.zeros(n, dtype=np.complex128)
    padded_a[: len(eigs_a)] = eigs_a
    padded_b[: len(eigs_b)] = eigs_b

    # Cost matrix: |lambda_i - mu_j| in complex plane
    cost = np.abs(padded_a[:, None] - padded_b[None, :])

    # Hungarian algorithm for optimal matching
    row_ind, col_ind = linear_sum_assignment(cost)
    return float(cost[row_ind, col_ind].sum())


def koopman_score(distance: float, n_modes: int = 8) -> float:
    """Map eigenvalue distance to a similarity score in [0, 1].

    Uses an exponential decay: score = exp(-distance / n_modes).

    Args:
        distance: Eigenvalue matching distance from
            :func:`koopman_eigenvalue_distance`.
        n_modes: Number of modes (controls the decay scale).

    Returns:
        Similarity score in [0, 1].
    """
    return float(np.exp(-distance / n_modes))


def koopman_match(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    dim: int = 8,
    lag: int = 3,
    n_modes: int = 8,
) -> float:
    """Full Koopman matching pipeline: embed, fit, compare.

    Convenience function that runs fit_koopman on both windows and returns
    a similarity score in [0, 1].

    Args:
        query: Normalized query window.
        candidate: Normalized candidate window.
        dim: Embedding dimension.
        lag: Time delay.
        n_modes: Number of DMD modes.

    Returns:
        Similarity score in [0, 1]. Returns 0.0 for degenerate inputs.
    """
    for series in (query, candidate):
        s = np.asarray(series, dtype=np.float64).ravel()
        if len(s) < KOOPMAN_MIN_WINDOW:
            return 0.0
        # All-constant series
        if np.ptp(s) < 1e-12:
            return 0.0

    try:
        result_q = fit_koopman(query, dim, lag, n_modes)
        result_c = fit_koopman(candidate, dim, lag, n_modes)
    except (ValueError, np.linalg.LinAlgError):
        return 0.0

    if len(result_q.eigenvalues) == 0 or len(result_c.eigenvalues) == 0:
        return 0.0

    distance = koopman_eigenvalue_distance(
        result_q.eigenvalues, result_c.eigenvalues, top_k=n_modes,
    )
    return koopman_score(distance, n_modes)


def clamp_eigenvalues(
    eigenvalues: NDArray[np.complex128],
) -> NDArray[np.complex128]:
    """Project eigenvalues onto the unit disk, preserving phase.

    Eigenvalues with |λ| > 1 represent unstable modes that would cause
    the forecast to diverge. Clamping scales their magnitude to 1.0
    while keeping the oscillation frequency (phase angle) intact.

    Args:
        eigenvalues: Complex eigenvalue array.

    Returns:
        Clamped eigenvalues with |λ| ≤ 1.
    """
    mags = np.abs(eigenvalues)
    scale = np.where(mags > 1.0, 1.0 / mags, 1.0)
    return eigenvalues * scale


def koopman_evolve(
    series: NDArray[np.float64],
    forward_bars: int,
    dim: int = 8,
    lag: int = 3,
    n_modes: int = 8,
) -> KoopmanForecast | None:
    """Evolve a time series forward using its fitted Koopman operator.

    Fits a Koopman operator on the input series via EDMD, clamps
    eigenvalues to the unit disk to prevent divergence, then evolves
    the last embedded state forward to produce a forecast.

    The trajectory is returned as cumulative returns relative to the
    last value of the input series, matching the Forecast convention.

    Args:
        series: 1-D time series (raw values, not returns).
        forward_bars: Number of steps to forecast.
        dim: Embedding dimension.
        lag: Time delay for embedding.
        n_modes: Number of DMD modes.

    Returns:
        KoopmanForecast with trajectory and uncertainty, or None if
        the series is too short or degenerate.

    Architecture:
        ┌─────────────┐
        │  Raw series  │
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │ delay_embed  │ → (n_rows, dim) embedded matrix
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │  fit_koopman │ → eigenvalues λ, eigenvectors W, U_r
        └──────┬──────┘
               ▼
        ┌──────────────────┐
        │ clamp_eigenvalues │ → |λ| ≤ 1 (stable evolution)
        └──────┬───────────┘
               ▼
        ┌──────────────────────────────────┐
        │ Project last state → eigencoords │
        │   x_reduced = U_r.T @ x_last     │
        │   b = W⁻¹ @ x_reduced            │
        └──────┬───────────────────────────┘
               ▼
        ┌──────────────────────────────────┐
        │ Evolve: x(t) = W @ diag(λᵗ) @ b │
        │   → take first component          │
        │   → convert to cumulative returns  │
        └──────────────────────────────────┘
    """
    series = np.asarray(series, dtype=np.float64).ravel()
    if len(series) < KOOPMAN_MIN_WINDOW:
        return None
    if np.ptp(series) < 1e-12:
        return None

    try:
        result = fit_koopman(series, dim, lag, n_modes)
    except (ValueError, np.linalg.LinAlgError):
        return None

    if len(result.eigenvalues) == 0 or result.u_r is None:
        return None

    # Delay-embed the series and get the last state
    embedded = delay_embed(series, dim, lag)
    x_last = embedded[-1]  # (dim,)

    # Project into reduced space
    u_r = result.u_r  # (dim, r)
    x_reduced = u_r.T @ x_last  # (r,)

    # Clamp eigenvalues to unit disk
    eigs_clamped = clamp_eigenvalues(result.eigenvalues)
    W = result.eigenvectors  # (r, r)

    # Project into eigenmode coordinates: b = W^{-1} @ x_reduced
    try:
        b = np.linalg.solve(W, x_reduced)
    except np.linalg.LinAlgError:
        return None

    # Compute reconstruction residuals for uncertainty estimation
    # Compare one-step predictions vs actuals on training data
    n_snapshots = len(embedded) - 1
    residuals = np.zeros(n_snapshots)
    for i in range(n_snapshots):
        x_i = u_r.T @ embedded[i]
        x_pred = u_r @ (result.a_tilde @ x_i)
        x_actual = embedded[i + 1]
        # Residual in the first coordinate (predicted value)
        residuals[i] = x_actual[0] - x_pred[0].real

    sigma = float(np.std(residuals)) if len(residuals) > 1 else 0.0

    # Evolve forward
    last_value = series[-1]
    use_returns = abs(last_value) > 1e-6
    trajectory = np.zeros(forward_bars)
    uncertainty = np.zeros(forward_bars)

    for t in range(1, forward_bars + 1):
        # x_reduced(t) = W @ diag(λ^t) @ b
        x_evolved = W @ (b * eigs_clamped ** t)
        # Project back to full space, take first component (most recent value)
        x_full = u_r @ x_evolved
        predicted_value = x_full[0].real

        # Convert to cumulative return relative to last value.
        # When last_value ≈ 0, use absolute difference instead of return.
        if use_returns:
            trajectory[t - 1] = (predicted_value - last_value) / last_value
        else:
            trajectory[t - 1] = predicted_value - last_value

        # Uncertainty grows with sqrt(t) (random walk noise assumption)
        unc = sigma * np.sqrt(t)
        if use_returns and abs(last_value) > 1e-12:
            unc /= abs(last_value)
        uncertainty[t - 1] = unc

    return KoopmanForecast(
        trajectory=trajectory,
        uncertainty=uncertainty,
    )
