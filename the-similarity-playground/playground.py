from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests


ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / "the_similarity"
DATA_ROOT = ROOT / "the-similarity-data"
API_ROOT = ROOT / "the-similarity-api"
APP_ROOT = ROOT / "the-similarity-app"
MANIFEST_PATH = DATA_ROOT / "manifests" / "catalog.json"

# ---------------------------------------------------------------------------
# Score field names (must match ScoreBreakdown dataclass in scorer.py)
# ---------------------------------------------------------------------------
SCORE_FIELDS = [
    "bempedelis_r2", "bempedelis_smoothness", "koopman",
    "wavelet_spectrum", "emd", "tda", "dtw", "pearson_warped",
    "transfer_entropy",
]

SCORE_LABELS = {
    "bempedelis_r2": "Bempedelis R²",
    "bempedelis_smoothness": "Bempedelis Smooth",
    "koopman": "Koopman",
    "wavelet_spectrum": "Wavelet",
    "emd": "EMD",
    "tda": "TDA",
    "dtw": "DTW",
    "pearson_warped": "Pearson",
    "transfer_entropy": "Transfer Ent.",
}

REGIME_COLORS = {
    "trending_up": "rgba(34,197,94,0.15)",
    "trending_down": "rgba(239,68,68,0.15)",
    "mean_reverting": "rgba(168,85,247,0.15)",
    "high_vol": "rgba(249,115,22,0.15)",
    "low_vol": "rgba(59,130,246,0.15)",
}

REGIME_COLORS_SOLID = {
    "trending_up": "#22c55e",
    "trending_down": "#ef4444",
    "mean_reverting": "#a855f7",
    "high_vol": "#f97316",
    "low_vol": "#3b82f6",
}


# ═══════════════════════════════════════════════════════════════════════════
# Bootstrap / Data Loading
# ═══════════════════════════════════════════════════════════════════════════

def bootstrap_imports() -> None:
    import sys
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def load_manifest() -> pd.DataFrame:
    payload = json.loads(MANIFEST_PATH.read_text())
    return pd.DataFrame(payload["datasets"]).sort_values(
        ["asset_class", "symbol", "timeframe", "source"]
    )


def dataset_path(asset_class: str, symbol: str, timeframe: str) -> Path:
    manifest = load_manifest()
    rows = manifest[
        (manifest["asset_class"] == asset_class)
        & (manifest["symbol"] == symbol)
        & (manifest["timeframe"] == timeframe)
    ]
    if rows.empty:
        raise KeyError(f"No dataset found for {asset_class}/{symbol}/{timeframe}")
    relative_path = rows.iloc[0]["path"]
    return DATA_ROOT / relative_path


def read_candles(asset_class: str, symbol: str, timeframe: str) -> pd.DataFrame:
    path = dataset_path(asset_class, symbol, timeframe)
    frame = pd.read_parquet(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


def build_query_slice(frame: pd.DataFrame, window_size: int, end_offset: int = 0) -> pd.DataFrame:
    if window_size <= 1:
        raise ValueError("window_size must be greater than 1")
    if len(frame) <= window_size + end_offset:
        raise ValueError("frame is too short for the requested query window")
    end_index = len(frame) - end_offset
    start_index = end_index - window_size
    return frame.iloc[start_index:end_index].copy()


# ═══════════════════════════════════════════════════════════════════════════
# Engine Wrappers
# ═══════════════════════════════════════════════════════════════════════════

def run_local_search(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    window_size: int = 100,
    top_k: int = 10,
    stride: int = 5,
    end_offset: int = 0,
    forward_bars: int = 30,
    active_methods: list[str] | None = None,
    tier1_candidates: int | None = 250,
    tier2_candidates: int | None = 40,
    percentiles: list[int] | None = None,
):
    bootstrap_imports()
    import the_similarity

    history_frame = read_candles(asset_class, symbol, timeframe)
    query_frame = build_query_slice(history_frame, window_size=window_size, end_offset=end_offset)

    history = the_similarity.load(history_frame, column="close", date_column="timestamp")
    query = the_similarity.load(query_frame, column="close", date_column="timestamp")

    results = the_similarity.search(
        query=query,
        history=history,
        top_k=top_k,
        stride=stride,
        active_methods=active_methods or SCORE_FIELDS,
        tier1_candidates=tier1_candidates,
        tier2_candidates=tier2_candidates,
    )
    forecast = the_similarity.project(
        results,
        history,
        forward_bars=forward_bars,
        percentiles=percentiles or [10, 25, 50, 75, 90],
    )

    return {
        "history_frame": history_frame,
        "query_frame": query_frame,
        "results": results,
        "forecast": forecast,
    }


def run_backtest_local(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    window_size: int = 100,
    forward_bars: int = 30,
    n_trials: int = 20,
    top_k: int = 10,
    active_methods: list[str] | None = None,
    seed: int = 42,
    progress_fn=None,
):
    bootstrap_imports()
    import the_similarity
    from the_similarity.config import Config

    history_frame = read_candles(asset_class, symbol, timeframe)
    history = the_similarity.load(history_frame, column="close", date_column="timestamp")

    config = Config()
    if active_methods:
        config.active_methods = active_methods

    report = the_similarity.backtest(
        history=history,
        window_size=window_size,
        forward_bars=forward_bars,
        n_trials=n_trials,
        config=config,
        seed=seed,
        top_k=top_k,
        progress_fn=progress_fn,
        n_workers=1,
    )
    return report


# ═══════════════════════════════════════════════════════════════════════════
# Data Extraction Helpers
# ═══════════════════════════════════════════════════════════════════════════

def top_matches_frame(results) -> pd.DataFrame:
    rows = []
    for match in results.matches:
        row = {
            "start_idx": match.start_idx,
            "end_idx": match.end_idx,
            "start_date": match.start_date,
            "end_date": match.end_date,
            "confidence_score": match.confidence_score,
        }
        for field in SCORE_FIELDS:
            row[field] = getattr(match.score_breakdown, field, 0.0)
        row["transform_r2"] = match.transform_r2
        row["regime"] = match.regime
        rows.append(row)
    return pd.DataFrame(rows)


def forecast_summary_frame(forecast) -> pd.DataFrame:
    rows = []
    for percentile, curve in forecast.curves.items():
        rows.append({
            "percentile": percentile,
            "terminal_return": float(curve[-1]) if len(curve) else 0.0,
            "bars": forecast.bars,
        })
    return pd.DataFrame(rows).sort_values("percentile")


def theory_scorecard(results, forecast) -> dict[str, float]:
    best = results.best
    card: dict[str, float] = {
        "match_count": float(len(results.matches)),
        "best_confidence": float(best.confidence_score if best else 0.0),
    }
    if best:
        for field in SCORE_FIELDS:
            card[f"best_{field}"] = float(getattr(best.score_breakdown, field, 0.0))
    for p in [10, 25, 50, 75, 90]:
        card[f"forecast_p{p}_terminal"] = (
            float(forecast.curves[p][-1]) if p in forecast.curves else 0.0
        )
    return card


# ═══════════════════════════════════════════════════════════════════════════
# API Helpers
# ═══════════════════════════════════════════════════════════════════════════

def run_api_search(payload: dict, *, base_url: str = "http://127.0.0.1:8000", timeout: int = 60) -> dict:
    response = requests.post(f"{base_url.rstrip('/')}/search", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def make_api_payload_from_dataset(
    asset_class: str, symbol: str, timeframe: str, *,
    window_size: int = 100, top_k: int = 10, stride: int = 5,
    end_offset: int = 0, forward_bars: int = 30,
    active_methods: list[str] | None = None,
    tier1_candidates: int | None = 250, tier2_candidates: int | None = 40,
    percentiles: list[int] | None = None,
) -> dict:
    history_frame = read_candles(asset_class, symbol, timeframe)
    query_frame = build_query_slice(history_frame, window_size=window_size, end_offset=end_offset)
    return {
        "queryValues": query_frame["close"].tolist(),
        "historyValues": history_frame["close"].tolist(),
        "topK": top_k,
        "forwardBars": forward_bars,
        "excludeSelf": True,
        "stride": stride,
        "activeMethods": active_methods or SCORE_FIELDS,
        "tier1Candidates": tier1_candidates,
        "tier2Candidates": tier2_candidates,
        "percentiles": percentiles or [10, 25, 50, 75, 90],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Plotly Chart Builders
# ═══════════════════════════════════════════════════════════════════════════

_LAYOUT_DEFAULTS = dict(
    template="plotly_dark",
    paper_bgcolor="#0d1117",
    plot_bgcolor="#0d1117",
    font=dict(family="JetBrains Mono, monospace", size=12, color="#c9d1d9"),
    margin=dict(l=60, r=30, t=50, b=50),
)


def _apply_layout(fig: go.Figure, **kwargs) -> go.Figure:
    merged = {**_LAYOUT_DEFAULTS, **kwargs}
    fig.update_layout(**merged)
    fig.update_xaxes(gridcolor="#21262d", zeroline=False)
    fig.update_yaxes(gridcolor="#21262d", zeroline=False)
    return fig


def plot_data_universe(manifest: pd.DataFrame) -> go.Figure:
    """Gantt-style timeline showing data coverage for each dataset."""
    fig = go.Figure()
    manifest = manifest.copy().reset_index(drop=True)
    manifest["start_dt"] = pd.to_datetime(manifest["start_timestamp"])
    manifest["end_dt"] = pd.to_datetime(manifest["end_timestamp"])
    manifest["label"] = manifest["asset_class"] + "/" + manifest["symbol"] + "/" + manifest["timeframe"]

    colors = {"stocks": "#3b82f6", "crypto": "#f59e0b", "forex": "#22c55e", "commodities": "#a855f7"}

    for i, row in manifest.iterrows():
        color = colors.get(row["asset_class"], "#6b7280")
        fig.add_trace(go.Bar(
            x=[(row["end_dt"] - row["start_dt"]).days],
            y=[row["label"]],
            base=[row["start_dt"]],
            orientation="h",
            marker_color=color,
            hovertemplate=(
                f"<b>{row['label']}</b><br>"
                f"Start: {row['start_dt']:%Y-%m-%d}<br>"
                f"End: {row['end_dt']:%Y-%m-%d}<br>"
                f"Rows: {row['row_count']:,}<extra></extra>"
            ),
            showlegend=False,
        ))

    _apply_layout(fig, title="Data Universe — Coverage Timeline", height=420, barmode="stack")
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="")
    return fig


def plot_query_vs_matches(query_frame: pd.DataFrame, results, top_n: int = 5) -> go.Figure:
    """Interactive overlay of query vs top-N matched patterns."""
    fig = go.Figure()

    query_values = query_frame["close"].values
    query_norm = (query_values - query_values.min()) / max(query_values.max() - query_values.min(), 1e-9)
    bar_idx = list(range(len(query_norm)))

    fig.add_trace(go.Scatter(
        x=bar_idx, y=query_norm,
        mode="lines", name="Query",
        line=dict(color="#60a5fa", width=3),
    ))

    match_colors = ["#f59e0b", "#22c55e", "#a855f7", "#ef4444", "#06b6d4",
                    "#ec4899", "#84cc16", "#f97316", "#6366f1", "#14b8a6"]

    for i, match in enumerate(results.matches[:top_n]):
        if match.matched_series is None:
            continue
        mv = np.array(match.matched_series)
        mn = (mv - mv.min()) / max(mv.max() - mv.min(), 1e-9)
        color = match_colors[i % len(match_colors)]

        scores_text = "<br>".join(
            f"{SCORE_LABELS.get(f, f)}: {getattr(match.score_breakdown, f, 0):.3f}"
            for f in SCORE_FIELDS
        )

        fig.add_trace(go.Scatter(
            x=bar_idx[:len(mn)], y=mn,
            mode="lines",
            name=f"#{i+1} ({match.confidence_score:.1f})",
            line=dict(color=color, width=1.5, dash="dot" if i > 0 else "solid"),
            opacity=0.8,
            hovertemplate=(
                f"<b>Match #{i+1}</b><br>"
                f"Score: {match.confidence_score:.2f}<br>"
                f"{match.start_date} → {match.end_date}<br>"
                f"{scores_text}<extra></extra>"
            ),
        ))

    _apply_layout(fig, title=f"Query vs Top-{top_n} Matches (normalized)", height=450)
    fig.update_xaxes(title_text="Bar")
    fig.update_yaxes(title_text="Normalized Close")
    return fig


def plot_score_radar(match, title: str = "Score Breakdown") -> go.Figure:
    """9-axis radar chart showing each method's contribution."""
    scores = [getattr(match.score_breakdown, f, 0.0) for f in SCORE_FIELDS]
    labels = [SCORE_LABELS.get(f, f) for f in SCORE_FIELDS]

    # Close the polygon
    scores_closed = scores + [scores[0]]
    labels_closed = labels + [labels[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=scores_closed,
        theta=labels_closed,
        fill="toself",
        fillcolor="rgba(96,165,250,0.2)",
        line=dict(color="#60a5fa", width=2),
        name="Scores",
        hovertemplate="%{theta}: %{r:.3f}<extra></extra>",
    ))

    _apply_layout(fig, title=title, height=450)
    fig.update_layout(
        polar=dict(
            bgcolor="#0d1117",
            radialaxis=dict(range=[0, 1], gridcolor="#21262d", tickfont=dict(size=10)),
            angularaxis=dict(gridcolor="#21262d"),
        ),
    )
    return fig


def plot_forecast_cone(forecast, *, show_koopman: bool = True) -> go.Figure:
    """Forecast fan chart with percentile bands and optional Koopman overlay."""
    fig = go.Figure()
    bars_x = list(range(forecast.bars))

    # Individual match paths (faint)
    if forecast.all_paths is not None and forecast.all_paths.shape[0] > 0:
        for i in range(forecast.all_paths.shape[0]):
            path = forecast.all_paths[i]
            fig.add_trace(go.Scatter(
                x=bars_x[:len(path)], y=path,
                mode="lines", line=dict(color="#4b5563", width=0.5),
                opacity=0.3, showlegend=False,
                hoverinfo="skip",
            ))

    # Percentile bands
    band_colors = {10: "#ef4444", 25: "#f59e0b", 50: "#22c55e", 75: "#f59e0b", 90: "#ef4444"}
    band_widths = {10: 1, 25: 1.5, 50: 2.5, 75: 1.5, 90: 1}
    band_dashes = {10: "dot", 25: "dash", 50: "solid", 75: "dash", 90: "dot"}

    for p in sorted(forecast.curves.keys()):
        curve = forecast.curves[p]
        fig.add_trace(go.Scatter(
            x=bars_x[:len(curve)], y=curve,
            mode="lines",
            name=f"P{p}",
            line=dict(
                color=band_colors.get(p, "#6b7280"),
                width=band_widths.get(p, 1),
                dash=band_dashes.get(p, "solid"),
            ),
            hovertemplate=f"P{p}: %{{y:.4f}}<extra></extra>",
        ))

    # Fill between P10 and P90
    if 10 in forecast.curves and 90 in forecast.curves:
        p10 = forecast.curves[10]
        p90 = forecast.curves[90]
        n = min(len(p10), len(p90))
        fig.add_trace(go.Scatter(
            x=bars_x[:n] + bars_x[:n][::-1],
            y=list(p90[:n]) + list(p10[:n])[::-1],
            fill="toself",
            fillcolor="rgba(249,115,22,0.08)",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ))

    # Koopman overlay
    if show_koopman and forecast.koopman_forecast is not None:
        traj = forecast.koopman_forecast.trajectory
        unc = forecast.koopman_forecast.uncertainty
        fig.add_trace(go.Scatter(
            x=bars_x[:len(traj)], y=traj,
            mode="lines",
            name="Koopman",
            line=dict(color="#a78bfa", width=2, dash="dashdot"),
            hovertemplate="Koopman: %{y:.4f}<extra></extra>",
        ))
        if unc is not None and len(unc) == len(traj):
            fig.add_trace(go.Scatter(
                x=bars_x[:len(traj)] + bars_x[:len(traj)][::-1],
                y=list(traj + unc) + list(traj - unc)[::-1],
                fill="toself",
                fillcolor="rgba(167,139,250,0.1)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, hoverinfo="skip",
            ))

    # Zero reference line
    fig.add_hline(y=0, line_dash="dot", line_color="#4b5563", opacity=0.5)

    _apply_layout(fig, title="Forecast Cone — Forward Projection", height=420)
    fig.update_xaxes(title_text="Forward Bars")
    fig.update_yaxes(title_text="Return")
    return fig


def plot_terminal_distribution(forecast) -> go.Figure:
    """Histogram of terminal returns from all match forward paths."""
    if forecast.all_paths is None or forecast.all_paths.shape[0] == 0:
        fig = go.Figure()
        _apply_layout(fig, title="Terminal Return Distribution (no data)")
        return fig

    terminals = forecast.all_paths[:, -1]
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=terminals,
        nbinsx=20,
        marker_color="#60a5fa",
        opacity=0.7,
        hovertemplate="Return: %{x:.4f}<br>Count: %{y}<extra></extra>",
    ))

    # Mark percentiles
    for p in sorted(forecast.curves.keys()):
        val = forecast.curves[p][-1]
        fig.add_vline(x=val, line_dash="dash", line_color="#f59e0b", opacity=0.7,
                      annotation_text=f"P{p}", annotation_position="top")

    _apply_layout(fig, title="Terminal Return Distribution", height=350)
    fig.update_xaxes(title_text="Terminal Return")
    fig.update_yaxes(title_text="Count")
    return fig


def plot_calibration_curve(report) -> go.Figure:
    """Calibration curve: expected vs observed percentile coverage."""
    cal = report.calibration
    percentiles = sorted(cal.keys())
    expected = [p / 100.0 for p in percentiles]
    observed = [cal[p] for p in percentiles]

    fig = go.Figure()

    # Perfect calibration line
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1],
        mode="lines", line=dict(color="#4b5563", dash="dot"),
        showlegend=False, hoverinfo="skip",
    ))

    fig.add_trace(go.Scatter(
        x=expected, y=observed,
        mode="lines+markers",
        name="Calibration",
        line=dict(color="#60a5fa", width=2),
        marker=dict(size=10, color="#60a5fa"),
        text=[f"P{p}" for p in percentiles],
        hovertemplate="P%{text}<br>Expected: %{x:.0%}<br>Observed: %{y:.0%}<extra></extra>",
    ))

    _apply_layout(fig, title="Calibration Curve", height=400)
    fig.update_xaxes(title_text="Expected Coverage", range=[0, 1])
    fig.update_yaxes(title_text="Observed Coverage", range=[0, 1])
    return fig


def plot_backtest_summary(report) -> go.Figure:
    """4-panel backtest summary: hit rate, MAE, CRPS, skip rate."""
    metrics = {
        "Hit Rate": f"{report.hit_rate:.1%}",
        "Mean Abs Error": f"{report.mean_error:.4f}",
        "CRPS": f"{report.crps:.4f}",
        "Valid Trials": f"{report.n_valid_trials}/{len(report.trials)}",
    }

    fig = go.Figure()
    fig.add_trace(go.Table(
        header=dict(
            values=["Metric", "Value"],
            fill_color="#161b22",
            font=dict(color="#c9d1d9", size=14),
            align="left",
        ),
        cells=dict(
            values=[list(metrics.keys()), list(metrics.values())],
            fill_color="#0d1117",
            font=dict(color="#c9d1d9", size=13),
            align="left",
            height=30,
        ),
    ))

    _apply_layout(fig, title="Backtest Summary", height=250)
    return fig


def plot_rolling_hit_rate(report, window: int = 5) -> go.Figure:
    """Rolling hit rate across valid trials."""
    valid = report.valid_trials
    if len(valid) < window:
        fig = go.Figure()
        _apply_layout(fig, title="Rolling Hit Rate (insufficient trials)")
        return fig

    hits = [1.0 if t.directional_hit else 0.0 for t in valid]
    rolling = pd.Series(hits).rolling(window=window, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(rolling))), y=rolling,
        mode="lines",
        line=dict(color="#22c55e", width=2),
        name=f"Rolling {window}-trial hit rate",
        hovertemplate="Trial %{x}<br>Hit Rate: %{y:.0%}<extra></extra>",
    ))
    fig.add_hline(y=0.5, line_dash="dot", line_color="#ef4444", opacity=0.5,
                  annotation_text="50% baseline")

    _apply_layout(fig, title=f"Rolling Hit Rate (window={window})", height=350)
    fig.update_xaxes(title_text="Trial #")
    fig.update_yaxes(title_text="Hit Rate", range=[0, 1])
    return fig


def plot_p50_error_distribution(report) -> go.Figure:
    """Distribution of P50 forecast errors."""
    valid = report.valid_trials
    errors = [t.p50_error for t in valid]

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=errors, nbinsx=20,
        marker_color="#f59e0b", opacity=0.7,
        hovertemplate="Error: %{x:.4f}<br>Count: %{y}<extra></extra>",
    ))

    _apply_layout(fig, title="P50 Forecast Error Distribution", height=350)
    fig.update_xaxes(title_text="|P50 Terminal - Actual Terminal|")
    fig.update_yaxes(title_text="Count")
    return fig


def plot_ablation_results(ablation_df: pd.DataFrame) -> go.Figure:
    """Bar chart of method ablation impact on hit rate and CRPS."""
    fig = make_subplots(rows=1, cols=2, subplot_titles=["Δ Hit Rate", "Δ CRPS"])

    methods = ablation_df["removed_method"].tolist()
    labels = [SCORE_LABELS.get(m, m) for m in methods]
    delta_hr = ablation_df["delta_hit_rate"].tolist()
    delta_crps = ablation_df["delta_crps"].tolist()

    # Hit rate: negative delta = method was helping (removing it hurt)
    hr_colors = ["#ef4444" if d < 0 else "#22c55e" for d in delta_hr]
    fig.add_trace(go.Bar(
        x=labels, y=delta_hr,
        marker_color=hr_colors,
        hovertemplate="%{x}: %{y:+.1%}<extra></extra>",
        showlegend=False,
    ), row=1, col=1)

    # CRPS: positive delta = method was helping (removing it made CRPS worse = higher)
    crps_colors = ["#22c55e" if d > 0 else "#ef4444" for d in delta_crps]
    fig.add_trace(go.Bar(
        x=labels, y=delta_crps,
        marker_color=crps_colors,
        hovertemplate="%{x}: %{y:+.4f}<extra></extra>",
        showlegend=False,
    ), row=1, col=2)

    _apply_layout(fig, title="Method Ablation — Impact of Removing Each Method", height=400)
    return fig


def plot_regime_price_chart(
    history_frame: pd.DataFrame,
    window: int = 120,
    stride: int = 30,
) -> go.Figure:
    """Price chart with background regime coloring."""
    bootstrap_imports()
    from the_similarity.core.regime import tag_regime

    prices = history_frame["close"].values
    timestamps = history_frame["timestamp"].values

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=prices,
        mode="lines", name="Close",
        line=dict(color="#c9d1d9", width=1.5),
        hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
    ))

    # Compute rolling regime
    regimes = []
    for i in range(0, len(prices) - window + 1, stride):
        segment = prices[i:i + window]
        regime = tag_regime(segment)
        regimes.append((i, min(i + stride, len(prices) - 1), regime))

    # Draw regime background rectangles
    for start_i, end_i, regime in regimes:
        if start_i >= len(timestamps) or end_i >= len(timestamps):
            continue
        fig.add_vrect(
            x0=timestamps[start_i], x1=timestamps[end_i],
            fillcolor=REGIME_COLORS.get(regime, "rgba(100,100,100,0.1)"),
            line_width=0,
            layer="below",
        )

    # Add regime legend entries
    for regime, color in REGIME_COLORS_SOLID.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=10, color=color),
            name=regime.replace("_", " ").title(),
        ))

    _apply_layout(fig, title="Price with Regime Overlay", height=450)
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="Close Price")
    return fig


def plot_hurst_rolling(history_frame: pd.DataFrame, window: int = 120, stride: int = 10) -> go.Figure:
    """Rolling Hurst exponent over time."""
    bootstrap_imports()
    from the_similarity.core.regime import hurst_dfa

    prices = history_frame["close"].values
    timestamps = history_frame["timestamp"].values

    hurst_values = []
    hurst_times = []
    for i in range(0, len(prices) - window + 1, stride):
        h = hurst_dfa(prices[i:i + window])
        hurst_values.append(h)
        hurst_times.append(timestamps[i + window - 1])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hurst_times, y=hurst_values,
        mode="lines",
        line=dict(color="#a78bfa", width=2),
        name="Hurst Exponent",
        hovertemplate="%{x}<br>H = %{y:.3f}<extra></extra>",
    ))

    fig.add_hline(y=0.5, line_dash="dot", line_color="#4b5563", annotation_text="Random Walk (H=0.5)")
    fig.add_hline(y=0.6, line_dash="dash", line_color="#22c55e", opacity=0.4, annotation_text="Trending")
    fig.add_hline(y=0.4, line_dash="dash", line_color="#a855f7", opacity=0.4, annotation_text="Mean Reverting")

    _apply_layout(fig, title="Rolling Hurst Exponent", height=350)
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="Hurst Exponent (H)", range=[0, 1])
    return fig


def plot_cross_asset_comparison(scorecards: dict[str, dict]) -> go.Figure:
    """Heatmap of confidence scores across datasets."""
    labels = list(scorecards.keys())
    metrics = ["best_confidence", "best_dtw", "best_pearson_warped", "best_koopman"]
    metric_labels = ["Confidence", "DTW", "Pearson", "Koopman"]

    z = []
    for metric in metrics:
        row = [scorecards[label].get(metric, 0.0) for label in labels]
        z.append(row)

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        z=z,
        x=labels,
        y=metric_labels,
        colorscale="Viridis",
        hovertemplate="%{y}<br>%{x}: %{z:.3f}<extra></extra>",
    ))

    _apply_layout(fig, title="Cross-Asset Comparison", height=350)
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# Ablation Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_ablation(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    window_size: int = 100,
    forward_bars: int = 30,
    n_trials: int = 15,
    top_k: int = 10,
    seed: int = 42,
    progress_fn=None,
) -> pd.DataFrame:
    """Run N+1 backtests: baseline with all methods, then drop one at a time.

    Returns DataFrame with columns:
        removed_method, hit_rate, crps, delta_hit_rate, delta_crps
    """
    all_methods = list(SCORE_FIELDS)

    # Baseline: all methods
    if progress_fn:
        progress_fn("baseline", 0, len(all_methods) + 1)

    baseline = run_backtest_local(
        asset_class, symbol, timeframe,
        window_size=window_size, forward_bars=forward_bars,
        n_trials=n_trials, top_k=top_k, seed=seed,
        active_methods=all_methods,
    )
    baseline_hr = baseline.hit_rate
    baseline_crps = baseline.crps

    rows = [{
        "removed_method": "(baseline)",
        "hit_rate": baseline_hr,
        "crps": baseline_crps,
        "delta_hit_rate": 0.0,
        "delta_crps": 0.0,
    }]

    # Ablation: remove one method at a time
    for i, method in enumerate(all_methods):
        if progress_fn:
            progress_fn(method, i + 1, len(all_methods) + 1)

        ablated = [m for m in all_methods if m != method]
        report = run_backtest_local(
            asset_class, symbol, timeframe,
            window_size=window_size, forward_bars=forward_bars,
            n_trials=n_trials, top_k=top_k, seed=seed,
            active_methods=ablated,
        )
        rows.append({
            "removed_method": method,
            "hit_rate": report.hit_rate,
            "crps": report.crps,
            "delta_hit_rate": report.hit_rate - baseline_hr,
            "delta_crps": report.crps - baseline_crps,
        })

    return pd.DataFrame(rows)
