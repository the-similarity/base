"""Trajectory corpus + analogue retrieval + 3D forecast cone.

This module is the second pillar of the 3D-trajectory MVP. Given a
collection of agent trajectories (each shape ``(T, 3)``), it:

1. Chops every trajectory into overlapping fixed-length windows of
   length ``window_len`` with a configurable stride. For each window
   it stores the raw (x, y, z) points, the Frenet (kappa, tau)
   descriptor, and the next ``J`` future points (the "continuation").
2. Builds a SAX-like discretized signature over (kappa, tau) for
   cheap prefiltering.
3. On query: prefilter -> bivariate DTW over the (kappa, tau)
   descriptors -> rank by similarity -> return top-N analogues.
4. Forecast cone: weighted aggregation of the analogues' future
   continuations, computed *per axis* (x, y, z independently) so
   the returned per-axis quantile curves form a 3D probabilistic
   forecast cone.

Why per-axis quantiles (rather than a 3D ellipsoid)?
----------------------------------------------------
The existing :func:`the_similarity.core.projector._weighted_quantile`
works on 1D values. Calling it three times — once per axis — gives
us a triple of (P10, P50, P90) curves that together describe an
axis-aligned bounding box around the forecast cone. A true 3D
covariance ellipsoid would be more expressive but also more
sensitive to small N; the bounding box is robust and falls out of
the existing infrastructure for free.

Lifecycles & invariants
-----------------------
- A :class:`TrajectoryCorpus` is built once and treated as immutable.
  Re-indexing requires a new instance.
- Window descriptors are pre-computed at corpus build time so query
  time is dominated by the per-candidate DTW on shortlist
  candidates only.
- Trajectories with fewer than ``window_len + forward_bars`` ticks
  contribute zero windows (the window must have a full continuation
  for the projector to use it). This is fail-closed: short paths
  are silently dropped rather than producing forecasts with nothing
  to predict against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import gaussian_filter1d

from the_similarity.core.projector import _weighted_quantile
from the_similarity.methods.sax_filter import sax_transform
from the_similarity.methods.trajectory_3d import (
    arc_length_resample,
    dtw_kt_distance,
    frenet_descriptors,
)


def _smooth_points(
    points: NDArray[np.float64], sigma_pos: float
) -> NDArray[np.float64]:
    """Per-axis Gaussian smoothing of a 3D polyline.

    Position smoothing is the right place to handle simulation /
    measurement noise. Without it, the discrete second-derivative
    in the Frenet pipeline amplifies tiny Cartesian jitters into
    huge spurious curvatures (a noisy line ends up with kappa values
    larger than a clean helix). Smoothing positions before computing
    descriptors keeps the analytical invariants intact (a clean
    helix still has its closed-form kappa) while suppressing noise.

    Reflective boundaries match the boundary handling in
    :func:`frenet_descriptors` so the two passes compose cleanly.
    """
    if sigma_pos <= 0.0:
        return points
    return np.column_stack(
        [
            gaussian_filter1d(points[:, axis], sigma=sigma_pos, mode="reflect")
            for axis in range(3)
        ]
    )


# ---------------------------------------------------------------------------
# Corpus + window record
# ---------------------------------------------------------------------------


@dataclass
class TrajectoryWindow:
    """A single window extracted from a trajectory plus its descriptor.

    Fields
    ------
    trajectory_id:
        ID of the source trajectory (e.g. agent id). Useful for
        avoiding self-matches in cross-validation.
    start_idx:
        Index of the first point in the window (within the source
        trajectory).
    points:
        ``(window_len, 3)`` raw (x, y, z) samples.
    kt:
        ``(window_len, 2)`` Frenet (kappa, tau) descriptor at the
        configured smoothing scale.
    sax_signature:
        SAX symbolic signature over a 1D projection of (kappa, tau)
        (we use ``kappa + |tau|`` as the proxy series). Used by the
        prefilter to score signature similarity in O(n_segments).
    future_points:
        ``(forward_bars, 3)`` continuation immediately after the
        window. None if the window doesn't have a full continuation.
    """

    trajectory_id: int
    start_idx: int
    points: NDArray[np.float64]
    kt: NDArray[np.float64]
    sax_signature: NDArray[np.int8]
    future_points: NDArray[np.float64] | None = None


@dataclass
class AnalogueMatch:
    """One ranked analogue with its similarity weight."""

    window: TrajectoryWindow
    dtw_distance: float
    similarity: float  # exp(-dtw / window_len), in (0, 1]


@dataclass
class TrajectoryForecast:
    """Per-axis quantile cone for a 3D forecast.

    Fields
    ------
    bars:
        Forecast horizon (number of forward ticks).
    percentiles:
        Which quantiles were computed (e.g. [10, 50, 90]).
    curves:
        ``{percentile: (bars, 3)}`` array per percentile. Column 0 is
        the X-axis quantile curve, column 1 Y, column 2 Z.
    weights:
        Normalized weights of the analogues used (sum to 1.0).
    n_analogues:
        How many analogues actually contributed (non-empty
        future_points).
    """

    bars: int
    percentiles: List[int]
    curves: Dict[int, NDArray[np.float64]]
    weights: NDArray[np.float64]
    n_analogues: int


@dataclass
class TrajectoryCorpus:
    """Indexed collection of trajectory windows for fast retrieval.

    Construction is non-trivial (resampling + Frenet for every
    window) — typically a few ms per window. For large corpora the
    build is the dominant cost; queries are cheap.

    Parameters
    ----------
    window_len:
        Number of points per window. Should match the query window
        length the caller will use; otherwise DTW between mismatched
        sizes still works but results are biased.
    stride:
        Step between consecutive windows (in points). 1 = maximally
        overlapped, window_len = non-overlapping tiles.
    forward_bars:
        Number of points stored in each window's continuation. Must
        be > 0 for the corpus to be useful as a forecast source.
    sigma:
        Gaussian smoothing scale passed to
        :func:`frenet_descriptors`. The "right" sigma is the natural
        motif scale for the data; we default to 1.5 which behaves
        well on toy helices and biased random walks alike.
    sigma_pos:
        Pre-smoothing scale applied to the *positions* before the
        Frenet pipeline. Critical for noisy data — the discrete
        second derivative amplifies tiny Cartesian jitters into
        huge spurious curvatures. Default 2.0 strikes a good
        balance for simulation / random-walk inputs; pass 0.0 to
        disable when the input is already clean (analytical
        helices, etc.).
    sax_segments / sax_alphabet:
        SAX prefilter granularity. 8 segments * 4 symbols = 32-bit
        signature; sufficient to prune obvious non-matches.
    """

    window_len: int = 50
    stride: int = 5
    forward_bars: int = 20
    sigma: float = 1.5
    sigma_pos: float = 2.0
    sax_segments: int = 8
    sax_alphabet: int = 4
    windows: List[TrajectoryWindow] = field(default_factory=list)

    def add_trajectory(
        self, trajectory_id: int, points: NDArray[np.float64]
    ) -> int:
        """Slice a trajectory into windows and append to the corpus.

        Returns the number of windows added. Trajectories shorter
        than ``window_len + forward_bars`` add zero windows.
        """
        pts = np.asarray(points, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise ValueError(f"trajectory must be (T, 3); got {pts.shape}")
        T = pts.shape[0]
        if T < self.window_len + self.forward_bars:
            return 0

        n_added = 0
        # The last legitimate start index is the one where (start +
        # window_len + forward_bars) just barely fits in T. Going
        # further would chop the continuation short.
        last_start = T - (self.window_len + self.forward_bars)
        for start in range(0, last_start + 1, self.stride):
            window_pts = pts[start: start + self.window_len]
            future_pts = pts[
                start + self.window_len:
                start + self.window_len + self.forward_bars
            ]
            try:
                # We resample to window_len in case the input was
                # uniform-time but variable-speed; arc-length
                # resampling is what makes shape descriptors stable.
                resampled = arc_length_resample(window_pts, self.window_len)
                # Pre-smooth positions to tame discrete-derivative noise
                # amplification. See _smooth_points docstring for why.
                if self.sigma_pos > 0.0:
                    resampled = _smooth_points(resampled, self.sigma_pos)
                kappa, tau = frenet_descriptors(resampled, sigma=self.sigma)
            except ValueError:
                # Degenerate window (zero arc length). Skip; never
                # raise — corpus building must be robust to a few
                # stationary agents.
                continue
            kt = np.column_stack([kappa, tau])

            # SAX signature over a 1D proxy. We z-score before SAX
            # because sax_transform assumes the input is N(0, 1).
            proxy = kappa + np.abs(tau)
            mean, std = float(np.mean(proxy)), float(np.std(proxy))
            if std < 1e-9:
                proxy_z = np.zeros_like(proxy)
            else:
                proxy_z = (proxy - mean) / std
            sig = sax_transform(
                proxy_z, n_segments=self.sax_segments, alphabet_size=self.sax_alphabet
            )

            self.windows.append(
                TrajectoryWindow(
                    trajectory_id=trajectory_id,
                    start_idx=start,
                    points=window_pts.copy(),
                    kt=kt,
                    sax_signature=sig,
                    future_points=future_pts.copy(),
                )
            )
            n_added += 1
        return n_added


def build_corpus(
    trajectories: Sequence[NDArray[np.float64]],
    window_len: int = 50,
    stride: int = 5,
    forward_bars: int = 20,
    sigma: float = 1.5,
    sigma_pos: float = 2.0,
) -> TrajectoryCorpus:
    """Convenience builder: construct a corpus from a list of trajectories.

    The integer trajectory IDs are assigned by enumeration so the
    caller doesn't have to manage them; :class:`TrajectoryCorpus`
    has a richer API if explicit IDs are needed.
    """
    corpus = TrajectoryCorpus(
        window_len=window_len,
        stride=stride,
        forward_bars=forward_bars,
        sigma=sigma,
        sigma_pos=sigma_pos,
    )
    for tid, traj in enumerate(trajectories):
        corpus.add_trajectory(tid, traj)
    return corpus


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _query_signature(
    query_points: NDArray[np.float64],
    corpus: TrajectoryCorpus,
) -> tuple[NDArray[np.float64], NDArray[np.int8]]:
    """Compute (kt, sax) for a query window the same way the corpus does.

    Centralizing this guarantees the query goes through the SAME
    pipeline (arc-length resample, identical sigma, identical SAX
    config) as the corpus — otherwise prefilter scores would be
    biased and DTW distances would not be comparable.
    """
    resampled = arc_length_resample(query_points, corpus.window_len)
    if corpus.sigma_pos > 0.0:
        resampled = _smooth_points(resampled, corpus.sigma_pos)
    kappa, tau = frenet_descriptors(resampled, sigma=corpus.sigma)
    kt = np.column_stack([kappa, tau])
    proxy = kappa + np.abs(tau)
    mean, std = float(np.mean(proxy)), float(np.std(proxy))
    proxy_z = (proxy - mean) / std if std >= 1e-9 else np.zeros_like(proxy)
    sig = sax_transform(
        proxy_z,
        n_segments=corpus.sax_segments,
        alphabet_size=corpus.sax_alphabet,
    )
    return kt, sig


def find_analogues(
    query_points: NDArray[np.float64],
    corpus: TrajectoryCorpus,
    top_n: int = 10,
    prefilter_n: int | None = None,
    exclude_trajectory_id: int | None = None,
) -> List[AnalogueMatch]:
    """Retrieve the ``top_n`` most-similar windows to ``query_points``.

    Pipeline:
    1. Compute query (kt, sax_signature).
    2. Prefilter by Hamming-like distance on SAX signatures: keep
       the ``prefilter_n`` candidates with the smallest mismatch.
       When ``prefilter_n`` is None, defaults to 4 * top_n (capped
       at corpus size).
    3. Bivariate DTW on (kappa, tau) for the shortlist.
    4. Return top_n by similarity = ``exp(-dtw / window_len)``.

    Parameters
    ----------
    query_points:
        ``(window_len, 3)`` raw (x, y, z) samples. The descriptor
        pipeline arc-length-resamples internally, so the input does
        not need to be pre-resampled.
    corpus:
        A built :class:`TrajectoryCorpus`.
    top_n:
        Maximum number of analogues to return.
    prefilter_n:
        How many candidates to pass from the SAX prefilter into the
        DTW stage. Larger = more accurate but slower.
    exclude_trajectory_id:
        Drop windows from this trajectory before ranking. Critical
        for backtests so the test window isn't matched to itself.
    """
    if not corpus.windows:
        return []

    qkt, qsig = _query_signature(query_points, corpus)

    # Prefilter: rank by element-wise SAX symbol mismatch (a cheap
    # proxy for MINDIST). True MINDIST would also work but adds
    # complexity for no measurable retrieval-quality gain in the MVP.
    if prefilter_n is None:
        prefilter_n = min(len(corpus.windows), max(top_n * 4, 32))

    # Vectorized signature comparison. We stack all signatures into a
    # 2D array once and broadcast the query.
    sigs = np.array([w.sax_signature for w in corpus.windows], dtype=np.int16)
    mismatch = np.sum(np.abs(sigs - qsig.astype(np.int16)), axis=1)

    # Apply trajectory exclusion before ranking.
    if exclude_trajectory_id is not None:
        excluded = np.array(
            [w.trajectory_id == exclude_trajectory_id for w in corpus.windows]
        )
        # +inf so excluded windows sort to the very end and won't
        # appear in the prefilter shortlist.
        mismatch = np.where(excluded, np.iinfo(np.int64).max, mismatch)

    # argsort gives ascending order — smaller mismatch = more similar.
    order = np.argsort(mismatch, kind="stable")
    shortlist = order[:prefilter_n]

    # Bivariate DTW on the shortlist. We compute distance, then
    # similarity via the same exp(-d / window_len) scoring used by
    # the 1D pipeline.
    matches: List[AnalogueMatch] = []
    for idx in shortlist:
        if exclude_trajectory_id is not None and corpus.windows[idx].trajectory_id == exclude_trajectory_id:
            continue
        w = corpus.windows[idx]
        d = dtw_kt_distance(qkt, w.kt)
        sim = float(np.exp(-d / max(corpus.window_len, 1)))
        matches.append(
            AnalogueMatch(window=w, dtw_distance=float(d), similarity=sim)
        )

    matches.sort(key=lambda m: m.similarity, reverse=True)
    return matches[:top_n]


# ---------------------------------------------------------------------------
# Forecast cone
# ---------------------------------------------------------------------------


def forecast_cone(
    query_points: NDArray[np.float64],
    corpus: TrajectoryCorpus,
    forward_bars: int | None = None,
    top_n: int = 10,
    percentiles: Sequence[int] = (10, 50, 90),
    exclude_trajectory_id: int | None = None,
    return_analogues: bool = False,
) -> TrajectoryForecast | tuple[TrajectoryForecast, List[AnalogueMatch]]:
    """Build a 3D forecast cone from analogue continuations.

    The forecast represents *displacement from the query's last
    point* — i.e. delta = future_point - query_endpoint. Computing
    relative displacements (rather than absolute positions) makes
    the cone translation-invariant: an agent that follows a
    helix-shape continuation should produce the same cone shape
    regardless of where in space it currently sits.

    Parameters
    ----------
    query_points:
        ``(window_len, 3)`` recent trajectory of the query agent.
    corpus:
        A :class:`TrajectoryCorpus` built on the historical paths.
    forward_bars:
        Optional override of the corpus's forward_bars. If None,
        the corpus default is used.
    top_n:
        Number of analogues to weight into the cone.
    percentiles:
        Which quantiles to compute. Default ``(10, 50, 90)`` matches
        the rest of the engine's cone convention.
    exclude_trajectory_id:
        Same semantics as :func:`find_analogues`.
    return_analogues:
        When True, return ``(forecast, analogues)`` so the caller
        can inspect or visualize the matched paths.

    Returns
    -------
    :class:`TrajectoryForecast` (or a tuple with the analogues).
    """
    if forward_bars is None:
        forward_bars = corpus.forward_bars

    analogues = find_analogues(
        query_points,
        corpus,
        top_n=top_n,
        exclude_trajectory_id=exclude_trajectory_id,
    )

    # Filter to analogues that actually have a stored future window.
    valid = [m for m in analogues if m.window.future_points is not None]
    n_analogues = len(valid)

    pcts = list(percentiles)
    if n_analogues == 0:
        # Empty cone — every percentile curve is zeros. The caller
        # can detect this via n_analogues=0.
        empty = np.zeros((forward_bars, 3), dtype=np.float64)
        return TrajectoryForecast(
            bars=forward_bars,
            percentiles=pcts,
            curves={p: empty.copy() for p in pcts},
            weights=np.array([], dtype=np.float64),
            n_analogues=0,
        )

    # Anchor at the query's last point — all analogue futures are
    # shifted to start from the same anchor before quantiling. This
    # is the same trick used by the 1D projector (anchor-relative
    # cumulative returns) but applied to 3D positions.
    anchor = np.asarray(query_points[-1], dtype=np.float64)

    # Stack analogue futures into (n, forward_bars, 3) array. We
    # truncate / pad along the bar axis to forward_bars in case a
    # corpus window's future is shorter (it shouldn't be, by
    # construction, but defensive code is cheap).
    futures = []
    weights_raw = []
    for m in valid:
        f = m.window.future_points
        # Re-anchor: shift so the analogue's pre-jump baseline aligns
        # with the query anchor. We use the last point of the
        # analogue's *window* as its anchor.
        analogue_anchor = m.window.points[-1]
        delta = f - analogue_anchor                  # shape (J, 3)
        if delta.shape[0] < forward_bars:
            # Pad with the terminal value so the cone stays defined.
            pad = np.tile(delta[-1:], (forward_bars - delta.shape[0], 1))
            delta = np.concatenate([delta, pad], axis=0)
        elif delta.shape[0] > forward_bars:
            delta = delta[:forward_bars]
        futures.append(delta)
        weights_raw.append(m.similarity)

    futures_arr = np.stack(futures, axis=0)          # (n, J, 3)
    weights = np.asarray(weights_raw, dtype=np.float64)
    total = float(np.sum(weights))
    if total > 0:
        weights = weights / total
    else:
        weights = np.full(len(weights), 1.0 / len(weights))

    # Per-axis weighted quantile. We loop bars-axis-percentile and
    # call the existing _weighted_quantile helper. For the corpus
    # sizes we target (a few thousand windows, top_n <= 32, J <= 50)
    # this is negligible overhead.
    curves: Dict[int, NDArray[np.float64]] = {p: np.zeros((forward_bars, 3)) for p in pcts}
    for axis in range(3):
        for bar in range(forward_bars):
            col = futures_arr[:, bar, axis]
            for p in pcts:
                curves[p][bar, axis] = _weighted_quantile(col, weights, p / 100.0)

    # Re-anchor the cone back to absolute coordinates so the caller
    # can plot directly. Subscribers that want delta form can
    # subtract anchor themselves; the absolute form is the more
    # common consumer need.
    for p in pcts:
        curves[p] = curves[p] + anchor[None, :]

    forecast = TrajectoryForecast(
        bars=forward_bars,
        percentiles=pcts,
        curves=curves,
        weights=weights,
        n_analogues=n_analogues,
    )
    if return_analogues:
        return forecast, valid
    return forecast


__all__ = [
    "AnalogueMatch",
    "TrajectoryCorpus",
    "TrajectoryForecast",
    "TrajectoryWindow",
    "build_corpus",
    "find_analogues",
    "forecast_cone",
]
