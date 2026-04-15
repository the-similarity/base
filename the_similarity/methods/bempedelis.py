"""Bempedelis self-similarity transform.

Implements the core optimization from Bempedelis et al. 2025:
"Extracting self-similarity from data."

Given a time series q(s, t) observed at discrete times t_1..t_N,
find scaling functions alpha(t) and beta(t) such that the
rescaled series q_tilde(xi, t) = beta(t) * q(alpha(t) * s, t)
collapses onto a single curve for all t.

If alpha(t) and beta(t) follow power laws (alpha ~ t^a, beta ~ t^b),
the signal is genuinely self-similar. The R^2 of these power law fits
is the self-similarity quality score.

For pattern matching: given query Q and candidate C, we split each
into sub-windows and optimize alpha/beta to collapse them. If both
achieve high R^2, the same dynamical process generated both.

Mathematical Formulations & Optimizations:
- Core Intuition: Measures pure self-similarity structure. Evaluates if the time
  scaling function `alpha(t)` and amplitude scaling function `beta(t)` adhere to
  clean power laws (scoring via R^2 fit).
- Optimization Bounds: We attempt to collapse N subwindows onto a strict common
  coordinate plane. This uses `scipy.optimize.minimize` (L-BFGS-B).
- Random Restarts Constraint: The objective function here is highly non-convex
  and exceptionally prone to local minima when encountering noisy signal variants.
  Random restarts with variable `x0` initial parameters are algorithmically mandatory.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.interpolate import interp1d


@dataclass
class BempedelisResult:
    """Result of self-similarity transform."""

    alpha: NDArray[np.float64]  # time-scaling vector, shape (n_subwindows,)
    beta: NDArray[np.float64]  # value-scaling vector, shape (n_subwindows,)
    power_law_r2: float  # R^2 of power law fit to alpha, beta
    alpha_r2: float  # R^2 of power law fit to alpha alone
    beta_r2: float  # R^2 of power law fit to beta alone
    smoothness: float  # 1 - normalized total variation (0=jagged, 1=smooth)
    residual: float  # optimization residual (lower = better collapse)
    score: float  # combined self-similarity score in [0, 1]


def self_similarity_transform(
    series: NDArray[np.float64],
    n_subwindows: int = 5,
    n_restarts: int = 3,
) -> BempedelisResult:
    """Compute the Bempedelis self-similarity transform of a series.

    Splits the series into n_subwindows equal sub-windows, then optimizes
    alpha(t) and beta(t) to minimize the pairwise distance between
    rescaled sub-windows.

    Args:
        series: 1D array (already normalized to log-returns or similar).
        n_subwindows: Number of sub-windows to split into. Must be >= 2.
        n_restarts: Number of random restarts for the optimizer.

    Returns:
        BempedelisResult with alpha, beta, R^2, smoothness, and score.
    """
    series = np.asarray(series, dtype=np.float64)
    if n_subwindows < 2:
        raise ValueError("n_subwindows must be >= 2")

    # Split series into sub-windows of equal length
    sub_len = len(series) // n_subwindows
    if sub_len < 3:
        raise ValueError(
            f"Series too short ({len(series)}) for {n_subwindows} sub-windows"
        )

    subwindows = []
    for k in range(n_subwindows):
        start = k * sub_len
        subwindows.append(series[start : start + sub_len])
    subwindows = np.array(subwindows)  # (n_subwindows, sub_len)

    # Reference coordinate: normalized [0, 1]
    s_ref = np.linspace(0, 1, sub_len)

    # Optimize: find alpha_k, beta_k for each sub-window k
    # such that beta_k * q_k(alpha_k * s) collapses to a common curve
    #
    # Parameters: [alpha_1..alpha_N, beta_1..beta_N]
    # We fix alpha_0 = 1, beta_0 = 1 to remove scale ambiguity.
    # So free parameters: (n_subwindows - 1) alphas + (n_subwindows - 1) betas

    n_free = n_subwindows - 1
    n_params = 2 * n_free

    def objective(params: NDArray) -> float:
        alpha = np.empty(n_subwindows)
        beta = np.empty(n_subwindows)
        alpha[0] = 1.0
        beta[0] = 1.0
        alpha[1:] = params[:n_free]
        beta[1:] = params[n_free:]

        rescaled = _rescale_subwindows(subwindows, s_ref, alpha, beta)
        return _pairwise_collapse_error(rescaled)

    # Bounds: alpha in [0.1, 10], beta in [-10, 10]
    bounds = (
        [(0.1, 10.0)] * n_free  # alpha bounds
        + [(-10.0, 10.0)] * n_free  # beta bounds
    )

    best_result = None
    best_cost = np.inf

    for restart in range(n_restarts):
        if restart == 0:
            # Start with identity: all alpha=1, beta=1
            x0 = np.ones(n_params)
        else:
            # Random start
            rng = np.random.default_rng(seed=restart)
            x0 = np.concatenate(
                [
                    rng.uniform(0.5, 2.0, n_free),  # alpha
                    rng.uniform(0.5, 2.0, n_free),  # beta
                ]
            )

        result = minimize(
            objective,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-10},
        )

        if result.fun < best_cost:
            best_cost = result.fun
            best_result = result

    # Extract best alpha, beta
    alpha = np.empty(n_subwindows)
    beta = np.empty(n_subwindows)
    alpha[0] = 1.0
    beta[0] = 1.0
    alpha[1:] = best_result.x[:n_free]
    beta[1:] = best_result.x[n_free:]

    # Evaluate how well alpha and beta profiles follow an exponential power law.
    # We fit a log-log regression to (time, scaling factor)
    t = np.arange(1, n_subwindows + 1, dtype=np.float64)
    alpha_r2 = _power_law_r2(t, np.abs(alpha))
    beta_r2 = _power_law_r2(t, np.abs(beta))
    power_law_r2 = (alpha_r2 + beta_r2) / 2.0

    smoothness = _smoothness_score(alpha, beta)

    # Combined score: high R^2 + smooth + low residual
    residual_score = float(np.exp(-best_cost))
    score = 0.5 * power_law_r2 + 0.3 * smoothness + 0.2 * residual_score

    return BempedelisResult(
        alpha=alpha,
        beta=beta,
        power_law_r2=power_law_r2,
        alpha_r2=alpha_r2,
        beta_r2=beta_r2,
        smoothness=smoothness,
        residual=best_cost,
        score=score,
    )


def bempedelis_match(
    query: NDArray[np.float64],
    candidate: NDArray[np.float64],
    n_subwindows: int = 5,
    n_restarts: int = 3,
) -> tuple[BempedelisResult, BempedelisResult, float, float]:
    """Compare two series via self-similarity transform.

    Runs the transform on both query and candidate independently.
    If both have high R^2, they share the same self-similar structure.

    Args:
        query: Normalized query window.
        candidate: Normalized candidate window (can be different length).
        n_subwindows: Sub-windows per series.
        n_restarts: Optimization restarts.

    Returns:
        (query_result, candidate_result, r2_score, smoothness_score)
        where r2_score and smoothness_score are the geometric means
        of the two transforms' scores, each in [0, 1].
    """
    q_result = self_similarity_transform(query, n_subwindows, n_restarts)
    c_result = self_similarity_transform(candidate, n_subwindows, n_restarts)

    # Both windows should be self-similar, but they should also induce similar
    # alpha/beta transform profiles. Otherwise two unrelated self-similar
    # processes could rank highly just because each one is individually smooth.
    transform_similarity = _transform_similarity(q_result, c_result)
    r2_score = float(
        np.sqrt(max(0, q_result.power_law_r2) * max(0, c_result.power_law_r2))
        * transform_similarity
    )
    smoothness_score = float(
        np.sqrt(max(0, q_result.smoothness) * max(0, c_result.smoothness))
        * transform_similarity
    )

    return q_result, c_result, r2_score, smoothness_score


def _rescale_subwindows(
    subwindows: NDArray[np.float64],
    s_ref: NDArray[np.float64],
    alpha: NDArray[np.float64],
    beta: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Apply alpha/beta rescaling to each sub-window.

    q_tilde_k(s) = beta_k * q_k(alpha_k * s)

    When alpha_k != 1, this stretches/compresses the time axis.
    We use interpolation to resample onto the reference grid.
    """
    n_sub, sub_len = subwindows.shape
    rescaled = np.empty_like(subwindows)

    for k in range(n_sub):
        # Original coordinate for sub-window k
        s_orig = np.linspace(0, 1, sub_len)
        # Rescaled coordinate: we want values at alpha_k * s_ref
        s_query = np.clip(alpha[k] * s_ref, 0, 1)

        interp = interp1d(
            s_orig, subwindows[k], kind="linear", fill_value="extrapolate"
        )
        rescaled[k] = beta[k] * interp(s_query)

    return rescaled


def _pairwise_collapse_error(rescaled: NDArray[np.float64]) -> float:
    """Sum of squared pairwise differences between rescaled sub-windows.

    This is the objective function for L-BFGS-B: if all sub-windows collapse to the
    same curve, this is exactly zero. It measures the quality of the collapse.
    """
    n = rescaled.shape[0]
    total = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            diff = rescaled[i] - rescaled[j]
            total += float(np.sum(diff**2))
    # Normalize by number of pairs and window length
    n_pairs = n * (n - 1) / 2
    return total / (n_pairs * rescaled.shape[1])


def _power_law_r2(t: NDArray[np.float64], values: NDArray[np.float64]) -> float:
    """Fit power law values = c * t^exponent via log-log regression, return R^2.

    Args:
        t: Independent variable (e.g., sub-window indices 1..N).
        values: Dependent variable (alpha or |beta|).

    Returns:
        R^2 of the log-log linear fit. Clamped to [0, 1].
    """
    # Guard against log(0)
    v = np.maximum(np.abs(values), 1e-12)
    log_t = np.log(t)
    log_v = np.log(v)

    # Linear regression in log-log space
    n = len(t)
    if n < 2:
        return 0.0

    mean_lt = np.mean(log_t)
    mean_lv = np.mean(log_v)
    ss_tot = np.sum((log_v - mean_lv) ** 2)
    if ss_tot < 1e-15:
        return 1.0  # constant = perfect power law with exponent 0

    ss_xy = np.sum((log_t - mean_lt) * (log_v - mean_lv))
    ss_xx = np.sum((log_t - mean_lt) ** 2)
    if ss_xx < 1e-15:
        return 0.0

    slope = ss_xy / ss_xx
    intercept = mean_lv - slope * mean_lt
    predicted = intercept + slope * log_t
    ss_res = np.sum((log_v - predicted) ** 2)

    r2 = 1.0 - ss_res / ss_tot
    return float(np.clip(r2, 0.0, 1.0))


def _smoothness_score(alpha: NDArray, beta: NDArray) -> float:
    """Score how smooth alpha(t) and beta(t) are.

    Uses total variation: smoother curves = less variation = higher score.
    Returns a value in [0, 1] where 1 = perfectly smooth.
    """

    def _tv_score(v: NDArray) -> float:
        if len(v) < 2:
            return 1.0
        tv = np.sum(np.abs(np.diff(v)))
        # Normalize by range
        rng = np.max(np.abs(v)) - np.min(np.abs(v))
        if rng < 1e-12:
            return 1.0
        # TV / range gives a rough measure; for a monotone function TV/range = 1
        normalized = tv / (rng * (len(v) - 1))
        return float(np.clip(1.0 - normalized, 0.0, 1.0))

    return (_tv_score(alpha) + _tv_score(beta)) / 2.0


def _transform_similarity(
    query_result: BempedelisResult,
    candidate_result: BempedelisResult,
) -> float:
    """Compare the learned transform profiles for two windows.

    The self-similarity transform is only useful for matching if the query and
    candidate collapse in comparable ways. We compare the alpha and |beta|
    trajectories after standardization so the score favors structurally similar
    transforms instead of merely rewarding two separately self-similar signals.
    """
    alpha_similarity = _profile_similarity(query_result.alpha, candidate_result.alpha)
    beta_similarity = _profile_similarity(
        np.abs(query_result.beta),
        np.abs(candidate_result.beta),
    )
    return 0.5 * alpha_similarity + 0.5 * beta_similarity


def _profile_similarity(
    left: NDArray[np.float64],
    right: NDArray[np.float64],
) -> float:
    if len(left) != len(right):
        size = min(len(left), len(right))
        left = left[:size]
        right = right[:size]

    left_std = np.std(left)
    right_std = np.std(right)
    if left_std < 1e-12 or right_std < 1e-12:
        mse = float(np.mean((left - right) ** 2))
        return float(np.exp(-mse))

    left_norm = (left - np.mean(left)) / left_std
    right_norm = (right - np.mean(right)) / right_std
    corr = np.corrcoef(left_norm, right_norm)[0, 1]
    if np.isnan(corr):
        corr = 0.0
    mse = float(np.mean((left_norm - right_norm) ** 2))
    corr_score = max(0.0, (corr + 1.0) / 2.0)
    mse_score = float(np.exp(-mse))
    return 0.5 * corr_score + 0.5 * mse_score
