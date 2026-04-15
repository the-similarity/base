"""
Canonical API contract models (Pydantic) for the_similarity HTTP service.

These models define the exact JSON shapes that cross the API boundary between
the Python backend (FastAPI) and the TypeScript frontend (Next.js). They are
the *single source of truth* for the API schema.

AI AGENT NOTES:
- Every model inherits from `ApiContract`, which configures camelCase aliasing.
  This means JSON keys are camelCase ("startIdx") but Python attribute names
  are snake_case ("start_idx"). Both forms work for input.
- Models use `extra="forbid"` to reject unknown fields — this catches typos
  in client payloads early.
- Field constraints (ge=0, le=100, min_length=2) are validated by Pydantic.
  FastAPI returns 422 for violations.
- When adding a new scoring method:
  1. Add the field to `ScoreBreakdownResponse` with Annotated[float, Field(ge=0, le=1)].
  2. Add it to `core/scorer.py` → ScoreBreakdown (the engine-side counterpart).
- The `SearchRequest` model supports both raw values (query_values) and dataset
  references (query_dataset_id) via the services layer — the contract itself
  only exposes the raw form; dataset resolution is handled in services.py.
- TypeScript mirror types live in `the-similarity-app/lib/types.ts`.
"""

from __future__ import annotations

import warnings
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Suppress pydantic v2 migration warnings that clutter the console.
# Safe to remove once all models have been validated under v2.
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")


def to_camel(value: str) -> str:
    """Convert snake_case to camelCase for JSON field aliasing.

    Example: "start_date" → "startDate"
    The first segment stays lowercase (camelCase, not PascalCase).
    """
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ApiContract(BaseModel):
    """Base model for all external API payloads.

    Configures:
    - alias_generator: auto-generates camelCase JSON keys from snake_case attrs
    - populate_by_name: allows both snake_case and camelCase for input
    - extra="forbid": rejects unknown fields to catch client-side typos
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


# --- Type aliases for range selector ---
# These are exhaustive literal types for the dashboard's time range picker.
RangeKey = Literal["1D", "1W", "1M", "3M", "1Y", "ALL"]
DataSource = Literal["mock", "api"]


# ---------------------------------------------------------------------------
# Dashboard layout contracts
# ---------------------------------------------------------------------------


class HeroContent(ApiContract):
    """Dashboard hero section content (title, description, badges)."""

    eyebrow: str  # Small label above title
    title: str  # Main headline
    description: str  # Paragraph below title
    badges: list[str] = Field(default_factory=list)  # Tech stack badges


class ForecastBands(ApiContract):
    """Simplified forecast bands for the dashboard widget (P10/P50/P90 only)."""

    p10: list[float] = Field(default_factory=list)  # 10th percentile (bearish)
    p50: list[float] = Field(default_factory=list)  # Median projection
    p90: list[float] = Field(default_factory=list)  # 90th percentile (bullish)


class RangeView(ApiContract):
    """One time range's worth of dashboard data (query + match + forecast)."""

    label: str  # Human-readable label
    query: list[float] = Field(default_factory=list)  # Query pattern values
    best_match: list[float] = Field(default_factory=list)  # Top match values
    forecast: ForecastBands  # Forward projection bands


class MatchCard(ApiContract):
    """Summary card for one match in the dashboard top-matches widget."""

    label: str  # Descriptive nickname
    window: str  # Date range (e.g., "2019-05-03 -> 2019-08-14")
    score: Annotated[float, Field(ge=0, le=100)]  # Composite confidence score
    delta: float  # Forward return after match (%)
    method: str  # Dominant scoring method
    regime: str  # Market regime label


class ModuleCard(ApiContract):
    """Architecture diagram card for the dashboard."""

    module: str  # File path (e.g., "core/matcher.py")
    responsibility: str  # One-line description
    scale: str  # Scalability note


class ConfidenceBreakdownItem(ApiContract):
    """One method's contribution to the confidence score."""

    label: str  # Method display name
    value: Annotated[float, Field(ge=0, le=1)]  # Score in [0, 1]


class DashboardDataResponse(ApiContract):
    """Complete response payload for the dashboard landing page.

    This is a pre-assembled payload designed for the frontend to render
    without additional API calls. It contains chart data, match cards,
    architecture info, and pipeline visualization data.
    """

    data_source: DataSource  # "mock" or "api"
    hero: HeroContent  # Hero section content
    ranges: list[RangeKey]  # Available range options
    default_range: RangeKey  # Initially selected range
    views: dict[RangeKey, RangeView]  # Chart data per range
    top_matches: list[MatchCard]  # Top-N match summary cards
    architecture_cards: list[ModuleCard]  # Architecture diagram cards
    pipeline_steps: list[str]  # Pipeline step descriptions
    base_breakdown: list[ConfidenceBreakdownItem]  # Example score breakdown


# ---------------------------------------------------------------------------
# Search pipeline contracts
# ---------------------------------------------------------------------------


class ScoreBreakdownResponse(ApiContract):
    """Wire-format mirror of core/scorer.py → ScoreBreakdown.

    Each field is a per-method similarity score in [0, 1].
    These must stay in sync with the engine's ScoreBreakdown dataclass.
    """

    bempedelis_r2: Annotated[float, Field(ge=0, le=1)] = 0.0  # Power law R²
    bempedelis_smoothness: Annotated[float, Field(ge=0, le=1)] = (
        0.0  # Scaling smoothness
    )
    koopman: Annotated[float, Field(ge=0, le=1)] = 0.0  # Eigenvalue match
    wavelet_spectrum: Annotated[float, Field(ge=0, le=1)] = 0.0  # f(α) distance
    emd: Annotated[float, Field(ge=0, le=1)] = 0.0  # Multi-scale match
    tda: Annotated[float, Field(ge=0, le=1)] = 0.0  # Persistence distance
    dtw: Annotated[float, Field(ge=0, le=1)] = 0.0  # Shape distance
    pearson_warped: Annotated[float, Field(ge=0, le=1)] = 0.0  # Post-warp correlation
    transfer_entropy: Annotated[float, Field(ge=0, le=1)] = (
        0.0  # Predictive information
    )


class MatchResultResponse(ApiContract):
    """Wire-format mirror of core/scorer.py → MatchResult.

    Contains the match location, scores, and diagnostic artifacts.
    Numpy arrays are serialized to plain lists for JSON transport.
    """

    start_idx: Annotated[int, Field(ge=0)]  # Window start in history
    end_idx: Annotated[int, Field(gt=0)]  # Window end (exclusive)
    start_date: str | None = None  # ISO date, if available
    end_date: str | None = None
    confidence_score: Annotated[float, Field(ge=0, le=100)]  # Composite 0–100
    score_breakdown: ScoreBreakdownResponse  # Per-method sub-scores
    matched_series: list[float] | None = None  # Raw matched values
    transform_alpha: list[float] | None = None  # Bempedelis α(t)
    transform_beta: list[float] | None = None  # Bempedelis β(t)
    transform_r2: Annotated[float, Field(ge=0, le=1)] = 0.0  # Combined R²
    koopman_eigenvalues: list[float] | None = None  # Complex eigenvalues
    fractal_spectrum: list[float] | None = None  # f(α) points
    persistence_diagram: list[list[float]] | None = None  # Birth-death pairs
    forward_window: list[float] | None = None  # Post-match returns


class ForecastResponse(ApiContract):
    """Wire-format mirror of core/projector.py → Forecast.

    Contains the percentile curves and all individual projection paths.
    """

    bars: Annotated[int, Field(ge=1)]  # Forward horizon
    percentiles: list[int] = Field(default_factory=list)  # Which Ps computed
    curves: dict[int, list[float]] = Field(default_factory=dict)  # {P: values}
    all_paths: list[list[float]] = Field(default_factory=list)  # All match paths
    weights: list[float] = Field(default_factory=list)  # Normalized weights


class SearchRequest(ApiContract):
    """Inbound search request from the frontend or API client.

    The two required fields are query_values and history_values.
    All other fields are optional overrides that default to
    Config values in the engine.
    """

    query_values: Annotated[list[float], Field(min_length=2)]  # Pattern to search for
    history_values: Annotated[list[float], Field(min_length=2)]  # History to search in
    top_k: Annotated[int, Field(ge=1, le=200)] = 20  # Return top N matches
    forward_bars: Annotated[int, Field(ge=1, le=500)] = 50  # Forecast horizon
    exclude_self: bool = True  # Skip self-match
    normalization: str | None = None  # Override default norm
    stride: Annotated[int | None, Field(ge=1)] = None  # Window step override
    tier1_candidates: Annotated[int | None, Field(ge=1, le=5000)] = (
        None  # Pre-filter depth
    )
    tier2_candidates: Annotated[int | None, Field(ge=1, le=1000)] = (
        None  # Enrichment depth
    )
    active_methods: list[str] = Field(default_factory=list)  # Scoring methods to use
    percentiles: list[int] = Field(default_factory=list)  # Forecast percentiles
    weights: dict[str, float] = Field(default_factory=dict)  # Method weight overrides


class SearchResponse(ApiContract):
    """Outbound search response containing matches and forecast."""

    query_values: list[float]  # Echo of input query (normalized)
    matches: list[MatchResultResponse]  # Ranked matches
    forecast: ForecastResponse | None = None  # Forward projection
