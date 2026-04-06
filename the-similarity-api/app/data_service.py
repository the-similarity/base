"""
Data loading service for the API layer.

Bridges the data warehouse (parquet files on disk) to the API endpoints.
Handles catalog loading, dataset validation, dead bar filtering, and
both single-column and OHLC data retrieval.

AI AGENT NOTES:
- Data lives in `/the-similarity-data/data/{asset_class}/{symbol}/{timeframe}.parquet`
- The catalog whitelist (`manifests/catalog.json`) controls which datasets
  are visible to API clients. This prevents directory traversal attacks.
- Dead bar filtering (`_drop_dead_bars`) removes stale/weekend bars that
  would create false flat segments in similarity search. It's applied
  automatically during loading.
- MAX_HISTORY_POINTS (10K) prevents memory abuse. The engine's search
  pipeline works well with 1K–10K bars; beyond that, increase stride instead.
- The data root can be overridden via THE_SIMILARITY_DATA_ROOT env var
  for deployment flexibility.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Maximum number of data points to return. If a dataset has more bars,
# we keep only the most recent ones (tail). This is a memory safety limit.
MAX_HISTORY_POINTS = 10_000


def _drop_dead_bars(df: pd.DataFrame, dataset_id: str) -> pd.DataFrame:
    """Remove bars with no meaningful price movement (weekends, stale fills).

    Dead bars cause problems for similarity search:
    - Flat segments inflate DTW distances artificially
    - They create false "low volatility" signals in regime detection
    - Weekends in non-crypto markets produce O=H=L=C bars that are noise

    Detection heuristics:
    1. O=H=L=C exactly (exchange-side stale fill)
    2. (high - low) / close < 0.01% (near-zero intrabar range)
    3. Saturday/Sunday for non-crypto datasets (weekend filter)

    Args:
        df: DataFrame with at least open/high/low/close columns.
        dataset_id: Used to detect crypto assets (skips weekend filter).

    Returns:
        DataFrame with dead bars removed.
    """
    # Only filter if OHLC columns are present
    if not all(c in df.columns for c in ("open", "high", "low", "close")):
        return df

    price_range = df["high"] - df["low"]
    # Normalize range by close price to make the threshold work across
    # penny stocks ($0.10 range on a $1 stock) and DJIA ($50 range on $30K).
    mid = df["close"].clip(lower=0.01)
    pct_range = price_range / mid

    # Heuristic 1: Exact flat bars (all four prices identical)
    # Heuristic 2: Near-zero range (< 0.01% of close price)
    dead = (
        ((df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"]))
        | (pct_range < 0.0001)
    )

    # Heuristic 3: Weekend filter for traditional markets (crypto trades 24/7)
    is_crypto = "crypto" in dataset_id.lower()
    if "timestamp" in df.columns and not is_crypto:
        dead = dead | (df["timestamp"].dt.dayofweek >= 5)

    n_dropped = dead.sum()
    if n_dropped > 0:
        logger.info("Dropped %d dead bars from %s", n_dropped, dataset_id)
    return df[~dead]


# Default data root: sibling directory to the project root
_DATA_ROOT = Path(__file__).resolve().parents[2] / "the-similarity-data"


def _data_root() -> Path:
    """Resolve the data directory root, checking env var override first.

    The env var THE_SIMILARITY_DATA_ROOT allows deploying with data stored
    in a different location (e.g., mounted volume, S3 sync target).
    """
    override = os.getenv("THE_SIMILARITY_DATA_ROOT")
    if override:
        return Path(override)
    return _DATA_ROOT


def load_catalog() -> list[dict]:
    """Load the dataset catalog from manifests/catalog.json.

    Only returns entries whose parquet files actually exist on disk.
    This prevents the UI from showing datasets that were declared in
    the manifest but never downloaded/generated.

    Returns:
        List of catalog entry dicts, each with keys:
        asset_class, symbol, timeframe, source, path, etc.
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

    # Validate each entry by checking if its parquet file exists.
    # This is a disk-level whitelist check that runs on every catalog load.
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
    """Build a set of valid dataset IDs from the catalog.

    Each ID is formatted as "asset_class/symbol/timeframe" (e.g., "equity/AAPL/1d").
    Used as a whitelist for input validation in load_series() and load_ohlc().
    """
    return {
        f"{d['asset_class']}/{d['symbol']}/{d['timeframe']}"
        for d in load_catalog()
    }


def validate_dataset_id(dataset_id: str) -> Path:
    """Validate a dataset_id against the catalog whitelist and return the parquet path.

    This is a SECURITY-CRITICAL function. It prevents path traversal attacks
    by only allowing dataset IDs that:
    1. Exist in the catalog JSON
    2. Follow the exact "class/symbol/timeframe" format
    3. Resolve to an existing parquet file

    Args:
        dataset_id: String like "equity/AAPL/1d"

    Returns:
        Path to the validated parquet file.

    Raises:
        ValueError: If the dataset is not in the catalog, format is wrong,
                    or the file is missing.
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
    """Load a single price column from a dataset.

    This is the main data retrieval function used by the search endpoint.
    It returns values suitable for the engine's `history_values` parameter.

    Pipeline:
    1. Validate dataset_id against catalog whitelist
    2. Read parquet file into DataFrame
    3. Sort by timestamp (if available)
    4. Apply date range filter (if specified)
    5. Remove dead bars
    6. Truncate to max_points (keep most recent)
    7. Extract the requested column as float64

    Args:
        dataset_id: Dataset identifier ("asset_class/symbol/timeframe").
        column: Which column to extract (default "close").
        start_date: ISO date string for start filter (inclusive).
        end_date: ISO date string for end filter (inclusive).
        max_points: Maximum number of data points to return.

    Returns:
        Tuple of (values, dates) where values are floats and dates are
        ISO timestamp strings. Dates may be empty if no timestamp column.

    Raises:
        ValueError: For invalid dataset_id, missing column, or read errors.
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

    # Sort + filter by timestamp if the column exists
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp")
        if start_date:
            df = df[df["timestamp"] >= pd.Timestamp(start_date, tz="UTC")]
        if end_date:
            df = df[df["timestamp"] <= pd.Timestamp(end_date, tz="UTC")]

    # Remove dead bars before truncation so we don't waste slots on junk data
    df = _drop_dead_bars(df, dataset_id)

    # Truncate to max_points, keeping the MOST RECENT data.
    # Rationale: recent data is nearly always more relevant for pattern matching
    # than ancient history. The tail() approach is simple and effective.
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
    """Load OHLC + volume data from a dataset for candlestick charts.

    Similar to load_series() but returns all four OHLC columns plus
    volume and dates.

    Returns:
        Dict with keys: open, high, low, close, volume, dates.
        Volume may be an empty list if the source doesn't provide it.

    Raises:
        ValueError: For invalid dataset_id, missing OHLC columns, or errors.
    """
    parquet_path = validate_dataset_id(dataset_id)

    try:
        df = pd.read_parquet(parquet_path)
    except Exception as exc:
        raise ValueError(f"Failed to read parquet for {dataset_id}: {exc}") from exc

    # Verify all four OHLC columns exist
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
    # Volume is optional — not all data sources provide it
    if "volume" in df.columns:
        result["volume"] = df["volume"].astype(np.float64).tolist()
    else:
        result["volume"] = []
    result["dates"] = (
        [ts.isoformat() for ts in df["timestamp"]] if "timestamp" in df.columns else []
    )
    return result
