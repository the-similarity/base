from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np

import the_similarity
from the_similarity.contracts.api import (
    ConfidenceBreakdownItem,
    DashboardDataResponse,
    ForecastBands,
    ForecastResponse,
    HeroContent,
    MatchCard,
    MatchResultResponse,
    ModuleCard,
    RangeView,
    ScoreBreakdownResponse,
    SearchRequest,
    SearchResponse,
)


def create_series(
    length: int,
    start: float,
    slope: float,
    amplitude: float,
    frequency: float,
    phase: float,
) -> list[float]:
    values = []
    for index in range(length):
        wave = np.sin(index * frequency + phase) * amplitude
        harmonic = np.cos(index * frequency * 0.55 + phase * 0.5) * amplitude * 0.32
        values.append(round(start + index * slope + wave + harmonic, 2))
    return values


def build_forecast(
    anchor: float,
    length: int,
    slope: float,
    amplitude: float,
    phase: float,
) -> ForecastBands:
    median = []
    for index in range(length):
        point = index + 1
        value = (
            anchor
            + point * slope
            + np.sin(point * 0.48 + phase) * amplitude
            + np.cos(point * 0.24 + phase) * amplitude * 0.35
        )
        median.append(round(value, 2))

    p10 = [round(value - 2.4 - index * 0.18, 2) for index, value in enumerate(median)]
    p90 = [round(value + 2.4 + index * 0.22, 2) for index, value in enumerate(median)]
    return ForecastBands(p10=p10, p50=median, p90=p90)


def build_range_view(
    label: str,
    query_config: tuple[int, float, float, float, float, float],
    match_config: tuple[int, float, float, float, float, float],
    forecast_config: tuple[int, float, float, float],
) -> RangeView:
    query = create_series(*query_config)
    best_match = create_series(*match_config)
    anchor = query[-1]
    forecast = build_forecast(anchor, *forecast_config)
    return RangeView(label=label, query=query, best_match=best_match, forecast=forecast)


def get_dashboard_payload() -> DashboardDataResponse:
    return DashboardDataResponse(
        data_source="api",
        hero=HeroContent(
            eyebrow="The Similarity dashboard",
            title="Pattern search, confidence scoring, and forecast cones in one research desk.",
            description=(
                "This backend payload mirrors the future split-repo contract and is served "
                "from FastAPI instead of local mock modules."
            ),
            badges=["FastAPI", "Pydantic", "Contract-first"],
        ),
        ranges=["1D", "1W", "1M", "3M", "1Y", "ALL"],
        default_range="3M",
        views={
            "1D": build_range_view(
                "Intraday scan",
                (24, 101.6, 0.28, 1.25, 0.54, 0.6),
                (24, 100.9, 0.26, 1.1, 0.56, 0.75),
                (8, 0.21, 0.7, 0.8),
            ),
            "1W": build_range_view(
                "Weekly shape",
                (26, 98.8, 0.42, 1.6, 0.42, 0.25),
                (26, 98.1, 0.39, 1.44, 0.44, 0.36),
                (8, 0.34, 0.86, 0.55),
            ),
            "1M": build_range_view(
                "Monthly analog",
                (28, 96.3, 0.55, 2.1, 0.33, 0.2),
                (28, 95.6, 0.5, 1.9, 0.34, 0.28),
                (10, 0.46, 1.05, 0.45),
            ),
            "3M": build_range_view(
                "Quarterly setup",
                (30, 92.4, 0.66, 2.45, 0.26, 0.18),
                (30, 91.7, 0.62, 2.2, 0.25, 0.26),
                (12, 0.59, 1.18, 0.38),
            ),
            "1Y": build_range_view(
                "Annual structure",
                (32, 84.2, 0.94, 3.3, 0.19, 0.18),
                (32, 83.5, 0.9, 2.95, 0.18, 0.26),
                (12, 0.84, 1.45, 0.34),
            ),
            "ALL": build_range_view(
                "Full history",
                (34, 76.8, 1.12, 4.2, 0.14, 0.16),
                (34, 75.9, 1.08, 3.8, 0.13, 0.24),
                (14, 1.06, 1.72, 0.28),
            ),
        },
        top_matches=[
            MatchCard(
                label="Primary analog",
                window="2019-05-03 -> 2019-08-14",
                score=86.4,
                delta=5.8,
                method="DTW + Pearson",
                regime="trending_up",
            ),
            MatchCard(
                label="Volatility twin",
                window="2020-10-19 -> 2021-01-28",
                score=82.1,
                delta=3.2,
                method="Wavelet",
                regime="high_vol",
            ),
            MatchCard(
                label="Compression setup",
                window="2018-02-12 -> 2018-05-25",
                score=78.7,
                delta=-1.4,
                method="Bempedelis",
                regime="mean_reverting",
            ),
            MatchCard(
                label="Late cycle echo",
                window="2023-03-11 -> 2023-06-20",
                score=74.2,
                delta=6.9,
                method="Koopman",
                regime="trending_up",
            ),
        ],
        architecture_cards=[
            ModuleCard(
                module="io/loader.py",
                responsibility="Data ingestion from CSV, parquet, DataFrame, dict, and array inputs.",
                scale="Swap for streaming loader later",
            ),
            ModuleCard(
                module="core/windower.py",
                responsibility="Sliding window generation and multi-scale candidate indexing.",
                scale="Chunkable and memory-bound",
            ),
            ModuleCard(
                module="core/matcher.py",
                responsibility="Pipeline orchestration from query normalization to ranked candidates.",
                scale="Delegates to independent methods",
            ),
            ModuleCard(
                module="core/scorer.py",
                responsibility="Confidence aggregation and method score normalization into a 0-100 rank.",
                scale="Pure math, easy to parallelize",
            ),
            ModuleCard(
                module="core/projector.py",
                responsibility="Weighted percentile forecast cone from post-match forward paths.",
                scale="Stateless projection surface",
            ),
            ModuleCard(
                module="methods/",
                responsibility="Independent scoring engines like DTW, Bempedelis, Wavelet, and Koopman.",
                scale="Worker-friendly extraction path",
            ),
        ],
        pipeline_steps=[
            "load() -> TimeSeries",
            "normalize(query)",
            "sliding_windows(history)",
            "tier 1 pre-filters",
            "tier 2 method scoring",
            "compute_confidence()",
            "project(matches, history)",
        ],
        base_breakdown=[
            ConfidenceBreakdownItem(label="DTW", value=0.91),
            ConfidenceBreakdownItem(label="Pearson", value=0.84),
            ConfidenceBreakdownItem(label="Bempedelis", value=0.71),
            ConfidenceBreakdownItem(label="Wavelet", value=0.66),
            ConfidenceBreakdownItem(label="Koopman", value=0.58),
            ConfidenceBreakdownItem(label="EMD", value=0.42),
        ],
    )


def _to_list(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (list, tuple)):
        return [_to_list(item) for item in value]
    return value


def build_score_breakdown_response(match) -> ScoreBreakdownResponse:
    breakdown = match.score_breakdown
    return ScoreBreakdownResponse(
        bempedelis_r2=breakdown.bempedelis_r2,
        bempedelis_smoothness=breakdown.bempedelis_smoothness,
        koopman=breakdown.koopman,
        wavelet_spectrum=breakdown.wavelet_spectrum,
        emd=breakdown.emd,
        tda=breakdown.tda,
        dtw=breakdown.dtw,
        pearson_warped=breakdown.pearson_warped,
        transfer_entropy=breakdown.transfer_entropy,
    )


def build_match_result_response(match) -> MatchResultResponse:
    return MatchResultResponse(
        start_idx=match.start_idx,
        end_idx=match.end_idx,
        start_date=match.start_date,
        end_date=match.end_date,
        confidence_score=match.confidence_score,
        score_breakdown=build_score_breakdown_response(match),
        matched_series=_to_list(match.matched_series),
        transform_alpha=_to_list(match.transform_alpha),
        transform_beta=_to_list(match.transform_beta),
        transform_r2=match.transform_r2,
        koopman_eigenvalues=_to_list(match.koopman_eigenvalues),
        fractal_spectrum=_to_list(match.fractal_spectrum),
        persistence_diagram=_to_list(match.persistence_diagram),
        forward_window=_to_list(match.forward_window),
    )


def build_forecast_response(forecast) -> ForecastResponse:
    return ForecastResponse(
        bars=forecast.bars,
        percentiles=forecast.percentiles,
        curves={key: _to_list(value) for key, value in forecast.curves.items()},
        all_paths=_to_list(forecast.all_paths),
        weights=_to_list(forecast.weights),
    )


def execute_search(request: SearchRequest) -> SearchResponse:
    query_values = np.asarray(request.query_values, dtype=np.float64)
    history_values = np.asarray(request.history_values, dtype=np.float64)

    search_kwargs: dict[str, Any] = {}
    if request.normalization is not None:
        search_kwargs["normalization"] = request.normalization
    if request.stride is not None:
        search_kwargs["stride"] = request.stride
    if request.tier1_candidates is not None:
        search_kwargs["tier1_candidates"] = request.tier1_candidates
    if request.tier2_candidates is not None:
        search_kwargs["tier2_candidates"] = request.tier2_candidates
    if request.active_methods:
        search_kwargs["active_methods"] = request.active_methods

    results = the_similarity.search(
        query=query_values,
        history=history_values,
        top_k=request.top_k,
        weights=request.weights or None,
        exclude_self=request.exclude_self,
        **search_kwargs,
    )

    forecast = the_similarity.project(
        matches=results,
        history=history_values,
        forward_bars=request.forward_bars,
        percentiles=request.percentiles or None,
    )

    return SearchResponse(
        query_values=_to_list(query_values),
        matches=[build_match_result_response(match) for match in results.matches],
        forecast=build_forecast_response(forecast),
    )
