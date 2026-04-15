"""
Global configuration and hyperparameters for the_similarity engine.

This module defines the single `Config` dataclass that controls the entire
matching pipeline. Every tunable knob — method weights, tier thresholds,
normalization strategy, windowing parameters — lives here.

Integration guide for new scoring methods:
- When adding a new scoring method, you must:
  1. Add its weight key to `weights` and `active_methods` below.
  2. Wire the computation in `core/matcher.py` (Tier 2 enrichment).
  3. Add the field to `core/scorer.py` → ScoreBreakdown.
  4. Add the field to `contracts/api.py` → ScoreBreakdownResponse.
- The weights dict is NOT required to sum to 1.0 as stored; the live scorer
  renormalizes across whichever `active_methods` are actually enabled for a
  given search call. This means you can add methods without rescaling others.
- Backward compatibility: new fields MUST have defaults that reproduce the
  prior behavior (e.g., `koopman_blend_weight=0.0` means "off by default").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Config:
    """Global configuration and default hyperparameters.

    Instances are typically created with defaults and selectively overridden:
        cfg = Config(stride=3, tier1_candidates=500)

    The search pipeline reads this once per call; it is safe to create
    different Config instances for different search strategies.
    """

    # -------------------------------------------------------------------------
    # Confidence score weights
    # -------------------------------------------------------------------------
    # Each key maps to a scoring method name used in ScoreBreakdown.
    # The float value is the "importance" of that method in the composite
    # confidence score. The scorer renormalizes these at runtime across only
    # the `active_methods` list, so the raw values here do NOT need to sum
    # to 1.0 — they represent *relative* importance.
    #
    # Current hierarchy rationale:
    # - Koopman (0.20) and Bempedelis R² (0.20) are the highest because they
    #   capture genuine dynamical/self-similar structure, not just shape.
    # - Wavelet spectrum (0.15) captures multifractal fingerprint similarity.
    # - DTW (0.07) and Pearson (0.05) are deliberately low because they are
    #   available at Tier 1 and are already used for pre-ranking; over-weighting
    #   them would make Tier 2 enrichment irrelevant.
    # - Transfer entropy (0.05) is experimental; raise it if forward-prediction
    #   accuracy becomes a primary objective.
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "bempedelis_r2": 0.20,  # Power law fit quality (self-similarity)
            "bempedelis_smoothness": 0.10,  # Scaling function smoothness
            "koopman": 0.20,  # Koopman eigenvalue spectrum match
            "wavelet_spectrum": 0.15,  # f(α) singularity spectrum distance
            "emd": 0.10,  # EMD multi-scale energy-weighted distance
            "tda": 0.08,  # Persistent homology Wasserstein distance
            "dtw": 0.07,  # Dynamic Time Warping (shape baseline)
            "pearson_warped": 0.05,  # Pearson correlation after DTW alignment
            "transfer_entropy": 0.05,  # Information transfer: match → forward
        }
    )

    # -------------------------------------------------------------------------
    # Active methods
    # -------------------------------------------------------------------------
    # Only methods in this list are computed during Tier 2 enrichment.
    # Removing methods here is the fastest way to speed up search at the cost
    # of less discriminative scoring. The WebSocket front-end also sends an
    # `active_methods` override per-request for interactive tuning.
    active_methods: list[str] = field(
        default_factory=lambda: [
            "bempedelis_r2",
            "bempedelis_smoothness",
            "koopman",
            "wavelet_spectrum",
            "emd",
            "tda",
            "dtw",
            "pearson_warped",
            "transfer_entropy",
        ]
    )

    # -------------------------------------------------------------------------
    # DTW configuration
    # -------------------------------------------------------------------------
    # Sakoe-Chiba band radius limits the DTW warping path to stay within
    # `radius` cells of the diagonal. None = auto-select (10% of window).
    # Larger radius = more flexible warping but O(n * radius) cost.
    dtw_sakoe_chiba_radius: int | None = None

    # -------------------------------------------------------------------------
    # Tier 1 pre-filter
    # -------------------------------------------------------------------------
    # After SAX + MASS distance profiles rank ALL candidate windows, only the
    # top `tier1_candidates` proceed to DTW/Pearson scoring. This is the main
    # throughput knob: lower = faster search, higher = more recall.
    tier1_candidates: int | None = 1000

    # -------------------------------------------------------------------------
    # Tier 2 quality matching
    # -------------------------------------------------------------------------
    # After Tier 1 (DTW + Pearson) ranking, only the top `tier2_candidates`
    # proceed to expensive enrichment (Koopman, Bempedelis, TDA, etc.).
    # 20 is a good default; increase for research-grade thoroughness.
    tier2_candidates: int | None = 20

    # -------------------------------------------------------------------------
    # Normalization
    # -------------------------------------------------------------------------
    # The default transform applied to both query and candidate windows before
    # shape matching. "logreturn_zscore" first takes log-returns (making the
    # comparison scale-invariant) then z-scores each window (making it
    # location-invariant). This is the recommended default for financial data.
    # Override per-method via core/normalizer.py → METHOD_NORM_DEFAULTS.
    normalization: str = "logreturn_zscore"

    # -------------------------------------------------------------------------
    # SAX pre-filter parameters
    # -------------------------------------------------------------------------
    # n_segments: how many PAA segments to reduce each window to.
    #   16 balances resolution (catching gross dissimilarities) vs. speed.
    # alphabet_size: number of SAX symbols (2–26). 8 is standard; larger values
    #   give tighter MINDIST bounds but diminishing returns past ~10.
    sax_n_segments: int = 16
    sax_alphabet_size: int = 8

    # -------------------------------------------------------------------------
    # Bempedelis self-similarity parameters
    # -------------------------------------------------------------------------
    # n_subwindows: how many equal slices to split each window into for the
    #   self-similarity transform. More = finer scale resolution, but needs
    #   longer windows (min window = n_subwindows * 3 points).
    # n_restarts: random restarts for the L-BFGS-B optimizer.
    bempedelis_n_subwindows: int = 5
    bempedelis_n_restarts: int = 3

    # -------------------------------------------------------------------------
    # Multi-scale search
    # -------------------------------------------------------------------------
    # When set (e.g., [1.0, 1.5, 2.0]), the matcher generates candidate
    # windows at each scale multiplier of the query length. This helps find
    # analogs that played out at different speeds. None = single scale only.
    window_scales: list[float] | None = None

    # -------------------------------------------------------------------------
    # Windower stride
    # -------------------------------------------------------------------------
    # Step size when sliding the window over the history array. stride=1 means
    # every position is a candidate (maximum recall, slowest). stride=3 or 5
    # is common for interactive use. The matcher may auto-increase stride for
    # very large histories to keep search sub-10s.
    stride: int = 1

    # -------------------------------------------------------------------------
    # Projection / forecast cone
    # -------------------------------------------------------------------------
    # forward_bars: how many bars into the future each match's post-match
    #   history is extracted for the projection cone.
    # percentiles: which quantiles to compute across all matches' forward paths.
    forward_bars: int = 50
    percentiles: list[int] = field(default_factory=lambda: [10, 25, 50, 75, 90])

    # -------------------------------------------------------------------------
    # Advanced forecast tuning
    # -------------------------------------------------------------------------
    # confidence_decay_rate: exponential decay applied to match weights as
    #   the forecast horizon increases. 0.0 = flat weighting (default).
    #   Positive values make nearer-future bars rely more on high-confidence
    #   matches, which can improve short-horizon accuracy.
    # koopman_blend_weight: fraction of the forecast blended from Koopman
    #   operator evolution (vs. purely historical analogs). 0.0 = historical
    #   only (backward compatible). Values 0.1–0.3 are reasonable for assets
    #   with strong dynamical structure.
    confidence_decay_rate: float = 0.0
    koopman_blend_weight: float = 0.0

    # -------------------------------------------------------------------------
    # Experimental feature flags
    # -------------------------------------------------------------------------
    # All experimental flags default to OFF so that `Config()` produces
    # identical behavior to the pre-flag codebase. Future integrations
    # (JEPA embeddings, autoresearch loops) toggle these without invasive
    # code edits.
    #
    # jepa_enabled: master switch for JEPA embedding similarity scoring.
    #   When False, no JEPA code paths execute and jepa_weight is forced
    #   to 0.0 as a fail-safe.
    # jepa_weight: relative importance of the JEPA method in the composite
    #   confidence score. Must be in [0.0, 1.0]. Only meaningful when
    #   jepa_enabled is True.
    # jepa_embedding_path: filesystem path to a pre-computed JEPA embedding
    #   store (e.g. an HDF5 or safetensors file). Required when
    #   jepa_enabled is True; ignored otherwise.
    jepa_enabled: bool = False
    jepa_weight: float = 0.0
    jepa_embedding_path: str | None = None

    # -------------------------------------------------------------------------
    # Post-init validation
    # -------------------------------------------------------------------------
    def __post_init__(self) -> None:
        """Validate configuration invariants after dataclass initialization.

        Checks:
        - jepa_weight is bounded to [0.0, 1.0].
        - If jepa_enabled is True, jepa_embedding_path must be a non-empty
          string (fail-fast so callers don't silently get zero JEPA scores).
        - If jepa_enabled is False, jepa_weight is clamped to 0.0 regardless
          of what the caller passed (fail-safe default-off semantics).
        """
        # --- JEPA flag validation ---
        if not isinstance(self.jepa_weight, (int, float)):
            raise TypeError(
                f"jepa_weight must be a number, got {type(self.jepa_weight).__name__}"
            )
        if not (0.0 <= self.jepa_weight <= 1.0):
            raise ValueError(
                f"jepa_weight must be in [0.0, 1.0], got {self.jepa_weight}"
            )
        if self.jepa_enabled:
            if not self.jepa_embedding_path:
                raise ValueError(
                    "jepa_embedding_path must be set when jepa_enabled is True"
                )
        else:
            # Fail-safe: disabled flag forces weight to zero so stale config
            # from a previous experiment cannot accidentally influence scoring.
            self.jepa_weight = 0.0

    # -------------------------------------------------------------------------
    # Feature flag introspection
    # -------------------------------------------------------------------------
    def feature_flags(self) -> dict[str, object]:
        """Return a dict of all experimental feature flags and their values.

        Designed for structured logging, experiment ledger entries, and
        reproducibility metadata. Keys are stable identifiers; values are
        the post-validation state (e.g. jepa_weight will be 0.0 if
        jepa_enabled is False, regardless of what was passed at init).
        """
        return {
            "jepa_enabled": self.jepa_enabled,
            "jepa_weight": self.jepa_weight,
            "jepa_embedding_path": self.jepa_embedding_path,
        }
