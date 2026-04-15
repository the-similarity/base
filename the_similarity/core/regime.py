"""
Market regime classification for matched time series segments.

Assigns one of five regime labels to each price window:
- "trending_up"   — persistent upward drift (Hurst > 0.6 + positive slope)
- "trending_down"  — persistent downward drift (Hurst > 0.6 + negative slope)
- "mean_reverting" — mean-reverting dynamics (Hurst < 0.4)
- "high_vol"       — high annualized volatility (> 40%)
- "low_vol"        — low annualized volatility (< 10%)

The core tool is Detrended Fluctuation Analysis (DFA), which estimates
the Hurst exponent H ∈ [0, 1]:
  H ≈ 0.5 → random walk (no memory)
  H > 0.5 → persistent (trending)
  H < 0.5 → anti-persistent (mean-reverting)

AI AGENT NOTES:
- Regime labels are attached to MatchResult.regime by the matcher after
  scoring, and displayed in the frontend match cards.
- The classification uses a priority system: volatility extremes override
  Hurst-based labels, because extreme volatility changes the character of
  any trend or mean-reversion.
- DFA is preferred over R/S analysis because it handles non-stationarity
  better (it detrends each box before computing fluctuations).
- The annualization factor √252 assumes daily data. If the engine starts
  supporting intraday data, this should be parameterized.
- 0.5 is returned as a safe fallback Hurst value for any edge case.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Classification thresholds (empirically tuned for daily financial data)
# ---------------------------------------------------------------------------
_SLOPE_THRESHOLD = 0.01  # Normalized OLS slope magnitude to consider "trending"
_HURST_TREND = 0.6  # H above this threshold confirms persistent trending
_HURST_MR = 0.4  # H below this threshold → anti-persistent / mean-reverting
_VOL_HIGH = 0.4  # Annualized vol above 40% → "high_vol" (overrides trend)
_VOL_LOW = 0.1  # Annualized vol below 10% → "low_vol" (overrides trend)
_MIN_LENGTH = 10  # Minimum series length for meaningful classification


def tag_regime(series: NDArray[np.float64] | list) -> str:
    """Label a price series with a market regime.

    Decision hierarchy (evaluated top-to-bottom, first match wins):
      1. Volatility extremes (high_vol / low_vol) — checked first because
         extreme vol changes the meaning of any trend/mean-reversion.
      2. Hurst anti-persistence (H < 0.4) → mean_reverting
      3. Hurst persistence (H > 0.6) + slope direction → trending_up/down
      4. Ambiguous zone (0.4 ≤ H ≤ 0.6) — use slope if strong enough
      5. Default → mean_reverting

    Args:
        series: 1D array of prices or values.

    Returns:
        One of: "trending_up", "trending_down", "mean_reverting",
                "high_vol", "low_vol"
    """
    s = np.asarray(series, dtype=np.float64).ravel()

    # --- Edge cases: too short or constant → default to low_vol ---
    if len(s) < 2:
        return "low_vol"
    if np.all(s == s[0]):  # Constant series = zero volatility
        return "low_vol"
    if len(s) < _MIN_LENGTH:  # Too short for reliable Hurst estimation
        return "low_vol"

    # --- Compute log-returns for volatility estimation ---
    safe = np.maximum(s, 1e-12)  # Guard against log(0)
    log_ret = np.diff(np.log(safe))
    if len(log_ret) == 0 or np.all(log_ret == 0):
        return "low_vol"

    # --- Realized volatility (annualized assuming daily data) ---
    # std(daily_log_returns) × √252 gives an annualized volatility estimate.
    # 252 = typical trading days per year for equities.
    ann_vol = float(np.std(log_ret) * np.sqrt(252))

    # --- OLS slope on z-scored series (captures directional drift) ---
    slope = _ols_slope(s)

    # --- Hurst exponent via DFA (captures memory structure) ---
    H = hurst_dfa(s)

    # --- Decision cascade ---

    # Priority 1: Volatility extremes override everything else
    if ann_vol > _VOL_HIGH:
        return "high_vol"
    if ann_vol < _VOL_LOW:
        return "low_vol"

    # Priority 2: Strong anti-persistence means mean-reversion dominates
    if H < _HURST_MR:
        return "mean_reverting"

    # Priority 3: Strong persistence + slope direction = trending
    if H > _HURST_TREND:
        # Hurst confirms persistent dynamics; slope gives direction
        return "trending_up" if slope > 0 else "trending_down"

    # Priority 4: Ambiguous Hurst zone (0.4 ≤ H ≤ 0.6)
    # Fall back to slope strength if the trend signal is strong enough
    if abs(slope) > _SLOPE_THRESHOLD:
        return "trending_up" if slope > 0 else "trending_down"

    # Default: no strong signal → classify as mean-reverting
    return "mean_reverting"


# ---------------------------------------------------------------------------
# Detrended Fluctuation Analysis (DFA)
# ---------------------------------------------------------------------------


def hurst_dfa(
    series: NDArray[np.float64] | list,
    min_box: int = 4,
    max_box: int | None = None,
) -> float:
    """Estimate the Hurst exponent via Detrended Fluctuation Analysis.

    DFA algorithm:
    1. Compute log-returns, then integrate (cumsum of mean-centered returns)
       to get the "profile" Y(t).
    2. Divide Y into non-overlapping boxes of size n.
    3. In each box, fit a linear trend and compute RMS of the residual.
    4. Average RMS across boxes → F(n).
    5. Repeat for multiple box sizes n (log-spaced).
    6. The slope of log(F(n)) vs log(n) is the Hurst exponent H.

    Why DFA over R/S analysis:
    - DFA removes local linear trends in each box, making it robust to
      non-stationarity (which is common in financial data).
    - R/S is biased for short series and sensitive to trends.

    Args:
        series: 1D price or value array.
        min_box: Smallest box size (default 4). Must be ≥ 2 for OLS.
        max_box: Largest box size (defaults to N//4 for statistical stability).

    Returns:
        Hurst exponent H ∈ [0, 1]. Clamped to this range.
        Falls back to 0.5 (random walk hypothesis) on any error.
    """
    try:
        s = np.asarray(series, dtype=np.float64).ravel()
        if len(s) < 2 * min_box:
            return 0.5  # Not enough data for meaningful DFA

        # Work on log-returns to make the analysis scale-invariant
        safe = np.maximum(s, 1e-12)
        x = np.diff(np.log(safe))
        if len(x) < 2 * min_box:
            return 0.5

        # Step 1: Build the "profile" — cumulative sum of mean-centered returns.
        # This is the integrated series that DFA analyzes.
        y = np.cumsum(x - np.mean(x))
        N = len(y)

        # Auto-select max_box if not specified.
        # N//4 is a common heuristic: ensures at least 4 boxes at the largest scale.
        if max_box is None:
            max_box = max(min_box + 1, N // 4)
        if max_box <= min_box:
            return 0.5

        # Step 2: Generate log-spaced box sizes (20 scales is sufficient for
        # a stable log-log regression).
        box_sizes = np.unique(
            np.logspace(
                np.log10(min_box),
                np.log10(max_box),
                num=20,
            ).astype(int)
        )
        box_sizes = box_sizes[box_sizes >= min_box]
        if len(box_sizes) < 2:
            return 0.5  # Need ≥ 2 points for a regression

        # Step 3: Compute fluctuation function F(n) for each box size
        fluct = np.empty(len(box_sizes))
        for i, n in enumerate(box_sizes):
            n_boxes = N // n  # Number of non-overlapping boxes
            if n_boxes == 0:
                fluct[i] = np.nan
                continue

            rms_vals = np.empty(n_boxes)
            for j in range(n_boxes):
                seg = y[j * n : (j + 1) * n]

                # Detrend each box by removing its linear fit.
                # This is what makes DFA "detrended" — local trends don't
                # inflate the fluctuation estimate.
                t = np.arange(n, dtype=np.float64)
                coeffs = np.polyfit(t, seg, 1)  # Linear fit
                trend = np.polyval(coeffs, t)
                rms_vals[j] = np.sqrt(np.mean((seg - trend) ** 2))

            # F(n) = average RMS across all boxes at this scale
            fluct[i] = np.mean(rms_vals)

        # Step 4: Remove invalid entries before regression
        valid = np.isfinite(fluct) & (fluct > 0)
        if np.sum(valid) < 2:
            return 0.5

        log_n = np.log(box_sizes[valid].astype(np.float64))
        log_f = np.log(fluct[valid])

        # Step 5: log-log OLS regression → slope is the Hurst exponent
        # F(n) ~ n^H, so log(F) = H * log(n) + const
        H = float(np.polyfit(log_n, log_f, 1)[0])
        return float(np.clip(H, 0.0, 1.0))

    except Exception:
        # Any numerical failure → safest assumption is random walk
        return 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ols_slope(series: NDArray[np.float64]) -> float:
    """Compute the OLS slope of the z-scored series.

    Why z-score first: raw OLS slope depends on the absolute scale of the
    series. Z-scoring makes the slope a dimensionless measure of how many
    standard deviations the series moves per bar — directly comparable
    across assets.

    Returns 0.0 for constant series.
    """
    std = np.std(series)
    if std == 0:
        return 0.0
    z = (series - np.mean(series)) / std
    t = np.arange(len(z), dtype=np.float64)
    return float(np.polyfit(t, z, 1)[0])
