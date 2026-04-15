"""
Matplotlib visualization for pattern match results and forecast cones.

This module provides two primary plotting functions:
- `plot_matches()` — overlays the query pattern with top-N matched segments
- `plot_forecast()` — renders the projection cone with percentile bands

AI AGENT NOTES:
- These plots use min-max normalization so different-priced assets can be
  visually compared on the same axes.
- Colors are intentionally pulled from the viridis colormap for colorblind
  safety.
- The forecast plot can show either cumulative-return paths or absolute
  prices depending on the `anchor_value` parameter.
- If you need interactive (non-matplotlib) charts, see the Next.js dashboard
  in `the-similarity-app/components/chart/` instead.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from the_similarity.core.scorer import MatchResult
from the_similarity.core.projector import Forecast


def plot_matches(
    query: np.ndarray,
    matches: list[MatchResult],
    top_n: int = 5,
    title: str = "Top Pattern Matches",
) -> Figure:
    """Plot the query pattern overlaid with top matches.

    Each series is independently min-max normalized to [0, 1] so they
    can be visually compared regardless of their original price levels.
    The query is drawn in bold black; matches are colored by rank.

    Args:
        query: Raw query window values (1D array).
        matches: Sorted match results from the search pipeline.
        top_n: How many matches to display (avoids visual clutter).
        title: Plot title.

    Returns:
        Matplotlib Figure object (call fig.savefig() or plt.show()).
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    # Normalize query to [0, 1] for visual comparison across assets.
    # This makes it easy to see shape agreement regardless of price scale.
    q_min, q_max = query.min(), query.max()
    q_range = q_max - q_min if q_max != q_min else 1.0
    q_norm = (query - q_min) / q_range
    # zorder=10 ensures the query draws on top of all match lines.
    ax.plot(q_norm, color="black", linewidth=2.5, label="Query", zorder=10)

    # Sample colors from viridis colormap — avoids the 0.0 and 1.0 extremes
    # which are too dark/light to read clearly.
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, top_n))

    for i, match in enumerate(matches[:top_n]):
        if match.matched_series is None:
            continue
        s = match.matched_series
        # Apply the same normalization to each match for fair comparison
        s_min, s_max = s.min(), s.max()
        s_range = s_max - s_min if s_max != s_min else 1.0
        s_norm = (s - s_min) / s_range

        # Build a descriptive label: rank + score + optional date range
        label = f"#{i + 1} score={match.confidence_score:.1f}"
        if match.start_date:
            label += f" ({match.start_date})"
        # Lower alpha and thinner lines keep the query visually dominant.
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

    Shows all individual projection paths as faint gray lines, with
    percentile curves overlaid as bold colored lines. The area between
    the lowest and highest percentile is filled for visual emphasis.

    Args:
        forecast: Forecast object from projector.py containing paths,
                  curves, and percentiles.
        anchor_value: The value at bar 0 (end of query window). All
                      projections are shown as cumulative returns applied
                      to this anchor, converting fractional returns to
                      absolute levels.
        title: Plot title.

    Returns:
        Matplotlib Figure object.
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(forecast.bars)

    # Sort percentiles for consistent rendering order (low to high)
    sorted_pcts = sorted(forecast.percentiles)

    # -- Individual paths --
    # Drawing all paths as faint lines gives a "spaghetti plot" view that
    # shows the full distribution shape, not just summary statistics.
    for path in forecast.all_paths:
        ax.plot(x, anchor_value * (1 + path), color="gray", alpha=0.1, linewidth=0.5)

    # -- Percentile curves --
    # Each percentile gets a distinct color for quick identification.
    # Common convention: red=bearish(P10), blue=median(P50), green=bullish(P90).
    colors = {
        10: "#d62728",  # Red — bearish tail
        25: "#ff7f0e",  # Orange — below median
        50: "#1f77b4",  # Blue — median
        75: "#17becf",  # Cyan — above median
        90: "#2ca02c",  # Green — bullish tail
    }
    for p in sorted_pcts:
        curve = forecast.curves[p]
        color = colors.get(p, "#333333")  # Fallback for custom percentiles
        ax.plot(x, anchor_value * (1 + curve), color=color, linewidth=2, label=f"P{p}")

    # -- Uncertainty band fill --
    # Fill between the extreme percentiles to make the cone visually obvious.
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

    # Dotted horizontal line at the anchor value for reference
    ax.axhline(anchor_value, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_title(title)
    ax.set_xlabel("Bars Forward")
    ax.set_ylabel("Projected Value")
    ax.legend()
    fig.tight_layout()
    return fig
