"""Public API for The Similarity."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from the_similarity.config import Config
from the_similarity.io.loader import load as _load, TimeSeries
from the_similarity.core.normalizer import normalize
from the_similarity.core.matcher import ProgressCallback, ProgressEvent, find_matches
from the_similarity.core.scorer import MatchResult
from the_similarity.core.projector import project as _project, Forecast
from the_similarity.core.ensemble import (
    ensemble_forecast as _ensemble_forecast,
    EnsembleForecast,
    MonteCarloResult,
    RegimeConditionalResult,
    ConformalResult,
)
from the_similarity.methods.koopman import koopman_evolve
from the_similarity.viz.plotter import plot_matches, plot_forecast


def load(source, column: str = "close", date_column: str | None = None) -> TimeSeries:
    """Load time series data from CSV, parquet, DataFrame, dict, or numpy array."""
    return _load(source, column=column, date_column=date_column)


class SearchResults:
    """Container for search results."""

    def __init__(self, matches: list[MatchResult], query: np.ndarray):
        self.matches = matches
        self.query = query

    @property
    def best(self) -> MatchResult | None:
        """Highest confidence match."""
        return self.matches[0] if self.matches else None

    def summary(self) -> str:
        """Print score breakdown table for top matches."""
        lines = [f"SearchResults: {len(self.matches)} matches\n"]
        for i, m in enumerate(self.matches[:10]):
            b = m.score_breakdown
            lines.append(
                f"  #{i+1}  score={m.confidence_score:5.1f}  "
                f"dtw={b.dtw:.2f}  pear={b.pearson_warped:.2f}  "
                f"bemp_r2={b.bempedelis_r2:.2f}  koop={b.koopman:.2f}  "
                f"wvlt={b.wavelet_spectrum:.2f}  emd={b.emd:.2f}  "
                f"tda={b.tda:.2f}  te={b.transfer_entropy:.2f}"
            )
            if m.start_date:
                lines[-1] += f"  [{m.start_date} → {m.end_date}]"
        result = "\n".join(lines)
        print(result)
        return result

    def __repr__(self) -> str:
        return f"SearchResults({len(self.matches)} matches)"


def search(
    query: TimeSeries | np.ndarray,
    history: TimeSeries | np.ndarray,
    top_k: int = 20,
    config: Config | None = None,
    weights: dict[str, float] | None = None,
    exclude_self: bool = True,
    feature_store=None,
    progress_fn: ProgressCallback | None = None,
    **kwargs,
) -> SearchResults:
    """Search history for patterns similar to query.

    Args:
        query: The pattern to search for (TimeSeries or array).
        history: Full historical data to search through.
        top_k: Number of top matches to return.
        config: Pipeline configuration. Created with defaults if None.
        weights: Optional custom confidence score weights (overrides config).
        exclude_self: If True and query is a slice of history, exclude the query region.
        feature_store: Optional FeatureStore for caching expensive computations.
        **kwargs: Additional config overrides (stride, normalization, etc).

    Returns:
        SearchResults with ranked matches.
    """
    if config is None:
        config = Config()
    else:
        # Copy to avoid mutating the caller's config (statelessness)
        from copy import deepcopy
        config = deepcopy(config)
    if weights is not None:
        config.weights.update(weights)
    for key, val in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, val)

    q_values = query.values if isinstance(query, TimeSeries) else np.asarray(query, dtype=np.float64)
    h_values = history.values if isinstance(history, TimeSeries) else np.asarray(history, dtype=np.float64)
    h_dates = history.dates if isinstance(history, TimeSeries) else None

    # Auto-detect query region for self-exclusion
    exclude_region = None
    if exclude_self and isinstance(query, TimeSeries) and isinstance(history, TimeSeries):
        # Try to find query in history by value match
        for i in range(len(h_values) - len(q_values) + 1):
            if np.array_equal(h_values[i:i + len(q_values)], q_values):
                exclude_region = (i, i + len(q_values))
                break

    ds_hash = ""
    if feature_store is not None:
        from the_similarity.core.feature_store import dataset_hash
        ds_hash = dataset_hash(h_values)

    matches = find_matches(
        query=q_values,
        history=h_values,
        top_k=top_k,
        config=config,
        dates=h_dates,
        exclude_query_region=exclude_region,
        feature_store=feature_store,
        ds_hash=ds_hash,
        progress_fn=progress_fn,
    )

    return SearchResults(matches=matches, query=q_values)


def project(
    matches: list[MatchResult] | SearchResults,
    history: TimeSeries | np.ndarray,
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
    query: TimeSeries | np.ndarray | None = None,
    config: Config | None = None,
) -> Forecast:
    """Generate forward projection from matched patterns.

    Combines weighted historical projection with an optional Koopman
    operator forecast. If a query is provided (or matches is a
    SearchResults with a stored query), the Koopman operator is fitted
    on the query and evolved forward to produce a separate dynamical
    forecast trajectory.

    Args:
        matches: Match results or SearchResults object.
        history: Full historical data.
        forward_bars: How many bars to project forward.
        percentiles: Percentile levels for uncertainty bands.
        query: Query series for Koopman forward evolution. If matches
            is a SearchResults, the query is extracted automatically.

    Returns:
        Forecast with projection curves and optional koopman_forecast.
    """
    q_values = None
    if isinstance(matches, SearchResults):
        q_values = matches.query
        matches = matches.matches
    if query is not None:
        q_values = query.values if isinstance(query, TimeSeries) else np.asarray(query, dtype=np.float64)

    h_values = history.values if isinstance(history, TimeSeries) else np.asarray(history, dtype=np.float64)

    forecast = _project(
        matches=matches,
        history=h_values,
        forward_bars=forward_bars,
        percentiles=percentiles,
        config=config,
    )

    # Koopman forward evolution on the query
    if q_values is not None:
        forecast.koopman_forecast = koopman_evolve(q_values, forward_bars)

    # Blend Koopman into curves if available
    if forecast.koopman_forecast is not None and config is not None:
        blend_w = config.koopman_blend_weight
        if blend_w > 0 and 50 in forecast.curves:
            koop = forecast.koopman_forecast.trajectory
            p50 = forecast.curves[50]
            blend_len = min(len(p50), len(koop))
            blended = np.zeros_like(p50)
            for i in range(len(p50)):
                if i < blend_len:
                    blended[i] = (1 - blend_w) * p50[i] + blend_w * koop[i]
                else:
                    blended[i] = p50[i]
            forecast.curves[50] = blended

    return forecast


def ensemble_project(
    matches: list[MatchResult] | SearchResults,
    history: TimeSeries | np.ndarray,
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
    query: TimeSeries | np.ndarray | None = None,
    config: Config | None = None,
    n_simulations: int = 1000,
    conformal_coverage: float = 0.9,
    regime_soft_weight: float = 0.5,
    mc_weight: float = 0.3,
    regime_weight: float = 0.3,
    historical_weight: float = 0.4,
    seed: int | None = 42,
) -> EnsembleForecast:
    """Generate an ensemble forecast combining multiple projection methods.

    Blends three signals:
    1. Historical weighted quantiles (standard projector)
    2. Monte Carlo simulation from match distribution
    3. Regime-conditional projection (filtered by query regime)

    Then applies conformal prediction for calibrated intervals.

    Args:
        matches: Match results or SearchResults object.
        history: Full historical data.
        forward_bars: How many bars to project forward.
        percentiles: Percentile levels for uncertainty bands.
        query: Query series for regime detection. Extracted from
            SearchResults automatically if available.
        config: Pipeline config.
        n_simulations: Number of Monte Carlo paths.
        conformal_coverage: Coverage level for conformal intervals (0-1).
        regime_soft_weight: How aggressively to filter incompatible regimes.
        mc_weight: Weight for Monte Carlo component.
        regime_weight: Weight for regime-conditional component.
        historical_weight: Weight for standard historical projection.
        seed: Random seed for reproducibility.

    Returns:
        EnsembleForecast with blended curves and component results.
    """
    q_values = None
    if isinstance(matches, SearchResults):
        q_values = matches.query
        matches = matches.matches
    if query is not None:
        q_values = query.values if isinstance(query, TimeSeries) else np.asarray(query, dtype=np.float64)

    h_values = history.values if isinstance(history, TimeSeries) else np.asarray(history, dtype=np.float64)

    return _ensemble_forecast(
        matches=matches,
        history=h_values,
        query=q_values,
        forward_bars=forward_bars,
        percentiles=percentiles,
        config=config,
        n_simulations=n_simulations,
        conformal_coverage=conformal_coverage,
        regime_soft_weight=regime_soft_weight,
        mc_weight=mc_weight,
        regime_weight=regime_weight,
        historical_weight=historical_weight,
        seed=seed,
    )


def plot(
    results: SearchResults,
    forecast: Forecast | None = None,
    top_n: int = 5,
    show: bool = True,
) -> None:
    """Visualize matches and optional forecast.

    Args:
        results: Search results.
        forecast: Optional forecast to plot alongside.
        top_n: Number of top matches to show.
        show: Whether to call plt.show().
    """
    plot_matches(results.query, results.matches, top_n=top_n)

    if forecast is not None:
        anchor = results.query[-1]
        plot_forecast(forecast, anchor_value=anchor)

    if show:
        plt.show()


def _resample_timeseries(
    ts: TimeSeries,
    target_timeframe: str,
) -> TimeSeries:
    """Resample a TimeSeries to a coarser timeframe.

    Uses pandas resample with .last() aggregation on close prices.

    Args:
        ts: Source TimeSeries with dates.
        target_timeframe: Pandas-compatible frequency string (e.g., "1h", "4h", "1D").

    Returns:
        Resampled TimeSeries.

    Raises:
        ValueError: If TimeSeries has no dates.
    """
    if ts.dates is None:
        raise ValueError("Cannot resample TimeSeries without dates")

    import pandas as pd
    df = pd.DataFrame({"close": ts.values}, index=pd.DatetimeIndex(ts.dates))
    resampled = df.resample(target_timeframe).last().dropna()

    if len(resampled) < 2:
        raise ValueError(f"Resampling to '{target_timeframe}' produced fewer than 2 bars")

    return TimeSeries(
        values=resampled["close"].values.astype(np.float64),
        dates=resampled.index.values,
        name=f"{ts.name}@{target_timeframe}",
    )


def _deduplicate_matches(
    matches: list[MatchResult],
    top_k: int,
    overlap_threshold: float = 0.5,
) -> list[MatchResult]:
    """Remove overlapping matches, keeping highest-scoring ones.

    Two matches overlap if the fraction of shared bars exceeds
    overlap_threshold.
    """
    if not matches:
        return []

    # Sort by confidence descending
    sorted_matches = sorted(matches, key=lambda m: m.confidence_score, reverse=True)
    kept: list[MatchResult] = []

    for match in sorted_matches:
        if len(kept) >= top_k:
            break

        overlaps = False
        for existing in kept:
            # Check temporal overlap
            overlap_start = max(match.start_idx, existing.start_idx)
            overlap_end = min(match.end_idx, existing.end_idx)
            if overlap_end > overlap_start:
                overlap_len = overlap_end - overlap_start
                match_len = match.end_idx - match.start_idx
                if match_len > 0 and overlap_len / match_len > overlap_threshold:
                    overlaps = True
                    break

        if not overlaps:
            kept.append(match)

    return kept


def cross_timeframe_search(
    query: TimeSeries | np.ndarray,
    history: TimeSeries,
    timeframes: list[str],
    top_k: int = 20,
    config: Config | None = None,
    min_window: int = 10,
    overlap_threshold: float = 0.5,
    feature_store=None,
    **kwargs,
) -> SearchResults:
    """Search for patterns across multiple timeframes.

    Resamples history to each target timeframe, runs search() on each,
    then merges and deduplicates results.

    The query is used at its original resolution. For coarser timeframes,
    the effective window_size is scaled down proportionally. Timeframes
    where the scaled window would be < min_window are skipped.

    Args:
        query: Query pattern (TimeSeries with dates, or array).
        history: Full history with dates (required for resampling).
        timeframes: List of pandas frequency strings (e.g., ["1h", "4h", "1D"]).
        top_k: Total matches to return after merge + dedup.
        config: Pipeline config.
        min_window: Minimum window size after scaling. Timeframes producing
            fewer bars are skipped.
        overlap_threshold: Fraction of overlap to consider matches duplicates.
        feature_store: Optional FeatureStore for caching.
        **kwargs: Passed through to search().

    Returns:
        SearchResults with matches from all timeframes, deduplicated.

    Raises:
        ValueError: If history has no dates.
    """
    if not isinstance(history, TimeSeries) or history.dates is None:
        raise ValueError("history must be a TimeSeries with dates for cross-timeframe search")

    if config is None:
        config = Config()

    q_values = query.values if isinstance(query, TimeSeries) else np.asarray(query, dtype=np.float64)
    query_len = len(q_values)

    all_matches: list[MatchResult] = []

    for tf in timeframes:
        try:
            resampled = _resample_timeseries(history, tf)
        except ValueError:
            continue

        # Scale window size: ratio of resampled length to original length
        scale_ratio = len(resampled) / len(history)
        scaled_window = max(1, int(round(query_len * scale_ratio)))

        if scaled_window < min_window:
            continue

        # Create a scaled query by resampling the original query
        if scaled_window != query_len:
            # Resample query to match the scaled window size
            x_old = np.linspace(0, 1, query_len)
            x_new = np.linspace(0, 1, scaled_window)
            scaled_query = np.interp(x_new, x_old, q_values)
        else:
            scaled_query = q_values

        try:
            results = search(
                query=scaled_query,
                history=resampled,
                top_k=top_k,
                config=config,
                feature_store=feature_store,
                exclude_self=False,
                **kwargs,
            )
        except Exception:
            continue

        # Tag each match with its source timeframe
        for match in results.matches:
            match.source_timeframe = tf

        all_matches.extend(results.matches)

    # Deduplicate and return top_k
    deduped = _deduplicate_matches(all_matches, top_k, overlap_threshold)

    return SearchResults(matches=deduped, query=q_values)


def backtest(
    history: TimeSeries | np.ndarray,
    window_size: int,
    forward_bars: int = 50,
    n_trials: int = 100,
    config: Config | None = None,
    seed: int | None = 42,
    n_workers: int | None = None,
    progress_fn=None,
    top_k: int = 10,
    feature_store=None,
):
    """Run walk-forward backtest to validate the search pipeline.

    Args:
        history: Full historical data to backtest on.
        window_size: Length of the query window for each trial.
        forward_bars: How many bars to project forward.
        n_trials: Number of random trials.
        config: Pipeline configuration. Uses defaults if None.
        seed: Random seed for reproducibility.
        n_workers: Parallel workers. None = auto.
        progress_fn: Optional callback(completed, total).
        top_k: Matches per trial.
        feature_store: Optional FeatureStore for caching expensive computations.

    Returns:
        BacktestReport with per-trial results and aggregate metrics.
    """
    from the_similarity.core.backtester import run_backtest as _run_backtest

    h_values = history.values if isinstance(history, TimeSeries) else np.asarray(history, dtype=np.float64)

    return _run_backtest(
        history=h_values,
        window_size=window_size,
        forward_bars=forward_bars,
        n_trials=n_trials,
        config=config,
        seed=seed,
        n_workers=n_workers,
        progress_fn=progress_fn,
        top_k=top_k,
    )
