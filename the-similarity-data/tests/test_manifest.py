import json

import pandas as pd

from the_similarity_data.manifest import load_manifest, update_manifest
from the_similarity_data.models import DatasetSpec


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


def _make_frame(n=3):
    return pd.DataFrame({
        "timestamp": pd.to_datetime(
            [f"2024-01-0{i+1}" for i in range(n)], utc=True
        ),
        "open": [100.0 + i for i in range(n)],
        "high": [105.0 + i for i in range(n)],
        "low": [95.0 + i for i in range(n)],
        "close": [103.0 + i for i in range(n)],
        "volume": [1000.0] * n,
    })


def test_load_manifest_missing_file(tmp_path):
    result = load_manifest(tmp_path / "missing.json")
    assert result == {"datasets": []}


def test_load_manifest_existing_file(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"datasets": [{"symbol": "btc"}]}))
    result = load_manifest(path)
    assert len(result["datasets"]) == 1


def test_update_manifest_creates_file(tmp_path):
    path = tmp_path / "manifests" / "catalog.json"
    spec = _make_spec()
    frame = _make_frame()

    result = update_manifest(path, spec, frame)
    assert path.exists()
    assert result.row_count == 3
    assert result.asset_class == "crypto"
    assert result.symbol == "btc_usdt"
    assert result.start_timestamp is not None
    assert result.end_timestamp is not None


def test_update_manifest_deduplicates(tmp_path):
    path = tmp_path / "catalog.json"
    spec = _make_spec()

    update_manifest(path, spec, _make_frame(3))
    update_manifest(path, spec, _make_frame(5))

    manifest = json.loads(path.read_text())
    # Should have 1 entry, not 2
    assert len(manifest["datasets"]) == 1
    assert manifest["datasets"][0]["row_count"] == 5


def test_update_manifest_multiple_datasets(tmp_path):
    path = tmp_path / "catalog.json"

    update_manifest(path, _make_spec(symbol="btc_usdt"), _make_frame())
    update_manifest(path, _make_spec(symbol="eth_usdt"), _make_frame())

    manifest = json.loads(path.read_text())
    assert len(manifest["datasets"]) == 2
    symbols = [d["symbol"] for d in manifest["datasets"]]
    assert "btc_usdt" in symbols
    assert "eth_usdt" in symbols


def test_update_manifest_sorts_entries(tmp_path):
    path = tmp_path / "catalog.json"

    update_manifest(path, _make_spec(symbol="zzz"), _make_frame())
    update_manifest(path, _make_spec(symbol="aaa"), _make_frame())

    manifest = json.loads(path.read_text())
    assert manifest["datasets"][0]["symbol"] == "aaa"
    assert manifest["datasets"][1]["symbol"] == "zzz"


def test_update_manifest_handles_empty_frame(tmp_path):
    path = tmp_path / "catalog.json"
    spec = _make_spec()
    empty = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    result = update_manifest(path, spec, empty)
    assert result.row_count == 0
    assert result.start_timestamp is None
    assert result.end_timestamp is None
