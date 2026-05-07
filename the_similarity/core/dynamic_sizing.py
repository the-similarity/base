"""Finite-action dynamic position sizing.

This module adds a small recursive-control layer on top of forecast cones. It
does not decide trade direction; it chooses size from a discrete action grid by
maximizing a one-step utility that balances expected edge, forecast variance,
trust, turnover, drawdown, and calibration risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from the_similarity.core.ensemble import EnsembleForecast
from the_similarity.core.projector import Forecast
from the_similarity.core.strategy import SignalType


@dataclass(frozen=True)
class SizingState:
    """Current state variables used by the sizing policy."""

    trust_score: float
    confidence: float
    current_position_size: float = 0.0
    drawdown: float = 0.0
    calibration_error: float = 0.0


@dataclass(frozen=True)
class DynamicSizingDecision:
    """Chosen size and utility diagnostics."""

    size: float
    utility: float
    expected_edge: float
    forecast_variance: float


@dataclass
class DynamicSizingPolicy:
    """Discrete dynamic sizing policy.

    The policy evaluates a fixed action grid and selects the size with maximum
    utility. This is deliberately small and deterministic, but it creates the
    right interface for later multi-period Bellman recursion.
    """

    action_grid: tuple[float, ...] = field(
        default_factory=lambda: (0.0, 0.10, 0.25, 0.50, 0.75, 1.0)
    )
    risk_aversion: float = 4.0
    turnover_penalty: float = 0.05
    drawdown_penalty: float = 0.50
    calibration_penalty: float = 0.75

    def choose_size(
        self,
        signal_type: SignalType,
        forecast: Forecast | EnsembleForecast | None,
        state: SizingState,
        *,
        min_position_size: float = 0.0,
        max_position_size: float = 1.0,
    ) -> DynamicSizingDecision:
        """Choose a position size for a directional signal."""
        if signal_type == SignalType.FLAT or forecast is None:
            return DynamicSizingDecision(0.0, 0.0, 0.0, 0.0)

        expected_edge, forecast_variance = _forecast_edge_and_variance(
            signal_type, forecast
        )
        trust = float(np.clip(state.trust_score, 0.0, 1.0))
        confidence = float(np.clip(state.confidence / 100.0, 0.0, 1.0))
        reliability = trust * confidence

        best_size = 0.0
        best_utility = -np.inf
        for raw_size in self.action_grid:
            size = float(np.clip(raw_size, 0.0, max_position_size))
            if size > 0.0:
                size = max(min_position_size, size)

            utility = (
                reliability * expected_edge * size
                - self.risk_aversion * forecast_variance * size * size
                - self.turnover_penalty * abs(size - state.current_position_size)
                - self.drawdown_penalty * max(0.0, state.drawdown) * size
                - self.calibration_penalty * max(0.0, state.calibration_error) * size
            )
            if utility > best_utility:
                best_utility = utility
                best_size = size

        return DynamicSizingDecision(
            size=float(np.clip(best_size, 0.0, max_position_size)),
            utility=float(best_utility),
            expected_edge=float(expected_edge),
            forecast_variance=float(forecast_variance),
        )


def _forecast_edge_and_variance(
    signal_type: SignalType,
    forecast: Forecast | EnsembleForecast,
) -> tuple[float, float]:
    p50 = _endpoint(forecast.curves, 50)
    if p50 is None:
        return 0.0, 0.0

    # If an ensemble carries an adverse ambiguity cone, size off the more
    # conservative median for the intended direction.
    robust = getattr(forecast, "robust_ambiguity", None)
    if robust is not None:
        robust_p50 = _endpoint(robust.curves, 50)
        if robust_p50 is not None:
            if signal_type == SignalType.LONG:
                p50 = min(p50, robust_p50)
            elif signal_type == SignalType.SHORT:
                p50 = max(p50, robust_p50)

    direction = 1.0 if signal_type == SignalType.LONG else -1.0
    expected_edge = max(0.0, direction * p50)

    all_paths = getattr(forecast, "all_paths", None)
    variance = _terminal_variance(all_paths)
    if variance == 0.0:
        p10 = _endpoint(forecast.curves, 10)
        p90 = _endpoint(forecast.curves, 90)
        if p10 is not None and p90 is not None:
            variance = max(0.0, ((p90 - p10) / 2.56) ** 2)

    return expected_edge, variance


def _endpoint(curves: dict[int, NDArray[np.float64]], percentile: int) -> float | None:
    curve = curves.get(percentile)
    if curve is None or len(curve) == 0:
        return None
    return float(curve[-1])


def _terminal_variance(paths: NDArray[np.float64] | None) -> float:
    if paths is None or len(paths) == 0:
        return 0.0
    arr = np.asarray(paths, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] == 0:
        return 0.0
    return float(np.var(arr[:, -1]))


__all__ = [
    "DynamicSizingDecision",
    "DynamicSizingPolicy",
    "SizingState",
]
