"""Port the projector-v2-v1 report into the canonical LaneReport format.

Reads the per-(variant, slice) JSON artefacts under
``progress/autoresearch/reports/`` that were emitted by
``run_projector_v2_sweep.py`` and writes
``progress/autoresearch/reports/projector-v2-v1-canonical.md``.

Unlike the retrieval-bench lane (which is a binary A/B), the
projector-v2 sweep evaluates five variants against a single baseline.
The canonical format handles this by rendering one LaneReport per
variant would be verbose; instead this script writes one report that:

  * treats `baseline` as the reference arm
  * includes every variant as a separate arm in the ``arms`` list
  * emits a separate gate decision *per variant* in the Discussion
    section, aggregated into a single verdict string

This mirrors the behaviour of the original
``projector-v2-v1.md`` (one report, per-variant keep/discard notes).
"""

from __future__ import annotations

import json
from pathlib import Path

from research.autoresearch.core.gates import Gate, evaluate_gates
from research.autoresearch.core.metrics_delta import delta_table
from research.autoresearch.core.report import LaneReport


REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports"
OUTPUT_PATH = REPORTS_DIR / "projector-v2-v1-canonical.md"


VARIANTS = [
    "baseline",
    "adaptive_conformal",
    "change_aware_conformal",
    "regime_aware_widening",
    "joint_path",
]

SLICES = ["spy-1d", "btc-1d"]


METRIC_DIRECTIONS: dict[str, str] = {
    "crps": "lower_is_better",
    "calibration_error_p10_p90": "lower_is_better",
    "calibration_error_over_time_p10_p90": "lower_is_better",
    "joint_path_crps": "lower_is_better",
    "hit_rate": "higher_is_better",
}


def _load_one(variant: str, slice_id: str) -> dict | None:
    path = REPORTS_DIR / f"projector-v2-{variant}-{slice_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _aggregate_variant(variant: str) -> dict[str, float]:
    rows = [r for r in (_load_one(variant, s) for s in SLICES) if r is not None]
    if not rows:
        return {}
    n = len(rows)
    agg = {
        "crps": sum(r["crps"] for r in rows) / n,
        "calibration_error_p10_p90": sum(r["calibration_error_p10_p90"] for r in rows) / n,
        "calibration_error_over_time_p10_p90": sum(
            r["calibration_error_over_time_p10_p90"] for r in rows
        ) / n,
        "joint_path_crps": sum(r["joint_path_crps"] for r in rows) / n,
        "hit_rate": sum(r["hit_rate"] for r in rows) / n,
        "runtime_seconds": sum(r["runtime_seconds"] for r in rows),
    }
    return agg


def _standard_gates() -> list[Gate]:
    """Gates for the projector-v2 lane (mirror the playbook thresholds)."""
    return [
        Gate(
            name="crps_improvement",
            metric="crps",
            threshold=-0.005,
            direction="lower_is_better",
            required=True,
            description="Mean CRPS must drop by at least 0.005 vs baseline.",
        ),
        Gate(
            name="calibration_improvement",
            metric="calibration_error_p10_p90",
            threshold=-0.005,
            direction="lower_is_better",
            required=False,
            description="Calibration error should drop by 0.005+.",
        ),
        Gate(
            name="hit_rate_floor",
            metric="hit_rate_delta",
            threshold=-0.05,
            direction="higher_is_better",
            required=True,
            description="Hit rate cannot regress by more than 5 pp.",
        ),
    ]


def main() -> None:
    baseline_agg = _aggregate_variant("baseline")
    if not baseline_agg:
        raise SystemExit("Baseline projector-v2 JSON artefacts not found.")

    # One delta_table per candidate variant.
    per_variant_deltas: dict[str, dict[str, float]] = {}
    per_variant_decisions = {}

    for variant in VARIANTS:
        if variant == "baseline":
            continue
        cand_agg = _aggregate_variant(variant)
        if not cand_agg:
            continue
        deltas = delta_table(baseline_agg, cand_agg, directions=METRIC_DIRECTIONS)
        raw_deltas = {name: d.raw_delta for name, d in deltas.items()}
        raw_deltas["hit_rate_delta"] = cand_agg["hit_rate"] - baseline_agg["hit_rate"]
        per_variant_deltas[variant] = raw_deltas
        per_variant_decisions[variant] = evaluate_gates(
            deltas=raw_deltas, gates=_standard_gates()
        )

    # Slice rows: one row per slice, arms = all variants.
    slice_rows = []
    for slice_id in SLICES:
        arm_metrics = {}
        for variant in VARIANTS:
            row = _load_one(variant, slice_id)
            if row is None:
                continue
            arm_metrics[variant] = {
                "crps": row["crps"],
                "cal_err": row["calibration_error_p10_p90"],
                "joint_crps": row["joint_path_crps"],
                "hit_rate": row["hit_rate"],
                "runtime_s": row["runtime_seconds"],
            }
        slice_rows.append({"slice_id": slice_id, "arm_metrics": arm_metrics})

    # Aggregate arms block.
    arms = [{"arm_id": v, "metrics": _aggregate_variant(v)} for v in VARIANTS]

    # Top-level verdict: KEEP if any variant kept, otherwise DISCARD.
    kept_variants = [v for v, d in per_variant_decisions.items() if d.keep]
    verdict = "keep" if kept_variants else "discard"
    rationale = (
        f"{len(kept_variants)} of {len(per_variant_decisions)} candidate variants "
        f"passed all required gates: {', '.join('`' + v + '`' for v in kept_variants) or 'none'}. "
        "See the per-variant breakdown below for details."
    )

    # Discussion: one block per variant.
    discussion_lines = ["### Per-variant gate decisions", ""]
    for variant, decision in per_variant_decisions.items():
        status = "KEEP" if decision.keep else "DISCARD"
        discussion_lines.append(f"**`{variant}` — {status}**")
        for name, res in decision.gate_results.items():
            observed = (
                f"{res.observed_delta:+.5f}"
                if res.observed_delta is not None
                else "—"
            )
            discussion_lines.append(
                f"- `{name}` (required={res.gate.required}) "
                f"metric=`{res.gate.metric}` "
                f"threshold={res.gate.threshold:+.5f} "
                f"observed={observed} → {'PASS' if res.passed else 'FAIL'}"
            )
        discussion_lines.append("")

    # Human narrative carried over from the original report.
    discussion_lines += [
        "### Narrative (from original `projector-v2-v1.md`)",
        "",
        "- **`adaptive_conformal`** — clear winner on this sweep. Terminal "
        "CRPS drops 14% (0.191 → 0.164) and calibration error drops both "
        "at the terminal (-0.033) and across the whole horizon (-0.058). "
        "Improvement holds on BOTH slices (spy-1d and btc-1d) with no "
        "regression in hit rate and a modest runtime *speedup*.",
        "- **`change_aware_conformal`** — numerically identical to "
        "`adaptive_conformal` on this sweep because the synthetic fallback "
        "data does not trigger the variance-jump detector often enough. "
        "Keep the variant but do not promote without a shift-rich slice.",
        "- **`joint_path`** — marginal CRPS improvement (-2.8%). Joint CRPS "
        "is slightly *worse* (+0.004). Keep for further tuning "
        "(noise_fraction, n_paths).",
        "- **`regime_aware_widening`** — CRPS regresses 2.8% and over-time "
        "calibration gets worse by 0.010. Re-visit with multipliers fit "
        "from a residual study rather than hand-picked constants. See "
        "rejection-log entry `regime_aware_widening`.",
    ]
    discussion = "\n".join(discussion_lines)

    # Top-level deltas: use adaptive_conformal vs baseline as the "headline"
    # delta since that's the winning variant; individual per-variant
    # deltas live in the Discussion block above.
    headline_deltas = per_variant_deltas.get("adaptive_conformal", {})

    preamble = (
        "**Canonical-format port of `projector-v2-v1.md`**\n\n"
        "This report is the canonical rendering of the Phase 1B projector-v2 "
        "sweep output. The original `projector-v2-v1.md` is kept for "
        "historical reference. Because the sweep evaluates five variants "
        "against one baseline, the canonical format lists the aggregate "
        "headline delta for the winning variant in the Deltas section and "
        "renders per-variant gate decisions in the Discussion section."
    )

    decision = evaluate_gates(
        deltas=headline_deltas, gates=_standard_gates()
    )

    report = LaneReport(
        lane_id="projector-v2-lane-v1",
        benchmark_id="projector-v2-core-v1",
        commit="unknown",
        timestamp="2026-04-15T05:20:38Z",
        arms=arms,
        slices=slice_rows,
        deltas=headline_deltas,
        gate_decision=decision,
        verdict=verdict,
        rationale=rationale,
        preamble=preamble,
        discussion=discussion,
        open_questions=[
            "Does adaptive_conformal's win hold on real (non-synthetic) parquets?",
            "What alpha_target and lr give the best CRPS under adaptive_conformal?",
            "Can adaptive_conformal + joint_path compose into a better variant?",
            "Does change_aware_conformal diverge from adaptive_conformal on a shift-rich slice?",
        ],
        artifacts=[
            "progress/autoresearch/reports/projector-v2-*.json (per-(variant, slice) JSONs)",
            "progress/autoresearch/reports/projector-v2-v1.md (original report)",
            "progress/autoresearch/experiments.jsonl (ledger entries)",
            "research/autoresearch/benchmarks/projector-v2-core-v1.yaml (spec)",
        ],
    )
    report.write(OUTPUT_PATH)
    print(f"Wrote canonical projector-v2 report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
