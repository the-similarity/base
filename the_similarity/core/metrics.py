"""
Evaluation metrics for backtesting the pattern matching engine.

These metrics assess the quality of the engine's forecast cones by comparing
projected outcomes against what actually happened. They are applied to
`TrialResult` objects produced by the backtester.

AI AGENT NOTES:
- All functions return NaN for empty trial lists (not 0 or an error),
  so downstream aggregation code must handle NaN values.
- `hit_rate` is the simplest metric: did P50 get the direction right?
- `calibration` checks statistical consistency: a P90 curve should contain
  90% of outcomes. Deviation indicates the cone is too tight or too wide.
- `crps` is the gold-standard probabilistic forecast metric. It uses a
  discrete approximation since we only have ~5 percentile curves, not a
  continuous CDF.
- TYPE_CHECKING import avoids circular dependency with backtester.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    # TrialResult is defined in backtester.py, which imports from this module's
    # siblings. Using TYPE_CHECKING avoids a circular import at runtime.
    from the_similarity.core.backtester import TrialResult


def hit_rate(trials: list[TrialResult]) -> float:
    """Fraction of trials where P50 predicted the correct direction.

    "Directional hit" means:
    - P50 predicted positive return AND actual return was positive, OR
    - P50 predicted negative return AND actual return was negative.

    This is the most basic sanity check: a random baseline is 50%.
    Consistently above 55% suggests the pattern matching has real signal.

    Returns:
        Float in [0, 1], or NaN if trials is empty.
    """
    if not trials:
        return float("nan")
    hits = sum(1 for t in trials if t.directional_hit)
    return hits / len(trials)


def mean_absolute_error(trials: list[TrialResult]) -> float:
    """Mean absolute error of P50 terminal forecast vs actual return.

    This measures point forecast accuracy: how far off was the median
    projection at the terminal bar from what actually happened?

    Lower is better. Units match the return representation
    (typically fractional returns, e.g., 0.05 = 5% error).

    Returns:
        Float >= 0, or NaN if trials is empty.
    """
    if not trials:
        return float("nan")
    errors = [t.p50_error for t in trials]
    return float(np.mean(errors))


def calibration(
    trials: list[TrialResult],
    percentiles: list[int],
) -> dict[int, float]:
    """Per-percentile containment rate (statistical calibration check).

    For each percentile P, computes the fraction of trials where the
    actual terminal return fell below the P-th percentile forecast curve.

    A well-calibrated system should have:
        containment(P10) ≈ 0.10
        containment(P50) ≈ 0.50
        containment(P90) ≈ 0.90

    Deviations reveal systematic biases:
    - containment(P90) << 0.90 → forecast cone is too narrow (overconfident)
    - containment(P10) >> 0.10 → forecast cone is biased high

    Args:
        trials: List of completed backtest trials.
        percentiles: Which percentiles to check (e.g., [10, 25, 50, 75, 90]).

    Returns:
        Dict mapping each percentile to its observed containment rate [0, 1].
        NaN for percentiles with no valid data.
    """
    if not trials:
        return {p: float("nan") for p in percentiles}

    result: dict[int, float] = {}
    for p in percentiles:
        contained = 0
        valid = 0
        for trial in trials:
            curve = trial.forecast_curves.get(p)
            if curve is None or len(curve) == 0:
                continue
            valid += 1
            # Check if actual terminal return is at or below this percentile
            # forecast. For a perfectly calibrated P-th percentile, exactly
            # P% of actuals should satisfy this condition.
            if trial.actual_returns[-1] <= curve[-1]:
                contained += 1
        result[p] = contained / valid if valid > 0 else float("nan")
    return result


def crps(trials: list[TrialResult]) -> float:
    """Continuous Ranked Probability Score (discrete approximation).

    CRPS is a strictly proper scoring rule for probabilistic forecasts.
    It measures the integrated squared difference between the forecast CDF
    and the observation's step-function CDF. Lower is better.

    Mathematical formulation:
        CRPS = integral over x of (F(x) - H(x - y))² dx

    where F(x) is the forecast CDF and H is the Heaviside step function
    centered at the actual observation y.

    Since our forecast is represented as only ~5 percentile curves (not a
    continuous CDF), we approximate this integral using:
        CRPS ≈ mean over percentile levels of (I(y ≤ F_p) - p/100)²

    where I is the indicator function and F_p is the forecast at percentile p.

    Interpretation:
    - CRPS = 0 → perfect probabilistic forecast (impossible in practice)
    - Lower CRPS → better calibrated AND sharper forecasts
    - CRPS penalizes both miscalibration AND lack of sharpness

    Returns:
        Float >= 0, or NaN if no valid trials.
    """
    if not trials:
        return float("nan")

    crps_values = []
    for trial in trials:
        if not trial.forecast_curves:
            continue

        # Sort percentile keys to create an ordered CDF approximation
        sorted_percentiles = sorted(trial.forecast_curves.keys())
        if not sorted_percentiles:
            continue

        # Extract the terminal-bar actual return
        actual_terminal = trial.actual_returns[-1]

        # Extract the terminal-bar forecast value at each percentile level
        forecast_terminals = np.array(
            [trial.forecast_curves[p][-1] for p in sorted_percentiles]
        )

        # Convert integer percentiles to [0, 1] CDF levels
        cdf_levels = np.array(sorted_percentiles) / 100.0

        # Approximate CRPS:
        # For each percentile level, the indicator I(y ≤ F_p) gives the
        # empirical CDF of the actual observation. The squared difference
        # between this and the nominal CDF level measures calibration error
        # at that point.
        indicators = (actual_terminal <= forecast_terminals).astype(float)
        crps_val = float(np.mean((indicators - cdf_levels) ** 2))
        crps_values.append(crps_val)

    if not crps_values:
        return float("nan")
    return float(np.mean(crps_values))


def interval_score(
    trials: list[TrialResult],
    alpha: float = 0.20,
) -> float:
    """Interval score at the terminal bar — a proper scoring rule for prediction intervals.

    The interval score evaluates a central (1-alpha) forecast interval by
    rewarding narrowness AND penalising actuals that fall outside it. Unlike
    raw coverage, it is a *proper* scoring rule: it cannot be gamed by
    submitting a trivially wide or trivially narrow interval.

    Mathematical formulation (per trial, at the terminal bar):

        IS_alpha(L, U, y) = (U - L)
                          + (2 / alpha) * max(0, L - y)
                          + (2 / alpha) * max(0, y - U)

    where:
        - L = lower-bound forecast at percentile (alpha/2) * 100
        - U = upper-bound forecast at percentile (1 - alpha/2) * 100
        - y = realised terminal actual return

    For alpha=0.20 this corresponds to the central 80% interval bounded by
    the P10 and P90 forecast curves (the canonical cone edges used elsewhere
    in this engine). Lower interval score is better.

    Penalty structure:
        - Sharpness term (U - L): wider intervals cost more, so the rule
          discourages hedging through extreme width.
        - Miss penalty (2/alpha * distance outside): a single miss costs
          proportionally more as alpha shrinks, so 99% intervals (alpha=0.01)
          are punished harder for outliers than 80% intervals (alpha=0.20).

    Implementation notes:
        - Requires percentile keys alpha/2*100 and (1-alpha/2)*100 to be
          present in forecast_curves. For the default alpha=0.20, this maps
          to P10 / P90.
        - Trials missing either bound are skipped (do not contribute),
          consistent with how calibration() handles missing percentiles.
        - NaN is returned if the trials list is empty OR if every trial
          lacks the required percentile pair (fail-closed).

    Args:
        trials: Completed backtest trials (skipped trials excluded upstream).
        alpha: Miscoverage level in (0, 1). The interval is (1-alpha) wide.
            Default 0.20 → 80% central interval using P10/P90.

    Returns:
        Mean interval score across trials. Lower is better. NaN if empty.
    """
    if not trials:
        return float("nan")

    # Map alpha to integer percentile keys used by forecast_curves. We round
    # to match the caller-supplied percentile granularity (typically 10, 25,
    # 50, 75, 90). If those exact keys are absent the trial is skipped.
    lower_pct = int(round((alpha / 2.0) * 100))
    upper_pct = int(round((1.0 - alpha / 2.0) * 100))

    scores: list[float] = []
    for trial in trials:
        lower_curve = trial.forecast_curves.get(lower_pct)
        upper_curve = trial.forecast_curves.get(upper_pct)
        if lower_curve is None or upper_curve is None:
            continue
        if len(lower_curve) == 0 or len(upper_curve) == 0:
            continue

        lower = float(lower_curve[-1])
        upper = float(upper_curve[-1])
        actual = float(trial.actual_returns[-1])

        # Sharpness term penalises width. Miss penalties only fire when the
        # actual falls outside the stated interval.
        width = upper - lower
        below_miss = max(0.0, lower - actual)
        above_miss = max(0.0, actual - upper)
        score = width + (2.0 / alpha) * (below_miss + above_miss)
        scores.append(score)

    if not scores:
        return float("nan")
    return float(np.mean(scores))


def coverage_probability(
    trials: list[TrialResult],
    lower_pct: int = 10,
    upper_pct: int = 90,
) -> float:
    """Empirical coverage: fraction of terminal actuals inside [P_lower, P_upper].

    This is the raw calibration statistic for a central interval, independent
    of sharpness. It answers "does the engine's nominal 80% cone actually
    contain 80% of outcomes?" The target value is (upper_pct - lower_pct)/100.

    Mathematical formulation:

        coverage = (1/N) * sum_i [ I(L_i <= y_i <= U_i) ]

    where I(.) is the indicator function and L_i, U_i are the lower/upper
    percentile forecast curves evaluated at the terminal bar.

    Interpretation:
        - coverage ≈ target → well-calibrated interval
        - coverage << target → interval too narrow (overconfident)
        - coverage >> target → interval too wide (underconfident / sandbagged)

    NOTE: Unlike interval_score(), this metric does NOT penalise width. A
    trivially wide interval can reach 100% coverage while being useless.
    Use both metrics together to assess both calibration AND sharpness.

    Args:
        trials: Completed backtest trials.
        lower_pct: Lower-bound percentile key (default 10).
        upper_pct: Upper-bound percentile key (default 90).

    Returns:
        Float in [0, 1], or NaN if empty/unavailable.
    """
    if not trials:
        return float("nan")

    # Containment test uses both endpoints. Trials missing either curve are
    # excluded from the denominator so coverage reflects only usable data.
    contained = 0
    valid = 0
    for trial in trials:
        lower_curve = trial.forecast_curves.get(lower_pct)
        upper_curve = trial.forecast_curves.get(upper_pct)
        if lower_curve is None or upper_curve is None:
            continue
        if len(lower_curve) == 0 or len(upper_curve) == 0:
            continue

        valid += 1
        actual = float(trial.actual_returns[-1])
        if lower_curve[-1] <= actual <= upper_curve[-1]:
            contained += 1

    if valid == 0:
        return float("nan")
    return contained / valid


def profit_factor(trials: list[TrialResult]) -> float:
    """Profit factor when trading the P50 direction for each trial.

    Simulates taking a single-unit position in the direction predicted by
    the P50 forecast at the terminal bar. The absolute realised return
    becomes a gain if the direction was correct, a loss otherwise.

    Mathematical formulation:

        profit_factor = sum_{i in wins}   |y_i|
                      / sum_{i in losses} |y_i|

    where wins are trials with directional_hit == True and losses are the
    complement.

    Interpretation:
        - profit_factor > 1 → net profitable directional signal
        - profit_factor = 1 → break-even (noise-level)
        - profit_factor < 1 → net losing directional signal
        - profit_factor = +inf → no losing trades (rare — usually small N)

    Caveats:
        - Ignores transaction costs, slippage, and position sizing.
        - Uses terminal-bar return only; ignores intrabar drawdown or MFE.
        - Directional signal is from P50_terminal > 0 (already captured in
          TrialResult.directional_hit), so trials with P50 == 0 count as
          losses rather than flat (consistent with existing hit_rate logic).

    Returns:
        Float > 0, +inf if no losses, NaN if empty.
    """
    if not trials:
        return float("nan")

    # Walk trials once, splitting absolute terminal returns into the gain/loss
    # buckets based on the pre-computed directional_hit flag. This keeps the
    # metric consistent with hit_rate() even if actual == 0 or p50 == 0.
    gains = 0.0
    losses = 0.0
    for trial in trials:
        magnitude = abs(float(trial.actual_returns[-1]))
        if trial.directional_hit:
            gains += magnitude
        else:
            losses += magnitude

    if losses == 0.0:
        # All wins (or all zero-magnitude actuals). Convention: infinite PF.
        return float("inf") if gains > 0 else float("nan")
    return gains / losses


def max_drawdown(trials: list[TrialResult]) -> float:
    """Maximum peak-to-trough drawdown of a P50-directed equity curve.

    Treats the backtest trials as a sequential stream of one-shot directional
    trades. Each trade contributes `sign(P50_terminal) * actual_terminal` to
    cumulative equity. The function returns the worst peak-to-trough fractional
    drop observed along that equity curve.

    Mathematical formulation:

        equity_t = sum_{i <= t} sign(P50_i) * y_i        (additive P&L)
        peak_t   = max_{s <= t} equity_s
        dd_t     = peak_t - equity_t
        max_drawdown = max_t dd_t

    Why additive (not multiplicative)? The per-trial actuals are already
    fractional returns. Compounding them would conflate per-bar position
    sizing with the strategy's directional alpha. Additive P&L gives a
    clean directional-signal drawdown independent of sizing.

    Interpretation:
        - Returned as a non-negative float (fraction of cumulative P&L lost
          from a peak). 0.15 means a 15-point drop in cumulative fractional
          return. Absolute magnitude is comparable across datasets sharing
          the same return representation.
        - max_drawdown = 0 → equity was monotonically non-decreasing.
        - Larger values → worse worst-case experience for a naïve trader.

    Note: This metric is path-dependent. Trials are consumed in the order
    provided (typically random walk-forward sampling order). For
    chronologically meaningful drawdowns the caller should sort trials by
    query_start before passing them in.

    Returns:
        Non-negative float, or NaN if empty.
    """
    if not trials:
        return float("nan")

    # Build directional P&L increments. Sign comes from P50 terminal; we fall
    # back to 0 (flat trade) if the P50 curve is missing, which is rare for
    # non-skipped trials but fail-closed here rather than raising.
    pnl_increments: list[float] = []
    for trial in trials:
        p50_curve = trial.forecast_curves.get(50)
        if p50_curve is None or len(p50_curve) == 0:
            pnl_increments.append(0.0)
            continue
        direction = np.sign(float(p50_curve[-1]))
        realised = float(trial.actual_returns[-1])
        pnl_increments.append(direction * realised)

    equity = np.cumsum(pnl_increments)
    # Running peak is the maximum equity observed up to each point. The
    # drawdown at t is (peak_t - equity_t); the max of these is the MDD.
    running_peak = np.maximum.accumulate(equity)
    drawdowns = running_peak - equity
    return float(np.max(drawdowns))


def sharpe_ratio(
    trials: list[TrialResult],
    periods_per_year: int = 252,
) -> float:
    """Annualised Sharpe ratio of per-trial P50-directed returns.

    Treats each trial as one sampled realisation of the directional strategy:
    the return is `sign(P50_terminal) * actual_terminal`. The Sharpe ratio
    scales the mean-to-std ratio by sqrt(periods_per_year) so values are
    comparable across sampling frequencies.

    Mathematical formulation:

        r_i = sign(P50_i) * y_i
        mu  = mean(r)
        sig = std(r)          (population std, ddof=0)
        Sharpe = (mu / sig) * sqrt(periods_per_year)

    Choice of ddof=0 matches numpy's default and treats the trial set as the
    full population of observed outcomes rather than a sample from a larger
    universe — appropriate for a fixed backtest run.

    Annualisation assumes each trial corresponds to one period of length
    (1 / periods_per_year) of a trading year. For daily bars the default
    252 is standard; callers using hourly / weekly bars should override
    (e.g. 252*6.5 for hourly US equities, 52 for weekly).

    Caveats:
        - Assumes trials are drawn i.i.d. and from the same regime. Walk-
          forward sampling approximately satisfies this; heavy regime
          clustering does not.
        - Ignores risk-free rate (excess-return Sharpe). Subtract r_f from
          r_i upstream if you need the strict definition.
        - Returns NaN if fewer than 2 trials or if std == 0 (no variance
          means undefined Sharpe, not infinite — fail-closed).

    Returns:
        Float Sharpe ratio, or NaN if empty/degenerate.
    """
    if not trials:
        return float("nan")

    returns: list[float] = []
    for trial in trials:
        p50_curve = trial.forecast_curves.get(50)
        if p50_curve is None or len(p50_curve) == 0:
            continue
        direction = np.sign(float(p50_curve[-1]))
        returns.append(direction * float(trial.actual_returns[-1]))

    if len(returns) < 2:
        # Sharpe is ill-defined with a single observation. Fail-closed to NaN
        # rather than raising so this composes with the other aggregate
        # metrics on tiny backtest runs.
        return float("nan")

    returns_arr = np.asarray(returns, dtype=np.float64)
    mu = float(np.mean(returns_arr))
    sigma = float(np.std(returns_arr, ddof=0))
    if sigma == 0.0:
        return float("nan")

    return (mu / sigma) * float(np.sqrt(periods_per_year))
