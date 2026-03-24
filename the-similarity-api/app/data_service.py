from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MAX_HISTORY_POINTS = 10_000


def _drop_dead_bars(df: pd.DataFrame, dataset_id: str) -> pd.DataFrame:
    """Remove bars with no meaningful price movement (weekends, stale fills)."""
    if not all(c in df.columns for c in ("open", "high", "low", "close")):
        return df
    price_range = df["high"] - df["low"]
    mid = df["close"].clip(lower=0.01)
    pct_range = price_range / mid
    # Exact flat (O=H=L=C) or near-zero range (<0.01% of price)
    dead = (
        ((df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"]))
        | (pct_range < 0.0001)
    )
    # Weekend filter for non-crypto (crypto trades 24/7)
    is_crypto = "crypto" in dataset_id.lower()
    if "timestamp" in df.columns and not is_crypto:
        dead = dead | (df["timestamp"].dt.dayofweek >= 5)
    n_dropped = dead.sum()
    if n_dropped > 0:
        logger.info("Dropped %d dead bars from %s", n_dropped, dataset_id)
    return df[~dead]

_DATA_ROOT = Path(__file__).resolve().parents[2] / "the-similarity-data"


def _data_root() -> Path:
    override = os.getenv("THE_SIMILARITY_DATA_ROOT")
    if override:
        return Path(override)
    return _DATA_ROOT


def load_catalog() -> list[dict]:
    """Load the dataset catalog from manifests/catalog.json.

    Only returns entries whose parquet files actually exist on disk.
    """
    catalog_path = _data_root() / "manifests" / "catalog.json"
    if not catalog_path.exists():
        logger.warning("Catalog not found at %s", catalog_path)
        return []
    try:
        payload = json.loads(catalog_path.read_text())
        raw = payload.get("datasets", [])
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read catalog: %s", exc)
        return []

    root = _data_root()
    valid: list[dict] = []
    for d in raw:
        parquet = root / "data" / d["asset_class"] / d["symbol"] / f"{d['timeframe']}.parquet"
        if parquet.exists():
            valid.append(d)
        else:
            logger.warning("Catalog entry %s/%s/%s has no data file — hiding from catalog",
                           d["asset_class"], d["symbol"], d["timeframe"])
    return valid


def _catalog_ids() -> set[str]:
    return {
        f"{d['asset_class']}/{d['symbol']}/{d['timeframe']}"
        for d in load_catalog()
    }


def validate_dataset_id(dataset_id: str) -> Path:
    """Validate dataset_id against the catalog whitelist and return the parquet path.

    Raises ValueError if the dataset is not in the catalog or the file is missing.
    """
    valid_ids = _catalog_ids()
    if dataset_id not in valid_ids:
        raise ValueError(f"Unknown dataset: {dataset_id}")

    parts = dataset_id.split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid dataset ID format: {dataset_id}")

    asset_class, symbol, timeframe = parts
    parquet_path = _data_root() / "data" / asset_class / symbol / f"{timeframe}.parquet"
    if not parquet_path.exists():
        raise ValueError(f"Data file missing for dataset: {dataset_id}")

    return parquet_path


def load_series(
    dataset_id: str,
    column: str = "close",
    start_date: str | None = None,
    end_date: str | None = None,
    max_points: int = MAX_HISTORY_POINTS,
) -> tuple[list[float], list[str]]:
    """Load a price series from a dataset.

    Returns (values, dates) where values are prices and dates are ISO timestamps.
    """
    parquet_path = validate_dataset_id(dataset_id)

    try:
        df = pd.read_parquet(parquet_path)
    except Exception as exc:
        raise ValueError(f"Failed to read parquet for {dataset_id}: {exc}") from exc

    if column not in df.columns:
        raise ValueError(
            f"Column '{column}' not found in {dataset_id}. Available: {list(df.columns)}"
        )

    if "timestamp" in df.columns:
        df = df.sort_values("timestamp")
        if start_date:
            df = df[df["timestamp"] >= pd.Timestamp(start_date, tz="UTC")]
        if end_date:
            df = df[df["timestamp"] <= pd.Timestamp(end_date, tz="UTC")]

    df = _drop_dead_bars(df, dataset_id)

    if len(df) > max_points:
        logger.info(
            "Truncating %s from %d to %d points (keeping most recent)",
            dataset_id,
            len(df),
            max_points,
        )
        df = df.tail(max_points)

    values = df[column].astype(np.float64).tolist()
    dates: list[str] = []
    if "timestamp" in df.columns:
        dates = [ts.isoformat() for ts in df["timestamp"]]

    return values, dates


def load_ohlc(
    dataset_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    max_points: int = MAX_HISTORY_POINTS,
) -> dict[str, list]:
    """Load OHLC + volume data from a dataset.

    Returns dict with keys: open, high, low, close, volume, dates.
    """
    parquet_path = validate_dataset_id(dataset_id)

    try:
        df = pd.read_parquet(parquet_path)
    except Exception as exc:
        raise ValueError(f"Failed to read parquet for {dataset_id}: {exc}") from exc

    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns in {dataset_id}: {missing}")

    if "timestamp" in df.columns:
        df = df.sort_values("timestamp")
        if start_date:
            df = df[df["timestamp"] >= pd.Timestamp(start_date, tz="UTC")]
        if end_date:
            df = df[df["timestamp"] <= pd.Timestamp(end_date, tz="UTC")]

    df = _drop_dead_bars(df, dataset_id)

    if len(df) > max_points:
        df = df.tail(max_points)

    result: dict[str, list] = {
        col: df[col].astype(np.float64).tolist() for col in ["open", "high", "low", "close"]
    }
    if "volume" in df.columns:
        result["volume"] = df["volume"].astype(np.float64).tolist()
    else:
        result["volume"] = []
    result["dates"] = (
        [ts.isoformat() for ts in df["timestamp"]] if "timestamp" in df.columns else []
    )
    return result
