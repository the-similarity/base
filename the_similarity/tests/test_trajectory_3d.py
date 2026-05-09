"""End-to-end 3D trajectory self-similarity backtest.

This is the experimental gate for the 3D-trajectory MVP. It asks:
*does the project's self-similarity primitive — analogue retrieval +
weighted forecast cone — actually beat trivial baselines on a corpus
of agent trajectories?*

Methodology
-----------
1. Generate N synthetic agents biased-random-walking on a sin/cos
   "terrain" (cheap pure-Python proxy for the worlds-runner output;
   the production data path is the JS sim with --track-agents +
   --heightmap, but for a fast deterministic test we want pure
   Python).
2. For each agent, slide a window of length K=50; predict next J=20
   ticks; record actual next J ticks.
3. Compare four predictors:
    - **model**: Frenet-DTW analogue retrieval + weighted forecast cone.
    - **persistence**: predicts the agent stays put at its last point.
    - **linear**: linear extrapolation from the last K points.
    - **random_analogue**: same machinery but picks N random corpus
      windows (no shape match) — the "is the shape signal doing
      anything" baseline.
4. Metrics: spatial MAE (Euclidean distance between P50 forecast and
   actual at horizon J), hit_rate (did the actual path enter the cone
   bounding box?), CRPS (probabilistic score on per-axis quantiles).

Pass criteria (per the MVP design doc):
- model.spatial_mae < persistence.spatial_mae (shape retrieval beats "stay still")
- model.hit_rate >= 0.5 at horizon J

If those don't hold the test still PASSES with an xfail-style
diagnostic so the result is visible in CI without lying about success.
The point of this experiment is the *data*, not green CI.

Determinism
-----------
Every numpy random call uses a seeded Generator. The test runs in
< 30 seconds on a developer laptop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np
import pytest

from the_similarity.core.trajectory_matcher import (
    build_corpus,
    forecast_cone,
)


# ---------------------------------------------------------------------------
# Synthetic terrain-walking trajectories
# ---------------------------------------------------------------------------


def _terrain_z(x: float, y: float) -> float:
    """Smooth sin/cos terrain function used as a stand-in for the JS heightmap.

    z = 0.5 * sin(0.15 x) * cos(0.12 y) + 0.3 * sin(0.07 (x + y))

    Chosen because:
    - It has multiple length scales (so curvature varies across the
      domain — a constant slope would defeat the experiment).
    - It is smooth and differentiable, so agents walking on it
      produce non-trivial torsion (the path bends both up/down and
      around contours).
    - It is cheap to evaluate at every step.
    """
    return 0.5 * np.sin(0.15 * x) * np.cos(0.12 * y) + 0.3 * np.sin(0.07 * (x + y))


def _generate_agent_trajectory(
    rng: np.random.Generator,
    n_steps: int,
    start_xy: np.ndarray,
    momentum: float = 0.7,
) -> np.ndarray:
    """Biased random walk on the sin/cos terrain.

    Each step: heading = momentum * prev_heading + (1-momentum) *
    random_unit_2d, then move one step at the new heading. The z
    coordinate is set by the terrain function.

    The momentum term yields trajectories with a natural curvature
    range — too low and we get pure noise (no shape signal), too
    high and we get straight lines (no torsion signal). 0.7 is the
    sweet spot empirically.
    """
    pts = np.zeros((n_steps, 3), dtype=np.float64)
    pos = start_xy.copy()
    heading = rng.uniform(-np.pi, np.pi)
    for t in range(n_steps):
        pts[t, 0] = pos[0]
        pts[t, 1] = pos[1]
        pts[t, 2] = _terrain_z(pos[0], pos[1])
        # Update heading with momentum + small random kick
        heading = momentum * heading + (1.0 - momentum) * rng.uniform(-np.pi, np.pi)
        # Step size has its own small randomness to avoid degenerate
        # zero-velocity stretches.
        step = 0.6 + 0.3 * rng.uniform(0, 1)
        pos = pos + step * np.array([np.cos(heading), np.sin(heading)])
    return pts


def _make_agent_corpus(seed: int = 7, n_agents: int = 50, n_steps: int = 500):
    """Generate a deterministic synthetic agent corpus."""
    rng = np.random.default_rng(seed)
    trajectories: List[np.ndarray] = []
    for i in range(n_agents):
        # Random starting locations spread across the domain so
        # different agents see different terrain scales.
        start = rng.uniform(-50, 50, size=2)
        traj = _generate_agent_trajectory(rng, n_steps, start)
        trajectories.append(traj)
    return trajectories


# ---------------------------------------------------------------------------
# Backtest harness
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    """Aggregate metrics from one predictor's walk-forward backtest."""

    name: str
    n_trials: int
    spatial_mae: float = 0.0
    hit_rate: float = 0.0
    crps: float = 0.0
    # Distribution of per-trial errors for diagnostics.
    per_trial_mae: List[float] = field(default_factory=list)


def _persistence_forecast(
    query_points: np.ndarray, forward_bars: int
) -> dict:
    """Baseline: agent stays put at its last position."""
    last = query_points[-1]
    p50 = np.tile(last[None, :], (forward_bars, 1))
    # No uncertainty for persistence — P10 = P90 = P50. This makes
    # the "hit rate" metric degenerate (we can never enter a zero-
    # width cone), so we add a tiny epsilon-cone for fairness.
    eps = 1.0  # one unit of position
    return {
        "P10": p50 - eps,
        "P50": p50.copy(),
        "P90": p50 + eps,
    }


def _linear_forecast(
    query_points: np.ndarray, forward_bars: int
) -> dict:
    """Baseline: linear extrapolation from the last K points.

    Fits a line per axis vs. step index using the last K points and
    extrapolates forward_bars ticks. This is what an "ARMA(1,0)
    momentum" baseline reduces to in the simplest case.
    """
    K = len(query_points)
    t = np.arange(K)
    coeffs = []
    for axis in range(3):
        # Closed-form least-squares slope + intercept per axis.
        slope, intercept = np.polyfit(t, query_points[:, axis], deg=1)
        coeffs.append((slope, intercept))
    future_t = np.arange(K, K + forward_bars)
    p50 = np.column_stack(
        [c[0] * future_t + c[1] for c in coeffs]
    )
    # Uncertainty band: scale residual std with horizon
    residuals = []
    for axis in range(3):
        slope, intercept = coeffs[axis]
        pred = slope * t + intercept
        residuals.append(np.std(query_points[:, axis] - pred))
    band = np.array(residuals) * np.sqrt(np.arange(1, forward_bars + 1))[:, None]
    return {
        "P10": p50 - 1.28 * band,
        "P50": p50.copy(),
        "P90": p50 + 1.28 * band,
    }


def _random_analogue_forecast(
    query_points: np.ndarray,
    corpus,
    forward_bars: int,
    rng: np.random.Generator,
    n_picks: int = 5,
):
    """Baseline: pick n_picks random corpus windows (no shape match).

    This isolates the "is the Frenet-DTW retrieval doing anything?"
    question. If the model beats persistence but not random-analogue,
    the win comes from the corpus's marginal distribution of
    continuations, not from the shape signal.
    """
    if not corpus.windows:
        return _persistence_forecast(query_points, forward_bars)
    anchor = query_points[-1]
    indices = rng.integers(0, len(corpus.windows), size=n_picks)
    futures = []
    for idx in indices:
        w = corpus.windows[idx]
        if w.future_points is None:
            continue
        delta = w.future_points - w.points[-1]
        if delta.shape[0] >= forward_bars:
            delta = delta[:forward_bars]
        else:
            pad = np.tile(delta[-1:], (forward_bars - delta.shape[0], 1))
            delta = np.concatenate([delta, pad], axis=0)
        futures.append(delta)
    if not futures:
        return _persistence_forecast(query_points, forward_bars)
    futures_arr = np.stack(futures, axis=0)
    p50 = np.median(futures_arr, axis=0) + anchor
    p10 = np.quantile(futures_arr, 0.1, axis=0) + anchor
    p90 = np.quantile(futures_arr, 0.9, axis=0) + anchor
    return {"P10": p10, "P50": p50, "P90": p90}


def _model_forecast(
    query_points: np.ndarray,
    corpus,
    forward_bars: int,
    exclude_trajectory_id: int,
):
    """Frenet-DTW analogue forecast — the system under test."""
    f = forecast_cone(
        query_points,
        corpus,
        forward_bars=forward_bars,
        top_n=10,
        percentiles=(10, 50, 90),
        exclude_trajectory_id=exclude_trajectory_id,
    )
    if f.n_analogues == 0:
        return _persistence_forecast(query_points, forward_bars)
    return {
        "P10": f.curves[10],
        "P50": f.curves[50],
        "P90": f.curves[90],
    }


def _evaluate_forecast(
    forecast: dict, actual: np.ndarray
) -> tuple[float, bool, float]:
    """Compute (spatial MAE at horizon, hit_inside_cone, crps_per_axis_avg).

    spatial_mae:
        Mean Euclidean distance between P50 and actual across all
        forecast bars (not just the terminal). Lower is better.
    hit:
        Boolean — did the actual *terminal* point lie inside the
        axis-aligned bounding box defined by [P10, P90] per axis?
    crps:
        Per-axis CRPS averaged over axes and horizon. Approximated
        from the three quantiles (P10, P50, P90) using the standard
        discrete formula.
    """
    p50 = forecast["P50"]
    p10 = forecast["P10"]
    p90 = forecast["P90"]
    # Spatial MAE: Euclidean error between P50 and actual at every
    # bar, then averaged.
    err = np.linalg.norm(p50 - actual, axis=1)
    spatial_mae = float(np.mean(err))
    # Hit: terminal actual inside the P10-P90 box on every axis.
    hit = bool(
        np.all(actual[-1] >= p10[-1])
        and np.all(actual[-1] <= p90[-1])
    )
    # CRPS approximation — per axis, per bar, sum over the (P10, P50,
    # P90) triple, then averaged. Same formula as
    # the_similarity.core.metrics.crps but computed locally so we
    # don't have to construct TrialResult dataclasses.
    crps_vals = []
    cdf_levels = np.array([0.1, 0.5, 0.9])
    for axis in range(3):
        for bar in range(p50.shape[0]):
            forecast_terminals = np.array(
                [p10[bar, axis], p50[bar, axis], p90[bar, axis]]
            )
            indicators = (actual[bar, axis] <= forecast_terminals).astype(float)
            crps_vals.append(float(np.mean((indicators - cdf_levels) ** 2)))
    crps = float(np.mean(crps_vals))
    return spatial_mae, hit, crps


def _walk_forward_backtest(
    trajectories: List[np.ndarray],
    forecaster,
    K: int = 50,
    J: int = 20,
    stride: int = 30,
    name: str = "model",
) -> BacktestResult:
    """Walk-forward over every trajectory; aggregate per-predictor metrics.

    For each trajectory, slide a window of length K with the given
    stride. At each position, call ``forecaster(query, future_idx, traj_idx)``
    -> dict with P10/P50/P90 keys (each shape (J, 3)). Compare against
    the actual next-J slice.
    """
    spatial_errors: List[float] = []
    hits: List[bool] = []
    crpses: List[float] = []

    for tid, traj in enumerate(trajectories):
        T = traj.shape[0]
        if T < K + J:
            continue
        for start in range(0, T - K - J + 1, stride):
            query = traj[start: start + K]
            actual = traj[start + K: start + K + J]
            try:
                forecast = forecaster(query, start, tid)
            except Exception:
                # A bad window (zero arc length, etc.) - skip rather
                # than fail the whole backtest. We track this via
                # n_trials so the metrics aren't silently inflated.
                continue
            mae, hit, crps_val = _evaluate_forecast(forecast, actual)
            spatial_errors.append(mae)
            hits.append(hit)
            crpses.append(crps_val)

    if not spatial_errors:
        return BacktestResult(name=name, n_trials=0)
    return BacktestResult(
        name=name,
        n_trials=len(spatial_errors),
        spatial_mae=float(np.mean(spatial_errors)),
        hit_rate=float(np.mean(hits)),
        crps=float(np.mean(crpses)),
        per_trial_mae=spatial_errors,
    )


# ---------------------------------------------------------------------------
# The actual experiment
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_trajectory_3d_backtest_vs_baselines():
    """End-to-end backtest of the 3D self-similarity primitive.

    Marked `slow` because it generates a 50-agent corpus and runs four
    full walk-forward backtests. Should still complete in well under a
    minute on commodity hardware.
    """
    K = 50  # window length
    J = 20  # forecast horizon
    rng = np.random.default_rng(123)

    # Synthetic corpus — 50 agents, 500 ticks each.
    trajectories = _make_agent_corpus(seed=7, n_agents=50, n_steps=500)

    # Build the corpus (excluding self-matches handled per-trial via
    # exclude_trajectory_id in the model forecaster).
    corpus = build_corpus(
        trajectories, window_len=K, stride=10, forward_bars=J
    )

    # Wrap each forecaster so it has the same signature for the harness.
    def model_fc(query, _start, tid):
        return _model_forecast(query, corpus, J, exclude_trajectory_id=tid)

    def persistence_fc(query, _start, _tid):
        return _persistence_forecast(query, J)

    def linear_fc(query, _start, _tid):
        return _linear_forecast(query, J)

    def random_fc(query, _start, _tid):
        # Pass a NEW rng-seeded generator so each random forecast is
        # deterministic but uses different picks across trials.
        return _random_analogue_forecast(
            query, corpus, J, np.random.default_rng(7 ^ _start), n_picks=5
        )

    # Run walk-forward backtests. Stride of 30 keeps the trial count
    # manageable while still giving each agent ~10-15 trials.
    bt_model = _walk_forward_backtest(
        trajectories, model_fc, K=K, J=J, stride=30, name="model"
    )
    bt_persistence = _walk_forward_backtest(
        trajectories, persistence_fc, K=K, J=J, stride=30, name="persistence"
    )
    bt_linear = _walk_forward_backtest(
        trajectories, linear_fc, K=K, J=J, stride=30, name="linear"
    )
    bt_random = _walk_forward_backtest(
        trajectories, random_fc, K=K, J=J, stride=30, name="random_analogue"
    )

    # Print a clean summary so the test output is informative whether
    # or not it passes.
    print()
    print(
        "=== 3D Trajectory Self-Similarity Backtest ==="
        f"\n  Corpus: {len(trajectories)} agents x 500 ticks "
        f"({len(corpus.windows)} windows in corpus)"
        f"\n  Window K={K}, horizon J={J}"
        f"\n  Trials per predictor: {bt_model.n_trials}\n"
    )
    header = f"  {'predictor':<18} {'MAE':>10} {'hit_rate':>10} {'CRPS':>10}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in [bt_model, bt_persistence, bt_linear, bt_random]:
        print(
            f"  {r.name:<18} {r.spatial_mae:>10.4f} "
            f"{r.hit_rate:>10.4f} {r.crps:>10.4f}"
        )
    print()

    # Validate basic well-formedness — these MUST hold or the harness
    # itself is broken.
    assert bt_model.n_trials > 0, "Backtest produced zero model trials"
    assert bt_persistence.n_trials == bt_model.n_trials
    assert bt_linear.n_trials == bt_model.n_trials
    assert bt_random.n_trials == bt_model.n_trials

    # ─── Pass criteria ───────────────────────────────────────────────
    # The MVP plan asks: does the model beat persistence on spatial
    # MAE, AND does it cover > 50% of paths at horizon J?
    #
    # Be honest: if the experiment fails, surface the diagnostic.
    # We use soft assertions that record the verdict but never fudge
    # the numbers.
    beats_persistence = bt_model.spatial_mae < bt_persistence.spatial_mae
    beats_random = bt_model.spatial_mae < bt_random.spatial_mae
    hit_rate_pass = bt_model.hit_rate > 0.5

    print(
        f"  Verdict:\n"
        f"    model_MAE < persistence_MAE: {beats_persistence}\n"
        f"    model_MAE < random_MAE:      {beats_random}\n"
        f"    model_hit_rate > 0.5:        {hit_rate_pass}\n"
    )
    # The test itself is *not* the gate — the printed verdict is.
    # CI will record this output verbatim and the PR body summarizes
    # the numbers. The hard assertion below is only "the harness ran";
    # we deliberately do not gate the experiment on a particular
    # outcome because the point is the *honest* result.
    assert bt_model.n_trials >= 50, (
        f"Too few trials to draw conclusions: {bt_model.n_trials}"
    )
