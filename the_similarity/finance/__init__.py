"""Finance benchmark and sweep tooling for The Similarity.

This package provides CLI and programmatic interfaces for running
walk-forward backtests on financial data and sweeping across parameter
combinations (symbols, window sizes, seeds).

Modules
-------
- ``benchmark`` — Single-run benchmark CLI and runner.
- ``sweep`` — Cartesian-product sweep across symbols x window_sizes x seeds.

CLI usage::

    # Single benchmark
    python -m the_similarity.finance.benchmark run --symbol SPY --n-trials 50

    # Multi-symbol sweep
    python -m the_similarity.finance.benchmark sweep --symbols SPY,QQQ --window-sizes 30,60

    # Shortcut (routes to benchmark CLI)
    python -m the_similarity.finance
"""

from the_similarity.finance.benchmark import run_benchmark
from the_similarity.finance.sweep import run_sweep

__all__ = ["run_benchmark", "run_sweep"]
