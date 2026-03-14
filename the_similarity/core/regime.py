from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
_SLOPE_THRESHOLD = 0.01  # normalized OLS slope to consider "trending"
_HURST_TREND = 0.6       # H above this confirms trending
_HURST_MR = 0.4          # H below this → mean-reverting
_VOL_HIGH = 0.4          # annualized vol above → high_vol
_VOL_LOW = 0.1           # annualized vol below → low_vol
_MIN_LENGTH = 10         # series shorter than this → fallback


def tag_regime(series: NDArray[np.float64] | list) -> str:
    """Label a price series with a market regime.

    Priority (highest first):
        1. Volatility override  (high_vol / low_vol)
        2. Hurst override       (mean_reverting)
        3. Slope direction      (trending_up / trending_down)

    Returns one of:
        "trending_up", "trending_down", "mean_reverting", "high_vol", "low_vol"
    """
    s = np.asarray(series, dtype=np.float64).ravel()

    # Edge cases
    if len(s) < 2:
        return "low_vol"
    if np.all(s == s[0]):
        return "low_vol"
    if len(s) < _MIN_LENGTH:
        return "low_vol"

    # --- Log-returns ---
    safe = np.maximum(s, 1e-12)
    log_ret = np.diff(np.log(safe))
    if len(log_ret) == 0 or np.all(log_ret == 0):
        return "low_vol"

    # --- Realized volatility (annualized) ---
    ann_vol = float(np.std(log_ret) * np.sqrt(252))

    # --- OLS slope on z-scored series ---
    slope = _ols_slope(s)

    # --- Hurst via DFA ---
    H = hurst_dfa(s)

    # --- Decide regime ---
    # 1) Vol override
    if ann_vol > _VOL_HIGH:
        return "high_vol"
    if ann_vol < _VOL_LOW:
        return "low_vol"

    # 2) Hurst override
    if H < _HURST_MR:
        return "mean_reverting"

    # 3) Slope direction (confirmed by Hurst if trending)
    if H > _HURST_TREND:
        return "trending_up" if slope > 0 else "trending_down"

    # Ambiguous zone (0.4 <= H <= 0.6): fall back to slope if strong enough
    if abs(slope) > _SLOPE_THRESHOLD:
        return "trending_up" if slope > 0 else "trending_down"

    # Default
    return "mean_reverting"


# ---------------------------------------------------------------------------
# Detrended Fluctuation Analysis
# ---------------------------------------------------------------------------

def hurst_dfa(
    series: NDArray[np.float64] | list,
    min_box: int = 4,
    max_box: int | None = None,
) -> float:
    """Estimate the Hurst exponent via Detrended Fluctuation Analysis.

    Args:
        series: 1-D price or value array.
        min_box: Smallest box size.
        max_box: Largest box size (defaults to N//4).

    Returns:
        H in [0, 1].  Falls back to 0.5 on error.
    """
    try:
        s = np.asarray(series, dtype=np.float64).ravel()
        if len(s) < 2 * min_box:
            return 0.5

        # Work on log-returns (or diffs if series has zeros)
        safe = np.maximum(s, 1e-12)
        x = np.diff(np.log(safe))
        if len(x) < 2 * min_box:
            return 0.5

        # Integrate: cumulative sum of (x - mean)
        y = np.cumsum(x - np.mean(x))
        N = len(y)

        if max_box is None:
            max_box = max(min_box + 1, N // 4)
        if max_box <= min_box:
            return 0.5

        # Generate box sizes (log-spaced integers, unique)
        box_sizes = np.unique(
            np.logspace(
                np.log10(min_box), np.log10(max_box), num=20,
            ).astype(int)
        )
        box_sizes = box_sizes[box_sizes >= min_box]
        if len(box_sizes) < 2:
            return 0.5

        fluct = np.empty(len(box_sizes))
        for i, n in enumerate(box_sizes):
            n_boxes = N // n
            if n_boxes == 0:
                fluct[i] = np.nan
                continue
            rms_vals = np.empty(n_boxes)
            for j in range(n_boxes):
                seg = y[j * n : (j + 1) * n]
                # Linear detrend
                t = np.arange(n, dtype=np.float64)
                coeffs = np.polyfit(t, seg, 1)
                trend = np.polyval(coeffs, t)
                rms_vals[j] = np.sqrt(np.mean((seg - trend) ** 2))
            fluct[i] = np.mean(rms_vals)

        # Remove NaNs / zeros
        valid = np.isfinite(fluct) & (fluct > 0)
        if np.sum(valid) < 2:
            return 0.5

        log_n = np.log(box_sizes[valid].astype(np.float64))
        log_f = np.log(fluct[valid])

        # OLS on log-log
        H = float(np.polyfit(log_n, log_f, 1)[0])
        return float(np.clip(H, 0.0, 1.0))

    except Exception:
        return 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ols_slope(series: NDArray[np.float64]) -> float:
    """OLS slope on the z-scored series."""
    std = np.std(series)
    if std == 0:
        return 0.0
    z = (series - np.mean(series)) / std
    t = np.arange(len(z), dtype=np.float64)
    return float(np.polyfit(t, z, 1)[0])
