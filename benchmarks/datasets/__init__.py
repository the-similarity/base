"""Dataset loaders for the benchmark harness.

Each module exposes one or more ``Iterable[Dataset]`` callables. Loaders
are responsible for:

- Caching raw downloads under ``benchmarks/cache/`` (gitignored).
- Yielding deterministic series subsets — fixed seed, fixed first-N
  ordering — so benchmark runs are reproducible across machines.
- Filtering out pathological series (length < 2 * seasonality, all
  zeros, all NaN) BEFORE yielding. The runner trusts loaders.

The ``ALL_LOADERS`` mapping is consumed by the CLI (``--datasets``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from benchmarks.core import Dataset
from benchmarks.datasets.finance import load_spy_daily
from benchmarks.datasets.m4 import load_m4_daily, load_m4_hourly
from benchmarks.datasets.nn5 import load_nn5_daily

ALL_LOADERS: dict[str, Callable[[], Iterable[Dataset]]] = {
    "m4_daily": load_m4_daily,
    "m4_hourly": load_m4_hourly,
    "nn5_daily": load_nn5_daily,
    "spy_daily": load_spy_daily,
}

__all__ = [
    "ALL_LOADERS",
    "load_m4_daily",
    "load_m4_hourly",
    "load_nn5_daily",
    "load_spy_daily",
]
