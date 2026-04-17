"""Finance benchmark CLI — single-run backtest with report generation.

Runnable as ``python -m the_similarity.finance.benchmark`` or imported
programmatically via :func:`run_benchmark`.

Subcommands
-----------
- ``run``  — Execute a single backtest for one symbol/config combo.
- ``sweep`` — Cartesian product sweep (delegates to :mod:`.sweep`).

Output artifacts (written to ``--out`` directory)
-------------------------------------------------
- ``benchmark_report.json`` — Full metrics dict, machine-readable.
- ``benchmark_summary.md``  — Human-readable markdown report.

Design notes
------------
- Data loading: generates synthetic data by default (trending + seasonal +
  noise) so the CLI works out-of-the-box without requiring CSV files. When
  ``--symbol`` is provided AND data files exist at
  ``the_similarity/data/equity/<symbol>/daily/*.csv``, they are loaded. This
  makes the CLI self-contained for CI smoke tests while supporting real data
  in production.
- The ``--register`` flag calls the finance adapter to persist the run in
  the platform registry. Off by default.
- The ``--methods`` flag accepts a comma-separated list of method names to
  restrict the active methods in the backtest config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Synthetic data generator (fallback when no CSV is available)
# ---------------------------------------------------------------------------


def _build_synthetic_history(n: int = 1500, seed: int = 42) -> np.ndarray:
    """Generate synthetic trending + seasonal + noise price series.

    This is the fallback data source when no CSV file is found for the
    requested symbol. The synthetic data has enough structure (trend,
    seasonality, noise) that the analogue search has a non-trivial signal
    to find, making benchmarks meaningful even without real market data.

    Parameters
    ----------
    n : int
        Number of bars to generate.
    seed : int
        RNG seed for reproducibility.

    Returns
    -------
    np.ndarray
        1-D float64 array of synthetic close prices.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=np.float64)
    trend = 100.0 + 0.04 * t
    seasonal = 3.0 * np.sin(t * 0.05) + 1.5 * np.cos(t * 0.13)
    noise = rng.standard_normal(n) * 0.7
    return trend + seasonal + noise


def _load_symbol_data(symbol: str, timeframe: str = "daily") -> np.ndarray:
    """Attempt to load real data for a symbol, falling back to synthetic.

    Looks for CSV files at ``the_similarity/data/equity/<symbol>/<timeframe>/*.csv``.
    If no file is found, generates synthetic data and prints a notice.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "SPY", "QQQ"). Case-insensitive for file lookup.
    timeframe : str
        Subdirectory under the symbol folder (default "daily").

    Returns
    -------
    np.ndarray
        1-D float64 array of close prices.
    """
    # Try to find real data first — look in the package data directory
    # relative to this file, then fall back to the repo root.
    package_dir = Path(__file__).resolve().parent.parent
    data_dir = package_dir / "data" / "equity" / symbol.lower() / timeframe

    if data_dir.exists():
        # Load the first CSV found in the directory
        csvs = sorted(data_dir.glob("*.csv"))
        if csvs:
            try:
                import pandas as pd

                df = pd.read_csv(csvs[0])
                # Try common column names for close price
                for col in ("close", "Close", "adj_close", "Adj Close"):
                    if col in df.columns:
                        values = df[col].dropna().values.astype(np.float64)
                        if len(values) > 100:
                            print(
                                f"  Loaded {len(values)} bars from {csvs[0].name}",
                                file=sys.stderr,
                            )
                            return values
            except Exception:
                pass  # Fall through to synthetic

    # Fallback: synthetic data
    print(
        f"  No data found for {symbol}/{timeframe}, using synthetic data "
        f"(1500 bars)",
        file=sys.stderr,
    )
    return _build_synthetic_history()


# ---------------------------------------------------------------------------
# Core benchmark runner (programmatic API)
# ---------------------------------------------------------------------------


def run_benchmark(
    symbol: str = "SPY",
    timeframe: str = "daily",
    window_size: int = 60,
    forward_bars: int = 20,
    n_trials: int = 50,
    seed: int = 42,
    register: bool = False,
    out_dir: Optional[str] = None,
    methods: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run a single finance backtest and produce a report.

    This is the programmatic entry point — the CLI ``run`` subcommand
    delegates here.

    Parameters
    ----------
    symbol : str
        Ticker symbol to benchmark (default "SPY").
    timeframe : str
        Data timeframe (default "daily").
    window_size : int
        Query window length in bars.
    forward_bars : int
        Projection horizon in bars.
    n_trials : int
        Number of walk-forward trials.
    seed : int
        RNG seed for reproducibility.
    register : bool
        If True, register the run in the platform registry.
    out_dir : str or None
        Output directory for artifacts. None = no file output.
    methods : list of str or None
        Subset of methods to use (default: all).

    Returns
    -------
    dict
        Result dict with keys: symbol, window_size, forward_bars, n_trials,
        seed, hit_rate, crps, mean_error, coverage, interval_score,
        profit_factor, max_drawdown, sharpe, calibration, n_valid_trials,
        n_skipped_trials, elapsed_seconds, and optionally run_id.
    """
    from the_similarity.api import backtest
    from the_similarity.config import Config

    # Build config with optional method restriction
    config_kwargs: Dict[str, Any] = {
        # Use smaller tier sizes for benchmark speed; real production
        # runs can override via a Config object directly.
        "tier1_candidates": 80,
        "tier2_candidates": 6,
        "stride": 5,
    }
    if methods:
        config_kwargs["active_methods"] = methods
    config = Config(**config_kwargs)

    # Load data
    history = _load_symbol_data(symbol, timeframe)

    # Run backtest
    t0 = time.monotonic()
    report = backtest(
        history,
        window_size=window_size,
        forward_bars=forward_bars,
        n_trials=n_trials,
        config=config,
        seed=seed,
        n_workers=1,  # Single worker for deterministic, portable benchmarks
        register=register,
        source_id=symbol.lower(),
    )
    elapsed = time.monotonic() - t0

    # Collect results into a flat dict
    result: Dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "window_size": window_size,
        "forward_bars": forward_bars,
        "n_trials": n_trials,
        "seed": seed,
        "hit_rate": report.hit_rate,
        "crps": report.crps,
        "mean_error": report.mean_error,
        "coverage": report.coverage,
        "interval_score": report.interval_score,
        "profit_factor": float(report.profit_factor)
        if np.isfinite(report.profit_factor)
        else None,
        "max_drawdown": report.max_drawdown,
        "sharpe": float(report.sharpe) if not np.isnan(report.sharpe) else None,
        "calibration": {str(k): v for k, v in report.calibration.items()},
        "n_valid_trials": report.n_valid_trials,
        "n_skipped_trials": report.n_skipped_trials,
        "elapsed_seconds": round(elapsed, 2),
    }

    # Capture run_id if registration happened
    run_id = getattr(report, "run_id", None)
    if run_id:
        result["run_id"] = run_id

    # Write artifacts if output directory is specified
    if out_dir:
        _write_artifacts(result, out_dir)

    return result


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------


def _write_artifacts(result: Dict[str, Any], out_dir: str) -> None:
    """Write benchmark_report.json and benchmark_summary.md to out_dir.

    Creates the output directory if it does not exist. Overwrites any
    existing files — benchmark results are reproducible via seed, so
    overwriting is safe.

    Parameters
    ----------
    result : dict
        The result dict from :func:`run_benchmark`.
    out_dir : str
        Target directory path.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # JSON report — machine-readable full metrics
    report_path = out_path / "benchmark_report.json"
    report_path.write_text(
        json.dumps(result, indent=2, sort_keys=False, default=str),
        encoding="utf-8",
    )

    # Markdown summary — human-readable
    summary_path = out_path / "benchmark_summary.md"
    summary_path.write_text(_format_summary_md(result), encoding="utf-8")

    print(f"  Artifacts written to {out_path}/", file=sys.stderr)


def _format_summary_md(result: Dict[str, Any]) -> str:
    """Render a human-readable markdown summary from a result dict.

    Parameters
    ----------
    result : dict
        The result dict from :func:`run_benchmark`.

    Returns
    -------
    str
        Markdown-formatted summary string.
    """
    lines = [
        f"# Finance Benchmark: {result['symbol']}",
        "",
        "## Parameters",
        "",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| Symbol | {result['symbol']} |",
        f"| Timeframe | {result['timeframe']} |",
        f"| Window Size | {result['window_size']} |",
        f"| Forward Bars | {result['forward_bars']} |",
        f"| Trials | {result['n_trials']} |",
        f"| Seed | {result['seed']} |",
        "",
        "## Results",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Hit Rate | {result['hit_rate']:.1%} |",
        f"| CRPS | {result['crps']:.4f} |",
        f"| Mean Absolute Error | {result['mean_error']:.4f} |",
        f"| Coverage (P10-P90) | {result['coverage']:.1%} |",
        f"| Interval Score | {result['interval_score']:.4f} |",
        f"| Profit Factor | {_fmt_optional(result.get('profit_factor'), '.3f')} |",
        f"| Max Drawdown | {result['max_drawdown']:.4f} |",
        f"| Sharpe (annualised) | {_fmt_optional(result.get('sharpe'), '.3f')} |",
        f"| Valid Trials | {result['n_valid_trials']} |",
        f"| Skipped Trials | {result['n_skipped_trials']} |",
        f"| Elapsed (s) | {result['elapsed_seconds']} |",
        "",
    ]

    # Calibration table
    calib = result.get("calibration", {})
    if calib:
        lines.extend(
            [
                "## Calibration",
                "",
                "| Percentile | Observed | Expected | Delta |",
                "|------------|----------|----------|-------|",
            ]
        )
        for p_str in sorted(calib, key=lambda x: int(x)):
            p = int(p_str)
            observed = calib[p_str]
            expected = p / 100.0
            delta = observed - expected
            lines.append(
                f"| P{p} | {observed:.1%} | {expected:.0%} | {delta:+.1%} |"
            )
        lines.append("")

    # Run ID if registered
    run_id = result.get("run_id")
    if run_id:
        lines.extend(
            [
                "## Registry",
                "",
                f"Run registered: `{run_id}`",
                "",
                "```bash",
                f"python -m the_similarity.platform show {run_id}",
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def _fmt_optional(value: Any, fmt: str) -> str:
    """Format a possibly-None numeric value."""
    if value is None:
        return "N/A"
    return f"{value:{fmt}}"


# ---------------------------------------------------------------------------
# Summary table printer (stdout)
# ---------------------------------------------------------------------------


def _print_summary_table(result: Dict[str, Any]) -> None:
    """Print a concise summary table to stdout.

    Designed for quick terminal inspection after a benchmark run.
    """
    print()
    print("=" * 60)
    print(f"  Finance Benchmark: {result['symbol']}")
    print("=" * 60)
    print(f"  window_size={result['window_size']}  forward_bars={result['forward_bars']}"
          f"  n_trials={result['n_trials']}  seed={result['seed']}")
    print("-" * 60)
    print(f"  hit_rate          : {result['hit_rate']:.1%}")
    print(f"  crps              : {result['crps']:.4f}")
    print(f"  mean_error        : {result['mean_error']:.4f}")
    print(f"  coverage(P10-P90) : {result['coverage']:.1%}")
    print(f"  interval_score    : {result['interval_score']:.4f}")
    pf = result.get("profit_factor")
    print(f"  profit_factor     : {_fmt_optional(pf, '.3f')}")
    print(f"  max_drawdown      : {result['max_drawdown']:.4f}")
    sh = result.get("sharpe")
    print(f"  sharpe(ann.)      : {_fmt_optional(sh, '.3f')}")
    print(f"  valid/skipped     : {result['n_valid_trials']}/{result['n_skipped_trials']}")
    print(f"  elapsed           : {result['elapsed_seconds']}s")

    run_id = result.get("run_id")
    if run_id:
        print(f"  run_id            : {run_id}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# CLI: argparse wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser with ``run`` and ``sweep`` subcommands.

    Kept as a separate function so tests can introspect the parser
    without invoking :func:`main`.
    """
    parser = argparse.ArgumentParser(
        prog="python -m the_similarity.finance.benchmark",
        description="Finance benchmark — single-run backtest and multi-symbol sweep.",
    )
    sub = parser.add_subparsers(dest="command")
    # Make subcommand optional: bare invocation defaults to "run"
    sub.required = False

    # --- run subcommand ---
    p_run = sub.add_parser("run", help="Run a single benchmark.")
    _add_run_args(p_run)

    # --- sweep subcommand ---
    p_sweep = sub.add_parser("sweep", help="Run a multi-symbol parameter sweep.")
    p_sweep.add_argument(
        "--symbols",
        type=str,
        default="SPY",
        help="Comma-separated list of symbols (default: SPY).",
    )
    p_sweep.add_argument(
        "--window-sizes",
        type=str,
        default="60",
        help="Comma-separated window sizes (default: 60).",
    )
    p_sweep.add_argument(
        "--seeds",
        type=str,
        default="42",
        help="Comma-separated seeds (default: 42).",
    )
    p_sweep.add_argument(
        "--timeframe",
        type=str,
        default="daily",
        help="Data timeframe (default: daily).",
    )
    p_sweep.add_argument(
        "--forward-bars",
        type=int,
        default=20,
        help="Projection horizon in bars (default: 20).",
    )
    p_sweep.add_argument(
        "--n-trials",
        type=int,
        default=50,
        help="Number of walk-forward trials per combo (default: 50).",
    )
    p_sweep.add_argument(
        "--register",
        action="store_true",
        help="Register each run in the platform registry.",
    )
    p_sweep.add_argument(
        "--out",
        type=str,
        default="artifacts/finance-sweep/",
        help="Output directory (default: artifacts/finance-sweep/).",
    )
    p_sweep.add_argument(
        "--methods",
        type=str,
        default=None,
        help="Comma-separated subset of methods (default: all).",
    )

    return parser


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    """Add the standard single-run arguments to a parser.

    Factored out so both the ``run`` subcommand and the bare (no
    subcommand) invocation can share the same arg definitions.
    """
    parser.add_argument(
        "--symbol",
        type=str,
        default="SPY",
        help="Ticker symbol (default: SPY).",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="daily",
        help="Data timeframe (default: daily).",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=60,
        help="Query window length (default: 60).",
    )
    parser.add_argument(
        "--forward-bars",
        type=int,
        default=20,
        help="Projection horizon (default: 20).",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=50,
        help="Walk-forward trials (default: 50).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed (default: 42).",
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register run in the platform registry.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="artifacts/finance-benchmark/",
        help="Output directory (default: artifacts/finance-benchmark/).",
    )
    parser.add_argument(
        "--methods",
        type=str,
        default=None,
        help="Comma-separated subset of methods (default: all).",
    )


def _handle_run(args: argparse.Namespace) -> int:
    """Execute the ``run`` subcommand."""
    methods = args.methods.split(",") if args.methods else None

    result = run_benchmark(
        symbol=args.symbol,
        timeframe=args.timeframe,
        window_size=args.window_size,
        forward_bars=args.forward_bars,
        n_trials=args.n_trials,
        seed=args.seed,
        register=args.register,
        out_dir=args.out,
        methods=methods,
    )
    _print_summary_table(result)
    return 0


def _handle_sweep(args: argparse.Namespace) -> int:
    """Execute the ``sweep`` subcommand by delegating to :mod:`.sweep`."""
    from the_similarity.finance.sweep import run_sweep

    symbols = [s.strip() for s in args.symbols.split(",")]
    window_sizes = [int(w.strip()) for w in args.window_sizes.split(",")]
    seeds = [int(s.strip()) for s in args.seeds.split(",")]
    methods = args.methods.split(",") if args.methods else None

    results = run_sweep(
        symbols=symbols,
        window_sizes=window_sizes,
        seeds=seeds,
        timeframe=args.timeframe,
        forward_bars=args.forward_bars,
        n_trials=args.n_trials,
        register=args.register,
        out_dir=args.out,
        methods=methods,
    )

    # Print summary table for all results
    print()
    print("=" * 80)
    print("  Sweep Results")
    print("=" * 80)
    header = f"  {'Symbol':<8} {'WinSz':>5} {'Seed':>5} {'HitRate':>8} {'CRPS':>8} {'Sharpe':>8}"
    print(header)
    print("-" * 80)
    for r in results:
        sharpe_str = f"{r['sharpe']:.3f}" if r.get("sharpe") is not None else "N/A"
        print(
            f"  {r['symbol']:<8} {r['window_size']:>5} {r['seed']:>5} "
            f"{r['hit_rate']:>7.1%} {r['crps']:>8.4f} {sharpe_str:>8}"
        )
    print("=" * 80)
    print(f"  {len(results)} runs completed.")
    print()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Module entry point. Returns an exit code.

    Parameters
    ----------
    argv : list of str or None
        Command-line arguments. Defaults to ``sys.argv[1:]``.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Default to "run" when no subcommand is given
    if args.command is None:
        # Re-parse with "run" prepended
        args = parser.parse_args(["run"] + (list(argv) if argv else sys.argv[1:]))

    if args.command == "run":
        return _handle_run(args)
    elif args.command == "sweep":
        return _handle_sweep(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
