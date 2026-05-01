"""Core dataclasses and protocols for the benchmark harness.

This module defines the FOUR public types every dataset loader, system
adapter, and metric consumer has to speak:

- ``Dataset`` — a single (train, test) pair with metadata.
- ``Forecast`` — a triple of percentile arrays (P10, P50, P90) covering a
  fixed forecast horizon.
- ``System`` — a Protocol for any forecaster the harness can drive.
- ``Result`` — the row written to the JSONL output for the report layer.

Why Protocol (and not ABC) for System?
    The engine adapter is plain numpy → numpy and never inherits anywhere.
    Using ``typing.Protocol`` lets system adapters stay decoupled from the
    benchmark package — they only need to expose ``name`` and
    ``forecast(...)``. This keeps unit tests trivially substitutable
    (a ``types.SimpleNamespace`` works as a System).

Numerical contract (enforced by metrics.py + tests):
    - All array fields are 1-D ``np.ndarray`` with dtype ``float64``.
    - ``Forecast.p10/p50/p90`` MUST share the same length == horizon.
    - ``Dataset.train`` and ``Dataset.test`` are level-space (raw values),
      NOT returns. The systems decide internally whether to differentiate.
    - Empty arrays are forbidden — loaders MUST drop short series before
      yielding them. Tests assert this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class Dataset:
    """A single forecast benchmark instance.

    Fields:
        name: Dataset family name (e.g., ``"m4_daily"``, ``"nn5_daily"``,
            ``"spy_daily"``). Used for grouping in the report.
        series_id: Per-series identifier inside the dataset (e.g., the M4
            series code ``"D1"``). Used to deduplicate completed runs in
            the resume layer.
        train: 1-D float64 array of in-sample observations.
        test:  1-D float64 array of held-out future observations. May be
            shorter than the harness horizon — the runner truncates the
            forecast to ``min(horizon, len(test))`` before scoring.
        frequency: Pandas-style frequency code (``"D"``, ``"H"``, etc.).
            Informational only; the runner does not resample.
        seasonality: Integer period used by the seasonal-naive baseline
            AND by MASE's denominator. For M4 Daily this is 7, M4 Hourly
            is 24, NN5 Daily is 7, SPY daily is 5 (trading week).
    """

    name: str
    series_id: str
    train: np.ndarray
    test: np.ndarray
    frequency: str
    seasonality: int


@dataclass
class Forecast:
    """Probabilistic point forecast over a fixed horizon.

    The harness deliberately fixes the cone to (P10, P50, P90) — three
    percentiles is the minimum needed for a CRPS approximation and
    matches what the published baselines (Chronos, etc.) most often
    report. Systems with richer cones must downsample to these three.

    Invariant: ``len(p10) == len(p50) == len(p90) == horizon``.
    """

    p10: np.ndarray
    p50: np.ndarray
    p90: np.ndarray


class System(Protocol):
    """Forecast adapter contract.

    The runner calls ``system.forecast(train, horizon, seasonality)`` and
    expects a populated :class:`Forecast`. ``name`` shows up verbatim in
    the JSONL output so it must be stable and human-readable.

    Adapters MUST be deterministic given a fixed numpy random state — the
    runner does not seed for them. Use ``np.random.default_rng(seed)``
    locally if your method is stochastic.
    """

    name: str

    def forecast(
        self,
        train: np.ndarray,
        horizon: int,
        seasonality: int,
    ) -> Forecast:  # pragma: no cover - Protocol stub
        ...


@dataclass
class Result:
    """One scored forecast — the JSONL row written to ``raw.jsonl``.

    The schema is shared with the parallel report agent. Every field is
    JSON-native (no numpy scalars), enforced by the runner before the
    line is appended.

    Field meanings (see ``benchmarks/metrics.py`` for exact formulas):
        mae:                Mean absolute error of P50 vs actuals.
        smape:              Symmetric MAPE of P50 vs actuals (percent, 0-200).
        crps:               Discrete CRPS approximation across (P10, P50, P90).
        mase:               Mean absolute scaled error using seasonal-naive
                            denominator computed on the train series.
        coverage_p10_p90:   Empirical fraction of actuals inside [P10, P90].
                            Target ≈ 0.80.
        query_ms:           Median wall-clock of three ``forecast()`` calls.
        peak_mb:            Peak heap allocation observed via ``tracemalloc``
                            during the timed forecast call.
    """

    dataset: str
    series_id: str
    system: str
    horizon: int
    mae: float
    smape: float
    crps: float
    mase: float
    coverage_p10_p90: float
    query_ms: float
    peak_mb: float
