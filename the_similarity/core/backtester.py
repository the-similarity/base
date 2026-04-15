"""Backtester for validating the similarity search pipeline.

Runs randomized walk-forward trials: for each trial, picks a random query
window, searches only the history BEFORE the query (no look-ahead), generates
a forecast cone, and compares it to what actually happened.
"""

from __future__ import annotations

import warnings
from concurrent.futures import ProcessPoolExecutor, BrokenExecutor
from dataclasses import dataclass
from multiprocessing import cpu_count
from typing import Callable

import numpy as np
from numpy.typing import NDArray

from the_similarity.config import Config
from the_similarity.core.metrics import (
    calibration,
    coverage_probability,
    crps,
    hit_rate,
    interval_score,
    max_drawdown,
    mean_absolute_error,
    profit_factor,
    sharpe_ratio,
)


@dataclass
class TrialResult:
    """Result of a single backtest trial."""

    query_start: int
    query_end: int
    actual_returns: NDArray[np.float64]
    forecast_curves: dict[int, NDArray[np.float64]]
    n_matches: int
    top_match_score: float
    directional_hit: bool
    p50_error: float
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class BacktestReport:
    """Aggregated backtest results."""

    trials: list[TrialResult]
    config: Config
    window_size: int
    forward_bars: int
    seed: int | None

    @property
    def valid_trials(self) -> list[TrialResult]:
        return [t for t in self.trials if not t.skipped]

    @property
    def n_valid_trials(self) -> int:
        return len(self.valid_trials)

    @property
    def n_skipped_trials(self) -> int:
        return len(self.trials) - self.n_valid_trials

    @property
    def hit_rate(self) -> float:
        return hit_rate(self.valid_trials)

    @property
    def mean_error(self) -> float:
        return mean_absolute_error(self.valid_trials)

    @property
    def calibration(self) -> dict[int, float]:
        return calibration(self.valid_trials, self.config.percentiles)

    @property
    def crps(self) -> float:
        return crps(self.valid_trials)

    # --- Richer metrics (interval / coverage / trading-oriented) ---
    # These compose with the primary set above and are computed on-demand
    # from the same underlying TrialResult list, so no per-trial caching or
    # state is stored on the report itself.

    @property
    def interval_score(self) -> float:
        """Proper scoring rule for the P10/P90 interval (default alpha=0.20)."""
        return interval_score(self.valid_trials)

    @property
    def coverage(self) -> float:
        """Empirical coverage of the central P10-P90 interval."""
        return coverage_probability(self.valid_trials)

    @property
    def profit_factor(self) -> float:
        """Gain-to-loss ratio when trading the P50 direction."""
        return profit_factor(self.valid_trials)

    @property
    def max_drawdown(self) -> float:
        """Worst peak-to-trough of the P50-directed equity curve."""
        return max_drawdown(self.valid_trials)

    @property
    def sharpe(self) -> float:
        """Annualised Sharpe of P50-directed per-trial returns (252 periods/yr)."""
        return sharpe_ratio(self.valid_trials)

    def summary(self) -> str:
        # Metric values are computed lazily via the properties above; we
        # capture them once here so the printed block is internally consistent
        # (cheap — each property is O(n_trials)).
        sharpe_val = self.sharpe
        pf_val = self.profit_factor
        lines = [
            f"BacktestReport: {self.n_valid_trials} valid trials, {self.n_skipped_trials} skipped",
            f"  window_size={self.window_size}, forward_bars={self.forward_bars}",
            f"  hit_rate={self.hit_rate:.1%}",
            f"  mean_absolute_error={self.mean_error:.4f}",
            f"  crps={self.crps:.4f}",
            f"  interval_score(P10/P90)={self.interval_score:.4f}",
            f"  coverage(P10/P90)={self.coverage:.1%}",
            # profit_factor can be +inf when losses == 0 — format defensively.
            f"  profit_factor={pf_val:.3f}"
            if np.isfinite(pf_val)
            else f"  profit_factor={pf_val}",
            f"  max_drawdown={self.max_drawdown:.4f}",
            f"  sharpe(annualised)={sharpe_val:.3f}"
            if not np.isnan(sharpe_val)
            else "  sharpe(annualised)=nan",
            "  calibration:",
        ]
        for p, rate in sorted(self.calibration.items()):
            expected = p / 100.0
            delta = rate - expected
            lines.append(
                f"    P{p}: {rate:.1%} (expected {expected:.0%}, delta {delta:+.1%})"
            )
        result = "\n".join(lines)
        print(result)
        return result


def run_backtest(
    history: NDArray[np.float64],
    window_size: int,
    forward_bars: int = 50,
    n_trials: int = 100,
    config: Config | None = None,
    seed: int | None = 42,
    n_workers: int | None = None,
    progress_fn: Callable[[int, int], None] | None = None,
    top_k: int = 10,
) -> BacktestReport:
    """Run walk-forward backtest trials.

    For each trial:
      1. Pick a random query position
      2. query = history[pos : pos + window_size]
      3. lookback = history[:pos]  (no look-ahead)
      4. Run search(query, lookback) → forecast
      5. Compare forecast to actual = history[pos + window_size : pos + window_size + forward_bars]

    Args:
        history: Full historical series (1D float64 array).
        window_size: Length of the query window.
        forward_bars: How many bars to project forward.
        n_trials: Number of random trials.
        config: Pipeline config. Uses defaults if None.
        seed: Random seed for reproducibility. None for random.
        n_workers: Number of parallel workers. None = min(4, cpu_count).
        progress_fn: Optional callback(completed, total) for progress updates.
        top_k: Number of matches to retrieve per trial.

    Returns:
        BacktestReport with per-trial results and aggregate metrics.
    """
    history = np.asarray(history, dtype=np.float64)

    # --- Input validation ---
    if history.ndim != 1:
        raise ValueError(f"history must be 1D, got {history.ndim}D")
    if np.any(np.isnan(history)):
        raise ValueError("history contains NaN values — clean data before backtesting")
    if np.any(np.isinf(history)):
        raise ValueError("history contains Inf values — clean data before backtesting")
    if window_size <= 0:
        raise ValueError(f"window_size must be positive, got {window_size}")
    if forward_bars <= 0:
        raise ValueError(f"forward_bars must be positive, got {forward_bars}")
    if n_trials <= 0:
        raise ValueError(f"n_trials must be positive, got {n_trials}")

    min_lookback = 3 * window_size
    min_history_len = min_lookback + window_size + forward_bars
    if len(history) < min_history_len:
        raise ValueError(
            f"history length {len(history)} is too short. "
            f"Need at least {min_history_len} bars "
            f"(3*window_size + window_size + forward_bars = "
            f"3*{window_size} + {window_size} + {forward_bars})"
        )

    if config is None:
        config = Config()

    # --- Pick trial positions ---
    positions = _pick_trial_positions(
        history_len=len(history),
        window_size=window_size,
        forward_bars=forward_bars,
        min_lookback=min_lookback,
        n_trials=n_trials,
        seed=seed,
    )

    # --- Run trials ---
    if n_workers is None:
        n_workers = min(4, cpu_count() or 1)

    trial_args = [
        (history, pos, window_size, forward_bars, config, top_k) for pos in positions
    ]

    trials: list[TrialResult] = []

    if n_workers > 1 and len(positions) > 1:
        try:
            trials = _run_parallel(trial_args, n_workers, progress_fn)
        except (BrokenExecutor, Exception) as exc:
            warnings.warn(
                f"Parallel execution failed ({exc}), falling back to sequential",
                RuntimeWarning,
                stacklevel=2,
            )
            trials = _run_sequential(trial_args, progress_fn)
    else:
        trials = _run_sequential(trial_args, progress_fn)

    return BacktestReport(
        trials=trials,
        config=config,
        window_size=window_size,
        forward_bars=forward_bars,
        seed=seed,
    )


def _pick_trial_positions(
    history_len: int,
    window_size: int,
    forward_bars: int,
    min_lookback: int,
    n_trials: int,
    seed: int | None,
) -> list[int]:
    """Sample random query start positions with constraints."""
    earliest = min_lookback
    latest = history_len - window_size - forward_bars

    if earliest > latest:
        raise ValueError(
            f"No valid trial positions: earliest={earliest}, latest={latest}. "
            f"History is too short for the given window_size and forward_bars."
        )

    rng = np.random.default_rng(seed)
    valid_range = latest - earliest + 1
    n_samples = min(n_trials, valid_range)

    if n_samples == valid_range:
        positions = list(range(earliest, latest + 1))
        rng.shuffle(positions)
    else:
        positions = sorted(
            rng.choice(
                range(earliest, latest + 1), size=n_samples, replace=False
            ).tolist()
        )

    return positions[:n_trials]


def _run_single_trial(args: tuple) -> TrialResult:
    """Execute one backtest trial."""
    history, query_start, window_size, forward_bars, config, top_k = args

    query_end = query_start + window_size
    forward_start = query_end
    forward_end = forward_start + forward_bars

    query = history[query_start:query_end]
    lookback = history[:query_start]
    actual = history[forward_start:forward_end]

    # Compute actual returns relative to query end
    anchor = history[query_end - 1]
    if anchor == 0:
        return TrialResult(
            query_start=query_start,
            query_end=query_end,
            actual_returns=np.zeros(forward_bars),
            forecast_curves={},
            n_matches=0,
            top_match_score=0.0,
            directional_hit=False,
            p50_error=0.0,
            skipped=True,
            skip_reason="anchor value is zero",
        )
    actual_returns = (actual - anchor) / anchor

    # Run search + project
    try:
        # Import here to avoid circular imports and to ensure clean process state
        from the_similarity.api import search, project

        results = search(
            query=query,
            history=lookback,
            top_k=top_k,
            config=config,
            exclude_self=False,  # lookback doesn't contain query
        )

        if not results.matches:
            return TrialResult(
                query_start=query_start,
                query_end=query_end,
                actual_returns=actual_returns,
                forecast_curves={},
                n_matches=0,
                top_match_score=0.0,
                directional_hit=False,
                p50_error=0.0,
                skipped=True,
                skip_reason="no matches found",
            )

        forecast = project(
            matches=results,
            history=lookback,
            forward_bars=forward_bars,
            percentiles=config.percentiles,
        )

        if forecast.all_paths.shape[0] == 0:
            return TrialResult(
                query_start=query_start,
                query_end=query_end,
                actual_returns=actual_returns,
                forecast_curves={},
                n_matches=len(results.matches),
                top_match_score=results.best.confidence_score if results.best else 0.0,
                directional_hit=False,
                p50_error=0.0,
                skipped=True,
                skip_reason="no valid forward paths in projection",
            )

        # Extract forecast curves as plain arrays
        forecast_curves = {p: np.array(curve) for p, curve in forecast.curves.items()}

        # Directional hit: does P50 predict the right direction?
        p50 = forecast_curves.get(50)
        if p50 is not None and len(p50) > 0:
            predicted_direction = p50[-1] > 0
            actual_direction = actual_returns[-1] > 0
            directional_hit = predicted_direction == actual_direction
            p50_error = float(np.abs(p50[-1] - actual_returns[-1]))
        else:
            directional_hit = False
            p50_error = 0.0

        return TrialResult(
            query_start=query_start,
            query_end=query_end,
            actual_returns=actual_returns,
            forecast_curves=forecast_curves,
            n_matches=len(results.matches),
            top_match_score=results.best.confidence_score if results.best else 0.0,
            directional_hit=directional_hit,
            p50_error=p50_error,
        )

    except Exception as exc:
        warnings.warn(
            f"Trial at position {query_start} failed: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return TrialResult(
            query_start=query_start,
            query_end=query_end,
            actual_returns=actual_returns,
            forecast_curves={},
            n_matches=0,
            top_match_score=0.0,
            directional_hit=False,
            p50_error=0.0,
            skipped=True,
            skip_reason=f"exception: {exc}",
        )


def _run_sequential(
    trial_args: list[tuple],
    progress_fn: Callable[[int, int], None] | None,
) -> list[TrialResult]:
    total = len(trial_args)
    results = []
    for i, args in enumerate(trial_args):
        results.append(_run_single_trial(args))
        if progress_fn is not None:
            progress_fn(i + 1, total)
    return results


def _run_parallel(
    trial_args: list[tuple],
    n_workers: int,
    progress_fn: Callable[[int, int], None] | None,
) -> list[TrialResult]:
    total = len(trial_args)
    results: list[TrialResult] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_run_single_trial, args) for args in trial_args]
        for future in futures:
            results.append(future.result())
            completed += 1
            if progress_fn is not None:
                progress_fn(completed, total)
    return results
