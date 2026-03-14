from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from the_similarity_data.models import DatasetSpec, RefreshResult


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"datasets": []}
    return json.loads(path.read_text())


def update_manifest(path: Path, spec: DatasetSpec, frame: pd.DataFrame) -> RefreshResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(path)
    datasets = manifest.setdefault("datasets", [])

    start_timestamp = None
    end_timestamp = None
    if not frame.empty:
        start_timestamp = frame["timestamp"].iloc[0].isoformat()
        end_timestamp = frame["timestamp"].iloc[-1].isoformat()

    last_updated_at = datetime.now(UTC).isoformat()
    relative_path = spec.relative_path.as_posix()

    record = {
        "asset_class": spec.asset_class,
        "symbol": spec.symbol,
        "timeframe": spec.timeframe,
        "source": spec.source,
        "path": relative_path,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "row_count": int(len(frame)),
        "last_updated_at": last_updated_at,
    }

    datasets = [
        item
        for item in datasets
        if not (
            item["asset_class"] == spec.asset_class
            and item["symbol"] == spec.symbol
            and item["timeframe"] == spec.timeframe
            and item["source"] == spec.source
        )
    ]
    datasets.append(record)
    datasets.sort(key=lambda item: (item["asset_class"], item["symbol"], item["timeframe"], item["source"]))
    manifest["datasets"] = datasets
    path.write_text(json.dumps(manifest, indent=2) + "\n")

    return RefreshResult(
        asset_class=spec.asset_class,
        symbol=spec.symbol,
        timeframe=spec.timeframe,
        source=spec.source,
        path=Path(relative_path),
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        row_count=int(len(frame)),
        last_updated_at=last_updated_at,
    )
