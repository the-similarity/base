"""Finance subpackage — benchmarks, sweeps, review artifacts, risk flags, and signal summaries.

This package provides:

1. **Benchmark & sweep tooling** — CLI and programmatic interfaces for running
   walk-forward backtests on financial data and sweeping across parameter
   combinations (symbols, window sizes, seeds).

2. **Review artifact layer** — Structured artifacts that sit between the raw
   backtest outputs (see ``the_similarity/core/backtester.py``) and the
   customer-facing API (see ``the-similarity-api/app/platform_routes.py``).

Modules
-------
- ``benchmark`` — Single-run benchmark CLI and runner.
- ``sweep`` — Cartesian-product sweep across symbols x window_sizes x seeds.
- ``review`` — ReviewArtifact and ReviewStatus for review lifecycle.
- ``risk_flags`` — Auto-detect risk conditions from BacktestReport summaries.
- ``signal_summary`` — One-line human-readable summaries of finance runs.

CLI usage::

    # Single benchmark
    python -m the_similarity.finance.benchmark run --symbol SPY --n-trials 50

    # Multi-symbol sweep
    python -m the_similarity.finance.benchmark sweep --symbols SPY,QQQ --window-sizes 30,60

    # Shortcut (routes to benchmark CLI)
    python -m the_similarity.finance
"""

from the_similarity.finance.benchmark import run_benchmark
from the_similarity.finance.presets import (
    MACRO_US_CORREIA_2015,
    FeaturePreset,
    MacroVariable,
    get_preset,
    list_presets,
)
from the_similarity.finance.review import ReviewArtifact, ReviewStatus
from the_similarity.finance.risk_flags import detect_risk_flags
from the_similarity.finance.signal_summary import generate_signal_summary
from the_similarity.finance.sweep import run_sweep

__all__ = [
    "MACRO_US_CORREIA_2015",
    "FeaturePreset",
    "MacroVariable",
    "ReviewArtifact",
    "ReviewStatus",
    "detect_risk_flags",
    "generate_signal_summary",
    "get_preset",
    "list_presets",
    "run_benchmark",
    "run_sweep",
]
