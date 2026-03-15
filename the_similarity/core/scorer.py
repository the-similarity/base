from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from the_similarity.config import Config


@dataclass
class ScoreBreakdown:
    """Per-method scores that compose the final confidence score.

    Each field is a score in [0, 1]. The composite confidence score
    is a weighted sum scaled to [0, 100].
    """
    bempedelis_r2: float = 0.0          # power law fit quality
    bempedelis_smoothness: float = 0.0  # alpha/beta total variation
    koopman: float = 0.0               # eigenvalue spectrum match
    wavelet_spectrum: float = 0.0      # f(alpha) spectrum distance
    emd: float = 0.0                   # multi-scale IMF match
    tda: float = 0.0                   # persistence diagram distance
    dtw: float = 0.0                   # shape distance
    pearson_warped: float = 0.0        # correlation post-alignment
    transfer_entropy: float = 0.0      # predictive information


# Map breakdown field names to config weight keys (they match 1:1)
_SCORE_FIELDS = [
    "bempedelis_r2", "bempedelis_smoothness", "koopman",
    "wavelet_spectrum", "emd", "tda", "dtw", "pearson_warped",
    "transfer_entropy",
]


@dataclass
class MatchResult:
    """A single pattern match result."""
    start_idx: int
    end_idx: int
    start_date: str | None = None
    end_date: str | None = None
    confidence_score: float = 0.0
    score_breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    matched_series: np.ndarray | None = None
    # Bempedelis transform
    transform_alpha: np.ndarray | None = None
    transform_beta: np.ndarray | None = None
    transform_r2: float = 0.0
    # Koopman
    koopman_eigenvalues: np.ndarray | None = None
    # Fractal
    fractal_spectrum: np.ndarray | None = None
    # TDA
    persistence_diagram: object | None = None
    # Regime
    regime: str | None = None
    # What happened after this match
    forward_window: np.ndarray | None = None
    # Cross-timeframe search: source timeframe label
    source_timeframe: str | None = None


def compute_confidence(breakdown: ScoreBreakdown, config: Config | None = None) -> float:
    """Compute weighted composite confidence score (0-100).

    Args:
        breakdown: Per-method scores, each in [0, 1].
        config: Configuration with weight dict and active method list.
            Uses defaults if None.

    Returns:
        Composite score in [0, 100].
    """
    if config is None:
        config = Config()

    w = config.weights
    active_fields = [
        field_name
        for field_name in config.active_methods
        if field_name in _SCORE_FIELDS and w.get(field_name, 0.0) > 0
    ]
    if not active_fields:
        return 0.0

    weight_total = sum(w[field_name] for field_name in active_fields)
    if weight_total <= 0:
        return 0.0

    raw = sum(
        (w[field_name] / weight_total) * getattr(breakdown, field_name)
        for field_name in active_fields
    )
    return float(np.clip(raw * 100, 0, 100))
