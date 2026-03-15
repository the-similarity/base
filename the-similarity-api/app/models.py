"""API models for data integration endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    asset_class: str
    symbol: str
    timeframe: str
    source: str
    path: str
    start_timestamp: str | None = None
    end_timestamp: str | None = None
    row_count: int = 0
    last_updated_at: str | None = None


class CatalogResponse(BaseModel):
    datasets: list[CatalogItem]


class DatasetSeriesResponse(BaseModel):
    dataset_id: str
    column: str
    values: list[float]
    dates: list[str] = Field(default_factory=list)
    row_count: int = 0
