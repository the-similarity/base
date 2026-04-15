"""Finaliser — read existing per-(slice, arm) JSONs, compute verdict, write
markdown report, append ledger entry.

Decoupled from ``run_bench.main`` so a partial sweep's results can still be
consolidated into the scorecard without re-running the engine.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.autoresearch.retrieval_bench.compare import (
    build_comparison_rows,
    decide,
    load_arm_reports,
)
from research.autoresearch.retrieval_bench.ledger import (
    append_ledger_entry,
    build_ledger_entry,
)
from research.autoresearch.retrieval_bench.report import write_markdown_report
from research.autoresearch.retrieval_bench.run_bench import (
    DEFAULT_SPEC,
    LEDGER_PATH,
    REPORTS_DIR,
    _git_sha,
    load_spec,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Finalise a retrieval-bench sweep from existing JSON artefacts."
    )
    parser.add_argument("--spec", default=str(DEFAULT_SPEC))
    parser.add_argument("--reports-dir", default=str(REPORTS_DIR))
    parser.add_argument(
        "--report-path",
        default=str(_REPO_ROOT / "progress" / "autoresearch" / "reports" / "retrieval-bench-v1.md"),
    )
    parser.add_argument("--ledger-path", default=str(LEDGER_PATH))
    parser.add_argument(
        "--n-trials-note", type=int, default=0,
        help="Informational: n_trials used when the sweep was executed."
    )
    parser.add_argument(
        "--seed-note", type=int, action="append", default=[],
        help="Informational: seed(s) used when the sweep was executed."
    )
    args = parser.parse_args(argv)

    spec = load_spec(args.spec)
    grouped = load_arm_reports(args.reports_dir)
    if not grouped:
        parser.error(f"No JSON reports found in {args.reports_dir}")

    rows = build_comparison_rows(grouped, thresholds=spec.thresholds)
    if not rows:
        parser.error(
            "No slices have BOTH arms present — cannot build comparison rows."
        )
    verdict = decide(rows, thresholds=spec.thresholds)

    md_path = write_markdown_report(
        verdict,
        args.report_path,
        benchmark_id=spec.id,
        n_trials=args.n_trials_note,
        seeds=args.seed_note or spec.seeds,
        git_sha=_git_sha(),
    )
    print(f"[report] wrote {md_path}")

    entry = build_ledger_entry(
        verdict,
        benchmark_id=spec.id,
        artefacts=[str(Path(md_path).relative_to(_REPO_ROOT))],
    )
    append_ledger_entry(entry, args.ledger_path)
    print(f"[ledger] appended to {args.ledger_path}  decision={verdict.decision}")

    # Print a terse scorecard for the operator
    print(f"\nVerdict: {verdict.decision.upper()}")
    print(verdict.rationale)
    print(f"Slices: {len(verdict.rows)}")
    print(
        f"CRPS improved in {verdict.slices_crps_improved} slices, "
        f"corr improved in {verdict.slices_corr_improved} slices."
    )
    print(
        f"Mean ΔCRPS = {verdict.mean_d_crps:+.4f}, "
        f"Mean Δcorr = {verdict.mean_d_corr:+.3f}, "
        f"mean runtime ratio = {verdict.mean_runtime_ratio:.1f}x."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
