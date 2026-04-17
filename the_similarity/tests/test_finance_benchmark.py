"""Tests for the finance benchmark and sweep modules.

Covers:
- Single benchmark with tiny trial count completes without error.
- Sweep with 2 symbols x 1 window x 1 seed produces 2 results.
- CLI ``--help`` exits 0.
- Output files are written to temp dir.
- Register flag creates a registry entry (uses temp DB).

All tests use small trial counts (n_trials=3) and a fast method subset
(dtw + pearson_warped) to keep runtime under a few seconds each.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_out(tmp_path: Path) -> str:
    """Return a temporary output directory path as a string."""
    return str(tmp_path / "bench_out")


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    """Return a temporary registry DB path and set the env var.

    Cleans up the env var after the test to avoid polluting other tests.
    """
    db_path = str(tmp_path / "test_registry.db")
    os.environ["THE_SIMILARITY_REGISTRY_DB"] = db_path
    yield db_path
    # Cleanup: remove the env var so subsequent tests use their own DB
    os.environ.pop("THE_SIMILARITY_REGISTRY_DB", None)


# Fast method subset — only DTW + Pearson to keep tests quick.
_FAST_METHODS = ["dtw", "pearson_warped"]


# ---------------------------------------------------------------------------
# Single benchmark tests
# ---------------------------------------------------------------------------


class TestRunBenchmark:
    """Tests for :func:`run_benchmark`."""

    def test_single_benchmark_completes(self, tmp_out: str) -> None:
        """A single benchmark with tiny trial count completes without error."""
        from the_similarity.finance.benchmark import run_benchmark

        result = run_benchmark(
            symbol="SPY",
            window_size=40,
            forward_bars=20,
            n_trials=3,
            seed=42,
            register=False,
            out_dir=tmp_out,
            methods=_FAST_METHODS,
        )

        # Verify the result dict has expected keys
        assert "hit_rate" in result
        assert "crps" in result
        assert "mean_error" in result
        assert "coverage" in result
        assert "n_valid_trials" in result
        assert "elapsed_seconds" in result
        assert result["symbol"] == "SPY"
        assert result["seed"] == 42

        # hit_rate should be between 0 and 1
        assert 0.0 <= result["hit_rate"] <= 1.0

    def test_output_files_written(self, tmp_out: str) -> None:
        """Benchmark writes JSON report and markdown summary to output dir."""
        from the_similarity.finance.benchmark import run_benchmark

        run_benchmark(
            symbol="SPY",
            window_size=40,
            forward_bars=20,
            n_trials=3,
            seed=42,
            out_dir=tmp_out,
            methods=_FAST_METHODS,
        )

        out_path = Path(tmp_out)
        assert (out_path / "benchmark_report.json").exists()
        assert (out_path / "benchmark_summary.md").exists()

        # Verify JSON is valid and contains expected fields
        report = json.loads((out_path / "benchmark_report.json").read_text())
        assert report["symbol"] == "SPY"
        assert "hit_rate" in report
        assert "calibration" in report

        # Verify markdown is non-empty and has a title
        md = (out_path / "benchmark_summary.md").read_text()
        assert "Finance Benchmark" in md
        assert "SPY" in md

    def test_register_creates_registry_entry(self, tmp_db: str) -> None:
        """The --register flag creates a registry entry in the platform DB."""
        from the_similarity.finance.benchmark import run_benchmark

        result = run_benchmark(
            symbol="SPY",
            window_size=40,
            forward_bars=20,
            n_trials=3,
            seed=42,
            register=True,
            methods=_FAST_METHODS,
        )

        # Should have a run_id
        assert "run_id" in result
        run_id = result["run_id"]

        # Verify the run exists in the registry
        from the_similarity.platform.registry import RunRegistry

        with RunRegistry(tmp_db) as registry:
            artifact = registry.get(run_id)
            assert artifact is not None
            assert artifact.summary.get("pillar") == "finance"
            assert artifact.summary.get("hit_rate") is not None

    def test_custom_methods(self, tmp_out: str) -> None:
        """Benchmark respects a custom methods subset."""
        from the_similarity.finance.benchmark import run_benchmark

        result = run_benchmark(
            symbol="SPY",
            window_size=40,
            forward_bars=20,
            n_trials=3,
            seed=42,
            out_dir=tmp_out,
            methods=["dtw"],
        )

        # Should complete without error with a single method
        assert result["n_valid_trials"] + result["n_skipped_trials"] == 3


# ---------------------------------------------------------------------------
# Sweep tests
# ---------------------------------------------------------------------------


class TestRunSweep:
    """Tests for :func:`run_sweep`."""

    def test_sweep_two_symbols(self, tmp_out: str) -> None:
        """Sweep with 2 symbols x 1 window x 1 seed produces 2 results."""
        from the_similarity.finance.sweep import run_sweep

        results = run_sweep(
            symbols=["SPY", "QQQ"],
            window_sizes=[40],
            seeds=[42],
            n_trials=3,
            out_dir=tmp_out,
            methods=_FAST_METHODS,
        )

        assert len(results) == 2
        symbols = {r["symbol"] for r in results}
        assert symbols == {"SPY", "QQQ"}

        # Each result should have a trust_score
        for r in results:
            assert "trust_score" in r
            assert 0.0 <= r["trust_score"] <= 1.0

    def test_sweep_writes_json(self, tmp_out: str) -> None:
        """Sweep writes sweep_results.json to output directory."""
        from the_similarity.finance.sweep import run_sweep

        run_sweep(
            symbols=["SPY"],
            window_sizes=[40],
            seeds=[42],
            n_trials=3,
            out_dir=tmp_out,
            methods=_FAST_METHODS,
        )

        results_path = Path(tmp_out) / "sweep_results.json"
        assert results_path.exists()

        data = json.loads(results_path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["symbol"] == "SPY"

    def test_sweep_cartesian_product(self) -> None:
        """Sweep with 2 symbols x 2 windows x 2 seeds produces 8 results."""
        from the_similarity.finance.sweep import run_sweep

        results = run_sweep(
            symbols=["SPY", "QQQ"],
            window_sizes=[30, 40],
            seeds=[42, 314],
            n_trials=3,
            methods=_FAST_METHODS,
        )

        assert len(results) == 8


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for the benchmark CLI (argparse)."""

    def test_help_exits_zero(self) -> None:
        """CLI --help exits with code 0."""
        result = subprocess.run(
            [sys.executable, "-m", "the_similarity.finance.benchmark", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert (
            "finance benchmark" in result.stdout.lower()
            or "benchmark" in result.stdout.lower()
        )

    def test_run_help_exits_zero(self) -> None:
        """CLI run --help exits with code 0."""
        result = subprocess.run(
            [sys.executable, "-m", "the_similarity.finance.benchmark", "run", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--symbol" in result.stdout

    def test_sweep_help_exits_zero(self) -> None:
        """CLI sweep --help exits with code 0."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "the_similarity.finance.benchmark",
                "sweep",
                "--help",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--symbols" in result.stdout

    def test_finance_module_help_exits_zero(self) -> None:
        """``python -m the_similarity.finance --help`` exits 0."""
        result = subprocess.run(
            [sys.executable, "-m", "the_similarity.finance", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_parser_structure(self) -> None:
        """Parser has run and sweep subcommands with expected args."""
        from the_similarity.finance.benchmark import _build_parser

        parser = _build_parser()
        # Verify parser can parse run args without error
        args = parser.parse_args(["run", "--symbol", "QQQ", "--n-trials", "5"])
        assert args.symbol == "QQQ"
        assert args.n_trials == 5

        # Verify parser can parse sweep args
        args = parser.parse_args(
            ["sweep", "--symbols", "SPY,QQQ", "--window-sizes", "30,60"]
        )
        assert args.symbols == "SPY,QQQ"
        assert args.window_sizes == "30,60"
