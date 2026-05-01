"""Core pattern matching orchestrator.

The engine uses a tiered search pipeline to find historical analogs for a given
query pattern in near real-time, even across decades of tick data.

Tier 0: Candidate Generation & Pre-filter (SAX + MASS) -> Prunes ~95%
Tier 1: Cheap Scoring (DTW, Pearson) -> Ranks remainder -> Defines Top N
Tier 2: Expensive Enrichment (Koopman, Wavelet, TDA, EMD, etc.) -> Final Scores

Lifecycle Overview:
Each `find_matches()` call represents a single search execution lifecycle.
The state array `history` remains immutable across the run. Candidate windows
are generated immutably as strided views.

Concurrency and Threading:
Tier 2 enrichment heavily relies on compiled extensions (NumPy, SciPy). Because
these operations release the Global Interpreter Lock (GIL), the `ThreadPoolExecutor`
actually provides true hardware parallelization up to the CPU core count.
Memory constraints typically cap this to `max_workers = 4`. Avoid running additional
thread pools inside methods invoked by the executor to prevent thread starvation.

Result Streaming & UI Hooks:
The `progress_fn` hook is critical. The web UI depends on `ProgressEvent` emissions
during major transitions (`tier1`, `tier2`, `done`) to render the live search
progress. Without this, WebSocket connections will timeout.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np
from numpy.typing import NDArray
from scipy.stats import pearsonr

from the_similarity.config import Config
from the_similarity.core.normalizer import METHOD_NORM_DEFAULTS, normalize
from the_similarity.core.latent_regime import (
    LatentRegimeState,
    infer_latent_regime,
    regime_probability_similarity,
)
from the_similarity.core.regime import tag_regime
from the_similarity.core.scorer import MatchResult, ScoreBreakdown, compute_confidence
from the_similarity.core.windower import sliding_windows, window_indices
from the_similarity.methods.bempedelis import bempedelis_match
from the_similarity.methods.dtw_matcher import batch_dtw_scores, dtw_distance, dtw_score
from the_similarity.methods.emd_matcher import emd_score
from the_similarity.methods.koopman import koopman_match
from the_similarity.methods.matrix_profile_filter import (
    HAS_STUMPY,
    mp_score_profile,
    query_profile,
)
from the_similarity.methods.sax_filter import sax_mindist, sax_score, sax_transform
from the_similarity.methods.tda_matcher import compare as tda_compare
from the_similarity.methods.transfer_entropy import te_score
from the_similarity.methods.wavelet_leaders import wavelet_spectrum_score


@dataclass
class ProgressEvent:
    """Progress update from the matching pipeline.

    Emitted at key stages so callers (e.g., WebSocket handlers) can
    stream real-time updates to clients.
    """

    stage: Literal["prefilter", "tier1", "tier2", "done"]
    completed: int = 0
    total: int = 0
    message: str = ""
    # Intermediate top match (updated as scoring progresses)
    top_score: float = 0.0
    top_match_idx: int = -1


# Callback type: receives a ProgressEvent, returns nothing.
ProgressCallback = Callable[[ProgressEvent], None]

# Method groupings for tiered execution
# Separating cheap and expensive methods ensures responsiveness.
CHEAP_SCORE_FIELDS = {"dtw", "pearson_warped"}
BEMPEDELIS_SCORE_FIELDS = {"bempedelis_r2", "bempedelis_smoothness"}
TIER2_SCORE_FIELDS = {
    "koopman",
    "wavelet_spectrum",
    "emd",
    "tda",
    "transfer_entropy",
}
ALL_SCORE_FIELDS = CHEAP_SCORE_FIELDS | BEMPEDELIS_SCORE_FIELDS | TIER2_SCORE_FIELDS


@dataclass
class CandidateWindow:
    """Internal structure tracking a single window as it moves through the pipeline."""

    start_idx: int
    end_idx: int
    scale: float
    raw_series: NDArray[np.float64]
    shape_series: NDArray[np.float64]
    prefilter_score: float
    breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    confidence_score: float = 0.0
    base_rank_score: float = 0.0
    transform_alpha: NDArray[np.float64] | None = None
    transform_beta: NDArray[np.float64] | None = None
    transform_r2: float = 0.0
    regime: str | None = None
    latent_regime: LatentRegimeState | None = None
    latent_regime_similarity: float | None = None


def score_dtw(
    query_norm: NDArray[np.float64],
    cand_norm: NDArray[np.float64],
    radius: int,
) -> float:
    """DTW similarity score in [0, 1]."""
    dist = dtw_distance(query_norm, cand_norm, sakoe_chiba_radius=radius)
    return dtw_score(dist, len(query_norm))


def score_pearson(
    query_norm: NDArray[np.float64],
    cand_norm: NDArray[np.float64],
) -> float:
    """Pearson correlation mapped to [0, 1].

    Negative correlation becomes < 0.5, positive correlation > 0.5.
    Perfect correlation = 1.0.
    """
    if np.std(query_norm) == 0 or np.std(cand_norm) == 0:
        return 0.0
    corr, _ = pearsonr(query_norm, cand_norm)
    if np.isnan(corr):
        return 0.0
    return max(0.0, (corr + 1) / 2)


def find_matches(
    query: NDArray[np.float64],
    history: NDArray[np.float64],
    top_k: int = 20,
    config: Config | None = None,
    dates: list[str] | NDArray | None = None,
    exclude_query_region: tuple[int, int] | None = None,
    feature_store=None,
    ds_hash: str = "",
    progress_fn: ProgressCallback | None = None,
) -> list[MatchResult]:
    """Run the full tiered matching pipeline.

    Algorithm overview:
    1. Tier 0: Generate overlapping candidate windows across `history` using
       multiple scales (e.g. 1.0x, 1.5x) via strided array views.
    2. Score these millions of candidates cheaply using SAX strings and FFT-based
       MASS distance profiles. Sort and keep only the top `tier1_candidates`.
    3. Tier 1: On survivors, run exact DTW (with constraints) and Pearson.
       Compute a "base score" and sort.
    4. Tier 2: Take the top `tier2_candidates` from Tier 1, and enrich them
       in parallel using Koopman, Wavelets, TDA, EMD, etc. These complex methods
       quantify dynamical and topological similarity.
    5. Aggregate final composite confidence scores.
    6. Return best `top_k` matches.

    Args:
        query: 1D array representing the pattern to search for.
        history: 1D array of background historical data.
        top_k: Number of highest-scoring matches to return.
        config: Configuration containing weights, active methods, and thresholds.
        dates: Optional parallel array of ISO datetime strings for annotation.
        exclude_query_region: Bounds (start, end) marking where the query itself
                              sits in the history to prevent trivial self-matching.
        feature_store: SQLite cache instance for skipping redundant Tier 2 compute.
        ds_hash: Unique identifier of `history` used for cache keys.
        progress_fn: Optional callback receiving ProgressEvent updates
            for streaming/real-time progress reporting.

    Returns:
        List of MatchResult objects sorted descending by confidence_score.
    """
    if config is None:
        config = Config()

    active_fields = {
        field_name
        for field_name in config.active_methods
        if field_name in ALL_SCORE_FIELDS
    }
    if not active_fields:
        return []

    query_shape = normalize(query, config.normalization)
    query_shape_len = len(query_shape)
    query_latent_regime = (
        infer_latent_regime(query) if config.latent_regime_enabled else None
    )

    radius = config.dtw_sakoe_chiba_radius
    if radius is None:
        # Default Sakoe-Chiba constraint is 10% of the window size,
        # providing enough slack for minor structural warping without
        # allowing degenerate flat alignments.
        radius = max(1, query_shape_len // 10)

    # --- Tier 0: Candidate generation with SAX + MASS prefilter ---
    candidates = _collect_candidates(
        query=query,
        history=history,
        query_shape=query_shape,
        config=config,
        exclude_query_region=exclude_query_region,
    )
    if not candidates:
        if progress_fn is not None:
            progress_fn(ProgressEvent(stage="done", message="no candidates found"))
        return []

    if progress_fn is not None:
        progress_fn(
            ProgressEvent(
                stage="prefilter",
                completed=len(candidates),
                total=len(candidates),
                message=f"{len(candidates)} candidates after prefilter",
            )
        )

    # --- Tier 1: Cheap methods on all survivors ---
    base_fields = [f for f in config.active_methods if f in CHEAP_SCORE_FIELDS]
    base_config = Config(
        weights=config.weights.copy(),
        active_methods=base_fields,
    )

    # Batch DTW computation using C-accelerated distance_matrix_fast
    if "dtw" in active_fields:
        cand_shapes = [c.shape_series for c in candidates]
        dtw_scores_batch = batch_dtw_scores(query_shape, cand_shapes, radius)
    else:
        dtw_scores_batch = [0.0] * len(candidates)

    for i, candidate in enumerate(candidates):
        breakdown = ScoreBreakdown()
        if "dtw" in active_fields:
            breakdown.dtw = dtw_scores_batch[i]
        if "pearson_warped" in active_fields:
            breakdown.pearson_warped = score_pearson(
                query_shape, candidate.shape_series
            )
        candidate.breakdown = breakdown

        if base_fields:
            candidate.base_rank_score = compute_confidence(
                candidate.breakdown, base_config
            )
        else:
            # Fallback if no tier1 methods are active
            candidate.base_rank_score = candidate.prefilter_score * 100.0
        # Initialize confidence score. Will be overwritten by Tier 2 if configured.
        candidate.confidence_score = compute_confidence(candidate.breakdown, config)
        _apply_direction_consistency_adjustment(candidate, query, config)
        _apply_latent_regime_adjustment(candidate, query_latent_regime, config)

    if progress_fn is not None:
        best_so_far = max(candidates, key=lambda c: c.confidence_score)
        progress_fn(
            ProgressEvent(
                stage="tier1",
                completed=len(candidates),
                total=len(candidates),
                message=f"DTW+Pearson scored {len(candidates)} candidates",
                top_score=best_so_far.confidence_score,
                top_match_idx=best_so_far.start_idx,
            )
        )

    # --- Tier 2: Expensive methods on top candidates ---
    tier2_fields = (BEMPEDELIS_SCORE_FIELDS | TIER2_SCORE_FIELDS) & active_fields
    if tier2_fields:
        rerank_count = config.tier2_candidates
        # Only enrich the most promising matches to save CPU
        rerank_pool = sorted(candidates, key=lambda c: c.base_rank_score, reverse=True)
        if rerank_count is not None:
            rerank_pool = rerank_pool[:rerank_count]

        _enrich_tier2(
            candidates=rerank_pool,
            query=query,
            history=history,
            config=config,
            active_fields=active_fields,
            feature_store=feature_store,
            ds_hash=ds_hash,
            progress_fn=progress_fn,
        )
        # Update composite scores including the newly added Tier2 breakdown scores
        for candidate in rerank_pool:
            candidate.confidence_score = compute_confidence(candidate.breakdown, config)
            _apply_direction_consistency_adjustment(candidate, query, config)
            _apply_latent_regime_adjustment(candidate, query_latent_regime, config)

    # --- Build results ---
    candidates.sort(key=lambda c: c.confidence_score, reverse=True)

    if progress_fn is not None:
        best = candidates[0] if candidates else None
        progress_fn(
            ProgressEvent(
                stage="done",
                completed=min(top_k, len(candidates)),
                total=min(top_k, len(candidates)),
                message=f"returning {min(top_k, len(candidates))} matches",
                top_score=best.confidence_score if best else 0.0,
                top_match_idx=best.start_idx if best else -1,
            )
        )

    results: list[MatchResult] = []
    # Only return top K to save serialization overhead
    for candidate in candidates[:top_k]:
        start = candidate.start_idx
        end = candidate.end_idx
        results.append(
            MatchResult(
                start_idx=start,
                end_idx=end,
                start_date=str(dates[start]) if dates is not None else None,
                end_date=str(dates[end - 1]) if dates is not None else None,
                confidence_score=candidate.confidence_score,
                score_breakdown=candidate.breakdown,
                matched_series=candidate.raw_series,
                transform_alpha=candidate.transform_alpha,
                transform_beta=candidate.transform_beta,
                transform_r2=candidate.transform_r2,
                regime=candidate.regime,
                latent_regime_probabilities=(
                    candidate.latent_regime.probabilities
                    if candidate.latent_regime is not None
                    else None
                ),
                latent_regime_similarity=candidate.latent_regime_similarity,
            )
        )
    return results


def _apply_latent_regime_adjustment(
    candidate: CandidateWindow,
    query_latent_regime: LatentRegimeState | None,
    config: Config,
) -> None:
    """Discount scores for candidates whose soft regime differs from the query."""
    if query_latent_regime is None or not config.latent_regime_enabled:
        return

    if candidate.latent_regime is None:
        candidate.latent_regime = infer_latent_regime(candidate.raw_series)
        candidate.regime = candidate.latent_regime.dominant_regime

    similarity = regime_probability_similarity(query_latent_regime, candidate.latent_regime)
    candidate.latent_regime_similarity = similarity

    keep = 1.0 - config.latent_regime_weight + config.latent_regime_weight * similarity
    candidate.base_rank_score *= keep
    candidate.confidence_score *= keep


def _apply_direction_consistency_adjustment(
    candidate: CandidateWindow,
    query: NDArray[np.float64],
    config: Config,
) -> None:
    """Discount candidates whose window direction contradicts the query.

    Saved badruns showed several high-shape candidates whose match-window
    direction disagreed with the query move. Tiny near-flat moves are ignored
    so chop does not get over-penalized.
    """
    if not config.empirical_label_rules_enabled:
        return

    query_ret = _window_return(query)
    candidate_ret = _window_return(candidate.raw_series)
    threshold = config.direction_mismatch_min_abs_return
    if abs(query_ret) < threshold or abs(candidate_ret) < threshold:
        return
    if np.sign(query_ret) == np.sign(candidate_ret):
        return

    keep = 1.0 - config.direction_mismatch_penalty
    candidate.base_rank_score *= keep
    candidate.confidence_score *= keep


def _window_return(values: NDArray[np.float64]) -> float:
    """Return simple start-to-end return, guarding bad/flat inputs."""
    if len(values) < 2:
        return 0.0
    start = float(values[0])
    end = float(values[-1])
    if not np.isfinite(start) or not np.isfinite(end) or start == 0.0:
        return 0.0
    return end / start - 1.0


def _collect_candidates(
    query: NDArray[np.float64],
    history: NDArray[np.float64],
    query_shape: NDArray[np.float64],
    config: Config,
    exclude_query_region: tuple[int, int] | None,
) -> list[CandidateWindow]:
    """Tier 0: Massive Candidate Filter

    Applies SAX bounding and FFT-based Matrix Profile distance profiling
    to rapidly evaluate every possible strided window in the history.
    """
    window_size = len(query)
    query_shape_len = len(query_shape)
    scales = config.window_scales if config.window_scales is not None else [1.0]

    # Pre-compute SAX for query once
    query_sax = sax_transform(
        query_shape,
        n_segments=config.sax_n_segments,
        alphabet_size=config.sax_alphabet_size,
    )

    # Pre-compute MASS distance profile for scale=1.0 (O(n log n) via FFT)
    # This evaluates ALL O(N) candidates natively in C/Numpy backend.
    mp_scores: NDArray[np.float64] | None = None
    if HAS_STUMPY and query_shape_len >= 4:
        history_shape = normalize(history, config.normalization)
        if len(history_shape) > query_shape_len:
            try:
                distances = query_profile(history_shape, query_shape)
                mp_scores = mp_score_profile(distances, query_shape_len)
            except Exception:
                mp_scores = None

    candidates: list[CandidateWindow] = []
    for scale in scales:
        window_length = max(2, int(round(window_size * scale)))
        if window_length > len(history):
            continue

        windows = sliding_windows(history, window_length, stride=config.stride)
        indices = window_indices(len(history), window_length, stride=config.stride)
        for index, (start, end) in enumerate(indices):
            # Exclude exact query match during self-search
            if exclude_query_region is not None:
                query_start, query_end = exclude_query_region
                if start < query_end and end > query_start:
                    continue

            raw_window = windows[index]
            shape_window = normalize(raw_window, config.normalization)

            # Stretch candidate into query length domain for fair SAX comparison
            if scale != 1.0:
                shape_window = _resample(shape_window, query_shape_len)

            mp_score_val: float | None = None
            if mp_scores is not None and scale == 1.0 and start < len(mp_scores):
                mp_score_val = float(mp_scores[start])

            # Prefilter heuristic equation blends the extremely fast MASS score
            # and SAX string distance into a loose early rejection score
            prefilter = _score_prefilter(
                query_shape,
                shape_window,
                query_sax,
                config,
                mp_score_val=mp_score_val,
            )
            candidates.append(
                CandidateWindow(
                    start_idx=start,
                    end_idx=end,
                    scale=scale,
                    raw_series=raw_window,
                    shape_series=shape_window,
                    prefilter_score=prefilter,
                )
            )

    tier1_candidates = config.tier1_candidates
    # Top K partial sort to isolate best candidates for Tier 1
    if tier1_candidates is not None and len(candidates) > tier1_candidates:
        candidates.sort(key=lambda c: c.prefilter_score, reverse=True)
        candidates = candidates[:tier1_candidates]
    return candidates


def _score_prefilter(
    query_shape: NDArray[np.float64],
    cand_shape: NDArray[np.float64],
    query_sax: NDArray[np.int8],
    config: Config,
    mp_score_val: float | None = None,
) -> float:
    """SAX + Matrix Profile prefilter for tier-1 pruning."""
    cand_sax = sax_transform(
        cand_shape,
        n_segments=config.sax_n_segments,
        alphabet_size=config.sax_alphabet_size,
    )
    mindist = sax_mindist(
        query_sax,
        cand_sax,
        original_length=len(query_shape),
        alphabet_size=config.sax_alphabet_size,
    )
    sax_sim = sax_score(mindist, len(query_shape))
    pearson = score_pearson(query_shape, cand_shape)

    if mp_score_val is not None:
        return 0.4 * sax_sim + 0.4 * mp_score_val + 0.2 * pearson
    return 0.6 * sax_sim + 0.4 * pearson


def _score_cheap_methods(
    query_shape: NDArray[np.float64],
    cand_shape: NDArray[np.float64],
    radius: int,
    active_fields: set[str],
) -> ScoreBreakdown:
    breakdown = ScoreBreakdown()
    if "dtw" in active_fields:
        breakdown.dtw = score_dtw(query_shape, cand_shape, radius)
    if "pearson_warped" in active_fields:
        breakdown.pearson_warped = score_pearson(query_shape, cand_shape)
    return breakdown


def _enrich_tier2(
    candidates: list[CandidateWindow],
    query: NDArray[np.float64],
    history: NDArray[np.float64],
    config: Config,
    active_fields: set[str],
    feature_store=None,
    ds_hash: str = "",
    progress_fn: ProgressCallback | None = None,
) -> None:
    """Run all expensive Tier 2 methods on a shortlist of candidates.

    Concurrency Model:
    Runs computations via a ThreadPoolExecutor. Heavy number-crunching in
    Methods like Koopman and EMD are done in compiled C routines that
    release Python's Global Interpreter Lock (GIL). Multi-threading here
    leads to near-linear performance scaling up to CPU bounds.
    """
    # Pre-normalize query for methods that need specific normalization
    # Allows us to avoid redundant normalization per Thread/Candidate.
    query_bemp = (
        normalize(query, METHOD_NORM_DEFAULTS["bempedelis"])
        if BEMPEDELIS_SCORE_FIELDS & active_fields
        else None
    )
    query_logret = (
        normalize(query, METHOD_NORM_DEFAULTS["koopman"])
        if {"koopman", "wavelet_spectrum", "tda"} & active_fields
        else None
    )
    query_raw = normalize(query, "raw") if "emd" in active_fields else None

    def _enrich_one(candidate: CandidateWindow) -> None:
        """Enrich a single candidate with all Tier 2 methods. Thread-safe."""
        raw = candidate.raw_series
        _wlen = candidate.end_idx - candidate.start_idx

        # --- Bempedelis (Self-Similarity Time Warping) ---
        if BEMPEDELIS_SCORE_FIELDS & active_fields and query_bemp is not None:
            cand_bemp = normalize(raw, METHOD_NORM_DEFAULTS["bempedelis"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import (
                        params_hash as _params_hash,
                    )

                    p_hash = _params_hash(
                        "bempedelis",
                        n_subwindows=config.bempedelis_n_subwindows,
                        n_restarts=config.bempedelis_n_restarts,
                    )
                    # Cache access for Tier 2 prevents recalcs on repeated background scans
                    result_tuple = feature_store.get_or_compute(
                        dataset_hash=ds_hash,
                        window_start=candidate.start_idx,
                        window_length=_wlen,
                        method="bempedelis",
                        params_hash=p_hash,
                        compute_fn=lambda q=query_bemp, c=cand_bemp: bempedelis_match(
                            query=q,
                            candidate=c,
                            n_subwindows=config.bempedelis_n_subwindows,
                            n_restarts=config.bempedelis_n_restarts,
                        ),
                    )
                    _, cand_result, r2, smoothness = result_tuple
                else:
                    _, cand_result, r2, smoothness = bempedelis_match(
                        query=query_bemp,
                        candidate=cand_bemp,
                        n_subwindows=config.bempedelis_n_subwindows,
                        n_restarts=config.bempedelis_n_restarts,
                    )
                candidate.breakdown.bempedelis_r2 = r2
                candidate.breakdown.bempedelis_smoothness = smoothness
                candidate.transform_alpha = cand_result.alpha
                candidate.transform_beta = cand_result.beta
                candidate.transform_r2 = cand_result.power_law_r2
            except (ValueError, Exception):
                pass

        # --- Koopman Operator EDMD ---
        if "koopman" in active_fields and query_logret is not None:
            cand_logret = normalize(raw, METHOD_NORM_DEFAULTS["koopman"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import (
                        params_hash as _params_hash,
                    )

                    p_hash = _params_hash("koopman", dim=8, lag=3, n_modes=8)
                    candidate.breakdown.koopman = feature_store.get_or_compute(
                        dataset_hash=ds_hash,
                        window_start=candidate.start_idx,
                        window_length=_wlen,
                        method="koopman",
                        params_hash=p_hash,
                        compute_fn=lambda q=query_logret, c=cand_logret: koopman_match(
                            q, c
                        ),
                    )
                else:
                    candidate.breakdown.koopman = koopman_match(
                        query_logret, cand_logret
                    )
            except Exception:
                pass

        # --- Wavelet Leaders (Multifractal Formalism) ---
        if "wavelet_spectrum" in active_fields and query_logret is not None:
            cand_logret_w = normalize(raw, METHOD_NORM_DEFAULTS["wavelet"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import (
                        params_hash as _params_hash,
                    )

                    p_hash = _params_hash("wavelet_spectrum")
                    candidate.breakdown.wavelet_spectrum = feature_store.get_or_compute(
                        dataset_hash=ds_hash,
                        window_start=candidate.start_idx,
                        window_length=_wlen,
                        method="wavelet_spectrum",
                        params_hash=p_hash,
                        compute_fn=lambda q=query_logret, c=cand_logret_w: (
                            wavelet_spectrum_score(q, c)
                        ),
                    )
                else:
                    candidate.breakdown.wavelet_spectrum = wavelet_spectrum_score(
                        query_logret,
                        cand_logret_w,
                    )
            except Exception:
                pass

        # --- EMD (Empirical Mode Decomposition) ---
        if "emd" in active_fields and query_raw is not None:
            cand_raw_emd = normalize(raw, METHOD_NORM_DEFAULTS["emd"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import (
                        params_hash as _params_hash,
                    )

                    p_hash = _params_hash("emd")
                    candidate.breakdown.emd = feature_store.get_or_compute(
                        dataset_hash=ds_hash,
                        window_start=candidate.start_idx,
                        window_length=_wlen,
                        method="emd",
                        params_hash=p_hash,
                        compute_fn=lambda q=query_raw, c=cand_raw_emd: emd_score(q, c),
                    )
                else:
                    candidate.breakdown.emd = emd_score(query_raw, cand_raw_emd)
            except Exception:
                pass

        # --- Topological Data Analysis (Persistence Diagrams) ---
        if "tda" in active_fields and query_logret is not None:
            cand_tda = normalize(raw, METHOD_NORM_DEFAULTS["tda"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import (
                        params_hash as _params_hash,
                    )

                    p_hash = _params_hash("tda")
                    candidate.breakdown.tda = feature_store.get_or_compute(
                        dataset_hash=ds_hash,
                        window_start=candidate.start_idx,
                        window_length=_wlen,
                        method="tda",
                        params_hash=p_hash,
                        compute_fn=lambda q=query_logret, c=cand_tda: tda_compare(q, c),
                    )
                else:
                    candidate.breakdown.tda = tda_compare(query_logret, cand_tda)
            except Exception:
                pass

        # --- Transfer Entropy (Information Theory) ---
        if "transfer_entropy" in active_fields:
            # TE measures predictive info from match -> forward region
            end_idx = candidate.end_idx
            forward_len = config.forward_bars
            if end_idx + forward_len <= len(history):
                forward = history[end_idx : end_idx + forward_len]
                try:
                    candidate.breakdown.transfer_entropy = te_score(raw, forward)
                except Exception:
                    pass

        # --- Regime tag ---
        try:
            candidate.regime = tag_regime(raw)
        except Exception:
            candidate.regime = None

    total = len(candidates)
    _completed = [0]  # mutable counter for closure

    def _enrich_and_report(candidate: CandidateWindow) -> None:
        _enrich_one(candidate)
        _completed[0] += 1
        if progress_fn is not None:
            progress_fn(
                ProgressEvent(
                    stage="tier2",
                    completed=_completed[0],
                    total=total,
                    message=f"enriched {_completed[0]}/{total} candidates",
                )
            )

    if total > 1:
        # Use threads — numpy/scipy release the GIL during computation
        # Bound arbitrary max_workers to 4 as higher concurrent memory loads
        # may hit typical machine constraints.
        n_threads = min(4, total)
        with ThreadPoolExecutor(max_workers=n_threads) as executor:
            list(executor.map(_enrich_and_report, candidates))
    else:
        for candidate in candidates:
            _enrich_and_report(candidate)


def _resample(series: NDArray[np.float64], target_len: int) -> NDArray[np.float64]:
    """Resample a 1D series to a different length via linear interpolation."""
    if len(series) == target_len:
        return series
    x_old = np.linspace(0, 1, len(series))
    x_new = np.linspace(0, 1, target_len)
    return np.interp(x_new, x_old, series)
