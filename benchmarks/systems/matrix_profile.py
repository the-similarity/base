"""Matrix-profile baseline forecaster (STUMPY wrapper).

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
        # Lazy import — keeps STUMPY out of the import path for thin
        # installs that don't run the matrix-profile system.
        import stumpy

        train = np.asarray(train, dtype=np.float64)
        n = len(train)

        # Choose a window size large enough to span ~2 seasonal cycles
        # (so the motif captures structure, not just noise) but small
        # enough that we can fit at least four non-overlapping
        # candidates in train. ``len(train) // 4`` is a coarse upper
        # bound borrowed from the MP/Discord literature.
        window_size = min(2 * seasonality, n // 4)
        # Need at least: window + horizon room in train for one
        # continuation, plus enough total length for stumpy.stump to
        # run (stumpy requires len >= 2 * window).
        if window_size < 4 or n < 2 * window_size + horizon:
            return self._degenerate_forecast(train, horizon)

        # Compute the matrix profile of train against itself. This
        # returns an (n - m + 1, 4) array — see STUMPY docs.
        mp = stumpy.stump(train, m=window_size)

        # We want the K nearest neighbours of the LAST window in train
        # (the "query tail"). Their indices into the matrix profile
        # are the candidate analog start positions.
        query_idx = n - window_size  # start index of the query tail
        # Exclude positions that overlap the query tail itself OR that
        # don't have ``horizon`` bars after their END (otherwise we
        # cannot extract a continuation).
        valid_starts: list[int] = []
        for i in range(len(mp)):
            if i + window_size + horizon > n:
                continue
            # Exclusion zone: avoid trivial overlap with the query.
            if abs(i - query_idx) < window_size:
                continue
            valid_starts.append(i)

        if not valid_starts:
            return self._degenerate_forecast(train, horizon)

        # Rank candidates by distance to the query. Column 0 of mp is
        # the nearest-neighbour distance for each window — but we want
        # distance to the query specifically. Easiest: mass() the
        # query_tail against the whole series.
        query_tail = train[query_idx:]
        # ``stumpy.core.mass`` returns the z-normalised distance
        # profile of `query` over `T`. For STUMPY ≥1.11 this lives at
        # ``stumpy.mass``; we try the public path first, then fall
        # back to the internal one for older installs.
        try:
            distances = stumpy.mass(query_tail, train)
        except AttributeError:  # pragma: no cover - very old STUMPY
            from stumpy import core as _core

            distances = _core.mass(query_tail, train)

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
