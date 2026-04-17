"""Multi-symbol parameter sweep for finance benchmarks.

Runs a Cartesian product of symbols x window_sizes x seeds through the
backtest engine, collecting results into a unified list. Each combo is
executed sequentially to keep resource usage predictable and results
deterministic.

The sweep produces:
- A list of result dicts (programmatic API)
- A ``sweep_results.json`` file (when ``out_dir`` is specified)

Design notes
------------
- Sequential execution is intentional: the backtest itself already
  parallelises across trials (via ``n_workers``), so sweeping in parallel
  would over-subscribe CPU cores and hurt throughput on most machines.
- Each combo re-loads data via :func:`benchmark.run_benchmark`, which
  caches the synthetic fallback cheaply. Real CSV loads are I/O-bound
  and fast enough for the expected sweep sizes (< 50 combos).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def run_sweep(
    symbols: List[str],
    window_sizes: List[int],
    seeds: List[int],
    timeframe: str = "daily",
    forward_bars: int = 20,
    n_trials: int = 50,
    register: bool = False,
    out_dir: Optional[str] = None,
    methods: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Run a Cartesian-product sweep of backtest configurations.

    Parameters
    ----------
    symbols : list of str
        Ticker symbols to benchmark (e.g. ["SPY", "QQQ"]).
    window_sizes : list of int
        Query window lengths to sweep.
    seeds : list of int
        RNG seeds to sweep.
    timeframe : str
        Data timeframe passed to each benchmark run (default "daily").
    forward_bars : int
        Projection horizon in bars (default 20).
    n_trials : int
        Walk-forward trials per combo (default 50).
    register : bool
        If True, register each run in the platform registry.
    out_dir : str or None
        Output directory for ``sweep_results.json``. None = no file output.
    methods : list of str or None
        Subset of methods to use (default: all).

    Returns
    -------
    list of dict
        One result dict per combo, each containing: symbol, window_size,
        seed, hit_rate, crps, mean_error, coverage, sharpe, trust_score,
        and all other fields from :func:`benchmark.run_benchmark`.

    Notes
    -----
    The function imports :func:`benchmark.run_benchmark` lazily to avoid
    circular imports at module level (both modules are in the same package).
    """
    from the_similarity.finance.benchmark import run_benchmark

    # Compute total combos for progress reporting
    total = len(symbols) * len(window_sizes) * len(seeds)
    results: List[Dict[str, Any]] = []
    idx = 0

    for symbol in symbols:
        for window_size in window_sizes:
            for seed in seeds:
                idx += 1
                print(
                    f"  [{idx}/{total}] {symbol} w={window_size} seed={seed}",
                    file=sys.stderr,
                )
                result = run_benchmark(
                    symbol=symbol,
                    timeframe=timeframe,
                    window_size=window_size,
                    forward_bars=forward_bars,
                    n_trials=n_trials,
                    seed=seed,
                    register=register,
                    # Don't write per-combo artifacts; the sweep writes one
                    # consolidated file at the end.
                    out_dir=None,
                    methods=methods,
                )

                # Add a trust_score: composite of hit_rate and crps.
                # Trust = hit_rate * (1 - min(crps, 1.0)) — a simple
                # heuristic that rewards both directional accuracy and
                # calibrated probability forecasts. Bounded [0, 1].
                crps_val = result.get("crps", 1.0)
                hit_val = result.get("hit_rate", 0.5)
                result["trust_score"] = round(hit_val * (1.0 - min(crps_val, 1.0)), 4)

                results.append(result)

    # Write consolidated sweep results if output directory is specified
    if out_dir:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        results_path = out_path / "sweep_results.json"
        results_path.write_text(
            json.dumps(results, indent=2, sort_keys=False, default=str),
            encoding="utf-8",
        )
        print(f"  Sweep results written to {results_path}", file=sys.stderr)

    return results


__all__ = ["run_sweep"]
