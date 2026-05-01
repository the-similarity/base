"""NN5 Daily dataset loader.

NN5 is a competition dataset of 111 daily ATM cash withdrawal series
with strong weekly seasonality (m=7). Like M4, we pull from the Monash
TSF mirror and cache locally — no gluonts dep.

Source CSV layout (Monash mirror):
    First column: series_name (e.g. "T1", "T2", ...)
    Remaining columns: comma-separated values (no padding, all 791
    observations present in every series).

Why a separate loader rather than parameterising m4.py?
    NN5's CSV happens to use the same wide layout, but the source URL,
    seasonality, frequency code, and degenerate-filter thresholds
    differ. Keeping loaders single-purpose makes future additions
    (e.g. M3, ETT) trivial drop-ins.
"""

from __future__ import annotations

import csv
import urllib.request
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from benchmarks.core import Dataset

_CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache" / "nn5"

# Monash TSF GitHub mirror — the maintained, citable host. Direct ZENODO
# links go stale; this one has been stable for years.
_NN5_URL = (
    "https://raw.githubusercontent.com/rakshitha123/TSForecasting/master/"
    "tsf_data/nn5_daily_dataset_without_missing_values.csv"
)
_NN5_FILE = "nn5_daily.csv"

# NN5's published forecast horizon is 56 days. We expose the full
# 56-day test split per series; the runner truncates per-call.
_TEST_HORIZON = 56


def _ensure_cached() -> Path:
    """Download NN5 to the cache (idempotent)."""
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cached = _CACHE_ROOT / _NN5_FILE
    if cached.exists() and cached.stat().st_size > 0:
        return cached
    tmp = cached.with_suffix(cached.suffix + ".part")
    urllib.request.urlretrieve(_NN5_URL, tmp)
    tmp.rename(cached)
    return cached


def load_nn5_daily() -> Iterable[Dataset]:
    """Yield NN5 Daily series (111 total, seasonality 7).

    Train/test split: last ``_TEST_HORIZON=56`` observations are held
    out per series, matching the official NN5 evaluation protocol.
    """
    path = _ensure_cached()

    with path.open("r", newline="") as fh:
        reader = csv.reader(fh)
        # The Monash mirror file has a single header row of column
        # numbers. We skip it.
        next(reader, None)
        for row in reader:
            if not row:
                continue
            series_id = row[0]
            try:
                values = np.asarray(
                    [float(v) for v in row[1:] if v != ""],
                    dtype=np.float64,
                )
            except ValueError:
                # Some rows in the legacy CSV header in extreme cases
                # contain non-numeric metadata — skip rather than crash
                # the whole loader.
                continue

            # Need at least one full seasonal lag in train + the test
            # split to be useful. NN5 is 791 obs/series so this never
            # actually fails, but the guard makes the contract explicit.
            if len(values) < _TEST_HORIZON + 14:
                continue
            if not np.all(np.isfinite(values)) or np.std(values) == 0:
                continue

            train = values[:-_TEST_HORIZON]
            test = values[-_TEST_HORIZON:]

            yield Dataset(
                name="nn5_daily",
                series_id=series_id,
                train=train,
                test=test,
                frequency="D",
                seasonality=7,
            )
