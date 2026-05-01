"""Finance dataset loader (SPY daily close).

Pulls SPY close-price daily bars from the local
``the-similarity-data/data/stocks/spy/`` parquet (the canonical seed
file maintained by the data refresh workflow). Train = first 80%,
test = last 20%.

Why parquet from the data repo (not the network)?
    The benchmark MUST be reproducible offline. The data repo is the
    source of truth for finance series in this project; pulling fresh
    from yfinance/stooq each run would couple the benchmark to network
    flakiness AND give different test sets on different days.

Fallback when the parquet is absent:
    Ship a tiny synthetic SPY-shaped series (geometric Brownian motion
    with a known seed) so CI smoke tests never depend on the data repo
    being populated. Real benchmarking still requires the parquet.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from benchmarks.core import Dataset

# Resolve the project root by walking up from this file. The benchmark
# package lives at ``<root>/benchmarks/datasets/finance.py`` so two
# parents up = the repo root that also contains the_similarity-data/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SPY_PARQUET = _PROJECT_ROOT / "the-similarity-data" / "data" / "stocks" / "spy" / "1d.parquet"

# Trading week is the meaningful seasonality for daily equities; 5 is
# what most published equity benchmarks use for MASE on daily bars.
_SPY_SEASONALITY = 5


def _load_spy_close() -> np.ndarray | None:
    """Return SPY close prices as a float64 array, or None if parquet missing.

    We sort by the date column (rather than trusting parquet row order)
    because the data repo's refresh workflow writes both backfill +
    incremental rows and historically has not always re-sorted.
    """
    if not _SPY_PARQUET.exists():
        return None
    df = pd.read_parquet(_SPY_PARQUET)
    # Tolerate either a "timestamp" or "date" column — both have appeared
    # across data-repo schema revisions.
    date_col = next((c for c in ("timestamp", "date", "Date") if c in df.columns), None)
    close_col = next((c for c in ("close", "Close", "adj_close") if c in df.columns), None)
    if close_col is None:
        return None
    if date_col is not None:
        df = df.sort_values(date_col)
    closes = pd.to_numeric(df[close_col], errors="coerce").dropna().to_numpy(dtype=np.float64)
    if len(closes) < 100:
        # Too short to be a useful benchmark series; treat as missing.
        return None
    return closes


def _synthetic_spy() -> np.ndarray:
    """Deterministic geometric Brownian motion as a fallback SPY proxy.

    Length 2,520 (~10 trading years), seed 42, drift 8%/yr, vol 16%/yr —
    in the right ballpark for the real series. Used ONLY when the
    parquet is unavailable so CI smoke can still exercise this loader.
    """
    rng = np.random.default_rng(42)
    n = 2520
    dt = 1.0 / 252.0
    drift = 0.08
    vol = 0.16
    shocks = rng.standard_normal(n)
    log_returns = (drift - 0.5 * vol**2) * dt + vol * np.sqrt(dt) * shocks
    return 100.0 * np.exp(np.cumsum(log_returns))


def load_spy_daily() -> Iterable[Dataset]:
    """Yield a single SPY-daily ``Dataset`` (train = first 80%, test = last 20%).

    Returns one dataset, not many — SPY is one series. The single-series
    yield keeps the runner's loop shape uniform across loaders.
    """
    closes = _load_spy_close()
    series_id = "SPY"
    if closes is None:
        closes = _synthetic_spy()
        # Tag the series so report consumers can spot the fallback.
        series_id = "SPY_SYNTHETIC"

    split = int(round(len(closes) * 0.8))
    train = closes[:split]
    test = closes[split:]
    if len(train) < 2 * _SPY_SEASONALITY or len(test) == 0:
        return
    yield Dataset(
        name="spy_daily",
        series_id=series_id,
        train=train,
        test=test,
        frequency="D",
        seasonality=_SPY_SEASONALITY,
    )
