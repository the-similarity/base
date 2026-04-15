from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def delay_embed(
    series: NDArray[np.float64],
    dim: int,
    lag: int,
) -> NDArray[np.float64]:
    """Construct a Takens delay embedding matrix.

    Each row is [x(t), x(t - lag), x(t - 2*lag), ..., x(t - (dim-1)*lag)].

    Args:
        series: 1-D time series array.
        dim: Embedding dimension (number of columns).
        lag: Time delay between successive coordinates.

    Returns:
        2-D array of shape (n - (dim - 1) * lag, dim).
    """
    series = np.asarray(series, dtype=np.float64).ravel()
    n = len(series)
    num_rows = n - (dim - 1) * lag
    if num_rows <= 0:
        raise ValueError(
            f"Series too short ({n}) for dim={dim}, lag={lag}. "
            f"Need at least {(dim - 1) * lag + 1} points."
        )
    # Build index matrix: each row picks dim elements spaced by lag
    row_indices = np.arange(num_rows)[:, None]  # (num_rows, 1)
    col_offsets = np.arange(dim)[None, :] * lag  # (1, dim)
    # Offset from the end so row i corresponds to time t = (dim-1)*lag + i
    indices = row_indices + (dim - 1) * lag - col_offsets  # (num_rows, dim)
    return series[indices]


def auto_lag(series: NDArray[np.float64], max_lag: int | None = None) -> int:
    """Estimate optimal delay lag via time-delayed mutual information.

    Uses histogram-based MI estimation. Falls back to first zero-crossing
    of autocorrelation if MI fails to find a minimum.

    Result is clamped to [1, len(series) // 4].

    Args:
        series: 1-D time series.
        max_lag: Maximum lag to consider. Defaults to len(series) // 4.

    Returns:
        Optimal integer lag >= 1.
    """
    series = np.asarray(series, dtype=np.float64).ravel()
    n = len(series)
    upper = max(1, n // 4)
    if max_lag is not None:
        upper = min(upper, max_lag)

    if n < 4:
        return 1

    # --- Histogram-based mutual information ---
    n_bins = max(4, int(np.sqrt(n / 5)))
    mi_values = np.empty(upper + 1)
    mi_values[0] = np.inf  # lag=0 is trivially maximal; skip

    for tau in range(1, upper + 1):
        x = series[: n - tau]
        y = series[tau:]
        # Joint and marginal histograms
        hist_xy, _, _ = np.histogram2d(x, y, bins=n_bins)
        pxy = hist_xy / hist_xy.sum()
        px = pxy.sum(axis=1)
        py = pxy.sum(axis=0)
        # MI = sum p(x,y) * log(p(x,y) / (p(x)*p(y)))
        mask = pxy > 0
        mi = np.sum(pxy[mask] * np.log(pxy[mask] / (px[:, None] * py[None, :])[mask]))
        mi_values[tau] = mi

    # First local minimum of MI
    for tau in range(2, upper):
        if mi_values[tau] < mi_values[tau - 1] and mi_values[tau] <= mi_values[tau + 1]:
            return int(np.clip(tau, 1, upper))

    # --- Fallback: first zero-crossing of autocorrelation ---
    centered = series - np.mean(series)
    var = np.dot(centered, centered)
    if var == 0:
        return 1
    for tau in range(1, upper + 1):
        acf = np.dot(centered[: n - tau], centered[tau:]) / var
        if acf <= 0:
            return int(np.clip(tau, 1, upper))

    return max(1, upper)


def auto_dim(
    series: NDArray[np.float64],
    lag: int,
    max_dim: int = 15,
) -> int:
    """Estimate embedding dimension via False Nearest Neighbors (FNN).

    Increases dimension until the fraction of false nearest neighbors
    drops below 2%.

    Args:
        series: 1-D time series.
        lag: Time delay (from :func:`auto_lag`).
        max_dim: Maximum dimension to try.

    Returns:
        Recommended embedding dimension in [2, max_dim].
    """
    series = np.asarray(series, dtype=np.float64).ravel()
    n = len(series)
    lag = max(1, lag)
    fallback = min(10, max(2, n // (3 * lag)))

    # Need enough points for meaningful neighbor search
    if n < (max_dim) * lag + 10:
        return int(np.clip(fallback, 2, max_dim))

    r_tol = 15.0  # standard FNN distance ratio threshold

    for d in range(1, max_dim):
        num_pts = n - d * lag
        if num_pts < 10:
            return int(np.clip(d, 2, max_dim))

        # Build embedding at dimension d
        embedded = delay_embed(series, d, lag)  # (num_pts_d, d)
        # Also need the (d+1)-th coordinate for FNN test
        num_pts_check = n - d * lag
        embedded_check = embedded[:num_pts_check]
        next_coord = series[d * lag : d * lag + num_pts_check]

        if len(embedded_check) < 10:
            return int(np.clip(d, 2, max_dim))

        # For efficiency, subsample if large
        n_check = len(embedded_check)
        if n_check > 500:
            indices = np.random.default_rng(42).choice(n_check, 500, replace=False)
        else:
            indices = np.arange(n_check)

        false_nn = 0
        total = 0

        for i in indices:
            # Find nearest neighbor (excluding self) via brute force
            diffs = embedded_check - embedded_check[i]
            dists = np.sqrt(np.sum(diffs**2, axis=1))
            dists[i] = np.inf
            nn_idx = np.argmin(dists)
            nn_dist = dists[nn_idx]

            if nn_dist < 1e-12:
                continue

            # Check if the neighbor is "false" — large jump in (d+1)-th coord
            extra_dist = abs(next_coord[i] - next_coord[nn_idx])
            if extra_dist / nn_dist > r_tol:
                false_nn += 1
            total += 1

        if total == 0:
            continue

        fnn_frac = false_nn / total
        if fnn_frac < 0.02:
            return int(np.clip(d, 2, max_dim))

    return int(np.clip(fallback, 2, max_dim))
