"""Tests for the metadata contract of ``GET /catalog``.

Scope
-----
The workstation dataset dropdown renders a rich per-item card (source
badge, date range, last-updated timestamp, bar count, frequency). Those
fields originate in ``manifests/catalog.json`` and are hydrated by
``load_catalog`` before being shipped over ``/catalog`` as
``CatalogItem`` payloads.

These tests lock the contract that:

1. Every field the UI consumes is present on the response.
2. ``frequency`` is derived server-side (the frontend must never parse
   ``timeframe`` on its own).
3. Missing manifest fields fall back to safe defaults (``source =
   "unknown"``, ``row_count = 0``, nullable timestamps) rather than
   raising.
4. The memoization layer respects manifest mtime changes so a fresh
   ingest becomes visible without restarting the API process.

The fixtures write a synthetic manifest + empty parquet files inside a
``tmp_path`` data root and redirect ``load_catalog`` at that root via
the ``THE_SIMILARITY_DATA_ROOT`` env var — the same override shipped
product code respects.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data_service import (
    _FREQUENCY_LABELS,
    _invalidate_catalog_cache,
    load_catalog,
)
from app.main import app


def _write_parquet(path: Path) -> None:
    """Create a minimal parquet file so the catalog's file-existence
    whitelist check passes. Contents are irrelevant; only the path is
    inspected by ``load_catalog``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": [1.0, 2.0, 3.0]}).to_parquet(path)


@pytest.fixture
def synthetic_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Spin up an isolated data root with a manifest + parquet files.

    The fixture:
    1. Writes a manifests/catalog.json with two entries (one fully
       annotated, one missing optional fields to exercise defaults).
    2. Creates empty parquet files at the referenced paths so the
       whitelist passes.
    3. Points ``THE_SIMILARITY_DATA_ROOT`` at the tmp directory.
    4. Invalidates the module-level catalog cache both before and
       after the test so state doesn't leak into/out of the test.
    """
    manifest = {
        "datasets": [
            {
                "asset_class": "stocks",
                "symbol": "spy",
                "timeframe": "1d",
                "source": "Yahoo Finance",
                "path": "data/stocks/spy/1d.parquet",
                "start_timestamp": "1995-01-03T00:00:00+00:00",
                "end_timestamp": "2026-04-20T00:00:00+00:00",
                "row_count": 7_842,
                "last_updated_at": "2026-04-20T16:00:00+00:00",
            },
            {
                # Intentionally minimal: no source, no row_count, no
                # timestamps. load_catalog must backfill with safe
                # defaults so the response is still valid.
                "asset_class": "crypto",
                "symbol": "btcusd",
                "timeframe": "1h",
                "path": "data/crypto/btcusd/1h.parquet",
            },
        ]
    }
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "catalog.json").write_text(json.dumps(manifest))

    _write_parquet(tmp_path / "data" / "stocks" / "spy" / "1d.parquet")
    _write_parquet(tmp_path / "data" / "crypto" / "btcusd" / "1h.parquet")

    monkeypatch.setenv("THE_SIMILARITY_DATA_ROOT", str(tmp_path))
    _invalidate_catalog_cache()
    yield tmp_path
    _invalidate_catalog_cache()


def test_load_catalog_hydrates_metadata(synthetic_data_root: Path) -> None:
    """Every entry should carry the full metadata set, with defaults
    filled in for the minimal manifest entry."""
    entries = load_catalog()
    assert len(entries) == 2

    by_id = {f"{e['asset_class']}/{e['symbol']}/{e['timeframe']}": e for e in entries}

    # Fully annotated entry preserves every manifest value.
    spy = by_id["stocks/spy/1d"]
    assert spy["source"] == "Yahoo Finance"
    assert spy["row_count"] == 7_842
    assert spy["start_timestamp"] == "1995-01-03T00:00:00+00:00"
    assert spy["end_timestamp"] == "2026-04-20T00:00:00+00:00"
    assert spy["last_updated_at"] == "2026-04-20T16:00:00+00:00"
    assert spy["frequency"] == "1 day"

    # Minimal entry gets safe defaults, not a KeyError.
    btc = by_id["crypto/btcusd/1h"]
    assert btc["source"] == "unknown"
    assert btc["row_count"] == 0
    assert btc["start_timestamp"] is None
    assert btc["end_timestamp"] is None
    assert btc["last_updated_at"] is None
    assert btc["frequency"] == "1 hour"


def test_catalog_endpoint_exposes_metadata(synthetic_data_root: Path) -> None:
    """``GET /catalog`` must surface the full metadata contract the
    dataset dropdown reads. This test doubles as a guard against future
    changes that might drop fields from CatalogItem."""
    client = TestClient(app)
    response = client.get("/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert "datasets" in payload
    datasets = payload["datasets"]
    assert len(datasets) == 2

    by_id = {f"{d['asset_class']}/{d['symbol']}/{d['timeframe']}": d for d in datasets}
    spy = by_id["stocks/spy/1d"]
    # Required UI fields — if any go missing, the dropdown breaks.
    for key in (
        "asset_class",
        "symbol",
        "timeframe",
        "source",
        "row_count",
        "start_timestamp",
        "end_timestamp",
        "last_updated_at",
        "frequency",
    ):
        assert key in spy, f"missing UI field: {key}"
    assert spy["frequency"] == "1 day"


def test_frequency_label_covers_documented_codes() -> None:
    """The ``_FREQUENCY_LABELS`` table must cover every timeframe the
    live catalog ships today. If a new short code is added to the data
    pipeline, this test fails and the author must extend the table
    (rather than silently echoing the raw code in the UI)."""
    live_codes = {"1m", "5m", "15m", "1h", "4h", "1d"}
    missing = live_codes - set(_FREQUENCY_LABELS)
    assert not missing, f"frequency label table missing codes: {missing}"


def test_catalog_cache_invalidates_on_manifest_change(
    synthetic_data_root: Path,
) -> None:
    """Memoization must not serve stale data across a manifest rewrite.

    The module-level cache keys on the manifest's mtime; when we mutate
    the manifest (new entry) and bump the mtime, the next ``load_catalog``
    call must re-read from disk rather than returning the cached list.
    """
    first = load_catalog()
    assert len(first) == 2

    # Append a third entry and advance the mtime. Using ``os.utime``
    # rather than touch() so the test is portable across platforms.
    manifest_path = synthetic_data_root / "manifests" / "catalog.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["datasets"].append(
        {
            "asset_class": "fx",
            "symbol": "eurusd",
            "timeframe": "5m",
            "source": "OANDA",
            "path": "data/fx/eurusd/5m.parquet",
        }
    )
    _write_parquet(synthetic_data_root / "data" / "fx" / "eurusd" / "5m.parquet")
    manifest_path.write_text(json.dumps(manifest))
    # Advance mtime 2 seconds forward to cross filesystem resolution.
    mtime = manifest_path.stat().st_mtime + 2
    os.utime(manifest_path, (mtime, mtime))

    second = load_catalog()
    assert len(second) == 3
    ids = {f"{e['asset_class']}/{e['symbol']}/{e['timeframe']}" for e in second}
    assert "fx/eurusd/5m" in ids
