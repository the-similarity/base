from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from the_similarity.core.scorer import MatchResult
from the_similarity.core.projector import Forecast
from the_similarity.io.loader import TimeSeries


def plot_matches(
    query: np.ndarray,
    matches: list[MatchResult],
    top_n: int = 5,
    title: str = "Top Pattern Matches",
) -> Figure:
    """Plot the query pattern overlaid with top matches.

    Args:
        query: Raw query window values.
        matches: Sorted match results.
        top_n: How many matches to display.
        title: Plot title.

    Returns:
        Matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    # Normalize query to [0, 1] for visual comparison
    q_min, q_max = query.min(), query.max()
    q_range = q_max - q_min if q_max != q_min else 1.0
    q_norm = (query - q_min) / q_range
    ax.plot(q_norm, color="black", linewidth=2.5, label="Query", zorder=10)

    colors = plt.cm.viridis(np.linspace(0.2, 0.8, top_n))
    for i, match in enumerate(matches[:top_n]):
        if match.matched_series is None:
            continue
        s = match.matched_series
        s_min, s_max = s.min(), s.max()
        s_range = s_max - s_min if s_max != s_min else 1.0
        s_norm = (s - s_min) / s_range

        label = f"#{i+1} score={match.confidence_score:.1f}"
        if match.start_date:
            label += f" ({match.start_date})"
        ax.plot(s_norm, color=colors[i], linewidth=1.2, alpha=0.7, label=label)

    ax.set_title(title)
    ax.set_xlabel("Bar")
    ax.set_ylabel("Normalized Value")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig


def plot_forecast(
    forecast: Forecast,
    anchor_value: float = 1.0,
    title: str = "Forward Projection",
) -> Figure:
    """Plot forecast cone with uncertainty bands.

    Args:
        forecast: Forecast object from projector.
        anchor_value: The value at bar 0 (end of query window).
        title: Plot title.

    Returns:
        Matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(forecast.bars)

    sorted_pcts = sorted(forecast.percentiles)

    # Plot individual paths faintly
    for path in forecast.all_paths:
        ax.plot(x, anchor_value * (1 + path), color="gray", alpha=0.1, linewidth=0.5)

    # Plot percentile curves
    colors = {
        10: "#d62728",
        25: "#ff7f0e",
        50: "#1f77b4",
        75: "#17becf",
        90: "#2ca02c",
    }
    for p in sorted_pcts:
        curve = forecast.curves[p]
        color = colors.get(p, "#333333")
        ax.plot(x, anchor_value * (1 + curve), color=color, linewidth=2, label=f"P{p}")

    # Fill between lowest and highest percentile
    if len(sorted_pcts) >= 2:
        lo = forecast.curves[sorted_pcts[0]]
        hi = forecast.curves[sorted_pcts[-1]]
        ax.fill_between(
            x,
            anchor_value * (1 + lo),
            anchor_value * (1 + hi),
            alpha=0.15,
            color="#1f77b4",
        )

    ax.axhline(anchor_value, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_title(title)
    ax.set_xlabel("Bars Forward")
    ax.set_ylabel("Projected Value")
    ax.legend()
    fig.tight_layout()
    return fig
