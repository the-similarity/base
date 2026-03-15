from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from the_similarity_data.models import DatasetSpec
from the_similarity_data.refresh import get_fetcher, refresh_all_datasets, refresh_dataset


def _make_spec(**overrides):
    defaults = dict(
        asset_class="crypto",
        symbol="btc_usdt",
        timeframe="1d",
        source="ccxt",
        source_symbol="BTC/USDT",
    )
    defaults.update(overrides)
    return DatasetSpec(**defaults)


def _mock_frame():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"], utc=True),
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [95.0, 96.0, 97.0],
        "close": [103.0, 104.0, 105.0],
        "volume": [1000.0, 1100.0, 1200.0],
    })


def test_get_fetcher_ccxt():
    spec = _make_spec(source="ccxt")
    fetcher = get_fetcher(spec)
    assert fetcher.__class__.__name__ == "CryptoCcxtFetcher"


def test_get_fetcher_stooq():
    spec = _make_spec(source="stooq")
    fetcher = get_fetcher(spec)
    assert fetcher.__class__.__name__ == "StooqDailyFetcher"


def test_get_fetcher_twelvedata():
    spec = _make_spec(source="twelvedata")
    fetcher = get_fetcher(spec)
    assert fetcher.__class__.__name__ == "ForexTwelveDataFetcher"


def test_get_fetcher_yfinance():
    spec = _make_spec(source="yfinance")
    fetcher = get_fetcher(spec)
    assert fetcher.__class__.__name__ == "MarketYFinanceFetcher"


def test_get_fetcher_unknown():
    spec = _make_spec(source="unknown")
    with pytest.raises(ValueError, match="Unsupported"):
        get_fetcher(spec)


@patch("the_similarity_data.refresh.get_fetcher")
def test_refresh_dataset(mock_get_fetcher, tmp_path):
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = _mock_frame()
    mock_get_fetcher.return_value = mock_fetcher

    spec = _make_spec()
    manifest_path = tmp_path / "manifests" / "catalog.json"

    with patch("the_similarity_data.refresh.default_manifest_path", return_value=manifest_path):
        result = refresh_dataset(spec, root=tmp_path)

    assert result.row_count == 3
    assert result.symbol == "btc_usdt"
    parquet_path = tmp_path / spec.relative_path
    assert parquet_path.exists()


@patch("the_similarity_data.refresh.get_fetcher")
def test_refresh_all_filters_by_asset_class(mock_get_fetcher, tmp_path):
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = _mock_frame()
    mock_get_fetcher.return_value = mock_fetcher

    specs = [
        _make_spec(asset_class="crypto", symbol="btc_usdt"),
        _make_spec(asset_class="stocks", symbol="spy"),
    ]
    manifest_path = tmp_path / "manifests" / "catalog.json"

    with patch("the_similarity_data.refresh.default_manifest_path", return_value=manifest_path):
        results = refresh_all_datasets(specs, asset_class="crypto")

    assert len(results) == 1
    assert results[0].asset_class == "crypto"


@patch("the_similarity_data.refresh.get_fetcher")
def test_refresh_all_skips_disabled(mock_get_fetcher, tmp_path):
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = _mock_frame()
    mock_get_fetcher.return_value = mock_fetcher

    specs = [
        _make_spec(enabled=True),
        _make_spec(symbol="disabled_coin", enabled=False),
    ]
    manifest_path = tmp_path / "manifests" / "catalog.json"

    with patch("the_similarity_data.refresh.default_manifest_path", return_value=manifest_path):
        results = refresh_all_datasets(specs)

    assert len(results) == 1
