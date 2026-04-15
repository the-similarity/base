"""Batch CLI runner for the synthetic pipeline.

Invoke as ``python -m the_similarity.synthetic.cli``. Loads a source series,
fits a generator, samples ``n`` synthetic rows, runs Fidelity / Privacy /
Utility scorecards, and writes artifacts (real/synth parquet, scorecard.json,
report.md, provenance.json) under a run directory keyed by
``<generator>-<seed>-<YYYYMMDD-HHMMSS>``.

Exit code
---------
- ``0`` if every present scorecard reports ``passed=True`` AND every threshold
  flag (``--threshold-*``) is satisfied.
- ``1`` otherwise.
"""
from __future__ import annotations

import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


GENERATOR_CHOICES = ("block", "regime-block")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the batch CLI.

    Exposed at module scope so tests can exercise parsing without invoking
    :func:`main` or touching the filesystem.
    """
    p = argparse.ArgumentParser(
        prog="python -m the_similarity.synthetic.cli",
        description=(
            "Run the synthetic-data pipeline: load source -> fit generator -> "
            "sample -> score fidelity/privacy/utility -> write artifacts."
        ),
    )
    p.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to source data (.csv or .parquet). Rows are timesteps.",
    )
    p.add_argument(
        "--n",
        required=True,
        type=int,
        help="Number of synthetic rows (timesteps) to generate.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed for reproducible sampling (default: 0).",
    )
    p.add_argument(
        "--generator",
        choices=GENERATOR_CHOICES,
        default="block",
        help="Which generator to use (default: block).",
    )
    p.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output root directory. A run subdir is created under it.",
    )
    p.add_argument(
        "--threshold-fidelity",
        type=float,
        default=None,
        help="Optional. Minimum FidelityReport.overall_score to pass.",
    )
    p.add_argument(
        "--threshold-privacy",
        type=float,
        default=None,
        help="Optional. Minimum PrivacyReport.overall_score to pass.",
    )
    p.add_argument(
        "--threshold-utility",
        type=float,
        default=None,
        help=(
            "Optional. Maximum UtilityReport.transfer_gap to pass "
            "(lower gap = better utility)."
        ),
    )
    return p
