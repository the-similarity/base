"""Automated risk flag detection for finance runs.

This module inspects a BacktestReport summary dict and returns a list of
short string flags identifying potential issues. Each flag has a
documented threshold that was chosen based on empirical calibration
studies (see ``obsidian_thesim/concepts/projector-v2.md``).

The flags are consumed by :class:`the_similarity.finance.review.ReviewArtifact`
and surfaced in the finance operating product's review UI.

Threshold rationale
-------------------
- ``n_valid_trials < 20``: below this count, hit-rate and calibration
  statistics are not statistically significant (binomial CI width > 20pp).
- ``skip_rate > 0.3``: more than 30% of trials skipped means the search
  window may not have enough analogues for the target regime.
- ``calibration_error > 0.15``: mean absolute calibration error above 15pp
  indicates the forecast cone quantiles are systematically misaligned.
- ``hit_rate < 0.5``: the P50 forecast is worse than a coin flip.
- ``max_drawdown > 0.3``: 30% peak-to-trough drawdown signals excessive
  tail risk in the signal's forward path.
- ``coverage < 0.7``: fewer than 70% of trials had a valid projection cone.
- ``crps > 0.5``: CRPS above 0.5 indicates the full distributional
  forecast is poorly calibrated relative to normalized returns.
"""

from __future__ import annotations

from typing import Any, Dict, List

# -------------------------------------------------------------------------
# Flag constants — importable by consumers who want to check for specific
# flags by name rather than by string literal.
# -------------------------------------------------------------------------

LOW_TRIAL_COUNT = "low_trial_count"
HIGH_SKIP_RATE = "high_skip_rate"
POOR_CALIBRATION = "poor_calibration"
LOW_HIT_RATE = "low_hit_rate"
HIGH_DRAWDOWN = "high_drawdown"
LOW_COVERAGE = "low_coverage"
HIGH_CRPS = "high_crps"

# -------------------------------------------------------------------------
# Threshold constants — centralized so callers can introspect or override.
# -------------------------------------------------------------------------

# Minimum number of valid (non-skipped) trials for statistical significance.
MIN_VALID_TRIALS = 20

# Maximum fraction of skipped trials before flagging.
MAX_SKIP_RATE = 0.3

# Maximum mean absolute calibration error (pp) before flagging.
MAX_CALIBRATION_ERROR = 0.15

# Minimum hit rate for the P50 forecast to be considered useful.
MIN_HIT_RATE = 0.5

# Maximum peak-to-trough drawdown before flagging tail risk.
MAX_DRAWDOWN = 0.3

# Minimum forecast cone coverage fraction.
MIN_COVERAGE = 0.7

# Maximum CRPS for acceptable distributional forecast quality.
MAX_CRPS = 0.5


def detect_risk_flags(report_summary: Dict[str, Any]) -> List[str]:
    """Auto-detect risk flags from a BacktestReport summary dict.

    Parameters
    ----------
    report_summary:
        A dict containing backtest metrics. Expected keys (all optional —
        missing keys are silently skipped):

        - ``n_valid_trials`` (int): number of non-skipped trials.
        - ``n_skipped_trials`` (int): number of skipped trials.
        - ``n_trials`` (int): total trial count (alternative to computing
          from valid + skipped).
        - ``calibration`` (dict or float): either a dict with per-quantile
          calibration errors or a single mean calibration error.
        - ``hit_rate`` (float): fraction of trials where the P50 forecast
          direction was correct.
        - ``max_drawdown`` (float): peak-to-trough drawdown.
        - ``coverage`` (float): fraction of trials with valid projection.
        - ``crps`` (float): continuous ranked probability score.

    Returns
    -------
    list[str]:
        List of risk flag string constants. Empty if no flags triggered.
        Order is deterministic (checked in declaration order above).
    """
    flags: List[str] = []

    # -- low trial count ---------------------------------------------------
    n_valid = report_summary.get("n_valid_trials")
    if n_valid is not None and n_valid < MIN_VALID_TRIALS:
        flags.append(LOW_TRIAL_COUNT)

    # -- high skip rate ----------------------------------------------------
    n_skipped = report_summary.get("n_skipped_trials")
    if n_skipped is not None:
        # Compute total from either explicit n_trials or valid + skipped.
        n_total = report_summary.get("n_trials")
        if n_total is None and n_valid is not None:
            n_total = n_valid + n_skipped
        if n_total is not None and n_total > 0:
            skip_rate = n_skipped / n_total
            if skip_rate > MAX_SKIP_RATE:
                flags.append(HIGH_SKIP_RATE)

    # -- poor calibration --------------------------------------------------
    calibration = report_summary.get("calibration")
    if calibration is not None:
        if isinstance(calibration, dict):
            # Per-quantile calibration dict — compute mean absolute error.
            # Each value is the absolute deviation: |empirical - nominal|.
            cal_values = [
                v for v in calibration.values() if isinstance(v, (int, float))
            ]
            if cal_values:
                mean_cal_error = sum(abs(v) for v in cal_values) / len(cal_values)
                if mean_cal_error > MAX_CALIBRATION_ERROR:
                    flags.append(POOR_CALIBRATION)
        elif isinstance(calibration, (int, float)):
            # Scalar mean calibration error directly.
            if abs(calibration) > MAX_CALIBRATION_ERROR:
                flags.append(POOR_CALIBRATION)

    # -- low hit rate ------------------------------------------------------
    hit_rate = report_summary.get("hit_rate")
    if hit_rate is not None and hit_rate < MIN_HIT_RATE:
        flags.append(LOW_HIT_RATE)

    # -- high drawdown -----------------------------------------------------
    max_drawdown = report_summary.get("max_drawdown")
    if max_drawdown is not None and max_drawdown > MAX_DRAWDOWN:
        flags.append(HIGH_DRAWDOWN)

    # -- low coverage ------------------------------------------------------
    coverage = report_summary.get("coverage")
    if coverage is not None and coverage < MIN_COVERAGE:
        flags.append(LOW_COVERAGE)

    # -- high CRPS ---------------------------------------------------------
    crps = report_summary.get("crps")
    if crps is not None and crps > MAX_CRPS:
        flags.append(HIGH_CRPS)

    return flags


__all__ = [
    "HIGH_CRPS",
    "HIGH_DRAWDOWN",
    "HIGH_SKIP_RATE",
    "LOW_COVERAGE",
    "LOW_HIT_RATE",
    "LOW_TRIAL_COUNT",
    "MAX_CALIBRATION_ERROR",
    "MAX_CRPS",
    "MAX_DRAWDOWN",
    "MAX_SKIP_RATE",
    "MIN_COVERAGE",
    "MIN_HIT_RATE",
    "MIN_VALID_TRIALS",
    "POOR_CALIBRATION",
    "detect_risk_flags",
]
