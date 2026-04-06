"""
Unified time series data loader.

Accepts CSV files, Parquet files, pandas DataFrames, dicts, and raw numpy
arrays and produces a standardized `TimeSeries` container with aligned values
and optional date arrays.

AI AGENT NOTES:
- `TimeSeries` supports date-string slicing (e.g., ts["2020-01-01":"2020-06-30"])
  so the search API can accept date-bounded queries without pre-slicing.
- The `load()` function is the only public entry point. All source-specific
  logic is delegated to `_from_dataframe()`.
- Column name matching is case-insensitive via `_find_column()`.
- Date column detection is automatic: checks common names first, then falls
  back to checking if the DataFrame index is a DatetimeIndex.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray


@dataclass
class TimeSeries:
    """Container for loaded time series data.

    Fields:
        values: 1D float64 array of the primary signal (e.g., close prices).
        dates:  Optional datetime64 array aligned with `values`. None if the
                source had no date information.
        name:   Human-readable identifier (e.g., file path, symbol name).
    """
    values: NDArray[np.float64]
    dates: NDArray | None = None
    name: str = ""

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, key):
        """Support both integer and date-string slicing.

        Examples:
            ts[10:20]                         → integer slice
            ts["2020-01-01":"2020-06-30"]      → date-based slice

        Date-based slicing returns a new TimeSeries with both `values` and
        `dates` filtered to the matching range, preserving alignment.
        """
        if isinstance(key, slice) and self.dates is not None:
            start, stop = key.start, key.stop
            # If start/stop are strings, interpret them as date bounds
            # and build a boolean mask over the dates array.
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
        # Scalar or non-slice indexing: return the raw value(s)
        return self.values[key]


def load(
    source,
    column: str = "close",
    date_column: str | None = None,
) -> TimeSeries:
    """Load time series data from various sources.

    This is the only public entry point for ingesting data into the engine.
    All downstream consumers (search, backtest, plot, etc.) expect a
    TimeSeries object.

    Args:
        source: One of:
            - str (file path): CSV or Parquet file path.
            - pd.DataFrame: Already-loaded DataFrame.
            - dict: Must contain a 'values' key (and optional 'dates').
            - np.ndarray: Raw 1D float array (no dates).
        column: Column name to extract as the primary signal. Only used
                when `source` is a DataFrame or file. Default "close" is
                the standard financial convention.
        date_column: Explicit column name for dates. If None, the loader
                     auto-detects by checking common names ("date",
                     "timestamp", etc.) and the DataFrame index.

    Returns:
        TimeSeries object with values and optional dates.

    Raises:
        ValueError: If a dict source is missing the 'values' key.
        TypeError: If the source type is not recognized.
        KeyError: If the requested column is not found in the DataFrame.
    """
    # --- numpy array: simplest case, no dates ---
    if isinstance(source, np.ndarray):
        return TimeSeries(values=source.astype(np.float64))

    # --- dict: manual construction with optional dates ---
    if isinstance(source, dict):
        if "values" in source:
            vals = np.array(source["values"], dtype=np.float64)
            dates = np.array(source.get("dates"), dtype="datetime64") if "dates" in source else None
            return TimeSeries(values=vals, dates=dates)
        raise ValueError("Dict must contain 'values' key")

    # --- string: treat as file path, detect format by extension ---
    if isinstance(source, str):
        if source.endswith(".parquet"):
            df = pd.read_parquet(source)
        else:
            # Default to CSV for any non-parquet extension
            df = pd.read_csv(source)
        return _from_dataframe(df, column, date_column, name=source)

    # --- DataFrame: direct processing ---
    if isinstance(source, pd.DataFrame):
        return _from_dataframe(source, column, date_column)

    raise TypeError(f"Unsupported source type: {type(source)}")


def _from_dataframe(
    df: pd.DataFrame,
    column: str,
    date_column: str | None,
    name: str = "",
) -> TimeSeries:
    """Convert a DataFrame to TimeSeries, handling column lookup and dates.

    This is the shared path for all DataFrame-based sources (CSV, Parquet,
    and raw DataFrames passed directly).
    """
    # Find the value column (case-insensitive search)
    col = _find_column(df, column)
    values = df[col].values.astype(np.float64)

    # Find date column: explicit name > auto-detect > index check
    dates = None
    if date_column is not None:
        # User specified an explicit date column
        dcol = _find_column(df, date_column)
        dates = pd.to_datetime(df[dcol]).values
    else:
        # Auto-detect: try common date column names in priority order
        for candidate in ["date", "Date", "datetime", "Datetime", "timestamp", "time", "Time"]:
            if candidate in df.columns:
                dates = pd.to_datetime(df[candidate]).values
                break
        # Last resort: check if the DataFrame index is itself a DatetimeIndex
        if dates is None and isinstance(df.index, pd.DatetimeIndex):
            dates = df.index.values

    return TimeSeries(values=values, dates=dates, name=name)


def _find_column(df: pd.DataFrame, name: str) -> str:
    """Find a column in a DataFrame by exact or case-insensitive match.

    Returns the actual column name as it appears in df.columns.
    Raises KeyError with a helpful message listing available columns.
    """
    # Exact match first (fast path)
    if name in df.columns:
        return name
    # Case-insensitive fallback
    lower_map = {c.lower(): c for c in df.columns}
    if name.lower() in lower_map:
        return lower_map[name.lower()]
    raise KeyError(f"Column '{name}' not found. Available: {list(df.columns)}")
