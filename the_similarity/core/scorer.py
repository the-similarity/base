"""
Composite confidence scoring for pattern match results.

This module contains the two core data structures (ScoreBreakdown, MatchResult)
and the weighted scoring function that collapses per-method sub-scores into a
single 0–100 confidence number.

Invariants and Constraints:
- ScoreBreakdown fields MUST EXACTLY match the keys in `Config.weights`.
- Any addition of a new scoring method demands synchronized updates to `Config.weights`
  and the `ScoreBreakdown` schema. Failure to do so leads to dropped scores.
- `MatchResult` is the immutable final output entity for the pipeline, carrying
  raw series snippets, location indices, and method diagnostic artifacts needed
  by the frontend visualization.

Scaling and Normalization:
- `compute_confidence()` renormalizes weights to sum to 1.0 across only
  the active methods. This prevents global score deflation when UI toggles
  disable individual sub-methods.
- Internally all numbers remain [0, 1] until the final scaling to [0, 100]
  prior to payload serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from the_similarity.config import Config


if TYPE_CHECKING:
    # Imported only for type hints — avoids the circular import that
    # would happen at module load (registry imports contracts which
    # would otherwise be free to import this module).
    from the_similarity.platform.registry import RunRegistry


@dataclass
class ScoreBreakdown:
    """Per-method scores that compose the final confidence score.

    Each field is a similarity score in [0, 1] where:
      0.0 = no similarity detected by this method
      1.0 = perfect match according to this method

    The composite confidence score is a weighted sum of these fields,
    scaled to [0, 100] for human readability.
    """

    # --- Bempedelis self-similarity transform ---
    # R² of the power law fit to the learned alpha(t)/beta(t) scaling functions.
    # High R² means the scaling follows a clean power law → genuine self-similarity.
    bempedelis_r2: float = 0.0

    # Total variation smoothness of the alpha/beta trajectories.
    # Smooth trajectories suggest the self-similar structure is regular, not noisy.
    bempedelis_smoothness: float = 0.0

    # --- Koopman operator matching ---
    # Similarity between eigenvalue spectra of the query and candidate's fitted
    # Koopman operators (via Hungarian matching). High = same dynamical system.
    koopman: float = 0.0

    # --- Wavelet Leaders multifractal spectrum ---
    # L2 distance between f(α) singularity spectra, converted to similarity.
    # Captures whether the two windows have the same multifractal "fingerprint".
    wavelet_spectrum: float = 0.0

    # --- Empirical Mode Decomposition ---
    # Energy-weighted distance across aligned IMFs. Captures whether the two
    # windows have the same multi-scale oscillatory structure.
    emd: float = 0.0

    # --- Topological Data Analysis ---
    # Wasserstein distance between persistence diagrams (H0 + H1).
    # Captures loop/hole structure in the delay-embedded attractor.
    tda: float = 0.0

    # --- Dynamic Time Warping ---
    # Classic shape-based distance, normalized to [0, 1] via exp(-d/w).
    # The most basic similarity signal; serves as a sanity check.
    dtw: float = 0.0

    # --- Pearson correlation (post-warp) ---
    # Pearson r computed after DTW alignment. Captures linear correlation
    # between the aligned series, complementing DTW's nonlinear distance.
    pearson_warped: float = 0.0

    # --- Transfer Entropy ---
    # Information-theoretic: how much does the match window predict the
    # forward window? High TE = the matched pattern is genuinely predictive.
    transfer_entropy: float = 0.0


# Ordered list of all score field names — used for iteration.
# This MUST stay in sync with ScoreBreakdown's fields.
_SCORE_FIELDS = [
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


@dataclass
class MatchResult:
    """A single pattern match result with full diagnostics.

    This is the central output type of the search pipeline. Each MatchResult
    represents one historical segment of the history that matched the query.

    Fields are grouped by category:
    - Location: where the match sits in the history array
    - Scoring: composite and per-method scores
    - Diagnostics: method-specific artifacts for visualization/explainability
    - Context: regime classification, forward window, source timeframe
    """

    # --- Location in the history array ---
    start_idx: int  # First index of the matched window
    end_idx: int  # Last index + 1 (exclusive)
    start_date: str | None = None  # ISO date string, if dates available
    end_date: str | None = None

    # --- Composite score ---
    confidence_score: float = 0.0  # Final weighted score [0, 100]
    score_breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)

    # --- The actual matched series values ---
    matched_series: np.ndarray | None = None  # Raw values of the matched segment

    # --- Bempedelis transform diagnostics ---
    transform_alpha: np.ndarray | None = None  # Learned time-scaling function
    transform_beta: np.ndarray | None = None  # Learned value-scaling function
    transform_r2: float = 0.0  # Combined alpha+beta R²

    # --- Koopman operator diagnostics ---
    koopman_eigenvalues: np.ndarray | None = (
        None  # Complex eigenvalues of fitted operator
    )

    # --- Wavelet Leaders diagnostics ---
    fractal_spectrum: np.ndarray | None = None  # f(α) singularity spectrum points

    # --- TDA diagnostics ---
    persistence_diagram: object | None = None  # Birth-death persistence pairs

    # --- Market regime context ---
    regime: str | None = None  # e.g., "trending_up", "high_vol"
    latent_regime_probabilities: dict[str, float] | None = None
    latent_regime_similarity: float | None = None

    # --- Forward window for projection ---
    # The values that actually occurred AFTER this match ended.
    # Used by the projector to build the forecast cone.
    forward_window: np.ndarray | None = None

    # --- Cross-timeframe search metadata ---
    source_timeframe: str | None = None  # e.g., "1h", "1d", "1w"


def compute_confidence(
    breakdown: ScoreBreakdown, config: Config | None = None
) -> float:
    """Compute weighted composite confidence score (0-100).

    The scoring formula:
      1. Filter to only active and positively-weighted methods
      2. Renormalize weights so they sum to 1.0 (prevents score deflation
         when methods are disabled)
      3. Weighted sum of per-method scores
      4. Scale to [0, 100] and clamp

    Args:
        breakdown: Per-method scores, each in [0, 1].
        config: Configuration with weight dict and active method list.
            Uses defaults if None.

    Returns:
        Composite score in [0, 100].

    Example:
        >>> bd = ScoreBreakdown(dtw=0.9, koopman=0.8)
        >>> compute_confidence(bd)  # Uses all default weights
        42.5  # Hypothetical — actual depends on default weights
    """
    if config is None:
        config = Config()

    w = config.weights

    # Step 1: Identify which fields are both active AND have positive weight.
    # Methods with zero weight are effectively disabled even if listed as active.
    active_fields = [
        field_name
        for field_name in config.active_methods
        if field_name in _SCORE_FIELDS and w.get(field_name, 0.0) > 0
    ]
    if not active_fields:
        return 0.0

    # Step 2: Renormalize — compute the sum of weights for active fields only,
    # then divide each weight by this sum so the effective weights sum to 1.0.
    # This is critical: if a user disables 3 out of 9 methods, the remaining
    # 6 methods should still be able to produce a score near 100.
    weight_total = sum(w[field_name] for field_name in active_fields)
    if weight_total <= 0:
        return 0.0

    # Step 3: Weighted sum of per-method [0, 1] scores
    raw = sum(
        (w[field_name] / weight_total) * getattr(breakdown, field_name)
        for field_name in active_fields
    )

    # Step 4: Apply small empirical adjustments learned from curated
    # goodrun/almost_good/badrun labels, then scale to [0, 100].
    adjusted = _apply_empirical_label_rules(raw, breakdown, config, set(active_fields))
    return float(np.clip(adjusted * 100, 0, 100))


def _apply_empirical_label_rules(
    raw_score: float,
    breakdown: ScoreBreakdown,
    config: Config,
    active_fields: set[str],
) -> float:
    """Bounded post-score heuristics from saved goodrun/badrun labels.

    Current evidence is intentionally treated as weak supervision. The label
    set suggests two robust-enough rules:
    - High DTW with weak Pearson/carry often marks a visual shape trap.
    - Strong Koopman plus transfer entropy deserves a modest carry boost.
    """
    if not config.empirical_label_rules_enabled:
        return raw_score

    score = raw_score

    has_dtw_trap_inputs = {"dtw", "pearson_warped", "transfer_entropy"} <= active_fields
    if (
        has_dtw_trap_inputs
        and breakdown.dtw >= 0.94
        and breakdown.pearson_warped <= 0.62
        and breakdown.transfer_entropy <= 0.24
    ):
        penalty = config.dtw_trap_penalty
        if "wavelet_spectrum" in active_fields and breakdown.wavelet_spectrum <= 0.08:
            penalty = min(1.0, penalty + 0.04)
        score *= 1.0 - penalty

    has_carry_inputs = {"koopman", "transfer_entropy"} <= active_fields
    if (
        has_carry_inputs
        and breakdown.koopman >= 0.86
        and breakdown.transfer_entropy >= 0.30
    ):
        boost = config.carry_alignment_boost
        if "pearson_warped" in active_fields and breakdown.pearson_warped >= 0.63:
            boost += 0.02
        score *= 1.0 + boost

    return float(np.clip(score, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Personalized setup scanner v1 — goodrun aggregation helper.
#
# Worktree A's job (per ``vision/personalized_setup_scanner.md``) is to
# persist thumbs-up/down feedback against a user's setups so v2 can
# train the goodrun filter on real human labels. v1 doesn't yet feed
# this signal into ``compute_confidence`` — that's a deliberate scope
# boundary. The helper below aggregates feedback rows into a simple
# net score the API surface or analytics dashboards can read.
#
# Why not in registry.py: the aggregation is a *scoring* concern, not
# a persistence concern. registry.py owns CRUD; scorer.py owns "how
# does feedback collapse into a confidence shift." Splitting them
# keeps v2's training pipeline clean — it imports ``compute_goodrun_score``
# without dragging the SQLite layer into model code.
#
# Existing goodrun infrastructure (``the-similarity-api/app/goodruns.py``,
# PRs #283/#284/#287) lives behind the API. This helper does NOT touch
# that DB — it operates over the multi-tenant ``feedback`` table the
# scanner persists to. v2 will reconcile the two surfaces; v1 keeps
# them additive.
# ---------------------------------------------------------------------------


def compute_goodrun_score(
    registry: "RunRegistry",
    user_id: str,
    setup_id: str | None = None,
) -> dict:
    """Aggregate thumbs feedback into a per-user (or per-setup) goodrun snapshot.

    Pure function over registry rows — does not mutate the registry,
    does not touch the legacy ``the-similarity-api/app/goodruns.py``
    surface. Computes:

    - ``thumbs_up``: count of ``thumb == "up"`` rows
    - ``thumbs_down``: count of ``thumb == "down"`` rows
    - ``total``: sum of the above
    - ``net_score``: ``(thumbs_up - thumbs_down) / max(1, total)`` in
      ``[-1.0, 1.0]``. Returns ``0.0`` when ``total == 0`` (no signal,
      not "neutral with high confidence").
    - ``alert_*`` / ``analog_*`` keys: per-kind breakdown so callers
      can weight live alerts and onboarding analogs differently.

    Parameters
    ----------
    registry:
        Live :class:`RunRegistry` with the v1 setups/feedback tables.
    user_id:
        Multi-tenant scope; required.
    setup_id:
        When supplied, restrict the aggregation to one setup. ``None``
        aggregates across every setup the user owns.

    Returns
    -------
    Dict with the keys above. Always returns a dict (never raises on an
    empty feedback set) so callers can chart "0 of 0" cleanly.
    """
    rows = registry.list_feedback(user_id=user_id, setup_id=setup_id, limit=10_000)
    thumbs_up = sum(1 for f in rows if f.thumb == "up")
    thumbs_down = sum(1 for f in rows if f.thumb == "down")
    total = thumbs_up + thumbs_down
    net = (thumbs_up - thumbs_down) / total if total > 0 else 0.0

    alert_rows = [f for f in rows if f.kind == "alert"]
    analog_rows = [f for f in rows if f.kind == "analog"]
    alert_up = sum(1 for f in alert_rows if f.thumb == "up")
    alert_down = sum(1 for f in alert_rows if f.thumb == "down")
    analog_up = sum(1 for f in analog_rows if f.thumb == "up")
    analog_down = sum(1 for f in analog_rows if f.thumb == "down")

    return {
        "user_id": user_id,
        "setup_id": setup_id,
        "thumbs_up": thumbs_up,
        "thumbs_down": thumbs_down,
        "total": total,
        "net_score": float(net),
        "alert_thumbs_up": alert_up,
        "alert_thumbs_down": alert_down,
        "analog_thumbs_up": analog_up,
        "analog_thumbs_down": analog_down,
    }
