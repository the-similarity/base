from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.stats import pearsonr

from the_similarity.config import Config
from the_similarity.core.normalizer import METHOD_NORM_DEFAULTS, normalize
from the_similarity.core.regime import tag_regime
from the_similarity.core.scorer import MatchResult, ScoreBreakdown, compute_confidence
from the_similarity.core.windower import sliding_windows, window_indices
from the_similarity.methods.bempedelis import bempedelis_match
from the_similarity.methods.dtw_matcher import dtw_distance, dtw_score
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

# Method groupings for tiered execution
CHEAP_SCORE_FIELDS = {"dtw", "pearson_warped"}
BEMPEDELIS_SCORE_FIELDS = {"bempedelis_r2", "bempedelis_smoothness"}
TIER2_SCORE_FIELDS = {
    "koopman", "wavelet_spectrum", "emd", "tda", "transfer_entropy",
}
ALL_SCORE_FIELDS = CHEAP_SCORE_FIELDS | BEMPEDELIS_SCORE_FIELDS | TIER2_SCORE_FIELDS


@dataclass
class CandidateWindow:
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
    """Pearson correlation mapped to [0, 1]."""
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
) -> list[MatchResult]:
    """Run the full tiered matching pipeline.

    1. Generate multi-scale candidate windows
    2. SAX + MASS + Pearson prefilter -> tier1_candidates survivors
    3. Score cheap methods (DTW, Pearson) on all tier-1 survivors
    4. Select tier2_candidates best -> enrich with all expensive methods
       (Bempedelis, Koopman, Wavelet, EMD, TDA, Transfer Entropy)
    5. Regime-tag each result
    6. Return top_k by final composite confidence
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

    radius = config.dtw_sakoe_chiba_radius
    if radius is None:
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
        return []

    # --- Tier 1: Cheap methods on all survivors ---
    base_fields = [f for f in config.active_methods if f in CHEAP_SCORE_FIELDS]
    base_config = Config(
        weights=config.weights.copy(),
        active_methods=base_fields,
    )

    for candidate in candidates:
        candidate.breakdown = _score_cheap_methods(
            query_shape=query_shape,
            cand_shape=candidate.shape_series,
            radius=radius,
            active_fields=active_fields,
        )
        if base_fields:
            candidate.base_rank_score = compute_confidence(candidate.breakdown, base_config)
        else:
            candidate.base_rank_score = candidate.prefilter_score * 100.0
        candidate.confidence_score = compute_confidence(candidate.breakdown, config)

    # --- Tier 2: Expensive methods on top candidates ---
    tier2_fields = (BEMPEDELIS_SCORE_FIELDS | TIER2_SCORE_FIELDS) & active_fields
    if tier2_fields:
        rerank_count = config.tier2_candidates
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
        )
        for candidate in rerank_pool:
            candidate.confidence_score = compute_confidence(candidate.breakdown, config)

    # --- Build results ---
    candidates.sort(key=lambda c: c.confidence_score, reverse=True)
    results: list[MatchResult] = []
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
            )
        )
    return results


def _collect_candidates(
    query: NDArray[np.float64],
    history: NDArray[np.float64],
    query_shape: NDArray[np.float64],
    config: Config,
    exclude_query_region: tuple[int, int] | None,
) -> list[CandidateWindow]:
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
            if exclude_query_region is not None:
                query_start, query_end = exclude_query_region
                if start < query_end and end > query_start:
                    continue

            raw_window = windows[index]
            shape_window = normalize(raw_window, config.normalization)
            if scale != 1.0:
                shape_window = _resample(shape_window, query_shape_len)

            mp_score_val: float | None = None
            if mp_scores is not None and scale == 1.0 and start < len(mp_scores):
                mp_score_val = float(mp_scores[start])

            prefilter = _score_prefilter(
                query_shape, shape_window, query_sax, config,
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
        query_sax, cand_sax,
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
) -> None:
    """Run all expensive Tier 2 methods on a shortlist of candidates."""
    # Pre-normalize query for methods that need specific normalization
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
    query_raw = (
        normalize(query, "raw")
        if "emd" in active_fields
        else None
    )

    for candidate in candidates:
        raw = candidate.raw_series
        _wlen = candidate.end_idx - candidate.start_idx

        # --- Bempedelis ---
        if BEMPEDELIS_SCORE_FIELDS & active_fields and query_bemp is not None:
            cand_bemp = normalize(raw, METHOD_NORM_DEFAULTS["bempedelis"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import params_hash as _params_hash
                    p_hash = _params_hash(
                        "bempedelis",
                        n_subwindows=config.bempedelis_n_subwindows,
                        n_restarts=config.bempedelis_n_restarts,
                    )
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

        # --- Koopman EDMD ---
        if "koopman" in active_fields and query_logret is not None:
            cand_logret = normalize(raw, METHOD_NORM_DEFAULTS["koopman"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import params_hash as _params_hash
                    p_hash = _params_hash("koopman", dim=8, lag=3, n_modes=8)
                    candidate.breakdown.koopman = feature_store.get_or_compute(
                        dataset_hash=ds_hash,
                        window_start=candidate.start_idx,
                        window_length=_wlen,
                        method="koopman",
                        params_hash=p_hash,
                        compute_fn=lambda q=query_logret, c=cand_logret: koopman_match(q, c),
                    )
                else:
                    candidate.breakdown.koopman = koopman_match(query_logret, cand_logret)
            except Exception:
                pass

        # --- Wavelet Leaders ---
        if "wavelet_spectrum" in active_fields and query_logret is not None:
            cand_logret_w = normalize(raw, METHOD_NORM_DEFAULTS["wavelet"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import params_hash as _params_hash
                    p_hash = _params_hash("wavelet_spectrum")
                    candidate.breakdown.wavelet_spectrum = feature_store.get_or_compute(
                        dataset_hash=ds_hash,
                        window_start=candidate.start_idx,
                        window_length=_wlen,
                        method="wavelet_spectrum",
                        params_hash=p_hash,
                        compute_fn=lambda q=query_logret, c=cand_logret_w: wavelet_spectrum_score(q, c),
                    )
                else:
                    candidate.breakdown.wavelet_spectrum = wavelet_spectrum_score(
                        query_logret, cand_logret_w,
                    )
            except Exception:
                pass

        # --- EMD ---
        if "emd" in active_fields and query_raw is not None:
            cand_raw_emd = normalize(raw, METHOD_NORM_DEFAULTS["emd"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import params_hash as _params_hash
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

        # --- TDA ---
        if "tda" in active_fields and query_logret is not None:
            cand_tda = normalize(raw, METHOD_NORM_DEFAULTS["tda"])
            try:
                if feature_store is not None:
                    from the_similarity.core.feature_store import params_hash as _params_hash
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

        # --- Transfer Entropy ---
        if "transfer_entropy" in active_fields:
            # TE measures predictive info from match -> forward region
            end_idx = candidate.end_idx
            forward_len = config.forward_bars
            if end_idx + forward_len <= len(history):
                forward = history[end_idx: end_idx + forward_len]
                try:
                    candidate.breakdown.transfer_entropy = te_score(raw, forward)
                except Exception:
                    pass

        # --- Regime tag ---
        try:
            candidate.regime = tag_regime(raw)
        except Exception:
            candidate.regime = None


def _resample(series: NDArray[np.float64], target_len: int) -> NDArray[np.float64]:
    """Resample a 1D series to a different length via linear interpolation."""
    if len(series) == target_len:
        return series
    x_old = np.linspace(0, 1, len(series))
    x_new = np.linspace(0, 1, target_len)
    return np.interp(x_new, x_old, series)
