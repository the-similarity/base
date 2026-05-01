"""System adapters for the benchmark harness.

Each adapter is a class with ``name: str`` and a ``forecast(train,
horizon, seasonality)`` method that returns a :class:`benchmarks.core.Forecast`.
Adapters MUST run with their library DEFAULT configuration — no per-
dataset tuning, no clever priors. The whole point of this harness is
to give an honest baseline reading.

Available adapters:
- :class:`benchmarks.systems.naive.SeasonalNaive`
- :class:`benchmarks.systems.matrix_profile.MatrixProfile`
- :class:`benchmarks.systems.engine.TheSimilarity`

The ``ALL_SYSTEMS`` mapping is consumed by the CLI (``--systems``).
``MatrixProfile`` is omitted from ``ALL_SYSTEMS`` if STUMPY is not
importable so a thin install can still run naive + engine.
"""

from __future__ import annotations

from collections.abc import Callable

from benchmarks.core import System
from benchmarks.systems.engine import TheSimilarity

# MatrixProfile now ships a numpy MASS fallback, so it loads
# unconditionally — STUMPY is preferred at runtime when available, but
# its absence no longer disables the adapter. Keeping the import at
# module top-level (not lazy) makes the adapter discoverable in tests
# and CLI on every platform.
from benchmarks.systems.matrix_profile import MatrixProfile
from benchmarks.systems.naive import SeasonalNaive

ALL_SYSTEMS: dict[str, Callable[[], System]] = {
    "naive": SeasonalNaive,
    "matrix_profile": MatrixProfile,
    "engine": TheSimilarity,
}

__all__ = ["ALL_SYSTEMS", "MatrixProfile", "SeasonalNaive", "TheSimilarity"]
