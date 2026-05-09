"""3D trajectory shape descriptors for the self-similarity primitive.

This module is the core of the 3D-trajectory MVP. It tests whether the
project's self-similarity primitive — analogue retrieval over invariant
shape descriptors followed by weighted forecast cones — generalizes
from 1D timeseries (price) and 2D heightmaps (terrain) to **3D paths**
(an agent's trajectory through space).

Mathematical foundation
-----------------------
For a smooth space curve gamma(s) parameterized by arc length s, the
Frenet-Serret apparatus gives two scalar invariants:

    kappa(s) = ||gamma''(s)||                      (curvature)
    tau(s)   = -<B'(s), N(s)>                      (torsion)

where T = gamma' is the unit tangent, N = T'/||T'|| is the principal
normal, and B = T x N is the binormal. Together kappa and tau
**uniquely determine** the curve up to rigid motion (translation +
rotation). A planar curve has tau identically zero — torsion is the
shape signal that *requires* a third dimension.

For the discrete case (N sampled points along a path) this module:

1. **Resamples to uniform arc length.** Raw simulation data is sampled
   at uniform Delta-t (per-tick) but agents move at variable speed,
   so kappa/tau computed over Delta-t time steps are biased by speed.
   Chord-length re-parameterization removes this bias and yields
   shape-invariant descriptors.

2. **Computes discrete kappa, tau** via central finite differences of
   the tangent / binormal vectors. Standard formulas:
       T_i = (P_{i+1} - P_i) / ||P_{i+1} - P_i||
       kappa_i ~ ||T_{i+1} - T_i|| / Delta_s
       N_i = (T_{i+1} - T_i) / ||T_{i+1} - T_i||
       B_i = T_i x N_i
       tau_i ~ -<B_{i+1} - B_i, N_i> / Delta_s
   Degenerate frames (collinear triples, zero-length tangent
   differences) collapse to kappa=0 / tau=0 with a clear, documented
   convention rather than NaN propagation.

3. **Multiscale Gaussian smoothing** with sigma in {1, 4, 16}. The
   right "shape scale" is rarely known a priori; running the matcher
   at several smoothing levels and combining them is the standard
   move from the curve-matching literature.

4. **Bivariate DTW** between two (kappa, tau) sequences — each point
   is a 2-vector and the local cost is Euclidean. We implement a tiny
   bivariate DTW inline rather than coercing the existing
   `dtw_matcher.dtw_distance` (which is 1D-only via `dtaidistance`).
   The implementation is O(NM) which is fine for the corpus sizes we
   target (hundreds to thousands of windows of length ~50).

Lifecycles & invariants
-----------------------
- All inputs/outputs are :class:`numpy.ndarray` with dtype float64.
  We do not mutate inputs; resampling and smoothing both return fresh
  arrays.
- Functions are pure: identical inputs produce identical outputs.
  No global state, no caches.
- Empty / degenerate inputs (< 3 points, zero-length curves) raise
  ``ValueError`` rather than returning NaN — the caller is expected
  to filter out trivial windows upstream.
- The Gaussian kernel uses ``scipy.ndimage.gaussian_filter1d`` with
  reflective boundary handling so the descriptors near window edges
  are stable.

Why this is the right shape signal
----------------------------------
- **Translation-invariant**: kappa and tau depend only on derivatives,
  so adding a constant vector to every point leaves them unchanged.
- **Rotation-invariant**: orthogonal transformations preserve cross
  products and inner products of unit vectors.
- **Time-shift / reparameterization-invariant**: arc-length resampling
  removes per-tick speed; what remains is the geometric shape.
- **Scale-aware** (not scale-invariant): a circle of radius 2 has
  half the curvature of radius-1 circle. This is intentional —
  shape *and* size are both meaningful signals for retrieval.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import gaussian_filter1d


# ---------------------------------------------------------------------------
# Arc-length resampling
# ---------------------------------------------------------------------------


def arc_length_resample(
    points: NDArray[np.float64],
    n_samples: int,
) -> NDArray[np.float64]:
    """Resample a 3D polyline to ``n_samples`` points uniformly along arc length.

    Algorithm:
    1. Compute cumulative chord-length distance along the polyline.
    2. Build a uniform grid of n_samples target arc lengths in
       [0, total_length].
    3. Linearly interpolate each spatial coordinate against the
       cumulative distance grid.

    Parameters
    ----------
    points:
        ``(N, 3)`` float64 array of (x, y, z) samples. Must have
        ``N >= 2`` and at least two distinct points (non-zero total
        length); otherwise the caller is asking to resample a single
        point which is degenerate.
    n_samples:
        Number of points to produce. Must be >= 2.

    Returns
    -------
    ``(n_samples, 3)`` float64 array of evenly-spaced (in arc length)
    samples. The first and last samples coincide with the original
    polyline endpoints.

    Raises
    ------
    ValueError
        If the polyline has zero total length (all points coincident)
        or if ``n_samples < 2``.
    """
    if n_samples < 2:
        raise ValueError(f"n_samples must be >= 2, got {n_samples}")
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(
            f"points must be shape (N, 3); got {pts.shape}"
        )
    if pts.shape[0] < 2:
        raise ValueError(f"need >= 2 points to resample; got {pts.shape[0]}")

    # Chord lengths between consecutive samples; cumulative sum is the
    # piecewise-linear arc length. The first cumulative entry is 0 so
    # the grid maps cleanly to original-index coordinates at t=0.
    diffs = np.diff(pts, axis=0)
    seg_lens = np.linalg.norm(diffs, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg_lens)])
    total = cum[-1]
    if total <= 0.0:
        raise ValueError("polyline has zero total length (all points coincident)")

    # Uniform target arc-length grid. We use n_samples points so the
    # output's first / last entries match the polyline endpoints
    # exactly (no extrapolation).
    targets = np.linspace(0.0, total, n_samples)

    # np.interp is 1D; loop over coordinate axes. The loop is over a
    # tiny constant (3) so vectorizing further would not pay off.
    out = np.empty((n_samples, 3), dtype=np.float64)
    for axis in range(3):
        out[:, axis] = np.interp(targets, cum, pts[:, axis])
    return out


# ---------------------------------------------------------------------------
# Frenet descriptors (curvature + torsion)
# ---------------------------------------------------------------------------


def _safe_normalize(v: NDArray[np.float64], eps: float = 1e-12) -> NDArray[np.float64]:
    """Return v / ||v||, or the zero vector when ||v|| < eps.

    Used everywhere a unit vector is needed. The eps guard avoids
    NaN propagation through the Frenet pipeline when a segment is
    degenerate (e.g. two consecutive samples coincide); by returning
    zero we let the downstream curvature/torsion fall to zero
    naturally rather than poisoning the rest of the array.
    """
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    out = np.zeros_like(v)
    mask = (n.squeeze(-1) > eps) if v.ndim > 1 else (n.item() > eps)
    if v.ndim == 1:
        return v / n.item() if mask else out
    np.divide(v, np.where(n > eps, n, 1.0), out=out, where=(n > eps))
    return out


def frenet_descriptors(
    points: NDArray[np.float64],
    sigma: float = 0.0,
) -> Tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Compute discrete (curvature, torsion) along a 3D polyline.

    The polyline is assumed to be **already arc-length resampled**
    (call :func:`arc_length_resample` first). This function does NOT
    re-parameterize internally because the caller may want to control
    the sample count and reuse the resampled points elsewhere.

    Discrete formulas (uniform arc-length spacing Delta_s):
        diff_i = P_{i+1} - P_i                    (i = 0 .. N-2)
        T_i    = diff_i / ||diff_i||              (unit tangent)
        dT_i   = T_{i+1} - T_i                    (i = 0 .. N-3)
        kappa_i = ||dT_i|| / Delta_s
        N_i     = dT_i / ||dT_i||                 (principal normal)
        B_i     = T_i x T_{i+1}, normalized       (binormal)
        dB_i    = B_{i+1} - B_i                   (i = 0 .. N-4)
        tau_i   = -<dB_i, N_i> / Delta_s

    Output convention: ``kappa`` and ``tau`` are returned with the
    SAME length N as the input. Indices that fall outside the
    finite-difference support (typically the last 1-3 entries) are
    filled by edge-replication so downstream consumers (DTW) do not
    have to handle ragged arrays. This is a deliberate trade-off:
    the very last samples carry less information but never bias the
    sequence length, which keeps the matcher aligned.

    Parameters
    ----------
    points:
        ``(N, 3)`` float64 array; expected to be arc-length resampled
        with uniform Delta_s.
    sigma:
        Optional Gaussian smoothing scale (in samples) applied to the
        kappa and tau arrays. ``sigma=0`` means no smoothing. Useful
        because raw discrete kappa is noisy near sharp turns.

    Returns
    -------
    (kappa, tau):
        Two ``(N,)`` float64 arrays. Both are non-negative? No — kappa
        is non-negative (it is a magnitude), tau is signed.

    Notes on the sign of torsion
    ----------------------------
    Torsion is signed: positive tau means the curve is twisting in
    the right-handed sense relative to its tangent direction. For
    rigid-motion *invariance with respect to reflection* the user
    would need to take ``|tau|``; for a torus / heightmap world
    where there is no global handedness reversal the signed value
    carries useful directional information and is preferred.
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(f"points must be shape (N, 3); got {pts.shape}")
    n = pts.shape[0]
    if n < 4:
        raise ValueError(
            f"need >= 4 points for Frenet descriptors; got {n}"
        )

    # Per-segment vectors and their lengths. We compute Delta_s as the
    # mean segment length — for arc-length-resampled input this is
    # essentially constant, but using the mean stabilizes against
    # tiny numerical drift in the resampler.
    diffs = pts[1:] - pts[:-1]                     # shape (N-1, 3)
    seg_lens = np.linalg.norm(diffs, axis=1)       # shape (N-1,)
    delta_s = float(np.mean(seg_lens))
    if delta_s <= 0.0:
        raise ValueError("polyline has zero arc length")

    # Unit tangents. Where a segment is degenerate (zero length)
    # the tangent is zero so downstream kappa/tau pick up zero.
    safe_lens = np.where(seg_lens > 1e-12, seg_lens, 1.0)
    tangents = diffs / safe_lens[:, None]          # shape (N-1, 3)
    tangents[seg_lens <= 1e-12] = 0.0

    # Discrete tangent derivative (= curvature direction). Length N-2.
    dT = tangents[1:] - tangents[:-1]              # (N-2, 3)
    dT_norm = np.linalg.norm(dT, axis=1)           # (N-2,)

    kappa_short = dT_norm / delta_s                # (N-2,)
    # Principal normal: dT / ||dT|| where defined; zero where dT=0
    # (collinear triple). Returning zero keeps the binormal computation
    # well-defined (cross with zero -> zero) which propagates correctly.
    safe_dT = np.where(dT_norm[:, None] > 1e-12, dT_norm[:, None], 1.0)
    normals = dT / safe_dT                         # (N-2, 3)
    normals[dT_norm <= 1e-12] = 0.0

    # Binormal: T x T_next, then normalized. Using consecutive
    # tangents (rather than T x N) keeps the formula stable when
    # N is zero.
    cross = np.cross(tangents[:-1], tangents[1:])  # (N-2, 3)
    cross_norm = np.linalg.norm(cross, axis=1)
    safe_cn = np.where(cross_norm[:, None] > 1e-12, cross_norm[:, None], 1.0)
    binormals = cross / safe_cn                    # (N-2, 3)
    binormals[cross_norm <= 1e-12] = 0.0

    # Discrete binormal derivative. Length N-3.
    dB = binormals[1:] - binormals[:-1]            # (N-3, 3)

    # Torsion: tau_i = -<dB_i, N_i> / Delta_s. We dot dB against the
    # *aligned* normal (normals[:-1] has length N-3 to match dB).
    tau_short = -np.einsum("ij,ij->i", dB, normals[:-1]) / delta_s

    # Numerical guard: when consecutive tangents are nearly parallel
    # (kappa near zero, i.e. the curve is locally straight), the
    # binormal direction is ill-defined and the discrete dB jitters
    # randomly. The result is a "tau is wild on lines" failure mode
    # where a noisy-straight trajectory looks more torsioned than a
    # clean helix.
    #
    # Mitigation: zero out tau where the local cross-product
    # magnitude (which equals |T_i x T_{i+1}| = sin(angle), an exact
    # surrogate for local kappa magnitude) is below a small
    # threshold. The threshold is in the *unitless* domain of
    # tangent cross-products, so it transfers across sample
    # spacings without rescaling.
    cross_mag_aligned = cross_norm[:tau_short.shape[0]]
    # 0.02 corresponds to a turning angle of ~1.1 degrees per step
    # — below that, position noise dominates the geometry signal
    # and tau cannot be trusted. Empirically this is the cleanest
    # cutoff that still preserves real torsion on helices
    # (whose cross_mag is ~0.05+ at our default sigma).
    straight_mask = cross_mag_aligned < 0.02
    tau_short = np.where(straight_mask, 0.0, tau_short)

    # Pad kappa to length N by edge-replication. Indices [0, N-3] are
    # the directly-computed values; the last 2 entries replicate the
    # final value. This keeps array shapes uniform across callers.
    kappa = np.empty(n, dtype=np.float64)
    kappa[:n - 2] = kappa_short
    if n >= 3:
        kappa[n - 2:] = kappa_short[-1]

    tau = np.empty(n, dtype=np.float64)
    tau[:n - 3] = tau_short
    if n - 3 >= 1:
        tau[n - 3:] = tau_short[-1]
    else:
        tau[:] = 0.0

    if sigma > 0.0:
        # Reflective boundary so the smoothed values don't pull toward
        # zero at the window edges (which would bias short-window
        # descriptors).
        kappa = gaussian_filter1d(kappa, sigma=sigma, mode="reflect")
        tau = gaussian_filter1d(tau, sigma=sigma, mode="reflect")

    return kappa, tau


def multiscale_descriptors(
    points: NDArray[np.float64],
    sigmas: List[float] | None = None,
) -> Dict[float, Tuple[NDArray[np.float64], NDArray[np.float64]]]:
    """Compute (kappa, tau) at multiple Gaussian smoothing scales.

    Returns a dict ``{sigma: (kappa_sigma, tau_sigma)}``. The default
    sigma list is ``[1.0, 4.0, 16.0]`` — order-of-magnitude spacing
    that covers fine-detail, mid-scale, and coarse-shape signals.

    The right scale is rarely known a priori for a brand-new domain
    like agent trajectories; storing all three lets the matcher
    decide which to weight (or fall back to the most informative one
    in the backtest).
    """
    if sigmas is None:
        sigmas = [1.0, 4.0, 16.0]
    out: Dict[float, Tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
    for s in sigmas:
        out[float(s)] = frenet_descriptors(points, sigma=s)
    return out


# ---------------------------------------------------------------------------
# Bivariate DTW on (kappa, tau) sequences
# ---------------------------------------------------------------------------


def dtw_kt_distance(
    kt_a: NDArray[np.float64],
    kt_b: NDArray[np.float64],
    sakoe_chiba_radius: int | None = None,
) -> float:
    """Dynamic time warping distance between two (kappa, tau) sequences.

    Each input is shape ``(N, 2)`` — column 0 is curvature, column 1
    is torsion. The local cost is plain Euclidean distance between
    2-vectors. The accumulated cost is the standard DTW recurrence:

        D[i, j] = c[i, j] + min(D[i-1, j], D[i, j-1], D[i-1, j-1])

    with the edge convention D[0, 0] = c[0, 0] (no warping at the
    start) and D[i, j] = +inf outside the Sakoe-Chiba band when one
    is supplied.

    Why bivariate-inline (not extending dtw_matcher.dtw_distance)?
    -------------------------------------------------------------
    The existing `dtw_matcher` wraps the C-level ``dtaidistance.dtw``
    library which expects 1D sequences. Coercing 2D points into a
    1D representation (e.g. interleaved or summed) loses information
    that a true bivariate DTW preserves. The inline NumPy
    implementation below is O(NM) in time and memory; for our target
    window length K=50 that's 2500 cells, sub-millisecond per pair.

    Parameters
    ----------
    kt_a, kt_b:
        Float64 arrays of shape (N, 2). N must be > 0; arrays of
        different length are aligned by warping (that's the point).
    sakoe_chiba_radius:
        Optional band constraint on the warping path. ``None`` allows
        the path to wander arbitrarily, which is fine for short
        sequences and removes a tunable hyperparameter from the
        experiment.

    Returns
    -------
    Non-negative float — total warped Euclidean distance. Note this
    is not normalized by path length; the caller can divide by
    ``len(kt_a) + len(kt_b)`` to get a per-step average if desired.
    """
    a = np.asarray(kt_a, dtype=np.float64)
    b = np.asarray(kt_b, dtype=np.float64)
    if a.ndim != 2 or a.shape[1] != 2:
        raise ValueError(f"kt_a must be (N, 2); got {a.shape}")
    if b.ndim != 2 or b.shape[1] != 2:
        raise ValueError(f"kt_b must be (M, 2); got {b.shape}")

    n, m = a.shape[0], b.shape[0]
    if n == 0 or m == 0:
        raise ValueError("DTW requires non-empty sequences")

    # Pairwise local costs: c[i, j] = ||a[i] - b[j]||. Use broadcasting
    # for a vectorized O(NM) build; for the sequence lengths we target
    # (N, M ~ 50) this stays well under a millisecond.
    diff = a[:, None, :] - b[None, :, :]           # (N, M, 2)
    cost = np.sqrt(np.sum(diff * diff, axis=-1))   # (N, M)

    # Accumulated cost matrix. Initialize to +inf so the boundary
    # conditions fall out of the standard min(...) recurrence.
    D = np.full((n, m), np.inf, dtype=np.float64)
    D[0, 0] = cost[0, 0]

    # Sakoe-Chiba band: only fill cells within `radius` of the
    # diagonal. When unset, every cell is in-band.
    radius = sakoe_chiba_radius if sakoe_chiba_radius is not None else max(n, m)

    for i in range(n):
        # Inner-loop bounds tightened by the band so the runtime is
        # O(N * radius) when radius << M.
        j_lo = max(0, i - radius) if i > 0 else 0
        j_hi = min(m, i + radius + 1)
        for j in range(j_lo, j_hi):
            if i == 0 and j == 0:
                continue
            best = np.inf
            if i > 0:
                best = min(best, D[i - 1, j])
            if j > 0:
                best = min(best, D[i, j - 1])
            if i > 0 and j > 0:
                best = min(best, D[i - 1, j - 1])
            D[i, j] = cost[i, j] + best

    return float(D[n - 1, m - 1])


__all__ = [
    "arc_length_resample",
    "frenet_descriptors",
    "multiscale_descriptors",
    "dtw_kt_distance",
]
