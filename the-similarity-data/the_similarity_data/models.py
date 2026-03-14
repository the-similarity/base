from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetSpec:
    asset_class: str
    symbol: str
    timeframe: str
    source: str
    source_symbol: str
    exchange: str | None = None
    lookback_days: int = 365
    enabled: bool = True

    @property
    def relative_path(self) -> Path:
        return Path("data") / self.asset_class / self.symbol / f"{self.timeframe}.parquet"


@dataclass(frozen=True)
class RefreshResult:
    asset_class: str
    symbol: str
    timeframe: str
    source: str
    path: Path
    start_timestamp: str | None
    end_timestamp: str | None
    row_count: int
    last_updated_at: str
