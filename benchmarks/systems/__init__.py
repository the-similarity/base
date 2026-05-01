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
from benchmarks.systems.naive import SeasonalNaive

ALL_SYSTEMS: dict[str, Callable[[], System]] = {
    "naive": SeasonalNaive,
    "engine": TheSimilarity,
}

# STUMPY is an optional dep — register the adapter only if it imports
# AND its numba/LLVM backing actually loads. On macOS in particular,
# stumpy raises OSError (not ImportError) when its llvmlite shared lib
# is unresolvable, so the guard catches both.
try:  # pragma: no cover - import guard
    import stumpy as _stumpy  # noqa: F401  - probe import + numba load

    from benchmarks.systems.matrix_profile import MatrixProfile

    ALL_SYSTEMS["matrix_profile"] = MatrixProfile
except (ImportError, OSError):  # pragma: no cover
    MatrixProfile = None  # type: ignore[assignment,misc]

__all__ = ["ALL_SYSTEMS", "SeasonalNaive", "TheSimilarity", "MatrixProfile"]
