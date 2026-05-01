"""M4 competition dataset loader (Daily and Hourly subsets).

The M4 dataset is a set of 100K real-world series across 6 frequencies.
For benchmarking we use Daily (4,227 series, seasonality 7) and Hourly
(414 series, seasonality 24). To keep runtime tractable on a laptop,
each loader yields a deterministic 100-series subset selected by
``random.Random(SEED).sample`` over a sorted list of series IDs (so
subset membership is stable across machines and Python versions).

Data sourcing:
    The loaders pull raw CSVs directly from the M4-methods GitHub
    mirror (the only canonical public host). Files are cached under
    ``benchmarks/cache/m4/`` after first download. We deliberately do
    NOT depend on ``gluonts`` — it pulls in PyTorch and is far too heavy
    for a CSV download.

CSV schema (M4-methods Daily-train.csv, Daily-test.csv):
    Column 0: series id (e.g. "D1")
    Columns 1..N: comma-separated values, with empty strings padding
    short series. The value count varies wildly per series (the train
    file ranges from 93 to 9,919 columns); we strip the empty cells
    per row.
"""

from __future__ import annotations

import csv
import random
import urllib.request
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from benchmarks.core import Dataset

# 100-series determinism rules: same seed everywhere → same subset → same
# results across machines. Do not change SEED without coordinating with
# Agent B's report layer (it cross-references series IDs).
SEED = 42
N_SERIES = 100

# Repo-relative cache so the runner doesn't pollute the user's home dir.
_CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache" / "m4"

# Canonical mirror. The official M4 site (m4.unic.ac.cy) goes offline
# periodically; the M4-methods GitHub repo is the de-facto stable host.
_M4_BASE_URL = (
    "https://raw.githubusercontent.com/Mcompetitions/M4-methods/master/Dataset"
)


def _ensure_cached(filename: str) -> Path:
    """Download ``filename`` from the M4 GitHub mirror to the cache, return path.

    Idempotent: if the file already exists it returns the cached path
    without touching the network. We use ``urllib`` rather than
    ``requests`` to avoid an extra dependency.
    """
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cached = _CACHE_ROOT / filename
    if cached.exists() and cached.stat().st_size > 0:
        return cached

    url = f"{_M4_BASE_URL}/{filename}"
    # Use a small temp suffix so a partial download never poisons the
    # cache: we only rename into place after the urlretrieve completes.
    tmp = cached.with_suffix(cached.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(cached)
    return cached


def _read_m4_csv(path: Path) -> dict[str, np.ndarray]:
    """Parse an M4 train/test CSV into ``{series_id: float64 array}``.

    M4 CSVs are wide-format with ragged rows (empty cells pad short
    series). We strip empties per row so each value array is dense.
    """
    out: dict[str, np.ndarray] = {}
    with path.open("r", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        for row in reader:
            if not row:
                continue
            series_id = row[0]
            # The first column is the series id; the rest are floats. Skip
            # empty cells (M4's right-padding for short series).
            values = [float(v) for v in row[1:] if v != ""]
            if not values:
                continue
            out[series_id] = np.asarray(values, dtype=np.float64)
    return out


def _load_m4_subset(
    train_filename: str,
    test_filename: str,
    dataset_name: str,
    frequency: str,
    seasonality: int,
) -> Iterable[Dataset]:
    """Shared body for both M4 frequencies — only file names + metadata vary."""
    train_path = _ensure_cached(train_filename)
    test_path = _ensure_cached(test_filename)
    train_dict = _read_m4_csv(train_path)
    test_dict = _read_m4_csv(test_path)

    # Deterministic 100-series sample over the SORTED key set so subset
    # membership doesn't depend on dict iteration order (Python 3.7+
    # guarantees insertion order, but file ordering across mirrors can
    # vary).
    common_ids = sorted(set(train_dict.keys()) & set(test_dict.keys()))
    rng = random.Random(SEED)
    chosen = sorted(rng.sample(common_ids, min(N_SERIES, len(common_ids))))

    for series_id in chosen:
        train = train_dict[series_id]
        test = test_dict[series_id]
        # Filter degenerate series — too short to score, all-zero
        # variance, or all-NaN. Doing this in the loader keeps the
        # runner's defensive code simpler.
        if len(train) < 2 * seasonality or len(test) == 0:
            continue
        if not np.all(np.isfinite(train)) or not np.all(np.isfinite(test)):
            continue
        if np.std(train) == 0:
            continue
        yield Dataset(
            name=dataset_name,
            series_id=series_id,
            train=train,
            test=test,
            frequency=frequency,
            seasonality=seasonality,
        )


def load_m4_daily() -> Iterable[Dataset]:
    """Yield up to 100 M4-Daily series (seasonality 7, horizon 14 in original spec).

    The benchmark runner picks its own horizons (typically 5 and 20);
    we expose the full 14-step test array and let the runner truncate
    as needed.
    """
    return _load_m4_subset(
        train_filename="Train/Daily-train.csv",
        test_filename="Test/Daily-test.csv",
        dataset_name="m4_daily",
        frequency="D",
        seasonality=7,
    )


def load_m4_hourly() -> Iterable[Dataset]:
    """Yield up to 100 M4-Hourly series (seasonality 24, horizon 48 in original spec)."""
    return _load_m4_subset(
        train_filename="Train/Hourly-train.csv",
        test_filename="Test/Hourly-test.csv",
        dataset_name="m4_hourly",
        frequency="H",
        seasonality=24,
    )
