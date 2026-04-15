"""Markdown report writer for the foundation-bench-v1 lane.

Consumes a list of ``CellResult`` objects produced by ``run_bench`` and
writes a human-readable scorecard at
``progress/autoresearch/reports/foundation-bench-v1.md``.

Report layout
-------------
1. Header with benchmark id, timestamp, git SHA, protocol knobs.
2. Per-slice table with columns (model, n_trials, n_skipped, crps, cal,
   hit, rt_med, status).
3. Cross-slice aggregates — arithmetic means over slices per model.
4. Fallback summary — how many cells ran real weights vs synthetic.
5. Notes section pulling each model's ``notes`` from its ``CellResult``.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

# Use TYPE_CHECKING to avoid circular imports; we only need the shape.
from research.autoresearch.foundation_bench.run_bench import CellResult  # noqa: E402


def _fmt(value: float, width: int = 7, decimals: int = 4) -> str:
    """Stable numeric formatting that never raises on NaN/None.

    Produces fixed-width strings so the markdown tables line up even
    when piped through ``git diff --color-words``.
    """
    if value is None:
        return " " * width
    try:
        return f"{float(value):>{width}.{decimals}f}"
    except Exception:
        return " " * width


def _group_by_slice(cells: Iterable[CellResult]) -> dict[str, list[CellResult]]:
    """Group cells by slice id, preserving insertion order."""
    out: dict[str, list[CellResult]] = {}
    for c in cells:
        out.setdefault(c.slice_id, []).append(c)
    return out


def _group_by_model(cells: Iterable[CellResult]) -> dict[str, list[CellResult]]:
    """Group cells by model id, preserving insertion order."""
    out: dict[str, list[CellResult]] = {}
    for c in cells:
        out.setdefault(c.model_id, []).append(c)
    return out


def _mean(values: list[float]) -> float:
    """Arithmetic mean with degenerate-empty → 0.0 semantics."""
    return sum(values) / len(values) if values else 0.0


def write_markdown_report(
    cells: list[CellResult],
    output_path: str | Path,
    *,
    benchmark_id: str = "foundation-bench-v1",
    n_trials: int = 0,
    seeds: Iterable[int] = (),
    git_sha: str = "unknown",
    per_cell_budget_seconds: float = 180.0,
) -> Path:
    """Render and write the consolidated markdown scorecard.

    ``cells`` can be in any order; the writer groups by slice then model
    for the per-slice tables, and by model for the cross-slice aggregate.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    seeds_list = list(seeds)

    lines: list[str] = []
    lines.append(f"# Foundation-bench v1 — scorecard")
    lines.append("")
    lines.append(f"- **benchmark_id:** `{benchmark_id}`")
    lines.append(f"- **timestamp:** {timestamp}")
    lines.append(f"- **git_sha:** `{git_sha}`")
    lines.append(f"- **n_trials:** {n_trials}")
    lines.append(f"- **seeds:** {seeds_list}")
    lines.append(f"- **per_cell_budget_seconds:** {per_cell_budget_seconds:.0f}")
    lines.append("")
    lines.append(
        "Walk-forward quantile-forecast evaluation. Metric helpers reused from "
        "`research/autoresearch/retrieval_bench/metrics.py`. Slices are the "
        "SPY/BTC subset of retrieval-bench-tiers-v1 so per-trial deltas are "
        "joinable with 1A artefacts."
    )
    lines.append("")

    # --- Per-slice tables -------------------------------------------------
    lines.append("## Per-slice scorecards")
    lines.append("")
    grouped = _group_by_slice(cells)
    for slice_id, slice_cells in grouped.items():
        lines.append(f"### {slice_id}")
        lines.append("")
        lines.append(
            "| model | n | skipped | crps | cal | hit | rt_med (s) | rt_p95 (s) | status |"
        )
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
        for c in slice_cells:
            lines.append(
                "| "
                + " | ".join(
                    [
                        c.model_id,
                        str(c.n_trials),
                        str(c.n_skipped_budget),
                        _fmt(c.crps, decimals=4),
                        _fmt(c.calibration_error_p10_p90, decimals=3),
                        _fmt(c.hit_rate, decimals=2),
                        _fmt(c.runtime.get("median", 0.0), decimals=3),
                        _fmt(c.runtime.get("p95", 0.0), decimals=3),
                        c.status,
                    ]
                )
                + " |"
            )
        lines.append("")

    # --- Cross-slice aggregate -------------------------------------------
    lines.append("## Cross-slice aggregate (arithmetic mean over slices)")
    lines.append("")
    lines.append(
        "| model | n_cells | mean_crps | mean_cal | mean_hit | mean_rt_med (s) |"
        " fallback_cells | explainability |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    by_model = _group_by_model(cells)
    for model_id, mc in by_model.items():
        crps_values = [c.crps for c in mc if c.n_trials > 0]
        cal_values = [c.calibration_error_p10_p90 for c in mc if c.n_trials > 0]
        hit_values = [c.hit_rate for c in mc if c.n_trials > 0]
        rt_values = [c.runtime.get("median", 0.0) for c in mc if c.n_trials > 0]
        fallback_cells = sum(1 for c in mc if c.any_fallback)
        # Explainability floor from the model's notes; the runner doesn't
        # carry it through CellResult so we use a stable lookup table.
        explainability = _EXPLAINABILITY.get(model_id, "low")
        lines.append(
            "| "
            + " | ".join(
                [
                    model_id,
                    str(len(mc)),
                    _fmt(_mean(crps_values), decimals=4),
                    _fmt(_mean(cal_values), decimals=3),
                    _fmt(_mean(hit_values), decimals=2),
                    _fmt(_mean(rt_values), decimals=3),
                    str(fallback_cells),
                    explainability,
                ]
            )
            + " |"
        )
    lines.append("")

    # --- Fallback summary -------------------------------------------------
    total = len(cells)
    synthetic = sum(
        1 for c in cells if c.status.startswith("partial_synthetic_fallback")
    )
    partial = sum(1 for c in cells if c.status == "partial_fallback")
    skipped = sum(1 for c in cells if c.n_skipped_budget > 0)
    real = sum(1 for c in cells if c.status == "ok")
    lines.append("## Fallback / budget summary")
    lines.append("")
    lines.append(f"- Total cells: **{total}**")
    lines.append(f"- Fully synthetic fallback cells: **{synthetic}**")
    lines.append(f"- Partial fallback cells: **{partial}**")
    lines.append(f"- Real / classical cells: **{real}**")
    lines.append(f"- Cells that hit the budget cap: **{skipped}**")
    lines.append("")
    if synthetic == total:
        lines.append(
            "> **NOTE:** every cell ran under the synthetic fallback path. "
            "No pretrained foundation weights were reachable in this "
            "environment; the per-cell artefacts still carry a complete "
            "quantile forecast + metric set, and the ledger row is "
            "flagged `partial_synthetic_fallback`."
        )
        lines.append("")

    # --- Notes ------------------------------------------------------------
    notes = [c for c in cells if c.notes]
    if notes:
        lines.append("## Notes")
        lines.append("")
        for c in notes:
            lines.append(f"- **{c.slice_id} / {c.model_id}:** {c.notes}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# Static explainability lookup so report.py does not have to reload
# models.yaml a second time. Keep this in sync with models.yaml.
_EXPLAINABILITY = {
    "timesfm": "low",
    "chronos": "low",
    "moirai": "low",
    "moment": "low",
    "wavelet_baseline": "medium",
}
