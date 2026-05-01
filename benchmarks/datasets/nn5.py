"""NN5 Daily dataset loader.

NN5 is a competition dataset of 111 daily ATM cash withdrawal series
with strong weekly seasonality (m=7). It is the canonical Chronos
*zero-shot* evaluation dataset — Chronos was NOT trained on it (unlike
M4), so cross-system numbers on NN5 are the only honest neural
comparison the report can make.

Source: Zenodo record 4656117 — "NN5 Daily (without missing values)"
from the Monash Time Series Forecasting Repository (Godahewa et al.
2021). The file is a Monash ``.tsf`` (Time Series Forecasting) format
inside a zip archive. We download once, extract on-the-fly, and parse
the .tsf in Python without any external deps.

The previous Monash GitHub mirror went stale — the maintained host has
been Zenodo since the original 2021 publication; we now point straight
at the citable record.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from benchmarks.core import Dataset

_CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache" / "nn5"

# Zenodo record 4656117. We use the records/ form (records/ is the
# current Zenodo URL scheme; record/ still 301-redirects but takes an
# extra hop). Direct file URL — the zip contains a single .tsf.
_NN5_URL = (
    "https://zenodo.org/records/4656117/files/"
    "nn5_daily_dataset_without_missing_values.zip"
)
_NN5_ZIP = "nn5_daily_dataset_without_missing_values.zip"
_NN5_TSF = "nn5_daily_dataset_without_missing_values.tsf"

# NN5's published forecast horizon is 56 days. We expose the full
# 56-day test split per series; the runner truncates per-call.
_TEST_HORIZON = 56


def _ensure_cached() -> Path:
    """Download NN5 zip to the cache (idempotent), return zip path."""
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cached = _CACHE_ROOT / _NN5_ZIP
    if cached.exists() and cached.stat().st_size > 0:
        return cached
    tmp = cached.with_suffix(cached.suffix + ".part")
    # The runner is patient — Zenodo is rate-limited but reliable.
    # We let urllib bubble HTTP errors so the user sees the actual
    # cause if Zenodo is briefly down.
    urllib.request.urlretrieve(_NN5_URL, tmp)
    tmp.rename(cached)
    return cached


def _parse_tsf(text: str) -> dict[str, np.ndarray]:
    """Parse a Monash ``.tsf`` file into ``{series_id: float64 array}``.

    The .tsf format is documented at
    https://github.com/rakshitha123/TSForecasting (utils/data_loader.py).
    Header lines start with ``@`` and declare attributes / metadata;
    after a single ``@data`` marker each remaining line is one series:

        <attr_value_1>:<attr_value_2>:...:<value_1>,<value_2>,...

    For NN5 the attributes are (series_name, start_timestamp), so the
    series identifier lives in the FIRST colon-separated field. The
    last field is always the comma-separated value vector.

    We ignore the timestamp because the benchmark only cares about the
    raw series and its seasonality (declared elsewhere as 7 for NN5).
    """
    out: dict[str, np.ndarray] = {}
    in_data = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not in_data:
            if line.lower() == "@data":
                in_data = True
            continue

        # In-data line: split on colons. The series id is field 0; the
        # value vector is the LAST field. Anything between is metadata
        # we don't need (just the start timestamp for NN5).
        parts = line.split(":")
        if len(parts) < 2:
            continue
        series_id = parts[0]
        values_str = parts[-1]
        try:
            # Empty cells are theoretically allowed in .tsf but the
            # NN5 "without missing values" variant guarantees none.
            values = np.fromstring(values_str, sep=",", dtype=np.float64)
        except ValueError:
            continue
        if values.size == 0:
            continue
        out[series_id] = values
    return out


def load_nn5_daily() -> Iterable[Dataset]:
    """Yield NN5 Daily series (111 total, seasonality 7).

    Train/test split: last ``_TEST_HORIZON=56`` observations are held
    out per series, matching the official NN5 evaluation protocol that
    Chronos uses for its published zero-shot results.

    Skip rules:
        - Series shorter than horizon + 14 (two seasonal cycles of
          training context): too thin to evaluate any forecaster.
        - Constant or non-finite series: degenerate, would NaN MASE.
    """
    zip_path = _ensure_cached()
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Some Monash zips ship with arbitrary inner names; locate the
        # .tsf rather than hard-coding to be robust to renames.
        tsf_name = next(
            (n for n in zf.namelist() if n.endswith(".tsf")),
            _NN5_TSF,
        )
        with zf.open(tsf_name) as fh:
            tsf_text = io.TextIOWrapper(fh, encoding="utf-8").read()

    series_dict = _parse_tsf(tsf_text)
    for series_id in sorted(series_dict.keys()):
        values = series_dict[series_id]
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
