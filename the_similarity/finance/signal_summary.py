"""Template-based signal summary — formats backtest metrics into a
human-readable one-liner. This is string formatting, not intelligence.
Future: replace with LLM-generated summaries that incorporate market
context.

The template is:
    "{symbol} {window_size}-bar window found {n_valid_trials} analogues
     with {hit_rate:.0%} hit rate, calibration {grade}, CRPS {crps:.2f}"

The ``{grade}`` slot uses the canonical finance-UX letter scale
(A/B/C/D/F). See
:func:`the_similarity.platform.adapters.trust.compute_calibration_grade`
for the authoritative threshold map — this module mirrors that contract
so a run's UI badge and its one-line signal summary always agree.

All fields are optional — missing fields are gracefully replaced with
``"N/A"`` so the summary always produces a readable string even from
partial data.
"""

from __future__ import annotations

from typing import Any, Dict


def _calibration_grade(calibration: Any) -> str:
    """Convert a calibration metric into a human-readable letter grade.

    Grading scale (mean absolute calibration error):
    - < 0.03: "A"
    - < 0.06: "B"
    - < 0.10: "C"
    - < 0.15: "D"
    - >= 0.15: "F"

    Thresholds mirror
    :func:`the_similarity.platform.adapters.trust.compute_calibration_grade`.
    We do NOT import that helper directly because it expects a
    ``{percentile_str: observed_coverage}`` dict whereas this helper
    also accepts a single float (mean error) for backwards compatibility
    with the summary-only call sites.

    Parameters
    ----------
    calibration:
        Either a float (mean calibration error) or a dict with
        per-quantile errors. If dict, the mean absolute value is used.
        Returns ``"N/A"`` for None or non-numeric values.
    """
    if calibration is None:
        return "N/A"

    # Handle per-quantile calibration dict.
    if isinstance(calibration, dict):
        values = [v for v in calibration.values() if isinstance(v, (int, float))]
        if not values:
            return "N/A"
        cal_error = sum(abs(v) for v in values) / len(values)
    elif isinstance(calibration, (int, float)):
        cal_error = abs(calibration)
    else:
        return "N/A"

    # Thresholds must stay in lock-step with trust.compute_calibration_grade.
    # If you change one, change the other — the test suite will catch
    # drift via test_finance_run_standardization.py.
    if cal_error < 0.03:
        return "A"
    elif cal_error < 0.06:
        return "B"
    elif cal_error < 0.10:
        return "C"
    elif cal_error < 0.15:
        return "D"
    else:
        return "F"


def generate_signal_summary(run_config: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    """Generate a one-line signal summary from run config and metrics.

    Parameters
    ----------
    run_config:
        Run configuration dict. Expected keys:
        - ``symbol`` (str): ticker symbol (e.g. ``"SPY"``).
        - ``window_size`` (int): search window bar count.

    metrics:
        Backtest metrics dict. Expected keys:
        - ``n_valid_trials`` (int): number of valid analogues found.
        - ``hit_rate`` (float): P50 directional accuracy.
        - ``calibration`` (float or dict): calibration error.
        - ``crps`` (float): continuous ranked probability score.

    Returns
    -------
    str:
        Human-readable summary. Always returns a valid string even when
        fields are missing — missing values render as ``"N/A"``.

    Examples
    --------
    >>> generate_signal_summary(
    ...     {"symbol": "SPY", "window_size": 60},
    ...     {"n_valid_trials": 8, "hit_rate": 0.72, "calibration": 0.08, "crps": 0.31},
    ... )
    'SPY 60-bar window found 8 analogues with 72% hit rate, calibration C, CRPS 0.31'
    """
    # Extract fields with graceful fallbacks.
    symbol = run_config.get("symbol", "N/A")
    window_size = run_config.get("window_size")
    window_str = f"{window_size}-bar" if window_size is not None else "N/A"

    n_trials = metrics.get("n_valid_trials")
    trials_str = str(n_trials) if n_trials is not None else "N/A"

    hit_rate = metrics.get("hit_rate")
    if hit_rate is not None:
        try:
            # Format as percentage without decimal (e.g. "72%").
            hit_rate_str = f"{hit_rate:.0%}"
        except (TypeError, ValueError):
            hit_rate_str = "N/A"
    else:
        hit_rate_str = "N/A"

    cal_grade = _calibration_grade(metrics.get("calibration"))

    crps = metrics.get("crps")
    if crps is not None:
        try:
            crps_str = f"{crps:.2f}"
        except (TypeError, ValueError):
            crps_str = "N/A"
    else:
        crps_str = "N/A"

    return (
        f"{symbol} {window_str} window found {trials_str} analogues "
        f"with {hit_rate_str} hit rate, calibration {cal_grade}, CRPS {crps_str}"
    )


__all__ = ["generate_signal_summary"]
