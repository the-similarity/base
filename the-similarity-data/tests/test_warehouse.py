"""Tests for the DuckDB warehouse layer."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from the_similarity_data.warehouse import CoverageStats, QualityIssue, Warehouse


@pytest.fixture
def sample_data_root(tmp_path):
    """Create a minimal data root with parquet files and manifest."""
    # Create parquet files
    data_dir = tmp_path / "data" / "crypto" / "btc_usdt"
    data_dir.mkdir(parents=True)

    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=100, freq="1D", tz="UTC"),
        "open": range(100, 200),
        "high": range(101, 201),
        "low": range(99, 199),
        "close": range(100, 200),
        "volume": [1000.0] * 100,
    })
    df.to_parquet(data_dir / "1d.parquet", index=False)

    # Create a second dataset
    data_dir2 = tmp_path / "data" / "stocks" / "aapl"
    data_dir2.mkdir(parents=True)
    df2 = pd.DataFrame({
        "timestamp": pd.date_range("2023-01-01", periods=50, freq="1D", tz="UTC"),
        "open": range(150, 200),
        "high": range(151, 201),
        "low": range(149, 199),
        "close": range(150, 200),
        "volume": [5000.0] * 50,
    })
    df2.to_parquet(data_dir2 / "1d.parquet", index=False)

    # Create manifest
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    catalog = {
        "datasets": [
            {
                "asset_class": "crypto",
                "symbol": "btc_usdt",
                "timeframe": "1d",
                "source": "ccxt",
                "path": "data/crypto/btc_usdt/1d.parquet",
                "start_timestamp": "2024-01-01T00:00:00+00:00",
                "end_timestamp": "2024-04-09T00:00:00+00:00",
                "row_count": 100,
                "last_updated_at": datetime.now(UTC).isoformat(),
            },
            {
                "asset_class": "stocks",
                "symbol": "aapl",
                "timeframe": "1d",
                "source": "stooq",
                "path": "data/stocks/aapl/1d.parquet",
                "start_timestamp": "2023-01-01T00:00:00+00:00",
                "end_timestamp": "2023-02-19T00:00:00+00:00",
                "row_count": 50,
                "last_updated_at": datetime.now(UTC).isoformat(),
            },
        ]
    }
    (manifest_dir / "catalog.json").write_text(json.dumps(catalog, indent=2))

    return tmp_path


class TestWarehouseRegistration:
    def test_register_all(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        count = wh.register_all()
        assert count == 2

    def test_register_single_dataset(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        assert wh.register_dataset("crypto", "btc_usdt", "1d") is True
        assert wh.register_dataset("crypto", "nonexistent", "1d") is False

    def test_register_empty_dir(self, tmp_path):
        (tmp_path / "data").mkdir()
        wh = Warehouse(tmp_path)
        count = wh.register_all()
        assert count == 0


class TestWarehouseQuery:
    def test_query_returns_dicts(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        wh.register_all()
        result = wh.query("SELECT COUNT(*) as cnt FROM ohlcv")
        assert result == [{"cnt": 150}]

    def test_query_with_filter(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        wh.register_all()
        result = wh.query(
            "SELECT COUNT(*) as cnt FROM ohlcv WHERE asset_class = 'crypto'"
        )
        assert result == [{"cnt": 100}]

    def test_query_df(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        wh.register_all()
        df = wh.query_df("SELECT DISTINCT symbol FROM ohlcv ORDER BY symbol")
        assert list(df["symbol"]) == ["aapl", "btc_usdt"]


class TestCoverage:
    def test_coverage_from_manifest(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        stats = wh.coverage()
        assert stats.total_datasets == 2
        assert stats.total_rows == 150
        assert stats.by_asset_class["crypto"] == 1
        assert stats.by_asset_class["stocks"] == 1
        assert len(stats.symbols) == 2

    def test_coverage_from_parquet(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        wh.register_all()
        stats = wh.coverage_from_parquet()
        assert stats.total_datasets == 2
        assert stats.total_rows == 150

    def test_coverage_empty(self, tmp_path):
        wh = Warehouse(tmp_path)
        stats = wh.coverage()
        assert stats.total_datasets == 0


class TestQuality:
    def test_quality_no_issues(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        issues = wh.check_quality()
        # Daily data shouldn't have gaps or spikes in our clean test data
        assert all(i.issue_type != "empty" for i in issues)

    def test_quality_missing_file(self, sample_data_root):
        # Add a manifest entry pointing to nonexistent file
        catalog_path = sample_data_root / "manifests" / "catalog.json"
        catalog = json.loads(catalog_path.read_text())
        catalog["datasets"].append({
            "asset_class": "forex",
            "symbol": "eurusd",
            "timeframe": "1h",
            "source": "twelvedata",
            "path": "data/forex/eurusd/1h.parquet",
            "row_count": 100,
            "last_updated_at": datetime.now(UTC).isoformat(),
        })
        catalog_path.write_text(json.dumps(catalog))

        wh = Warehouse(sample_data_root)
        issues = wh.check_quality()
        missing = [i for i in issues if i.issue_type == "missing_file"]
        assert len(missing) == 1
        assert "eurusd" in missing[0].dataset_id

    def test_quality_empty_dataset(self, sample_data_root):
        catalog_path = sample_data_root / "manifests" / "catalog.json"
        catalog = json.loads(catalog_path.read_text())
        catalog["datasets"].append({
            "asset_class": "forex",
            "symbol": "ghost",
            "timeframe": "1d",
            "source": "test",
            "path": "data/forex/ghost/1d.parquet",
            "row_count": 0,
            "last_updated_at": datetime.now(UTC).isoformat(),
        })
        catalog_path.write_text(json.dumps(catalog))

        wh = Warehouse(sample_data_root)
        issues = wh.check_quality()
        empties = [i for i in issues if i.issue_type == "empty"]
        assert len(empties) == 1


class TestFreshness:
    def test_freshness_report(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        report = wh.freshness_report()
        assert len(report) == 2
        assert all("dataset_id" in r for r in report)
        assert all("hours_since_update" in r for r in report)


class TestSearchAssets:
    def test_search_by_class(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        results = wh.search_assets(asset_class="crypto")
        assert len(results) == 1
        assert results[0]["symbol"] == "btc_usdt"

    def test_search_by_source(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        results = wh.search_assets(source="stooq")
        assert len(results) == 1

    def test_search_min_rows(self, sample_data_root):
        wh = Warehouse(sample_data_root)
        results = wh.search_assets(min_rows=75)
        assert len(results) == 1
        assert results[0]["symbol"] == "btc_usdt"


class TestContextManager:
    def test_with_statement(self, sample_data_root):
        with Warehouse(sample_data_root) as wh:
            wh.register_all()
            result = wh.query("SELECT COUNT(*) as cnt FROM ohlcv")
            assert result[0]["cnt"] == 150
