from __future__ import annotations

from pathlib import Path

from the_similarity_data.config import default_manifest_path, repo_root
from the_similarity_data.fetchers import (
    CryptoCcxtFetcher,
    ForexTwelveDataFetcher,
    MarketYFinanceFetcher,
    StooqDailyFetcher,
)
from the_similarity_data.manifest import update_manifest
from the_similarity_data.models import DatasetSpec, RefreshResult
from the_similarity_data.storage import upsert_parquet


def get_fetcher(spec: DatasetSpec):
    if spec.source == "ccxt":
        return CryptoCcxtFetcher()
    if spec.source == "stooq":
        return StooqDailyFetcher()
    if spec.source == "twelvedata":
        return ForexTwelveDataFetcher()
    if spec.source == "yfinance":
        return MarketYFinanceFetcher()
    raise ValueError(f"Unsupported data source: {spec.source}")


def refresh_dataset(spec: DatasetSpec, root: Path | None = None) -> RefreshResult:
    data_root = root or repo_root()
    fetcher = get_fetcher(spec)
    frame = fetcher.fetch(spec)
    merged = upsert_parquet(data_root / spec.relative_path, frame)
    return update_manifest(default_manifest_path(), spec, merged)


def refresh_all_datasets(
    specs: list[DatasetSpec],
    *,
    asset_class: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> list[RefreshResult]:
    selected = [
        spec
        for spec in specs
        if spec.enabled
        and (asset_class is None or spec.asset_class == asset_class)
        and (symbol is None or spec.symbol == symbol)
        and (timeframe is None or spec.timeframe == timeframe)
    ]
    return [refresh_dataset(spec) for spec in selected]
