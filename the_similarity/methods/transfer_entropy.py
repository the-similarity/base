"""Transfer Entropy (TE) for measuring information transfer between windows.

Histogram-based estimation: discretize source/target into bins, then compute
TE = H(target_future | target_past) - H(target_future | target_past, source_past).

High TE means the source (match window) genuinely predicts the target (forward window).

Information Theoretic Causal Flow:
- Contextual Uniqueness: TE fundamentally diverges from standard pairwise metrics.
  It directly quantifies the Information Flow passing from the `candidate` sequence
  purely into its own deterministic `forward_window`, ignoring the `query` entirely.
- Distribution Estimation: Probability density operations rely exclusively on fast
  discretized integer histograms, enabling normalized Shannon Entropy calculations
  `H(X)` without costly kernel density overheads.
- Causal Determinism: High Transfer Entropy rigidly implies that the historically
  matched feature explicitly mitigated future sequence uncertainty, enforcing a
  structural cause-and-effect relationship rather than spurious alignment.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def _discretize(series: NDArray[np.float64], bins: int) -> NDArray[np.intp]:
    """Discretize a continuous series into integer bin indices."""
    mn, mx = series.min(), series.max()
    if mx - mn < 1e-12:
        return np.zeros(len(series), dtype=np.intp)
    edges = np.linspace(mn, mx, bins + 1)
    # np.digitize returns 1-based; clamp to [0, bins-1]
    return np.clip(np.digitize(series, edges[1:-1]), 0, bins - 1)


def _entropy_from_counts(counts: NDArray[np.float64]) -> float:
    """Shannon entropy from a counts array (any shape, flattened)."""
    c = counts.ravel().astype(np.float64)
    total = c.sum()
    if total == 0:
        return 0.0
    p = c[c > 0] / total
    return float(-np.sum(p * np.log2(p)))


def compute_transfer_entropy(
    source: NDArray[np.float64],
    target: NDArray[np.float64],
    lag: int = 1,
    bins: int = 8,
) -> float:
    """Compute normalized transfer entropy from source to target.

    TE = H(Y_future | Y_past) - H(Y_future | Y_past, X_past)
    Normalized by H(Y_future) to yield a value in [0, 1].

    Args:
        source: 1-D source time series (match window).
        target: 1-D target time series (forward window).
        lag: Number of time steps for the lag.
        bins: Number of histogram bins for discretization.

    Returns:
        Normalized transfer entropy in [0, 1].  0.0 for degenerate inputs.
    """
    source = np.asarray(source, dtype=np.float64).ravel()
    target = np.asarray(target, dtype=np.float64).ravel()

    min_len = lag + 1
    if len(source) < min_len or len(target) < min_len:
        return 0.0

    # Align lengths
    n = min(len(source), len(target))
    source = source[:n]
    target = target[:n]

    # Constant series check
    if np.ptp(source) < 1e-12 or np.ptp(target) < 1e-12:
        return 0.0

    # Discretize
    s = _discretize(source, bins)
    t = _discretize(target, bins)

    # Build lagged variables
    y_past = t[:-lag]
    y_future = t[lag:]
    x_past = s[:-lag]

    # Joint counts via histogramming tuples
    # H(Y_future)
    h_yf = _entropy_from_counts(np.bincount(y_future, minlength=bins))

    if h_yf < 1e-12:
        return 0.0

    # H(Y_future, Y_past)
    joint_yf_yp = np.zeros((bins, bins), dtype=np.float64)
    for yf, yp in zip(y_future, y_past):
        joint_yf_yp[yf, yp] += 1.0
    h_yf_yp = _entropy_from_counts(joint_yf_yp)

    # H(Y_past)
    h_yp = _entropy_from_counts(np.bincount(y_past, minlength=bins))

    # H(Y_future, Y_past, X_past)
    joint_yf_yp_xp = np.zeros((bins, bins, bins), dtype=np.float64)
    for yf, yp, xp in zip(y_future, y_past, x_past):
        joint_yf_yp_xp[yf, yp, xp] += 1.0
    h_yf_yp_xp = _entropy_from_counts(joint_yf_yp_xp)

    # H(Y_past, X_past)
    joint_yp_xp = np.zeros((bins, bins), dtype=np.float64)
    for yp, xp in zip(y_past, x_past):
        joint_yp_xp[yp, xp] += 1.0
    h_yp_xp = _entropy_from_counts(joint_yp_xp)

    # TE = H(Y_future, Y_past) + H(Y_past, X_past) - H(Y_past) - H(Y_future, Y_past, X_past)
    # Equivalent to H(Y_f | Y_p) - H(Y_f | Y_p, X_p)
    te = h_yf_yp + h_yp_xp - h_yp - h_yf_yp_xp

    # Clamp numerical noise
    te = max(te, 0.0)

    # Normalize by H(Y_future)
    return min(te / h_yf, 1.0)


def te_score(
    match_window: NDArray[np.float64],
    forward_window: NDArray[np.float64],
    lag: int = 1,
    bins: int = 8,
) -> float:
    """Score how much the match window predicts the forward window.

    Args:
        match_window: 1-D array — the historical pattern that was matched.
        forward_window: 1-D array — what happened after the match.
        lag: Lag for the TE computation.
        bins: Histogram bins for discretization.

    Returns:
        Normalized TE score in [0, 1].  High = match is genuinely predictive.
    """
    return compute_transfer_entropy(match_window, forward_window, lag=lag, bins=bins)
