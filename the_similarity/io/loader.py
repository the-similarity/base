from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray


@dataclass
class TimeSeries:
    """Container for loaded time series data."""
    values: NDArray[np.float64]
    dates: NDArray | None = None
    name: str = ""

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, key):
        if isinstance(key, slice) and self.dates is not None:
            start, stop = key.start, key.stop
            # If start/stop are strings, do date-based slicing
            if isinstance(start, str) or isinstance(stop, str):
                mask = np.ones(len(self.dates), dtype=bool)
                if start is not None:
                    mask &= self.dates >= np.datetime64(start)
                if stop is not None:
                    mask &= self.dates <= np.datetime64(stop)
                return TimeSeries(
                    values=self.values[mask],
                    dates=self.dates[mask],
                    name=self.name,
                )
            # Integer/None slicing — return TimeSeries with sliced dates
            return TimeSeries(
                values=self.values[key],
                dates=self.dates[key],
                name=self.name,
            )
        return self.values[key]


def load(
    source,
    column: str = "close",
    date_column: str | None = None,
) -> TimeSeries:
    """Load time series data from various sources.

    Args:
        source: File path (CSV/parquet), pandas DataFrame, dict, or numpy array.
        column: Column name to use as values (for DataFrame/CSV/parquet).
        date_column: Column name for dates. Auto-detected if None.

    Returns:
        TimeSeries object with values and optional dates.
    """
    if isinstance(source, np.ndarray):
        return TimeSeries(values=source.astype(np.float64))

    if isinstance(source, dict):
        if "values" in source:
            vals = np.array(source["values"], dtype=np.float64)
            dates = np.array(source.get("dates"), dtype="datetime64") if "dates" in source else None
            return TimeSeries(values=vals, dates=dates)
        raise ValueError("Dict must contain 'values' key")

    if isinstance(source, str):
        if source.endswith(".parquet"):
            df = pd.read_parquet(source)
        else:
            df = pd.read_csv(source)
        return _from_dataframe(df, column, date_column, name=source)

    if isinstance(source, pd.DataFrame):
        return _from_dataframe(source, column, date_column)

    raise TypeError(f"Unsupported source type: {type(source)}")


def _from_dataframe(
    df: pd.DataFrame,
    column: str,
    date_column: str | None,
    name: str = "",
) -> TimeSeries:
    # Find the value column (case-insensitive)
    col = _find_column(df, column)
    values = df[col].values.astype(np.float64)

    # Find date column
    dates = None
    if date_column is not None:
        dcol = _find_column(df, date_column)
        dates = pd.to_datetime(df[dcol]).values
    else:
        # Auto-detect: look for common date column names
        for candidate in ["date", "Date", "datetime", "Datetime", "timestamp", "time", "Time"]:
            if candidate in df.columns:
                dates = pd.to_datetime(df[candidate]).values
                break
        # Check if index is datetime
        if dates is None and isinstance(df.index, pd.DatetimeIndex):
            dates = df.index.values

    return TimeSeries(values=values, dates=dates, name=name)


def _find_column(df: pd.DataFrame, name: str) -> str:
    if name in df.columns:
        return name
    # Case-insensitive search
    lower_map = {c.lower(): c for c in df.columns}
    if name.lower() in lower_map:
        return lower_map[name.lower()]
    raise KeyError(f"Column '{name}' not found. Available: {list(df.columns)}")
