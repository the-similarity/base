"""Finance benchmark v2 — programmatic single-run + sweep example.

Demonstrates how to:
1. Run a single benchmark programmatically via ``run_benchmark()``.
2. Run a multi-symbol sweep via ``run_sweep()``.
3. Query results from the platform registry after registration.

Usage
-----
    python examples/finance_benchmark_v2.py

The script is self-contained — it uses synthetic data (no CSV files
required) and a temporary registry database so it leaves no side effects.

Design notes
------------
- Uses tiny trial counts (n_trials=3) for speed. A real benchmark would
  use n_trials=50+ for statistically meaningful results.
- Demonstrates both the programmatic API and how the CLI is structured
  behind the scenes — the CLI is just a thin wrapper around these same
  functions.
"""

from __future__ import annotations

import os
import sys
import tempfile

# Make the example runnable directly from the repo root without installation.
_THIS = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main() -> None:
    print("=" * 70)
    print("Finance Benchmark v2 — Programmatic Example")
    print("=" * 70)

    # Use a temporary directory so artifacts don't pollute the repo
    with tempfile.TemporaryDirectory() as tmpdir:
        # ---------------------------------------------------------------
        # 1. SINGLE BENCHMARK — one symbol, one config
        # ---------------------------------------------------------------
        print("\n[1/3] Running single benchmark (SPY, window=40, 3 trials)...")
        from the_similarity.finance.benchmark import run_benchmark

        result = run_benchmark(
            symbol="SPY",
            window_size=40,
            forward_bars=20,
            n_trials=3,  # tiny for demo speed
            seed=42,
            register=False,  # no registry for this one
            out_dir=os.path.join(tmpdir, "single"),
            methods=["dtw", "pearson_warped"],  # fast subset
        )
        print(f"  hit_rate    = {result['hit_rate']:.1%}")
        print(f"  crps        = {result['crps']:.4f}")
        print(f"  elapsed     = {result['elapsed_seconds']}s")

        # ---------------------------------------------------------------
        # 2. MULTI-SYMBOL SWEEP — 2 symbols x 2 window sizes x 1 seed
        # ---------------------------------------------------------------
        print("\n[2/3] Running sweep (2 symbols x 2 windows x 1 seed)...")
        from the_similarity.finance.sweep import run_sweep

        sweep_results = run_sweep(
            symbols=["SPY", "QQQ"],
            window_sizes=[30, 40],
            seeds=[42],
            n_trials=3,  # tiny for demo speed
            out_dir=os.path.join(tmpdir, "sweep"),
            methods=["dtw", "pearson_warped"],
        )

        print(f"\n  Sweep produced {len(sweep_results)} results:")
        for r in sweep_results:
            print(
                f"    {r['symbol']:<6} w={r['window_size']:>3} "
                f"hit={r['hit_rate']:.1%}  crps={r['crps']:.4f}  "
                f"trust={r['trust_score']:.4f}"
            )

        # ---------------------------------------------------------------
        # 3. REGISTRY INTEGRATION — register + query
        # ---------------------------------------------------------------
        print("\n[3/3] Registry integration demo...")

        # Point the registry at a temp DB so we don't touch the real one
        tmp_db = os.path.join(tmpdir, "test_registry.db")
        os.environ["THE_SIMILARITY_REGISTRY_DB"] = tmp_db

        # Run a benchmark with registration enabled
        reg_result = run_benchmark(
            symbol="SPY",
            window_size=40,
            forward_bars=20,
            n_trials=3,
            seed=42,
            register=True,
            methods=["dtw", "pearson_warped"],
        )

        run_id = reg_result.get("run_id")
        if run_id:
            print(f"  Registered run: {run_id}")

            # Query the registry to retrieve the registered run
            from the_similarity.platform.registry import RunRegistry

            with RunRegistry(tmp_db) as registry:
                artifact = registry.get(run_id)
                if artifact:
                    print(f"  Retrieved from registry: kind={artifact.kind.value}")
                    print(f"  Summary hit_rate: {artifact.summary.get('hit_rate')}")
                else:
                    print("  (could not retrieve — unexpected)")
        else:
            print("  (registration did not return a run_id)")

        # Clean up the env var
        del os.environ["THE_SIMILARITY_REGISTRY_DB"]

    print("\nDone.")


if __name__ == "__main__":
    main()
