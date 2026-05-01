"""
Pydantic response models for data integration endpoints.

These models define the HTTP response shapes for catalog listing,
time series retrieval, and OHLC data endpoints. They are separate from
the contracts in `the_similarity.contracts.api` because they belong to
the API layer (not the engine library).

AI AGENT NOTES:
- CatalogItem mirrors the structure in manifests/catalog.json.
- DatasetSeriesResponse returns a single column (default "close") as a
  flat list, suitable for the search pipeline's `history_values` input.
- OhlcResponse returns all four OHLC columns plus volume and dates,
  suitable for candlestick chart rendering in the frontend.
- `row_count` is included for pagination/display purposes; it always
  equals len(values) or len(close).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CatalogItem(BaseModel):
    """A single dataset entry in the data warehouse catalog.

    Mirrors the structure stored in manifests/catalog.json.
    Each item identifies one symbol+timeframe combination from one source.

    Metadata fields (`source`, `start_timestamp`, `end_timestamp`,
    `row_count`, `last_updated_at`, `frequency`) are surfaced to the UI
    so the dataset picker can render rich per-item cards (source badge,
    date range, staleness indicator). They are all OPTIONAL from a
    consumer's perspective: older clients that don't read them still
    receive a valid payload, and newer clients must tolerate their
    absence (e.g. for a freshly-ingested dataset whose manifest entry
    hasn't been rewritten yet).

    `frequency` is a human-readable rendering of `timeframe` (e.g.
    ``"1 hour"`` for ``"1h"``). It is derived on the server so every
    consumer sees the same string; the frontend should NEVER re-parse
    the short timeframe code into English on its own.
    """
    asset_class: str       # e.g., "equity", "crypto", "forex"
    symbol: str            # e.g., "AAPL", "BTCUSD"
    timeframe: str         # e.g., "1h", "1d", "1w"
    source: str            # e.g., "polygon", "binance", "manual"
    path: str              # Relative parquet file path within data/
    start_timestamp: str | None = None    # ISO timestamp of first bar
    end_timestamp: str | None = None      # ISO timestamp of last bar
    row_count: int = 0                    # Total number of bars
    last_updated_at: str | None = None    # When the data was last refreshed
    # Human-readable frequency derived from ``timeframe`` (e.g. "1 hour").
    # Kept optional for backwards compatibility: pre-metadata clients
    # simply ignore it, and the server falls back to ``timeframe`` itself
    # when the code is unrecognised.
    frequency: str | None = None


class CatalogResponse(BaseModel):
    """Wrapper for the full dataset catalog response."""
    datasets: list[CatalogItem]  # All datasets that have valid parquet files


class DatasetSeriesResponse(BaseModel):
    """Response for single-column time series requests.

    Used by the search UI to populate the history_values field.
    """
    dataset_id: str                              # e.g., "equity/AAPL/1d"
    # ``source_timeframe`` is the parquet/native timeframe from the URL.
    # ``timeframe`` is the effective timeframe returned to the client. They
    # differ when the API generates coarser candles at request time.
    source_timeframe: str | None = None
    timeframe: str | None = None
    column: str                                  # Which column was extracted
    values: list[float]                          # The price/value array
    dates: list[str] = Field(default_factory=list)  # ISO timestamps, if available
    row_count: int = 0                           # len(values)


class OhlcResponse(BaseModel):
    """Response for OHLC candlestick data requests.

    Used by the frontend to render candlestick charts.
    All four OHLC arrays are always the same length; volume may be empty
    for sources that don't provide it.
    """
    dataset_id: str
    source_timeframe: str | None = None
    timeframe: str | None = None
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float] = Field(default_factory=list)   # Empty if not available
    dates: list[str] = Field(default_factory=list)       # ISO timestamps
    row_count: int = 0                                   # len(close)
