"""Public API for The Similarity."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from the_similarity.config import Config
from the_similarity.io.loader import load as _load, TimeSeries
from the_similarity.core.normalizer import normalize
from the_similarity.core.matcher import find_matches
from the_similarity.core.scorer import MatchResult
from the_similarity.core.projector import project as _project, Forecast
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

    matches = find_matches(
        query=q_values,
        history=h_values,
        top_k=top_k,
        config=config,
        dates=h_dates,
        exclude_query_region=exclude_region,
    )

    return SearchResults(matches=matches, query=q_values)


def project(
    matches: list[MatchResult] | SearchResults,
    history: TimeSeries | np.ndarray,
    forward_bars: int = 50,
    percentiles: list[int] | None = None,
) -> Forecast:
    """Generate forward projection from matched patterns.

    Args:
        matches: Match results or SearchResults object.
        history: Full historical data.
        forward_bars: How many bars to project forward.
        percentiles: Percentile levels for uncertainty bands.

    Returns:
        Forecast with projection curves.
    """
    if isinstance(matches, SearchResults):
        matches = matches.matches

    h_values = history.values if isinstance(history, TimeSeries) else np.asarray(history, dtype=np.float64)

    return _project(
        matches=matches,
        history=h_values,
        forward_bars=forward_bars,
        percentiles=percentiles,
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
