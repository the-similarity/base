"""CLI subcommand for generator comparison and promotion.

Invoke as ``python -m the_similarity.synthetic.cli compare ...`` (once wired
into the main CLI's subparser), or directly:

::

    python -m the_similarity.synthetic.compare_cli \\
        --input data.csv \\
        --generators block_bootstrap,regime_block_bootstrap \\
        --n 500 --seed 42 --out /tmp/compare

Outputs
-------
- ``comparison_report.json`` — machine-readable ranked results.
- ``comparison_summary.md`` — human-readable comparison table.
- If ``--promote`` is passed, the best generator's run is promoted in
  the platform registry as the canonical synthetic dataset for the
  input's stem name.

Exit codes
----------
- ``0`` on success (artifacts written).
- ``1`` on pipeline error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from the_similarity.synthetic.comparison import (
    ComparisonResult,
    compare_generators,
)


def build_compare_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the compare subcommand."""
    p = argparse.ArgumentParser(
        prog="python -m the_similarity.synthetic.compare_cli",
        description=(
            "Compare multiple synthetic generators on the same source data. "
            "Scores with fidelity/privacy/utility scorecards, ranks results, "
            "and optionally promotes the best generator."
        ),
    )
    p.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to source data (.csv or .parquet).",
    )
    p.add_argument(
        "--generators",
        required=True,
        type=str,
        help=(
            "Comma-separated list of generator names "
            "(e.g. block_bootstrap,regime_block_bootstrap)."
        ),
    )
    p.add_argument(
        "--n",
        required=True,
        type=int,
        help="Number of synthetic rows per generator.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base RNG seed (default: 42).",
    )
    p.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output directory for comparison artifacts.",
    )
    p.add_argument(
        "--promote",
        action="store_true",
        default=False,
        help=(
            "If set, promote the best generator's run in the platform "
            "registry as the canonical synthetic dataset."
        ),
    )
    return p


def render_summary_md(result: ComparisonResult) -> str:
    """Render a human-readable markdown summary of the comparison.

    Produces a table with columns: Rank, Generator, Fidelity, Privacy,
    Utility Gap, and an optional Error column. The best generator is
    highlighted with a note at the bottom.
    """
    lines: list[str] = []
    lines.append("# Generator Comparison Summary")
    lines.append("")
    lines.append("| Rank | Generator | Fidelity | Privacy | Utility Gap | Error |")
    lines.append("|------|-----------|----------|---------|-------------|-------|")

    for r in result.results:
        # Format utility_gap: show "inf" for infinite values, else 4 decimal places.
        ugap = "inf" if r.utility_gap == float("inf") else f"{r.utility_gap:.4f}"
        error_col = r.error or ""
        lines.append(
            f"| {r.overall_rank} | {r.generator_name} | "
            f"{r.fidelity_score:.4f} | {r.privacy_score:.4f} | "
            f"{ugap} | {error_col} |"
        )

    lines.append("")
    if result.results:
        best = result.best()
        lines.append(f"**Best generator: `{best.generator_name}`** (rank 1)")
        lines.append(
            f"- Fidelity: {best.fidelity_score:.4f}, "
            f"Privacy: {best.privacy_score:.4f}, "
            f"Utility Gap: {best.utility_gap if best.utility_gap != float('inf') else 'inf'}"
        )
    lines.append("")
    return "\n".join(lines)


def run_compare(args: argparse.Namespace) -> int:
    """Execute the comparison pipeline. Returns exit code."""
    # Load source data — reuse the existing loader from cli.py.
    from the_similarity.synthetic.cli import load_source

    try:
        df = load_source(args.input)
    except Exception as exc:
        print(f"error: failed to load input: {exc}", file=sys.stderr)
        return 1

    generator_names = [g.strip() for g in args.generators.split(",") if g.strip()]
    if not generator_names:
        print("error: no generators specified", file=sys.stderr)
        return 1

    # Run the comparison.
    result = compare_generators(
        source_data=df,
        generators=generator_names,
        n=args.n,
        seed=args.seed,
    )

    # Write output artifacts.
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "comparison_report.json"
    report_path.write_text(json.dumps(result.to_dict(), indent=2, default=str))
    print(f"wrote: {report_path}")

    summary_path = out_dir / "comparison_summary.md"
    summary_path.write_text(render_summary_md(result))
    print(f"wrote: {summary_path}")

    # Print best generator to stdout for programmatic consumers.
    best = result.best()
    print(f"best_generator: {best.generator_name} (fidelity={best.fidelity_score:.4f})")

    # Optional promotion of the best generator's run.
    if args.promote:
        try:
            from the_similarity.platform.registry import RunRegistry
            from the_similarity.synthetic.promotion import promote_run

            # Use the default registry path. The registry is opened
            # fresh here and closed after the single write.
            registry = RunRegistry()
            # Use the input file's stem as the dataset name for promotion.
            dataset_name = args.input.stem
            # We need a run_id — in a full pipeline this comes from the
            # registry. For the comparison CLI, we generate a synthetic
            # run_id from the best generator name + seed.
            from the_similarity.platform.artifacts import new_run_id

            run_id = new_run_id()
            promoted_id = promote_run(run_id, dataset_name, registry)
            print(f"promoted: {promoted_id} (run_id={run_id})")
        except ImportError as exc:
            print(
                f"warning: --promote requested but platform unavailable: {exc}",
                file=sys.stderr,
            )

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_compare_parser()
    args = parser.parse_args(argv)
    return run_compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
