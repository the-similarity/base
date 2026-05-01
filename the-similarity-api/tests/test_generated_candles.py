"""Tests for request-time candle generation in the API data service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data_service import _invalidate_catalog_cache, load_ohlc, load_series
from app.main import app


@pytest.fixture
def candle_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Create a catalogued 5m crypto dataset with enough rows for 1h candles."""

    manifest = {
        "datasets": [
            {
                "asset_class": "crypto",
                "symbol": "btcusd",
                "timeframe": "5m",
                "path": "data/crypto/btcusd/5m.parquet",
            }
        ]
    }
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "catalog.json").write_text(json.dumps(manifest))

    data_path = tmp_path / "data" / "crypto" / "btcusd" / "5m.parquet"
    data_path.parent.mkdir(parents=True)
    base = list(range(19))
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01T00:00:00Z", periods=19, freq="5min"),
            "open": [100 + i for i in base],
            "high": [101 + i for i in base],
            "low": [99 + i for i in base],
            "close": [100.5 + i for i in base],
            "volume": [10 + i for i in base],
        }
    ).to_parquet(data_path)

    monkeypatch.setenv("THE_SIMILARITY_DATA_ROOT", str(tmp_path))
    _invalidate_catalog_cache()
    yield tmp_path
    _invalidate_catalog_cache()


def test_load_ohlc_can_generate_target_timeframe(candle_data_root: Path) -> None:
    data = load_ohlc("crypto/btcusd/5m", target_timeframe="1h")

    assert data["open"] == [100.0]
    assert data["high"] == [112.0]
    assert data["low"] == [99.0]
    assert data["close"] == [111.5]
    assert data["volume"] == [186.0]
    assert len(data["dates"]) == 1


def test_load_series_extracts_from_generated_candles(candle_data_root: Path) -> None:
    values, dates = load_series("crypto/btcusd/5m", target_timeframe="1h")

    assert values == [111.5]
    assert len(dates) == 1


def test_ohlc_endpoint_returns_effective_generated_timeframe(
    candle_data_root: Path,
) -> None:
    client = TestClient(app)

    response = client.get("/datasets/crypto/btcusd/5m/ohlc?target_timeframe=1h")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_id"] == "crypto/btcusd/5m"
    assert payload["source_timeframe"] == "5m"
    assert payload["timeframe"] == "1h"
    assert payload["open"] == [100.0]
    assert payload["close"] == [111.5]


def test_generated_endpoint_can_keep_incomplete_candles(
    candle_data_root: Path,
) -> None:
    client = TestClient(app)

    response = client.get(
        "/datasets/crypto/btcusd/5m/ohlc?target_timeframe=1h&include_incomplete=true"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["open"] == [100.0, 112.0]
    assert payload["close"] == [111.5, 118.5]
