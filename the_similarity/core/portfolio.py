"""Portfolio-level cross-asset analysis.

Phase 7c — provides tools for analyzing relationships across multiple assets:
- Cross-asset pattern scanning (lead/lag, correlation of forward returns)
- Portfolio-wide regime snapshots
- Correlation divergence detection
- Information flow (transfer entropy) network analysis
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
from numpy.typing import NDArray

from the_similarity.core.regime import tag_regime, hurst_dfa
from the_similarity.core.scorer import MatchResult
from the_similarity.methods.transfer_entropy import compute_transfer_entropy


# ---------------------------------------------------------------------------
# Cross-asset scan
# ---------------------------------------------------------------------------

@dataclass
class CrossAssetResult:
    """Result of scanning how a target asset behaves when source patterns match."""
    source_asset: str
    target_asset: str
    source_matches: list[MatchResult]
    target_forward: NDArray[np.float64]  # what target did after source matched
    correlation: float  # correlation of forward returns
    transfer_entropy: float  # information flow score
    lag_bars: int  # optimal lag between assets


def cross_asset_scan(
    source_matches: list[MatchResult],
    source_history: NDArray[np.float64],
    target_history: NDArray[np.float64],
    forward_bars: int = 50,
    source_name: str = "",
    target_name: str = "",
) -> CrossAssetResult:
    """Scan how a target asset responds when source patterns are found.

    For each source match, extracts what both source and target did in the
    forward window after the match. Computes correlation, transfer entropy,
    and optimal lag between the two.

    Args:
        source_matches: Match results from the source asset search.
        source_history: Full price history for the source asset.
        target_history: Full price history for the target asset.
        forward_bars: Number of bars to look forward after each match.
        source_name: Label for the source asset.
        target_name: Label for the target asset.

    Returns:
        CrossAssetResult with correlation, TE, and lag analysis.
    """
    source_history = np.asarray(source_history, dtype=np.float64).ravel()
    target_history = np.asarray(target_history, dtype=np.float64).ravel()

    source_forwards: list[NDArray[np.float64]] = []
    target_forwards: list[NDArray[np.float64]] = []

    for match in source_matches:
        start = match.end_idx
        end = start + forward_bars
        if end > len(source_history) or end > len(target_history):
            continue
        if start < 0:
            continue

        # Forward returns for source
        src_anchor = source_history[start - 1] if start > 0 else source_history[start]
        if abs(src_anchor) < 1e-12:
            continue
        src_fwd = (source_history[start:end] - src_anchor) / abs(src_anchor)

        # Forward returns for target (same time window)
        tgt_anchor = target_history[start - 1] if start > 0 else target_history[start]
        if abs(tgt_anchor) < 1e-12:
            continue
        tgt_fwd = (target_history[start:end] - tgt_anchor) / abs(tgt_anchor)

        source_forwards.append(src_fwd)
        target_forwards.append(tgt_fwd)

    if not source_forwards:
        return CrossAssetResult(
            source_asset=source_name,
            target_asset=target_name,
            source_matches=source_matches,
            target_forward=np.array([], dtype=np.float64),
            correlation=0.0,
            transfer_entropy=0.0,
            lag_bars=0,
        )

    # Average forward returns across all match instances
    src_avg = np.mean(source_forwards, axis=0)
    tgt_avg = np.mean(target_forwards, axis=0)

    # Correlation of average forward return curves
    if np.std(src_avg) < 1e-12 or np.std(tgt_avg) < 1e-12:
        corr = 0.0
    else:
        corr = float(np.corrcoef(src_avg, tgt_avg)[0, 1])
        if np.isnan(corr):
            corr = 0.0

    # Transfer entropy: information flow from source to target
    # Use the concatenated forward windows for a richer signal
    src_concat = np.concatenate(source_forwards)
    tgt_concat = np.concatenate(target_forwards)
    te = compute_transfer_entropy(src_concat, tgt_concat, lag=1, bins=8)

    # Optimal lag via cross-correlation
    lag = _find_optimal_lag(src_avg, tgt_avg, max_lag=min(forward_bars // 2, 20))

    return CrossAssetResult(
        source_asset=source_name,
        target_asset=target_name,
        source_matches=source_matches,
        target_forward=tgt_avg,
        correlation=corr,
        transfer_entropy=te,
        lag_bars=lag,
    )


def _find_optimal_lag(
    source: NDArray[np.float64],
    target: NDArray[np.float64],
    max_lag: int = 20,
) -> int:
    """Find the lag that maximizes cross-correlation between source and target."""
    if len(source) < 2 or len(target) < 2:
        return 0

    best_lag = 0
    best_corr = -1.0
    n = min(len(source), len(target))

    for lag in range(0, min(max_lag + 1, n - 1)):
        if lag == 0:
            s, t = source[:n], target[:n]
        else:
            s = source[:n - lag]
            t = target[lag:n]

        if len(s) < 2 or np.std(s) < 1e-12 or np.std(t) < 1e-12:
            continue

        c = abs(float(np.corrcoef(s, t)[0, 1]))
        if np.isnan(c):
            continue
        if c > best_corr:
            best_corr = c
            best_lag = lag

    return best_lag


# ---------------------------------------------------------------------------
# Portfolio regime snapshot
# ---------------------------------------------------------------------------

@dataclass
class RegimeSnapshot:
    """Regime classification for a single asset at current time."""
    asset: str
    regime: str
    hurst: float  # Hurst exponent from DFA
    volatility: float  # realized annualized volatility
    trend_slope: float  # linear regression slope on z-scored series


def portfolio_regime_scan(
    assets: dict[str, NDArray[np.float64]],
    window: int = 60,
) -> list[RegimeSnapshot]:
    """Classify regime for each asset using the last `window` bars.

    Args:
        assets: Mapping of asset name to price series.
        window: Number of trailing bars to analyze.

    Returns:
        List of RegimeSnapshot sorted by volatility (highest first).
    """
    snapshots: list[RegimeSnapshot] = []

    for name, series in assets.items():
        s = np.asarray(series, dtype=np.float64).ravel()
        tail = s[-window:] if len(s) >= window else s

        if len(tail) < 2:
            snapshots.append(RegimeSnapshot(
                asset=name, regime="low_vol", hurst=0.5,
                volatility=0.0, trend_slope=0.0,
            ))
            continue

        regime = tag_regime(tail)
        hurst = hurst_dfa(tail)

        # Realized volatility (annualized)
        safe = np.maximum(tail, 1e-12)
        log_ret = np.diff(np.log(safe))
        vol = float(np.std(log_ret) * np.sqrt(252)) if len(log_ret) > 0 else 0.0

        # Trend slope on z-scored series
        std = float(np.std(tail))
        if std > 0:
            z = (tail - np.mean(tail)) / std
            t = np.arange(len(z), dtype=np.float64)
            slope = float(np.polyfit(t, z, 1)[0])
        else:
            slope = 0.0

        snapshots.append(RegimeSnapshot(
            asset=name,
            regime=regime,
            hurst=hurst,
            volatility=vol,
            trend_slope=slope,
        ))

    snapshots.sort(key=lambda x: x.volatility, reverse=True)
    return snapshots


# ---------------------------------------------------------------------------
# Divergence scanner
# ---------------------------------------------------------------------------

@dataclass
class DivergenceResult:
    """Detects correlation regime changes between two assets."""
    asset_a: str
    asset_b: str
    historical_correlation: float  # long-term correlation
    recent_correlation: float  # recent window correlation
    divergence_score: float  # |historical - recent|
    direction: str  # "decorrelating" or "recorrelating"


def divergence_scanner(
    assets: dict[str, NDArray[np.float64]],
    lookback: int = 252,
    recent_window: int = 20,
) -> list[DivergenceResult]:
    """Scan all asset pairs for correlation divergence.

    Compares long-term correlation with recent-window correlation to
    detect pairs that are decorrelating or recorrelating.

    Args:
        assets: Mapping of asset name to price series.
        lookback: Bars for long-term correlation.
        recent_window: Bars for recent correlation.

    Returns:
        List of DivergenceResult sorted by divergence_score descending.
    """
    names = list(assets.keys())
    if len(names) < 2:
        return []

    # Pre-compute log returns for each asset
    returns_map: dict[str, NDArray[np.float64]] = {}
    for name in names:
        s = np.asarray(assets[name], dtype=np.float64).ravel()
        safe = np.maximum(s, 1e-12)
        returns_map[name] = np.diff(np.log(safe))

    results: list[DivergenceResult] = []

    for a, b in combinations(names, 2):
        ret_a = returns_map[a]
        ret_b = returns_map[b]

        # Align to same length
        n = min(len(ret_a), len(ret_b))
        if n < recent_window:
            continue

        ra = ret_a[-n:]
        rb = ret_b[-n:]

        # Historical correlation (up to lookback)
        hist_n = min(n, lookback)
        hist_a = ra[-hist_n:]
        hist_b = rb[-hist_n:]
        if np.std(hist_a) < 1e-12 or np.std(hist_b) < 1e-12:
            hist_corr = 0.0
        else:
            hist_corr = float(np.corrcoef(hist_a, hist_b)[0, 1])
            if np.isnan(hist_corr):
                hist_corr = 0.0

        # Recent correlation
        rec_a = ra[-recent_window:]
        rec_b = rb[-recent_window:]
        if np.std(rec_a) < 1e-12 or np.std(rec_b) < 1e-12:
            rec_corr = 0.0
        else:
            rec_corr = float(np.corrcoef(rec_a, rec_b)[0, 1])
            if np.isnan(rec_corr):
                rec_corr = 0.0

        div_score = abs(hist_corr - rec_corr)
        direction = "decorrelating" if rec_corr < hist_corr else "recorrelating"

        results.append(DivergenceResult(
            asset_a=a,
            asset_b=b,
            historical_correlation=hist_corr,
            recent_correlation=rec_corr,
            divergence_score=div_score,
            direction=direction,
        ))

    results.sort(key=lambda x: x.divergence_score, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Information flow network
# ---------------------------------------------------------------------------

@dataclass
class InformationFlowResult:
    """Pairwise transfer entropy analysis between two assets."""
    source: str
    target: str
    te_forward: float  # TE from source -> target
    te_reverse: float  # TE from target -> source
    net_flow: float  # te_forward - te_reverse
    direction: str  # "source_leads", "target_leads", or "bidirectional"


def information_flow_network(
    assets: dict[str, NDArray[np.float64]],
    window: int = 60,
) -> list[InformationFlowResult]:
    """Build pairwise transfer entropy network across assets.

    For each pair, computes TE in both directions to determine
    which asset leads and which follows.

    Args:
        assets: Mapping of asset name to price series.
        window: Number of trailing bars to use for TE computation.

    Returns:
        List of InformationFlowResult sorted by |net_flow| descending.
    """
    names = list(assets.keys())
    if len(names) < 2:
        return []

    # Pre-compute tails
    tails: dict[str, NDArray[np.float64]] = {}
    for name in names:
        s = np.asarray(assets[name], dtype=np.float64).ravel()
        tails[name] = s[-window:] if len(s) >= window else s

    results: list[InformationFlowResult] = []

    for a, b in combinations(names, 2):
        ta = tails[a]
        tb = tails[b]

        # Align lengths
        n = min(len(ta), len(tb))
        if n < 4:
            continue

        sa = ta[-n:]
        sb = tb[-n:]

        te_ab = compute_transfer_entropy(sa, sb, lag=1, bins=8)
        te_ba = compute_transfer_entropy(sb, sa, lag=1, bins=8)
        net = te_ab - te_ba

        # Threshold for "bidirectional" — if net flow is small relative to both
        threshold = 0.05
        if abs(net) < threshold:
            direction = "bidirectional"
        elif net > 0:
            direction = "source_leads"
        else:
            direction = "target_leads"

        results.append(InformationFlowResult(
            source=a,
            target=b,
            te_forward=te_ab,
            te_reverse=te_ba,
            net_flow=net,
            direction=direction,
        ))

    results.sort(key=lambda x: abs(x.net_flow), reverse=True)
    return results
