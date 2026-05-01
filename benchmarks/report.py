"""Markdown comparison report builder for the benchmark harness.

Lifecycle
=========
The runner (Agent A's territory) writes one JSON line per scored
``(dataset, series, system, horizon)`` combo to
``benchmarks/results/raw.jsonl``. This module reads that file, groups
by ``(dataset, horizon)``, aggregates across series, and renders a
single Markdown document with one table per group plus a fixed
"Caveats" footer.

Aggregation rules
=================
Inside each ``(dataset, horizon)`` group:

- ``mae, smape, crps, mase, coverage_p10_p90``: arithmetic mean across
  series. Mean is the right reducer because the metrics are already
  per-series scaled (MAE is in target units, MASE is dimensionless,
  etc.) — taking a median would discard tail behaviour the report is
  specifically here to surface.
- ``query_ms``: median across series. Latency distributions are
  right-skewed (cold-cache outliers) and the median answers "what does
  one query cost in the typical case?" without being yanked by warmup.
- ``peak_mb``: max across series. We care about the worst-case
  footprint, not the average — a system that spikes to 8 GB on one
  series is operationally unusable even if it averages 1 GB.

Best-value highlighting
=======================
Within each table, the best cell per metric column is wrapped in
``**bold**``. "Best" means smallest for error metrics + latency +
peak memory, and *closest to 0.80* for ``coverage_p10_p90`` (the
nominal target). Ties are all-bolded so the reader sees them.

Chronos reference row
=====================
For each dataset that has a published Chronos MASE
(:mod:`benchmarks.chronos_published`), one extra row labelled
``Chronos-T5-small (published, zero-shot)`` is appended. ONLY the MASE
column is filled — every other cell is the literal string ``"-"``
because per-series numbers are not published in the paper. The label
explicitly carries "(published, zero-shot)" except for in-domain
datasets where it switches to "(published, in-domain)" to match the
paper's own categorisation.

CLI
===
::

    python -m benchmarks.report \\
        --raw benchmarks/results/raw.jsonl \\
        --out benchmarks/results/REPORT.md

Library entry point
===================
:func:`build_report` takes a path or list-of-rows and returns the
Markdown string. It does no I/O of its own beyond the optional output
file, so tests can call it with a synthetic ``raw.jsonl`` written to a
``tmp_path``.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.chronos_published import (
    get_chronos_mase,
    get_chronos_regime,
)

# ---------------------------------------------------------------------------
# Column spec — one source of truth for header order, JSON key, display
# label, and aggregation rule. Keeping this as data (not code) means we
# can add a new metric (e.g. "winkler_score") in one place without
# touching the table renderer.
# ---------------------------------------------------------------------------
# Each tuple: (jsonl_key, display_header, aggregator, lower_is_better)
# - aggregator is a string tag interpreted by ``_aggregate_group``.
# - lower_is_better drives the bolding rule. The special value "near_0_8"
#   marks coverage_p10_p90 (target = 0.80, not 0).
_COLUMNS: list[tuple[str, str, str, str]] = [
    ("mae", "MAE", "mean", "lower"),
    ("smape", "sMAPE", "mean", "lower"),
    ("crps", "CRPS", "mean", "lower"),
    ("mase", "MASE", "mean", "lower"),
    ("coverage_p10_p90", "P10/P90 cov.", "mean", "near_0_8"),
    ("query_ms", "median query ms", "median", "lower"),
    ("peak_mb", "peak MB", "max", "lower"),
]

# Numeric formatting per column. We pick precision so the largest
# expected value fits without scientific notation: MAE/CRPS get 4 dp
# (financial returns), sMAPE/coverage get 3 dp, latency/memory are
# integers-ish so 1 dp keeps them readable.
_FMT: dict[str, str] = {
    "mae": "{:.4f}",
    "smape": "{:.3f}",
    "crps": "{:.4f}",
    "mase": "{:.3f}",
    "coverage_p10_p90": "{:.3f}",
    "query_ms": "{:.1f}",
    "peak_mb": "{:.1f}",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read every non-blank line of ``path`` as a JSON object.

    Returns an empty list if the file does not exist OR is empty —
    callers handle the empty case by emitting a placeholder report.
    Each line is validated for the seven numeric metric keys; missing
    keys raise ``ValueError`` with the offending line number so a
    malformed runner output is loud, not silent.
    """
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    required = {
        "dataset",
        "series_id",
        "system",
        "horizon",
        "mae",
        "smape",
        "crps",
        "mase",
        "coverage_p10_p90",
        "query_ms",
        "peak_mb",
    }
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                msg = f"{path}:{lineno}: invalid JSON ({exc})"
                raise ValueError(msg) from exc
            missing = required - obj.keys()
            if missing:
                msg = (
                    f"{path}:{lineno}: missing required keys: "
                    f"{sorted(missing)}"
                )
                raise ValueError(msg)
            rows.append(obj)
    return rows


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _aggregate_group(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, float]]:
    """Reduce a list of per-series rows into per-system aggregated metrics.

    Returns a dict keyed by system name → dict keyed by jsonl_key →
    float. Missing values (NaN, ``None``) are dropped per-column
    *before* aggregation so a single broken series does not poison the
    whole row. If a system has zero valid samples for a column the
    result is ``float("nan")`` and the renderer prints ``"-"``.
    """
    by_system: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        sys_name = str(row["system"])
        for key, _disp, _agg, _bold in _COLUMNS:
            v = row.get(key)
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            # NaN is JSON-illegal but Python-legal; if the runner ever
            # writes it, drop rather than propagate to the mean.
            if fv != fv:  # NaN check without importing math
                continue
            by_system[sys_name][key].append(fv)

    out: dict[str, dict[str, float]] = {}
    for sys_name, cols in by_system.items():
        sys_out: dict[str, float] = {}
        for key, _disp, agg, _bold in _COLUMNS:
            samples = cols.get(key, [])
            if not samples:
                sys_out[key] = float("nan")
                continue
            if agg == "mean":
                sys_out[key] = statistics.fmean(samples)
            elif agg == "median":
                sys_out[key] = statistics.median(samples)
            elif agg == "max":
                sys_out[key] = max(samples)
            else:  # pragma: no cover - guarded by _COLUMNS literal set
                msg = f"unknown aggregator {agg!r} for column {key}"
                raise ValueError(msg)
        out[sys_name] = sys_out
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _is_nan(x: float) -> bool:
    """Local NaN check that does not require importing ``math.isnan``."""
    return x != x


def _format_cell(key: str, value: float) -> str:
    """Format a numeric cell, returning ``"-"`` for NaN."""
    if _is_nan(value):
        return "-"
    return _FMT[key].format(value)


def _best_indices(
    column_values: Sequence[float], rule: str
) -> set[int]:
    """Return the row indices whose value should be bolded for this column.

    ``rule`` is one of:
        - ``"lower"``     — smallest non-NaN value(s) win.
        - ``"near_0_8"``  — value(s) closest to 0.80 win (coverage).

    NaN entries are never selected. Ties (within 1e-12 absolute) are
    all selected so a renderer can bold every winner.
    """
    valid = [
        (i, v) for i, v in enumerate(column_values) if not _is_nan(v)
    ]
    if not valid:
        return set()
    if rule == "lower":
        scored = [(i, v) for i, v in valid]
        best = min(scored, key=lambda iv: iv[1])[1]
        return {i for i, v in scored if abs(v - best) <= 1e-12}
    if rule == "near_0_8":
        target = 0.8
        scored = [(i, abs(v - target)) for i, v in valid]
        best = min(scored, key=lambda iv: iv[1])[1]
        return {i for i, d in scored if abs(d - best) <= 1e-12}
    msg = f"unknown bolding rule {rule!r}"  # pragma: no cover
    raise ValueError(msg)


def _render_table(
    dataset: str,
    horizon: int,
    aggregated: Mapping[str, Mapping[str, float]],
    chronos_label: str | None,
    chronos_mase: float | None,
) -> str:
    """Render one (dataset, horizon) table as a Markdown string.

    The Chronos row, if any, is appended LAST and competes for the
    MASE-best bold like any other row. All other Chronos cells render
    as ``"-"`` because per-series numbers are not published.
    """
    # Stable system ordering: alphabetical. Avoids "test passes locally
    # but fails in CI because dict insertion order leaked".
    system_names = sorted(aggregated.keys())

    # Build the matrix of raw values (rows × cols) so we can compute
    # bolding column-by-column without re-scanning the dict.
    rows: list[tuple[str, list[float]]] = []
    for sys_name in system_names:
        per_col = [aggregated[sys_name][key] for key, *_ in _COLUMNS]
        rows.append((sys_name, per_col))

    # Append Chronos reference row if applicable.
    if chronos_label is not None and chronos_mase is not None:
        chronos_row: list[float] = []
        for key, *_ in _COLUMNS:
            if key == "mase":
                chronos_row.append(chronos_mase)
            else:
                chronos_row.append(float("nan"))
        rows.append((chronos_label, chronos_row))

    # Determine bold cells per column.
    bold_cells: list[set[int]] = []
    for col_idx, (_key, _disp, _agg, rule) in enumerate(_COLUMNS):
        values = [r[1][col_idx] for r in rows]
        bold_cells.append(_best_indices(values, rule))

    # Build the header.
    headers = ["System"] + [disp for _k, disp, _a, _b in _COLUMNS]
    sep = ["---"] + ["---:" for _ in _COLUMNS]  # right-align numerics
    lines: list[str] = []
    lines.append(f"### {dataset} — horizon {horizon}")
    lines.append("")
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(sep) + " |")
    for row_idx, (sys_name, values) in enumerate(rows):
        cells: list[str] = [sys_name]
        for col_idx, (key, _disp, _agg, _rule) in enumerate(_COLUMNS):
            cell = _format_cell(key, values[col_idx])
            if cell != "-" and row_idx in bold_cells[col_idx]:
                cell = f"**{cell}**"
            cells.append(cell)
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Caveats footer — rendered verbatim. Edit here, not in tests.
# ---------------------------------------------------------------------------
_CAVEATS = """## Caveats

- **Chronos numbers are paper-aggregate over the full Monash split**;
  ours are computed on a 100-series subset of each dataset. The two
  numbers are not strictly comparable — treat the Chronos row as a
  ballpark reference, not a head-to-head.
- **All systems run with default config, no tuning.** No hyperparameter
  search, no per-dataset overrides, no ensembling beyond what each
  system does internally.
- **SPY / BTC have no Chronos comparison row** — those instruments are
  not part of the Monash benchmark, so no published number exists.
- **Pretraining contamination warning.** Chronos was pretrained on
  millions of public time series; the paper itself flags M4 (Daily)
  and M4 (Hourly) as Benchmark I (in-domain), meaning the model has
  effectively seen them during training. NN5 (Daily) is the only
  truly zero-shot reference here.
"""


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def build_report(
    rows: Iterable[Mapping[str, Any]] | str | Path,
) -> str:
    """Build the Markdown report from a JSONL path OR a row iterable.

    Args:
        rows: Either a path to a ``raw.jsonl`` file (anything that
            ``Path()`` accepts) or an already-parsed iterable of
            dict-like rows. Lets tests bypass disk I/O entirely.

    Returns:
        The full Markdown document as a single string. Includes a
        title, one ``### dataset — horizon H`` section per group, and
        the Caveats footer. If no rows are provided, the report still
        renders the title + caveats + an explicit "no results yet"
        notice so a stale CI artifact is recognisable.
    """
    # Normalise input to a list of dicts.
    if isinstance(rows, (str, Path)):
        loaded = _load_jsonl(Path(rows))
    else:
        loaded = list(rows)

    out: list[str] = []
    out.append("# Benchmark report")
    out.append("")
    out.append(
        "Cross-system forecasting benchmark. One table per "
        "(dataset, horizon) combo. The Chronos reference row uses "
        "published numbers from arxiv 2403.07815v3 and is **not**"
        " from a fresh inference run — see Caveats."
    )
    out.append("")

    if not loaded:
        out.append("_No results in raw.jsonl yet._")
        out.append("")
        out.append(_CAVEATS)
        return "\n".join(out)

    # Group rows by (dataset, horizon). Sorted so the document is
    # deterministic across machines.
    groups: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(
        list
    )
    for row in loaded:
        key = (str(row["dataset"]), int(row["horizon"]))
        groups[key].append(row)

    for (dataset, horizon) in sorted(groups.keys()):
        agg = _aggregate_group(groups[(dataset, horizon)])
        # Resolve the Chronos reference for this dataset, if any.
        chronos_value = get_chronos_mase(dataset, "chronos-t5-small")
        chronos_label: str | None = None
        if chronos_value is not None:
            regime = get_chronos_regime(dataset) or "unknown"
            regime_label = (
                "zero-shot" if regime == "zero_shot" else "in-domain"
            )
            chronos_label = (
                f"Chronos-T5-small (published, {regime_label})"
            )
        out.append(
            _render_table(
                dataset=dataset,
                horizon=horizon,
                aggregated=agg,
                chronos_label=chronos_label,
                chronos_mase=chronos_value,
            )
        )

    out.append(_CAVEATS)
    return "\n".join(out)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Argparse setup factored out for testability."""
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.report",
        description=(
            "Render benchmarks/results/raw.jsonl into a Markdown "
            "comparison report."
        ),
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=Path("benchmarks/results/raw.jsonl"),
        help="Path to the JSONL produced by the benchmark runner.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("benchmarks/results/REPORT.md"),
        help="Destination Markdown file. Created/overwritten in place.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code.

    Reads ``--raw``, writes ``--out``, prints the destination path to
    stdout. Designed to be safe under CI: never touches a file outside
    the path the user explicitly passed.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(args.raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(str(args.out))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(main())
