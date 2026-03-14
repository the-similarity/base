from __future__ import annotations

import pandas as pd

CANONICAL_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def canonicalize_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.rename(columns={column: column.lower() for column in frame.columns})

    if "timestamp" not in renamed.columns:
        raise ValueError("OHLCV frame must include a timestamp column")

    for column in ["open", "high", "low", "close"]:
        if column not in renamed.columns:
            raise ValueError(f"OHLCV frame missing required column: {column}")

    if "volume" not in renamed.columns:
        renamed["volume"] = 0.0

    renamed["timestamp"] = pd.to_datetime(renamed["timestamp"], utc=True)
    renamed = renamed.dropna(subset=["timestamp", "open", "high", "low", "close"])
    renamed = renamed.drop_duplicates(subset=["timestamp"], keep="last")
    renamed = renamed.sort_values("timestamp").reset_index(drop=True)

    for column in ["open", "high", "low", "close", "volume"]:
        renamed[column] = pd.to_numeric(renamed[column], errors="coerce").astype("float64")

    renamed["volume"] = renamed["volume"].fillna(0.0)
    renamed = renamed.dropna(subset=["open", "high", "low", "close"])

    return renamed[CANONICAL_COLUMNS]
