"""Markdown report writer for the retrieval-bench lane.

Consumes the output of ``compare.decide`` (plus the raw ArmResult rows) and
writes a Markdown scorecard with:

1. YAML-style front matter for metadata
2. Slice-by-slice table of (corr, CRPS, calibration, hit rate, runtime) for
   both arms plus deltas
3. Aggregate summary + keep/discard verdict
4. "Next actions" stub filled from the verdict rationale

The renderer is pure string building — deterministic given the same inputs.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from research.autoresearch.retrieval_bench.compare import ComparisonRow, Verdict


def _fmt_float(v, digits: int = 4) -> str:
    """Format a float for markdown tables; returns '—' for None/NaN."""
    try:
        f = float(v)
    except Exception:  # pragma: no cover
        return "—"
    if f != f:  # NaN
        return "—"
    return f"{f:.{digits}f}"


def _fmt_signed(v: float, digits: int = 3) -> str:
    """Signed float for delta columns (always shows + or -)."""
    return f"{v:+.{digits}f}"


def _slice_row_line(r: ComparisonRow) -> str:
    """Single markdown table row for one slice."""
    a = r.tier1_only
    b = r.tier1_plus_full
    return (
        f"| `{r.slice_id}` "
        f"| {_fmt_float(a['forward_return_correlation'], 3)} "
        f"| {_fmt_float(b['forward_return_correlation'], 3)} "
        f"| {_fmt_signed(r.d_forward_return_correlation, 3)} "
        f"| {_fmt_float(a['crps'], 4)} "
        f"| {_fmt_float(b['crps'], 4)} "
        f"| {_fmt_signed(r.d_crps, 4)} "
        f"| {_fmt_float(a['calibration_error_p10_p90'], 3)} "
        f"| {_fmt_float(b['calibration_error_p10_p90'], 3)} "
        f"| {_fmt_float(a['hit_rate'], 2)} "
        f"| {_fmt_float(b['hit_rate'], 2)} "
        f"| {_fmt_float(a['runtime_seconds']['median'], 2)}s "
        f"| {_fmt_float(b['runtime_seconds']['median'], 2)}s "
        f"| {r.runtime_ratio:.1f}x |"
    )


def render_markdown(
    verdict: Verdict,
    *,
    benchmark_id: str = "retrieval-bench-tiers-v1",
    n_trials: int = 0,
    seeds: Iterable[int] = (42,),
    git_sha: str = "unknown",
) -> str:
    """Render the full markdown report as a string.

    Keeping this pure (string -> string) makes it trivial to snapshot-test.
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    header_lines = [
        f"# Retrieval benchmark — Tier 1 vs Tier 1+2 ablation (`{benchmark_id}`)",
        "",
        f"- Generated: {now}",
        f"- Git SHA: `{git_sha}`",
        f"- Trials per slice: {n_trials}",
        f"- Seeds: {list(seeds)}",
        f"- Baseline arm: `tier1_only` (SAX+MASS → DTW + Pearson)",
        f"- Experiment arm: `tier1_plus_full` (current 9-method default)",
        "",
        "## Decision",
        "",
        f"**Verdict: `{verdict.decision.upper()}`**",
        "",
        f"{verdict.rationale}",
        "",
        f"- Slices with strict CRPS improvement: {verdict.slices_crps_improved} / {len(verdict.rows)}",
        f"- Slices with correlation lift: {verdict.slices_corr_improved} / {len(verdict.rows)}",
        f"- Mean Tier1+2 - Tier1 CRPS delta: {_fmt_signed(verdict.mean_d_crps, 4)}",
        f"- Mean correlation delta: {_fmt_signed(verdict.mean_d_corr, 3)}",
        f"- Mean runtime multiplier: {verdict.mean_runtime_ratio:.1f}x",
        "",
        "## Per-slice scorecard",
        "",
        "Columns: `corr` = forward-return correlation (higher is better),",
        "`CRPS` (lower is better), `cal` = |p10-p90 coverage - 0.80| (lower is better),",
        "`hit` = sign hit rate, `rt_med` = median runtime per query.",
        "",
        "| slice | T1 corr | T1+2 corr | Δcorr | T1 CRPS | T1+2 CRPS | ΔCRPS | T1 cal | T1+2 cal | T1 hit | T1+2 hit | T1 rt | T1+2 rt | rt× |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    body_rows = [_slice_row_line(r) for r in verdict.rows]

    # ---- Next actions ----
    if verdict.decision == "keep":
        next_actions = [
            "## Next actions",
            "",
            "- Keep Tier 1+2 as default retrieval stack (current behaviour).",
            "- Expand sweep to full n_trials and both seeds for the long-form scorecard.",
            "- Drill into slices where CRPS did NOT improve to decide whether Tier 2 "
            "weights can be specialised by regime.",
        ]
    else:
        next_actions = [
            "## Next actions",
            "",
            "- Do NOT change engine defaults from this run — this is measurement,",
            "  not replacement. Keeping the current 9-method stack preserves the",
            "  option value while we investigate.",
            "- Identify which Tier 2 methods individually contribute (next lane:",
            "  per-method ablation — drop one method at a time).",
            "- Consider reducing Tier 2 cost (smaller `tier2_candidates`, feature",
            "  store caching) rather than removing methods outright.",
            "- Re-run with full `n_trials` and both seeds before a keep/discard on",
            "  the default config; the current sample is budget-capped.",
        ]

    footer = [
        "",
        "## Artefacts",
        "",
        "- Raw per-(slice, arm) JSON: `progress/autoresearch/reports/retrieval-bench/`",
        "- Ledger entry: `progress/autoresearch/experiments.jsonl`",
        f"- Spec: `research/autoresearch/retrieval_bench/slices.yaml`",
    ]

    lines = header_lines + body_rows + [""] + next_actions + footer
    return "\n".join(lines) + "\n"


def write_markdown_report(
    verdict: Verdict,
    output_path: str | Path,
    *,
    benchmark_id: str = "retrieval-bench-tiers-v1",
    n_trials: int = 0,
    seeds: Iterable[int] = (42,),
    git_sha: str = "unknown",
) -> Path:
    """Render and write the markdown scorecard."""
    text = render_markdown(
        verdict,
        benchmark_id=benchmark_id,
        n_trials=n_trials,
        seeds=seeds,
        git_sha=git_sha,
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out
