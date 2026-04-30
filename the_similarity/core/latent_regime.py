"""Probabilistic market regime state estimation.

The existing ``regime.tag_regime`` API emits one hard label. This module keeps
that label vocabulary but returns a probability distribution over regimes so
retrieval and projection can prefer analogues from similar latent states
without throwing away otherwise useful matches.

The estimator is intentionally lightweight: it converts trend, volatility, and
Hurst features into smooth emission scores. It is not a fitted HMM yet, but its
output has the same lifecycle shape needed by a future learned state-space
model: current-state probabilities plus one-step transition probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

from the_similarity.core.regime import hurst_dfa


REGIME_LABELS: tuple[str, ...] = (
    "trending_up",
    "trending_down",
    "mean_reverting",
    "high_vol",
    "low_vol",
)

_TRANSITION_MATRIX = np.array(
    [
        # to:   up    down    mr    hi    low
        [0.62, 0.04, 0.16, 0.12, 0.06],  # from trending_up
        [0.04, 0.62, 0.16, 0.12, 0.06],  # from trending_down
        [0.12, 0.12, 0.52, 0.08, 0.16],  # from mean_reverting
        [0.12, 0.12, 0.16, 0.50, 0.10],  # from high_vol
        [0.14, 0.10, 0.28, 0.06, 0.42],  # from low_vol
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class LatentRegimeState:
    """Probabilistic state estimate for one price window."""

    probabilities: dict[str, float]
    transition_probabilities: dict[str, float]
    volatility: float
    trend_slope: float
    hurst: float

    @property
    def dominant_regime(self) -> str:
        """Most likely hard regime label."""
        return max(self.probabilities.items(), key=lambda kv: kv[1])[0]


def infer_latent_regime(series: NDArray[np.float64] | list) -> LatentRegimeState:
    """Infer a soft regime distribution from a price series."""
    s = np.asarray(series, dtype=np.float64).ravel()
    if len(s) < 2 or np.all(s == s[0]):
        probs = _one_hot("low_vol")
        return LatentRegimeState(
            probabilities=probs,
            transition_probabilities=_transition(probs),
            volatility=0.0,
            trend_slope=0.0,
            hurst=0.5,
        )

    safe = np.maximum(s, 1e-12)
    log_ret = np.diff(np.log(safe))
    volatility = float(np.std(log_ret) * np.sqrt(252)) if len(log_ret) else 0.0
    trend_slope = _ols_slope(s)
    hurst = hurst_dfa(s)

    high_vol = _sigmoid((volatility - 0.32) / 0.07)
    low_vol = _sigmoid((0.12 - volatility) / 0.035)
    persistent = _sigmoid((hurst - 0.56) / 0.06)
    anti_persistent = _sigmoid((0.44 - hurst) / 0.06)
    up_drift = _sigmoid((trend_slope - 0.006) / 0.012)
    down_drift = _sigmoid((-trend_slope - 0.006) / 0.012)

    raw_scores = np.array(
        [
            persistent * up_drift * (1.0 - 0.45 * high_vol),
            persistent * down_drift * (1.0 - 0.45 * high_vol),
            anti_persistent * (1.0 - 0.35 * high_vol),
            high_vol,
            low_vol,
        ],
        dtype=np.float64,
    )
    raw_scores = np.maximum(raw_scores, 1e-8)
    probs_arr = raw_scores / raw_scores.sum()
    probs = {label: float(probs_arr[i]) for i, label in enumerate(REGIME_LABELS)}

    return LatentRegimeState(
        probabilities=probs,
        transition_probabilities=_transition(probs),
        volatility=volatility,
        trend_slope=trend_slope,
        hurst=hurst,
    )


def regime_probability_similarity(
    a: LatentRegimeState | Mapping[str, float],
    b: LatentRegimeState | Mapping[str, float],
) -> float:
    """Cosine similarity between two regime probability vectors."""
    a_vec = _as_vector(a)
    b_vec = _as_vector(b)
    denom = float(np.linalg.norm(a_vec) * np.linalg.norm(b_vec))
    if denom <= 1e-12:
        return 0.0
    return float(np.clip(np.dot(a_vec, b_vec) / denom, 0.0, 1.0))


def _transition(probabilities: Mapping[str, float]) -> dict[str, float]:
    p = _as_vector(probabilities)
    next_p = p @ _TRANSITION_MATRIX
    next_p = next_p / next_p.sum()
    return {label: float(next_p[i]) for i, label in enumerate(REGIME_LABELS)}


def _as_vector(state: LatentRegimeState | Mapping[str, float]) -> NDArray[np.float64]:
    probabilities = state.probabilities if isinstance(state, LatentRegimeState) else state
    return np.array(
        [float(probabilities.get(label, 0.0)) for label in REGIME_LABELS],
        dtype=np.float64,
    )


def _one_hot(label: str) -> dict[str, float]:
    return {name: 1.0 if name == label else 0.0 for name in REGIME_LABELS}


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-np.clip(x, -40.0, 40.0))))


def _ols_slope(series: NDArray[np.float64]) -> float:
    std = float(np.std(series))
    if std <= 1e-12:
        return 0.0
    z = (series - np.mean(series)) / std
    t = np.arange(len(z), dtype=np.float64)
    return float(np.polyfit(t, z, 1)[0])


__all__ = [
    "LatentRegimeState",
    "REGIME_LABELS",
    "infer_latent_regime",
    "regime_probability_similarity",
]
