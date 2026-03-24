"""HTTP-facing contracts for the future The Similarity API service.

These models are the canonical boundary types for a split-repo setup:
- the API repo can validate and serialize them with pydantic
- the frontend repo can mirror these shapes in TypeScript
"""

from __future__ import annotations

import warnings
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ApiContract(BaseModel):
    """Base model for all external API payloads."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


RangeKey = Literal["1D", "1W", "1M", "3M", "1Y", "ALL"]
DataSource = Literal["mock", "api"]


class HeroContent(ApiContract):
    eyebrow: str
    title: str
    description: str
    badges: list[str] = Field(default_factory=list)


class ForecastBands(ApiContract):
    p10: list[float] = Field(default_factory=list)
    p50: list[float] = Field(default_factory=list)
    p90: list[float] = Field(default_factory=list)


class RangeView(ApiContract):
    label: str
    query: list[float] = Field(default_factory=list)
    best_match: list[float] = Field(default_factory=list)
    forecast: ForecastBands


class MatchCard(ApiContract):
    label: str
    window: str
    score: Annotated[float, Field(ge=0, le=100)]
    delta: float
    method: str
    regime: str


class ModuleCard(ApiContract):
    module: str
    responsibility: str
    scale: str


class ConfidenceBreakdownItem(ApiContract):
    label: str
    value: Annotated[float, Field(ge=0, le=1)]


class DashboardDataResponse(ApiContract):
    data_source: DataSource
    hero: HeroContent
    ranges: list[RangeKey]
    default_range: RangeKey
    views: dict[RangeKey, RangeView]
    top_matches: list[MatchCard]
    architecture_cards: list[ModuleCard]
    pipeline_steps: list[str]
    base_breakdown: list[ConfidenceBreakdownItem]


class ScoreBreakdownResponse(ApiContract):
    bempedelis_r2: Annotated[float, Field(ge=0, le=1)] = 0.0
    bempedelis_smoothness: Annotated[float, Field(ge=0, le=1)] = 0.0
    koopman: Annotated[float, Field(ge=0, le=1)] = 0.0
    wavelet_spectrum: Annotated[float, Field(ge=0, le=1)] = 0.0
    emd: Annotated[float, Field(ge=0, le=1)] = 0.0
    tda: Annotated[float, Field(ge=0, le=1)] = 0.0
    dtw: Annotated[float, Field(ge=0, le=1)] = 0.0
    pearson_warped: Annotated[float, Field(ge=0, le=1)] = 0.0
    transfer_entropy: Annotated[float, Field(ge=0, le=1)] = 0.0


class MatchResultResponse(ApiContract):
    start_idx: Annotated[int, Field(ge=0)]
    end_idx: Annotated[int, Field(gt=0)]
    start_date: str | None = None
    end_date: str | None = None
    confidence_score: Annotated[float, Field(ge=0, le=100)]
    score_breakdown: ScoreBreakdownResponse
    matched_series: list[float] | None = None
    transform_alpha: list[float] | None = None
    transform_beta: list[float] | None = None
    transform_r2: Annotated[float, Field(ge=0, le=1)] = 0.0
    koopman_eigenvalues: list[float] | None = None
    fractal_spectrum: list[float] | None = None
    persistence_diagram: list[list[float]] | None = None
    forward_window: list[float] | None = None


class ForecastResponse(ApiContract):
    bars: Annotated[int, Field(ge=1)]
    percentiles: list[int] = Field(default_factory=list)
    curves: dict[int, list[float]] = Field(default_factory=dict)
    all_paths: list[list[float]] = Field(default_factory=list)
    weights: list[float] = Field(default_factory=list)


class SearchRequest(ApiContract):
    query_values: Annotated[list[float], Field(min_length=2)]
    history_values: Annotated[list[float], Field(min_length=2)]
    top_k: Annotated[int, Field(ge=1, le=200)] = 20
    forward_bars: Annotated[int, Field(ge=1, le=500)] = 50
    exclude_self: bool = True
    normalization: str | None = None
    stride: Annotated[int | None, Field(ge=1)] = None
    tier1_candidates: Annotated[int | None, Field(ge=1, le=5000)] = None
    tier2_candidates: Annotated[int | None, Field(ge=1, le=1000)] = None
    active_methods: list[str] = Field(default_factory=list)
    percentiles: list[int] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)


class SearchResponse(ApiContract):
    query_values: list[float]
    matches: list[MatchResultResponse]
    forecast: ForecastResponse | None = None
