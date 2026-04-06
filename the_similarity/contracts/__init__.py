"""
Pydantic API contracts for external service boundaries.

This package re-exports all Pydantic models that define the JSON shape of
API requests and responses. These models are the single source of truth
for the API contract between the Python backend and TypeScript frontend.

AI AGENT NOTES:
- All models live in `contracts/api.py`. This __init__.py just re-exports them.
- When adding a new model, add it in api.py, import it here, and add to __all__.
- The TypeScript counterparts live in `the-similarity-app/lib/types.ts`.
- Models use camelCase JSON aliases (see ApiContract base class in api.py).
"""

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

__all__ = [
    # Dashboard layout contracts
    "ConfidenceBreakdownItem",
    "DashboardDataResponse",
    "ForecastBands",
    "ForecastResponse",
    "HeroContent",
    "MatchCard",
    "MatchResultResponse",
    "ModuleCard",
    "RangeView",
    # Search pipeline contracts
    "ScoreBreakdownResponse",
    "SearchRequest",
    "SearchResponse",
]
