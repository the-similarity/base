"""Matrix-profile baseline forecaster (STUMPY wrapper, numpy fallback).

Matrix profile is a fast nearest-neighbour distance computation over a
sliding window. We use it as a "nearest neighbour analog" forecast:

1. Set the query to the last ``window_size`` bars of train, where
   window_size = min(2 * seasonality, len(train) // 4).
2. Compute the matrix profile of train against itself.
3. Pick the top-K=5 motifs (lowest distance, NOT overlapping the query
   tail) using ``stumpy.motifs``.
4. For each motif, extract the ``horizon`` bars that immediately
   follow it. Drop motifs without enough room.
5. Return per-bar P10/P50/P90 across the K continuations.

This is the most natural "minimal analog forecaster" against which the
9-method engine should compete: same retrieval intuition, but with a
single distance metric (z-normalised Euclidean) and no fancy ranking.

STUMPY default config (we deliberately do not tune):
    - ``stumpy.stump`` defaults: z-normalised Euclidean distance, no
      exclusion zone overrides, no GPU.
    - ``stumpy.motifs`` defaults: ``cutoff=np.inf`` → take the K
      lowest-distance motifs even if they're loose. Matches the
      "default config" rule.
"""

from __future__ import annotations

import numpy as np

from benchmarks.core import Forecast


class MatrixProfile:
    """STUMPY-backed nearest-neighbour analog forecaster."""

    name = "matrix_profile"

    # Number of motifs we average per bar. Five is the standard "top
    # motifs" choice in MP literature; small enough to still expose
    # variance, large enough to smooth single-motif noise.
    top_k = 5

    def forecast(
        self,
        train: np.ndarray,
        horizon: int,
        seasonality: int,
    ) -> Forecast:
        """Top-K motif continuation forecast.

        Falls back to a degenerate last-value forecast when the train
        series is too short to admit even one motif of the chosen
        window. The runner still scores it so the report layer can
        flag the affected series.
        """
        # Try STUMPY first (preferred — vetted, fast). Fall back to a
        # pure-numpy MASS when the native stumpy stack (numba/llvmlite)
        # cannot load — common on macOS conda envs without a working
        # libllvmlite.dylib. The numpy fallback is slower but
        # mathematically identical and dependency-free.
        mass_fn = _resolve_mass_function()

        train = np.asarray(train, dtype=np.float64)
        n = len(train)

        # Choose a window size large enough to span ~2 seasonal cycles
        # (so the motif captures structure, not just noise) but small
        # enough that we can fit at least four non-overlapping
        # candidates in train. ``len(train) // 4`` is a coarse upper
        # bound borrowed from the MP/Discord literature.
        window_size = min(2 * seasonality, n // 4)
        # Need at least: window + horizon room in train for one
        # continuation, plus enough total length for the distance
        # profile to be defined (n >= 2 * window).
        if window_size < 4 or n < 2 * window_size + horizon:
            return self._degenerate_forecast(train, horizon)

        # We want the K nearest neighbours of the LAST window in train
        # (the "query tail"). Their indices into the distance profile
        # are the candidate analog start positions. The number of
        # subsequence start positions of length window_size in train
        # is (n - window_size + 1).
        query_idx = n - window_size  # start index of the query tail
        valid_starts: list[int] = []
        for i in range(n - window_size + 1):
            if i + window_size + horizon > n:
                continue
            # Exclusion zone: avoid trivial overlap with the query.
            if abs(i - query_idx) < window_size:
                continue
            valid_starts.append(i)

        if not valid_starts:
            return self._degenerate_forecast(train, horizon)

        # Distance profile: z-normalised Euclidean distance of the
        # query tail against every length-``window_size`` subsequence
        # of train. Length is (n - window_size + 1).
        query_tail = train[query_idx:]
        distances = mass_fn(query_tail, train)

        valid_arr = np.array(valid_starts)
        valid_distances = distances[valid_arr]
        # argsort ascending → smallest distances first (best matches).
        order = np.argsort(valid_distances)
        chosen_starts = valid_arr[order[: self.top_k]]
        if len(chosen_starts) == 0:
            return self._degenerate_forecast(train, horizon)

        # Extract the ``horizon`` bars after each motif window's end.
        continuations = np.stack(
            [train[s + window_size : s + window_size + horizon] for s in chosen_starts],
            axis=0,
        )  # shape: (k, horizon)

        # Per-bar quantiles across motifs. With k=5 the empirical
        # quantile is coarse, but matches the "minimal MP forecaster"
        # spirit. numpy uses linear interpolation between observations
        # by default, which is fine for this baseline.
        p10 = np.quantile(continuations, 0.10, axis=0)
        p50 = np.quantile(continuations, 0.50, axis=0)
        p90 = np.quantile(continuations, 0.90, axis=0)

        return Forecast(
            p10=p10.astype(np.float64),
            p50=p50.astype(np.float64),
            p90=p90.astype(np.float64),
        )

    @staticmethod
    def _degenerate_forecast(train: np.ndarray, horizon: int) -> Forecast:
        """Fallback when the train series is too short for matrix profile.

        We still return a valid Forecast (constant last-value) so the
        runner can score and the report can flag the series. Failing
        loudly here would create reporting gaps that look like coverage
        bugs.
        """
        last = float(train[-1]) if len(train) > 0 else 0.0
        flat = np.full(horizon, last, dtype=np.float64)
        return Forecast(p10=flat.copy(), p50=flat.copy(), p90=flat.copy())


# ---------------------------------------------------------------------------
# MASS distance-profile helpers
# ---------------------------------------------------------------------------
#
# MASS = Mueen's Algorithm for Similarity Search (Mueen 2017). Given a
# z-normalised query Q of length m and a time series T of length n,
# MASS returns the z-normalised Euclidean distance between Q and every
# length-m subsequence of T in O(n log n) via FFT.
#
# We try the STUMPY implementation first (faster on large inputs because
# numba JITs the inner loops). When STUMPY's native stack fails to load
# (e.g. macOS conda envs missing libllvmlite.dylib), we fall back to a
# pure-numpy MASS implementation. Identical math, slower for very long
# series but plenty fast for our 100-1000 bar benchmark windows.


def _resolve_mass_function():
    """Return the MASS implementation to use this run.

    Order of preference:
        1. ``stumpy.mass`` (modern STUMPY public API)
        2. ``stumpy.core.mass`` (older STUMPY internal path)
        3. ``_numpy_mass`` (dependency-free fallback)

    The resolver swallows ImportError AND OSError because STUMPY's
    transitive numba/llvmlite dependency loads native shared libraries
    at import time, and a broken dylib raises OSError during ``import
    stumpy`` rather than ImportError.
    """
    try:
        import stumpy

        if hasattr(stumpy, "mass"):
            return stumpy.mass
        from stumpy import core as _core  # pragma: no cover - older STUMPY

        return _core.mass
    except (ImportError, OSError):
        return _numpy_mass


def _numpy_mass(query: np.ndarray, ts: np.ndarray) -> np.ndarray:
    """Pure-numpy z-normalised distance profile (no numba / FFT lib deps).

    For each length-``m`` subsequence T_i of ``ts`` (m = len(query)),
    returns the z-normalised Euclidean distance to ``query``. Output
    length is (len(ts) - m + 1).

    Math:
        Both query and each subsequence are z-normalised before the
        distance is taken. After z-normalisation, ||x|| = sqrt(m) for
        any window x, so the squared Euclidean distance simplifies to:

            D(Q, T_i)^2 = 2 * m * (1 - corr(Q, T_i))

        where ``corr`` is the Pearson correlation between Q and T_i.
        We compute the sliding correlation via the running mean / std
        of T (vectorised) and a single sliding dot-product. For our
        benchmark window sizes (m up to ~50, n up to a few thousand)
        the explicit dot product is faster than FFT convolution and
        avoids a scipy dependency.

    Numerical guards:
        - Subsequences with zero std produce a NaN correlation, which
          we coerce to a large finite distance (sqrt(2m)) so they are
          ranked LAST by the caller's ``argsort`` rather than crashing.
        - The sqrt argument is clamped to >= 0 to absorb tiny negatives
          from floating-point round-off in (1 - corr).
    """
    query = np.asarray(query, dtype=np.float64)
    ts = np.asarray(ts, dtype=np.float64)
    m = len(query)
    n = len(ts)
    if m == 0 or n < m:
        return np.array([], dtype=np.float64)

    # Z-normalise the query once.
    q_mean = float(query.mean())
    q_std = float(query.std())
    if q_std == 0.0:
        # Degenerate query — every distance is undefined. Return all
        # large-but-finite so the caller's ranking still works.
        return np.full(n - m + 1, np.sqrt(2.0 * m), dtype=np.float64)
    q_norm = (query - q_mean) / q_std

    # Sliding mean / std of ts via cumulative sums. This is O(n) and
    # avoids constructing a full (n - m + 1, m) window matrix, which
    # would blow up memory on the longer NN5 / SPY series.
    cs = np.concatenate(([0.0], np.cumsum(ts)))
    cs2 = np.concatenate(([0.0], np.cumsum(ts * ts)))
    s_sum = cs[m:] - cs[:-m]
    s_sum_sq = cs2[m:] - cs2[:-m]
    s_mean = s_sum / m
    # Variance via E[X^2] - E[X]^2. Clip at 0 to absorb round-off.
    s_var = np.maximum(s_sum_sq / m - s_mean * s_mean, 0.0)
    s_std = np.sqrt(s_var)

    # Sliding dot product of (z-normalised) query against raw ts. Using
    # numpy.lib.stride_tricks views the windows without copying. The
    # resulting dot is q_norm . T_i (raw, not z-normalised T_i).
    windows = np.lib.stride_tricks.sliding_window_view(ts, m)  # (n-m+1, m)
    dot = windows @ q_norm  # (n-m+1,)

    # Pearson correlation: corr(q_raw, T_i_raw) = (dot - m * q_mean * s_mean)
    # / (m * q_std * s_std). Because q_norm already absorbs (q - q_mean) /
    # q_std, the formula collapses to: corr = dot / (m * s_std).
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = dot / (m * s_std)
    # Subsequences with zero std → NaN correlation. Replace with -inf
    # so the resulting distance is the maximum (sqrt(2m * 2) = sqrt(4m)),
    # i.e. they sort last under argsort-ascending.
    corr = np.where(np.isfinite(corr), corr, -1.0)

    dist_sq = np.maximum(2.0 * m * (1.0 - corr), 0.0)
    return np.sqrt(dist_sq)
