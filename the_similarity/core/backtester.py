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
from the_similarity.core.metrics import calibration, crps, hit_rate, mean_absolute_error


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

    def summary(self) -> str:
        lines = [
            f"BacktestReport: {self.n_valid_trials} valid trials, {self.n_skipped_trials} skipped",
            f"  window_size={self.window_size}, forward_bars={self.forward_bars}",
            f"  hit_rate={self.hit_rate:.1%}",
            f"  mean_absolute_error={self.mean_error:.4f}",
            f"  crps={self.crps:.4f}",
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


@dataclass
class EnsembleTrialResult:
    """Single walk-forward trial evaluating the full ensemble forecast.

    Captures not just the blended ensemble percentile curves, but also each
    component (basic projector, Monte Carlo, regime-conditional) alongside
    the conformal bounds so the aggregate report can compare them head-to-
    head on the same backtest positions.

    Fields mirror `TrialResult` for the ensemble blend, so the shared
    `metrics` module can score ensemble performance via duck typing
    (`forecast_curves`, `actual_returns`, `directional_hit`, `p50_error`).

    Note:
        `forecast_curves` holds the BLENDED ensemble curves. The component
        curves live in `basic_curves`, `mc_curves`, `regime_curves` to let
        reports compute per-component hit_rate / calibration without
        re-running the engine.
    """

    query_start: int
    query_end: int
    actual_returns: NDArray[np.float64]
    # Blended ensemble forecast (primary scored curves)
    forecast_curves: dict[int, NDArray[np.float64]]
    # Per-component forecasts for head-to-head comparison
    basic_curves: dict[int, NDArray[np.float64]]
    mc_curves: dict[int, NDArray[np.float64]]
    regime_curves: dict[int, NDArray[np.float64]]
    # Conformal prediction bounds — target coverage is the requested
    # marginal coverage (e.g. 0.9) for the central interval.
    conformal_lower: NDArray[np.float64]
    conformal_upper: NDArray[np.float64]
    conformal_coverage: float
    # Metadata
    n_matches: int
    top_match_score: float
    regime_tag: str
    n_regime_matches: int
    # Derived metrics from the ensemble P50
    directional_hit: bool
    p50_error: float
    # Basic-projector P50 outcome for comparison (no extra compute — we
    # already ran the basic projector inside the trial).
    basic_directional_hit: bool
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class EnsembleBacktestReport:
    """Aggregated ensemble backtest results.

    The primary scorecard (``hit_rate`` / ``mean_error`` / ``calibration`` /
    ``crps``) is computed on the BLENDED ensemble curves to answer "does the
    ensemble outperform the basic projector?" Per-component properties
    (``basic_hit_rate`` / ``ensemble_hit_rate``) expose the underlying
    comparison; ``conformal_empirical_coverage`` checks whether the
    conformal interval achieves its stated marginal coverage.
    """

    trials: list[EnsembleTrialResult]
    config: Config
    window_size: int
    forward_bars: int
    seed: int | None
    conformal_coverage: float = 0.9

    @property
    def valid_trials(self) -> list[EnsembleTrialResult]:
        return [t for t in self.trials if not t.skipped]

    @property
    def n_valid_trials(self) -> int:
        return len(self.valid_trials)

    @property
    def n_skipped_trials(self) -> int:
        return len(self.trials) - self.n_valid_trials

    # --- Ensemble scorecard (duck-typed via TrialResult interface) ---

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

    # --- Per-component comparison ---

    @property
    def ensemble_hit_rate(self) -> float:
        """Alias for `hit_rate` — explicit name for comparison contexts."""
        return self.hit_rate

    @property
    def basic_hit_rate(self) -> float:
        """Hit rate computed from the basic projector's P50 (same trials)."""
        trials = self.valid_trials
        if not trials:
            return float("nan")
        hits = sum(1 for t in trials if t.basic_directional_hit)
        return hits / len(trials)

    @property
    def conformal_empirical_coverage(self) -> float:
        """Fraction of terminal actuals inside [conformal_lower, conformal_upper].

        Gold-standard sanity check: a 90% target-coverage conformal interval
        should empirically contain ≈ 90% of observed terminal returns. A
        large gap indicates the conformal calibration is mis-specified.
        """
        trials = self.valid_trials
        if not trials:
            return float("nan")
        contained = 0
        for t in trials:
            if len(t.conformal_lower) == 0 or len(t.conformal_upper) == 0:
                continue
            actual = float(t.actual_returns[-1])
            if t.conformal_lower[-1] <= actual <= t.conformal_upper[-1]:
                contained += 1
        return contained / len(trials)

    def summary(self) -> str:
        lines = [
            f"EnsembleBacktestReport: {self.n_valid_trials} valid, {self.n_skipped_trials} skipped",
            f"  window_size={self.window_size}, forward_bars={self.forward_bars}",
            f"  basic_hit_rate={self.basic_hit_rate:.1%}",
            f"  ensemble_hit_rate={self.ensemble_hit_rate:.1%}",
            f"  ensemble_mean_error={self.mean_error:.4f}",
            f"  ensemble_crps={self.crps:.4f}",
            f"  conformal_coverage(target={self.conformal_coverage:.0%}):"
            f" empirical={self.conformal_empirical_coverage:.1%}",
            f"  ensemble_calibration:",
        ]
        for p, rate in sorted(self.calibration.items()):
            expected = p / 100.0
            delta = rate - expected
            lines.append(f"    P{p}: {rate:.1%} (expected {expected:.0%}, delta {delta:+.1%})")
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


# ---------------------------------------------------------------------------
# Ensemble backtest
# ---------------------------------------------------------------------------

def run_ensemble_backtest(
    history: NDArray[np.float64],
    window_size: int,
    forward_bars: int = 50,
    n_trials: int = 100,
    config: Config | None = None,
    seed: int | None = 42,
    n_workers: int | None = None,
    progress_fn: Callable[[int, int], None] | None = None,
    top_k: int = 10,
    mc_simulations: int = 500,
    conformal_coverage: float = 0.9,
) -> EnsembleBacktestReport:
    """Walk-forward backtest of the full ensemble forecast pipeline.

    Identical walk-forward sampling / no-look-ahead guarantees as
    ``run_backtest``, but each trial runs BOTH the basic projector and the
    full ensemble (Monte Carlo + regime-conditional + conformal), so the
    report can compare them on the same underlying positions and seeds.

    Args:
        history: 1D float64 price series.
        window_size: Query window length.
        forward_bars: Forecast horizon.
        n_trials: Random positions to sample.
        config: Pipeline config (defaults applied if None).
        seed: RNG seed for reproducibility (threads through MC sampler too).
        n_workers: Parallel workers. None ⇒ sequential (MC + conformal are
            already expensive; process-pool overhead rarely wins).
        progress_fn: Optional callback(completed, total).
        top_k: Matches per trial.
        mc_simulations: Number of Monte Carlo paths per trial.
        conformal_coverage: Target marginal coverage in (0, 1).

    Returns:
        `EnsembleBacktestReport` with blended and per-component metrics.
    """
    history = np.asarray(history, dtype=np.float64)

    # Input validation mirrors run_backtest to keep contracts aligned.
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
    if not 0.0 < conformal_coverage < 1.0:
        raise ValueError(f"conformal_coverage must be in (0, 1), got {conformal_coverage}")

    min_lookback = 3 * window_size
    min_history_len = min_lookback + window_size + forward_bars
    if len(history) < min_history_len:
        raise ValueError(
            f"history length {len(history)} is too short, need at least {min_history_len}"
        )

    if config is None:
        config = Config()

    positions = _pick_trial_positions(
        history_len=len(history),
        window_size=window_size,
        forward_bars=forward_bars,
        min_lookback=min_lookback,
        n_trials=n_trials,
        seed=seed,
    )

    # Ensemble trials run sequentially by default: the per-trial ensemble
    # cost dominates process-pool overhead, and Monte Carlo RNGs can behave
    # counter-intuitively across subprocess boundaries on some platforms.
    trials: list[EnsembleTrialResult] = []
    total = len(positions)
    for i, pos in enumerate(positions):
        trials.append(
            _run_single_ensemble_trial(
                history=history,
                query_start=pos,
                window_size=window_size,
                forward_bars=forward_bars,
                config=config,
                top_k=top_k,
                mc_simulations=mc_simulations,
                conformal_coverage=conformal_coverage,
                seed=seed,
            )
        )
        if progress_fn is not None:
            progress_fn(i + 1, total)

    return EnsembleBacktestReport(
        trials=trials,
        config=config,
        window_size=window_size,
        forward_bars=forward_bars,
        seed=seed,
        conformal_coverage=conformal_coverage,
    )


def _empty_curves(percentiles: list[int], forward_bars: int) -> dict[int, NDArray[np.float64]]:
    """Return a dict of zero-length percentile curves for failure paths."""
    return {p: np.zeros(0) for p in percentiles}


def _run_single_ensemble_trial(
    *,
    history: NDArray[np.float64],
    query_start: int,
    window_size: int,
    forward_bars: int,
    config: Config,
    top_k: int,
    mc_simulations: int,
    conformal_coverage: float,
    seed: int | None,
) -> EnsembleTrialResult:
    """Execute one ensemble backtest trial (walk-forward, no look-ahead)."""
    query_end = query_start + window_size
    forward_end = query_end + forward_bars

    query = history[query_start:query_end]
    lookback = history[:query_start]
    actual = history[query_end:forward_end]
    anchor = history[query_end - 1]

    percentiles = list(config.percentiles)
    empty_curves = _empty_curves(percentiles, forward_bars)

    if anchor == 0:
        return EnsembleTrialResult(
            query_start=query_start,
            query_end=query_end,
            actual_returns=np.zeros(forward_bars),
            forecast_curves={},
            basic_curves={},
            mc_curves={},
            regime_curves={},
            conformal_lower=np.zeros(0),
            conformal_upper=np.zeros(0),
            conformal_coverage=conformal_coverage,
            n_matches=0,
            top_match_score=0.0,
            regime_tag="",
            n_regime_matches=0,
            directional_hit=False,
            p50_error=0.0,
            basic_directional_hit=False,
            skipped=True,
            skip_reason="anchor value is zero",
        )

    actual_returns = (actual - anchor) / anchor

    try:
        # Lazy import to avoid circulars — mirrors _run_single_trial.
        from the_similarity.api import ensemble_project, project, search

        results = search(
            query=query,
            history=lookback,
            top_k=top_k,
            config=config,
            exclude_self=False,
        )
        if not results.matches:
            return EnsembleTrialResult(
                query_start=query_start, query_end=query_end,
                actual_returns=actual_returns,
                forecast_curves={}, basic_curves={}, mc_curves={}, regime_curves={},
                conformal_lower=np.zeros(0), conformal_upper=np.zeros(0),
                conformal_coverage=conformal_coverage,
                n_matches=0, top_match_score=0.0,
                regime_tag="", n_regime_matches=0,
                directional_hit=False, p50_error=0.0, basic_directional_hit=False,
                skipped=True, skip_reason="no matches found",
            )

        basic = project(
            matches=results, history=lookback,
            forward_bars=forward_bars, percentiles=percentiles,
        )
        ensemble = ensemble_project(
            matches=results, history=lookback, query=query,
            forward_bars=forward_bars, percentiles=percentiles,
            config=config, n_simulations=mc_simulations,
            conformal_coverage=conformal_coverage, seed=seed,
        )

        # Extract per-component curves. Each component may be missing (e.g.
        # regime_conditional may return None if insufficient matches) — in
        # that case we fall back to empty curves so downstream metrics
        # cleanly skip that component.
        ensemble_curves = {p: np.asarray(c) for p, c in ensemble.curves.items()}
        basic_curves = {p: np.asarray(c) for p, c in basic.curves.items()}
        mc_curves = (
            {p: np.asarray(c) for p, c in ensemble.monte_carlo.percentiles.items()}
            if ensemble.monte_carlo is not None
            else empty_curves
        )
        regime_curves = (
            {p: np.asarray(c) for p, c in ensemble.regime_conditional.curves.items()}
            if ensemble.regime_conditional is not None
            else empty_curves
        )
        conformal_lower = (
            np.asarray(ensemble.conformal.lower)
            if ensemble.conformal is not None else np.zeros(0)
        )
        conformal_upper = (
            np.asarray(ensemble.conformal.upper)
            if ensemble.conformal is not None else np.zeros(0)
        )
        regime_tag = (
            ensemble.regime_conditional.regime
            if ensemble.regime_conditional is not None else ""
        )
        n_regime_matches = (
            ensemble.regime_conditional.n_matches_used
            if ensemble.regime_conditional is not None else 0
        )

        # Ensemble P50 drives the primary directional_hit / p50_error used
        # by the inherited hit_rate / MAE metrics.
        ens_p50 = ensemble_curves.get(50)
        if ens_p50 is not None and len(ens_p50) > 0:
            ens_directional_hit = (ens_p50[-1] > 0) == (actual_returns[-1] > 0)
            ens_p50_error = float(np.abs(ens_p50[-1] - actual_returns[-1]))
        else:
            ens_directional_hit, ens_p50_error = False, 0.0

        basic_p50 = basic_curves.get(50)
        if basic_p50 is not None and len(basic_p50) > 0:
            basic_hit = (basic_p50[-1] > 0) == (actual_returns[-1] > 0)
        else:
            basic_hit = False

        return EnsembleTrialResult(
            query_start=query_start,
            query_end=query_end,
            actual_returns=actual_returns,
            forecast_curves=ensemble_curves,
            basic_curves=basic_curves,
            mc_curves=mc_curves,
            regime_curves=regime_curves,
            conformal_lower=conformal_lower,
            conformal_upper=conformal_upper,
            conformal_coverage=conformal_coverage,
            n_matches=len(results.matches),
            top_match_score=results.best.confidence_score if results.best else 0.0,
            regime_tag=regime_tag,
            n_regime_matches=n_regime_matches,
            directional_hit=ens_directional_hit,
            p50_error=ens_p50_error,
            basic_directional_hit=basic_hit,
        )

    except Exception as exc:
        warnings.warn(
            f"Ensemble trial at position {query_start} failed: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return EnsembleTrialResult(
            query_start=query_start, query_end=query_end,
            actual_returns=actual_returns,
            forecast_curves={}, basic_curves={}, mc_curves={}, regime_curves={},
            conformal_lower=np.zeros(0), conformal_upper=np.zeros(0),
            conformal_coverage=conformal_coverage,
            n_matches=0, top_match_score=0.0,
            regime_tag="", n_regime_matches=0,
            directional_hit=False, p50_error=0.0, basic_directional_hit=False,
            skipped=True, skip_reason=f"exception: {exc}",
        )
