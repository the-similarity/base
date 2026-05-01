"""Calibration metric helpers for finance review surfaces.

Backtest reports expose calibration as observed coverage by percentile:
``{"10": 0.12, "50": 0.48, "90": 0.88}``. Review gates and summaries need
the derived error ``|observed - expected|`` where expected coverage is
``percentile / 100``. Scalar calibration values are treated as pre-computed
mean absolute errors for compatibility with older artifacts.
"""

from __future__ import annotations

from typing import Any, Mapping


def mean_calibration_error(calibration: Any) -> float | None:
    """Return mean absolute calibration error from scalar or per-percentile data.

    Parameters
    ----------
    calibration:
        Either a scalar mean absolute error, or a mapping from percentile key
        (``10``, ``"10"``, ``"p10"``) to observed coverage rate.

    Returns
    -------
    float | None
        Mean absolute error, or ``None`` when no numeric calibration data can
        be interpreted.
    """
    if calibration is None:
        return None

    if isinstance(calibration, (int, float)):
        return abs(float(calibration))

    if not isinstance(calibration, Mapping):
        return None

    errors: list[float] = []
    for raw_percentile, raw_observed in calibration.items():
        if not isinstance(raw_observed, (int, float)):
            continue

        percentile = _parse_percentile(raw_percentile)
        if percentile is None:
            continue

        expected = percentile / 100.0
        errors.append(abs(float(raw_observed) - expected))

    if not errors:
        return None
    return sum(errors) / len(errors)


def _parse_percentile(value: Any) -> float | None:
    """Parse percentile keys like ``10``, ``"10"``, or ``"p10"``."""
    if isinstance(value, (int, float)):
        percentile = float(value)
    elif isinstance(value, str):
        key = value.strip().lower()
        if key.startswith("p"):
            key = key[1:]
        try:
            percentile = float(key)
        except ValueError:
            return None
    else:
        return None

    if 0.0 <= percentile <= 100.0:
        return percentile
    return None


__all__ = ["mean_calibration_error"]
