"""Canonical Markdown report renderer for autoresearch lanes.

Every lane emits the same report shape:

    1. Metadata (lane, benchmark, commit, timestamp)
    2. Slice × arm scorecard (one row per slice, one column per arm metric)
    3. Deltas (candidate − baseline with direction-aware win flags)
    4. Gates (pass/fail with reasons)
    5. Verdict (keep / discard with rationale)
    6. Open questions / follow-up lanes
    7. Artifacts (links to raw JSON, ledger, spec)

This module provides :class:`LaneReport` that takes the structured
inputs, renders the canonical markdown, and writes it to disk. The
renderer is a pure function of its inputs so snapshot tests stay
deterministic.

Why a class rather than a function?
-----------------------------------
Lanes often need to assemble the report in two passes — first run all
variants, collect per-slice rows, then compute deltas and gates. The
dataclass lets them mutate fields incrementally before calling
``render()``. The renderer itself is still deterministic.

Markdown sink
-------------
The output is plain GitHub-flavoured Markdown. No YAML frontmatter —
keeping the first line as an H1 heading means Obsidian, GitHub, and
``ghostscript``-style raw viewers all render it uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research.autoresearch.core.gates import GateDecision
from research.autoresearch.core.metrics_delta import Delta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_float(value: Any, digits: int = 4) -> str:
    """Format a number for table cells; return '—' for None / NaN / non-numeric."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v != v:  # NaN
        return "—"
    return f"{v:.{digits}f}"


def _fmt_signed(value: float, digits: int = 4) -> str:
    """Signed float for delta columns (always shows + or -)."""
    return f"{value:+.{digits}f}"


# ---------------------------------------------------------------------------
# Report object
# ---------------------------------------------------------------------------


@dataclass
class LaneReport:
    """Canonical lane report.

    Inputs
    ------
    lane_id, benchmark_id, commit, timestamp:
        Identifying metadata. ``commit`` is a git SHA or "unknown" for
        synthetic-data runs that do not record a commit.
    arms:
        Aggregate scorecards, one dict per arm. Each arm dict should
        have at minimum ``{"arm_id": str, "metrics": dict[str, float]}``
        and may carry extra keys (rendered as a bullet list under the
        arm header).
    slices:
        Per-slice rows. Each entry:
        ``{"slice_id": str, "arm_metrics": {arm_id: metrics_dict}}``.
    deltas:
        Map metric → raw signed delta (candidate − baseline). Optional
        :class:`Delta` objects can be passed in ``delta_objects`` for
        richer rendering (direction-aware win flags).
    gate_decision:
        Output of :func:`research.autoresearch.core.gates.evaluate_gates`.
    verdict:
        Final verdict string — typically ``"keep"`` or ``"discard"``.
    rationale:
        One-paragraph rationale rendered under the verdict.
    open_questions, artifacts:
        Free-text lists for the Open questions and Artifacts sections.
    delta_objects:
        Optional dict of :class:`Delta` for direction-aware rendering.
        If provided, overrides ``deltas`` as the source of the delta
        table.
    """

    lane_id: str
    benchmark_id: str
    commit: str
    timestamp: str
    arms: list[dict[str, Any]]
    slices: list[dict[str, Any]]
    deltas: dict[str, float]
    gate_decision: GateDecision
    verdict: str
    rationale: str
    open_questions: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    delta_objects: dict[str, Delta] | None = None
    # Optional pre-formatted prose blocks a lane wants to inject.
    preamble: str = ""
    discussion: str = ""

    # ------------------------------------------------------------------
    # Section renderers (pure functions of ``self``)
    # ------------------------------------------------------------------

    def _render_header(self) -> list[str]:
        return [
            f"# Lane report — `{self.lane_id}`",
            "",
            f"_{self.verdict.upper()} — generated {self.timestamp}_",
            "",
        ]

    def _render_preamble(self) -> list[str]:
        if not self.preamble:
            return []
        return [self.preamble.strip(), ""]

    def _render_metadata(self) -> list[str]:
        arm_ids = [a["arm_id"] for a in self.arms]
        arm_list = ", ".join(f"`{aid}`" for aid in arm_ids) or "—"
        return [
            "## Metadata",
            "",
            f"- Lane id: `{self.lane_id}`",
            f"- Benchmark id: `{self.benchmark_id}`",
            f"- Commit: `{self.commit}`",
            f"- Timestamp: `{self.timestamp}`",
            f"- Arms: {arm_list}",
            "",
        ]

    def _render_slice_table(self) -> list[str]:
        """One row per slice; columns = each arm's metrics interleaved."""
        if not self.slices:
            return ["## Slice × arm scorecard", "", "_No per-slice data._", ""]

        # Metric column set = union of all metrics observed per arm.
        metric_keys: list[str] = []
        seen: set[str] = set()
        for sl in self.slices:
            for arm_id, metrics in sl.get("arm_metrics", {}).items():
                for k in metrics.keys():
                    if k not in seen:
                        seen.add(k)
                        metric_keys.append(k)

        arm_ids = [a["arm_id"] for a in self.arms]
        header = ["| slice |"]
        sep = ["|---|"]
        for arm in arm_ids:
            for mk in metric_keys:
                header.append(f" {arm}·{mk} |")
                sep.append("---|")
        header_row = "".join(header)
        sep_row = "".join(sep)

        lines = ["## Slice × arm scorecard", "", header_row, sep_row]
        for sl in self.slices:
            row = [f"| `{sl['slice_id']}` |"]
            arm_metrics = sl.get("arm_metrics", {})
            for arm in arm_ids:
                m = arm_metrics.get(arm, {}) or {}
                for mk in metric_keys:
                    row.append(f" {_fmt_float(m.get(mk))} |")
            lines.append("".join(row))
        lines.append("")
        return lines

    def _render_deltas(self) -> list[str]:
        """Deltas table with direction-aware win flags when available."""
        lines = ["## Deltas", ""]
        if self.delta_objects:
            lines += [
                "| metric | direction | baseline | candidate | Δ | improvement |",
                "|---|---|---|---|---|---|",
            ]
            for name, d in self.delta_objects.items():
                lines.append(
                    f"| `{name}` | {d.direction} | "
                    f"{_fmt_float(d.baseline)} | {_fmt_float(d.candidate)} | "
                    f"{_fmt_signed(d.raw_delta)} | {'yes' if d.is_improvement else 'no'} |"
                )
        elif self.deltas:
            lines += ["| metric | Δ (candidate − baseline) |", "|---|---|"]
            for name, val in self.deltas.items():
                lines.append(f"| `{name}` | {_fmt_signed(float(val))} |")
        else:
            lines.append("_No deltas recorded._")
        lines.append("")
        return lines

    def _render_gates(self) -> list[str]:
        lines = ["## Gates", ""]
        gr = self.gate_decision.gate_results
        if not gr:
            lines += ["_No gates declared._", ""]
            return lines
        lines += [
            "| gate | required | metric | direction | threshold | observed | result |",
            "|---|---|---|---|---|---|---|",
        ]
        for name, res in gr.items():
            g = res.gate
            lines.append(
                f"| `{name}` | {g.required} | `{g.metric}` | {g.direction} | "
                f"{_fmt_signed(g.threshold)} | {_fmt_float(res.observed_delta)} | "
                f"{'PASS' if res.passed else 'FAIL'} |"
            )
        if self.gate_decision.reasons:
            lines += [
                "",
                "**Failing required gates:**",
                "",
            ]
            for r in self.gate_decision.reasons:
                lines.append(f"- {r}")
        lines.append("")
        return lines

    def _render_verdict(self) -> list[str]:
        return [
            "## Verdict",
            "",
            f"**{self.verdict.upper()}** — {self.rationale}",
            "",
        ]

    def _render_discussion(self) -> list[str]:
        if not self.discussion:
            return []
        return ["## Discussion", "", self.discussion.strip(), ""]

    def _render_open_questions(self) -> list[str]:
        lines = ["## Open questions", ""]
        if not self.open_questions:
            lines += ["_None recorded._", ""]
            return lines
        for q in self.open_questions:
            lines.append(f"- {q}")
        lines.append("")
        return lines

    def _render_artifacts(self) -> list[str]:
        lines = ["## Artifacts", ""]
        if not self.artifacts:
            lines += ["_None linked._", ""]
            return lines
        for a in self.artifacts:
            lines.append(f"- `{a}`")
        lines.append("")
        return lines

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self) -> str:
        """Render the full report as a Markdown string.

        The returned string always ends with a single trailing newline so
        round-tripping through a file system does not add/remove a blank
        line on every write.
        """
        parts: list[str] = []
        parts += self._render_header()
        parts += self._render_preamble()
        parts += self._render_metadata()
        parts += self._render_slice_table()
        parts += self._render_deltas()
        parts += self._render_gates()
        parts += self._render_verdict()
        parts += self._render_discussion()
        parts += self._render_open_questions()
        parts += self._render_artifacts()
        return "\n".join(parts).rstrip() + "\n"

    def write(self, output_path: str | Path) -> Path:
        """Render and persist the report. Returns the written path."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.render(), encoding="utf-8")
        return out


__all__ = ["LaneReport"]
