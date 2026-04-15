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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from the_similarity.synthetic.contracts import (
    FidelityReport,
    PrivacyReport,
    SyntheticDataset,
    UtilityReport,
)

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


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_source(path: Path) -> "Any":
    """Load a .csv or .parquet file into a pandas DataFrame.

    pandas is a first-party dep (see pyproject.toml); importing here keeps
    the module import cheap for tools that only parse ``--help``.
    """
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input suffix {suffix!r}; use .csv or .parquet")


def run_dir_name(generator: str, seed: int, now: Optional[datetime] = None) -> str:
    """Canonical run-directory name: ``<generator>-<seed>-<YYYYMMDD-HHMMSS>``.

    UTC timestamp, seconds resolution. ``now`` is injectable so tests can
    pin a deterministic value.
    """
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"{generator}-{seed}-{ts}"


# ---------------------------------------------------------------------------
# Lazy imports for parallel-PR dependencies
# ---------------------------------------------------------------------------


_MISSING_DEPS_MSG = (
    "Synthetic pipeline dependency not found: {name}. "
    "Run after dependent PRs merge (generator/fidelity/privacy/utility)."
)


def build_generator(name: str) -> "Any":
    """Resolve a generator name to an instantiated generator object.

    Imports are deferred so this module stays importable even when sibling
    PRs have not yet landed -- the failure surfaces as a clear message at
    pipeline run time rather than at ``python -m`` load time.
    """
    try:
        # Standard names agreed with the sibling generator agent.
        from the_similarity.synthetic.generators import (  # type: ignore[import-not-found]
            BlockBootstrapGenerator,
            RegimeBlockBootstrapGenerator,
        )
    except ImportError as exc:  # pragma: no cover - exercised only before merge
        raise RuntimeError(_MISSING_DEPS_MSG.format(name="generators")) from exc

    if name == "block":
        return BlockBootstrapGenerator()
    if name == "regime-block":
        return RegimeBlockBootstrapGenerator()
    raise ValueError(f"Unknown generator {name!r}")


def run_scorecards(
    real: SyntheticDataset, synth: SyntheticDataset
) -> "tuple[Optional[FidelityReport], Optional[PrivacyReport], Optional[UtilityReport]]":
    """Run Fidelity/Privacy/Utility scorecards, tolerating missing siblings.

    Each scorecard is imported and executed independently so one missing
    dependency does not cascade -- the returned tuple has ``None`` for any
    scorecard whose implementation is not yet available.
    """
    fidelity: Optional[FidelityReport] = None
    privacy: Optional[PrivacyReport] = None
    utility: Optional[UtilityReport] = None

    try:
        from the_similarity.synthetic.fidelity import (  # type: ignore[import-not-found]
            FidelityScorecard,
        )
        fidelity = FidelityScorecard().evaluate(real, synth)
    except ImportError:
        print(_MISSING_DEPS_MSG.format(name="fidelity"), file=sys.stderr)

    try:
        from the_similarity.synthetic.privacy import (  # type: ignore[import-not-found]
            PrivacyScorecard,
        )
        privacy = PrivacyScorecard().evaluate(real, synth)
    except ImportError:
        print(_MISSING_DEPS_MSG.format(name="privacy"), file=sys.stderr)

    try:
        from the_similarity.synthetic.utility import (  # type: ignore[import-not-found]
            UtilityScorecard,
        )
        utility = UtilityScorecard().evaluate(real, synth)
    except ImportError:
        print(_MISSING_DEPS_MSG.format(name="utility"), file=sys.stderr)

    return fidelity, privacy, utility
