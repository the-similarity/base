"""
Joint-path projector — samples correlated forward paths, not independent
per-bar quantiles.

Part of the ``projector-v2`` research lane. Signature-compatible with
``the_similarity.core.projector.project`` so the lane runner can swap it
in-place.

Why joint sampling?
-------------------
The baseline projector builds each percentile curve **independently per
bar**: P10 at bar *k* is the weighted 10th-percentile of match returns
at bar *k*. This is correct per-bar marginally, but it **destroys the
time correlation** between bars. A user looking at a P10 / P90 cone has
no guarantee that any *actual* realised path stays inside it for many
consecutive bars — independence across bars makes the joint coverage
dramatically worse than the marginal coverage implies.

This module samples entire correlated forward paths by:
1. Treating the set of match forward windows as an empirical copula over
   paths (each path = one weighted draw from the empirical joint
   distribution).
2. Optionally re-applying the match confidence weights via importance
   resampling with replacement.
3. Adding *bar-coupled* Gaussian noise whose per-bar std is the
   empirical residual std at that bar, but whose random seed is shared
   within a path — producing correlated disturbances rather than
   independent jitter.
4. Reporting percentile curves from the resampled *paths* so callers
   see a statistically consistent joint cone.

Walk-forward invariant
----------------------
All inputs are the match forward windows from the lookback — identical
to the baseline projector. No new information source is introduced; we
just sample the same distribution differently. This keeps the module
safe inside walk-forward backtests.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from the_similarity.config import Config
from the_similarity.core.projector import Forecast, project as _baseline_project
from the_similarity.core.scorer import MatchResult


@dataclass
class JointPathState:
    """Diagnostics for the joint-path sampler, attached to Forecast."""

    n_base_paths: int
    n_simulated_paths: int
    noise_scale_mean: float
    seed: int | None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def project(
    matches: list[MatchResult],
    history: NDArray[np.float64],
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
    config: Config | None = None,
    *,
    n_paths: int = 1000,
    noise_fraction: float = 0.25,
    seed: int | None = 42,
) -> Forecast:
    """Return a forecast whose percentile curves come from joint path sampling.

    Args:
        matches: Ranked match results from the search pipeline.
        history: Raw price history.
        forward_bars: Forecast horizon.
        percentiles: Percentile levels.
        config: Pipeline config, forwarded to the baseline projector to
            reuse its `all_paths` extraction and (optionally) the baseline
            cone as the P50 anchor.
        n_paths: Number of joint paths to simulate.
        noise_fraction: Fraction of per-bar empirical std added as
            path-correlated Gaussian noise. Small (<=0.5) fractions
            preserve the joint structure of historical paths while
            smoothing pathological outliers.
        seed: RNG seed for reproducibility (mandatory for walk-forward
            runs).

    Returns:
        A :class:`Forecast` whose per-percentile curves are computed
        from the joint-path sample, plus a ``joint_path`` attribute
        describing the sampler's diagnostics.
    """
    baseline = _baseline_project(
        matches=matches,
        history=history,
        forward_bars=forward_bars,
        percentiles=percentiles,
        config=config,
    )

    # Fail-closed: if the baseline had no usable paths, keep its shape.
    n_base = baseline.all_paths.shape[0]
    if n_base == 0:
        setattr(
            baseline,
            "joint_path",
            JointPathState(
                n_base_paths=0,
                n_simulated_paths=0,
                noise_scale_mean=0.0,
                seed=seed,
            ),
        )
        return baseline

    # --- Extract sampling primitives from the baseline cone ---
    paths = baseline.all_paths.astype(np.float64)  # (n_base, bars)
    weights = np.asarray(baseline.weights, dtype=np.float64)
    # Defensive normalisation in case the baseline fell back to uniform.
    if weights.sum() <= 0:
        weights = np.full(n_base, 1.0 / n_base)
    else:
        weights = weights / weights.sum()

    # Per-bar empirical std, reused for path-correlated noise scaling.
    bar_means = np.average(paths, axis=0, weights=weights)
    bar_vars = np.average((paths - bar_means) ** 2, axis=0, weights=weights)
    bar_stds = np.sqrt(np.maximum(bar_vars, 1e-12))

    rng = np.random.default_rng(seed)

    # --- 1. Importance resample entire paths (preserves time coupling) ---
    # np.random.choice with weights gives us a fresh empirical joint
    # distribution — duplicates are fine because they increase the
    # weight of high-confidence paths naturally.
    idx = rng.choice(n_base, size=n_paths, replace=True, p=weights)
    sampled = paths[idx]  # (n_paths, bars)

    # --- 2. Path-correlated noise ---
    # Each path gets its OWN scalar noise draw that is then multiplied by
    # a bar-dependent decay, yielding correlated disturbances across
    # bars of the same path. This preserves the joint structure: a
    # "high" draw lifts the whole path, rather than independently
    # shifting each bar.
    bar_profile = np.sqrt(np.arange(1, forward_bars + 1) / forward_bars)
    # Per-path scalar, Gaussian (0, 1). Broadcast over bars below.
    path_noise = rng.standard_normal(n_paths)[:, None]
    # Per-bar profile × per-bar std × fraction × per-path scalar.
    noise = noise_fraction * path_noise * (bar_stds * bar_profile)[None, :]
    sampled_with_noise = sampled + noise

    # --- 3. Percentile curves from the joint sample ---
    curves: dict[int, NDArray[np.float64]] = {}
    for p in baseline.percentiles:
        curves[p] = np.percentile(sampled_with_noise, p, axis=0)

    # Enforce marginal monotonicity across percentiles (numerical safety).
    sorted_pcts = sorted(curves.keys())
    stacked = np.stack([curves[p] for p in sorted_pcts], axis=0)
    stacked = np.maximum.accumulate(stacked, axis=0)
    for i, p in enumerate(sorted_pcts):
        curves[p] = stacked[i]

    out = Forecast(
        bars=forward_bars,
        percentiles=list(baseline.percentiles),
        curves=curves,
        all_paths=sampled_with_noise,  # expose joint sample for metrics
        weights=np.full(n_paths, 1.0 / n_paths, dtype=np.float64),
        koopman_forecast=baseline.koopman_forecast,
    )
    setattr(
        out,
        "joint_path",
        JointPathState(
            n_base_paths=int(n_base),
            n_simulated_paths=int(n_paths),
            noise_scale_mean=float(np.mean(bar_stds) * noise_fraction),
            seed=seed,
        ),
    )
    return out
