from dataclasses import dataclass, field


@dataclass
class Config:
    """Global configuration and default hyperparameters."""

    # Confidence score weights (sum to 1.0 across all known methods).
    # Live scoring renormalizes across `active_methods` so future metrics can be
    # defined here without compressing the confidence scale today.
    weights: dict[str, float] = field(default_factory=lambda: {
        "bempedelis_r2": 0.20,          # power law fit quality
        "bempedelis_smoothness": 0.10,  # transform smoothness
        "koopman": 0.20,               # dynamical system match
        "wavelet_spectrum": 0.15,      # fractal fingerprint match
        "emd": 0.10,                   # multi-scale shape match
        "tda": 0.08,                   # topological similarity
        "dtw": 0.07,                   # baseline shape match
        "pearson_warped": 0.05,        # correlation post-warp
        "transfer_entropy": 0.05,      # predictive information
    })
    active_methods: list[str] = field(default_factory=lambda: [
        "bempedelis_r2",
        "bempedelis_smoothness",
        "koopman",
        "wavelet_spectrum",
        "emd",
        "tda",
        "dtw",
        "pearson_warped",
        "transfer_entropy",
    ])

    # DTW
    dtw_sakoe_chiba_radius: int | None = None  # None = auto (10% of window)

    # Tier 1 pre-filter
    tier1_candidates: int | None = 1000

    # Tier 2 quality matching
    tier2_candidates: int | None = 20

    # Normalization: default transform applied before shape matching.
    # "logreturn_zscore" = log-returns then per-window z-score (recommended).
    # Individual methods override this via METHOD_NORM_DEFAULTS.
    normalization: str = "logreturn_zscore"

    # SAX pre-filter
    sax_n_segments: int = 16
    sax_alphabet_size: int = 8

    # Bempedelis
    bempedelis_n_subwindows: int = 5
    bempedelis_n_restarts: int = 3

    # Multi-scale search
    window_scales: list[float] | None = None  # None = single scale (1.0 only)

    # Windower
    stride: int = 1

    # Projection
    forward_bars: int = 50
    percentiles: list[int] = field(default_factory=lambda: [10, 25, 50, 75, 90])

    # Forecast cone
    confidence_decay_rate: float = 0.0  # 0.0 = no decay (backward compatible)
    koopman_blend_weight: float = 0.0   # 0.0 = historical only (backward compatible)
