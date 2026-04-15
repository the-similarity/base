"""Port the retrieval-bench-v1 report into the canonical LaneReport format.

Reads the existing per-(slice, arm) JSON artefacts under
``progress/autoresearch/reports/retrieval-bench/`` and writes a
``retrieval-bench-v1-canonical.md`` alongside the existing
``retrieval-bench-v1.md`` so reviewers can eyeball the before/after
migration.

This is a one-shot porting utility; it is not invoked by the live
retrieval_bench runner.  The live runner will migrate in a follow-up
PR after the canonical format has landed and stabilised.
"""

from __future__ import annotations

import json
from pathlib import Path

from research.autoresearch.core.gates import Gate, evaluate_gates
from research.autoresearch.core.metrics_delta import compute_delta, delta_table
from research.autoresearch.core.report import LaneReport


REPO_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO_ROOT / "progress" / "autoresearch" / "reports" / "retrieval-bench"
OUTPUT_PATH = (
    REPO_ROOT
    / "progress"
    / "autoresearch"
    / "reports"
    / "retrieval-bench-v1-canonical.md"
)


# Metric directions for the retrieval-bench lane (mirrors the
# conventions documented in research/autoresearch/retrieval_bench/compare.py).
METRIC_DIRECTIONS: dict[str, str] = {
    "forward_return_correlation": "higher_is_better",
    "crps": "lower_is_better",
    "calibration_error_p10_p90": "lower_is_better",
    "hit_rate": "higher_is_better",
}


def _load_grouped() -> dict[str, dict[str, dict]]:
    """Load raw JSONs into ``{slice_id: {arm_id: result_dict}}``."""
    grouped: dict[str, dict[str, dict]] = {}
    for path in sorted(REPORTS_DIR.glob("*.json")):
        payload = json.loads(path.read_text())
        result = payload.get("result", {})
        slice_id = result.get("slice_id")
        arm_id = result.get("arm_id")
        if not slice_id or not arm_id:
            continue
        grouped.setdefault(slice_id, {})[arm_id] = result
    return grouped


def _aggregate(grouped: dict[str, dict[str, dict]], arm: str) -> dict[str, float]:
    """Mean-aggregate an arm's metrics across slices."""
    rows = [g[arm] for g in grouped.values() if arm in g]
    if not rows:
        return {}
    n = len(rows)
    agg = {
        "forward_return_correlation": sum(r["forward_return_correlation"] for r in rows) / n,
        "crps": sum(r["crps"] for r in rows) / n,
        "calibration_error_p10_p90": sum(r["calibration_error_p10_p90"] for r in rows) / n,
        "hit_rate": sum(r["hit_rate"] for r in rows) / n,
        "runtime_seconds_median": sum(r["runtime_seconds"]["median"] for r in rows) / n,
    }
    return agg


def main() -> None:
    grouped = _load_grouped()
    if not grouped:
        raise SystemExit(f"No retrieval-bench JSONs under {REPORTS_DIR}")

    baseline_arm = "tier1_only"
    candidate_arm = "tier1_plus_full"

    baseline_agg = _aggregate(grouped, baseline_arm)
    candidate_agg = _aggregate(grouped, candidate_arm)

    # Runtime multiplier is a derived metric for the report only.
    # We keep it in ``deltas`` as a raw numeric but do not attach it to
    # a Delta object (the direction is clear: lower is better, but the
    # baseline "delta" is 1.0 by construction).
    runtime_ratio = (
        candidate_agg.get("runtime_seconds_median", 1.0)
        / (baseline_agg.get("runtime_seconds_median", 1.0) or 1e-9)
    )

    deltas = delta_table(
        baseline_agg,
        candidate_agg,
        directions={
            "forward_return_correlation": "higher_is_better",
            "crps": "lower_is_better",
            "calibration_error_p10_p90": "lower_is_better",
            "hit_rate": "higher_is_better",
        },
    )
    raw_deltas = {name: d.raw_delta for name, d in deltas.items()}
    raw_deltas["runtime_multiplier"] = runtime_ratio

    # Gates for the retrieval-bench lane:
    #   REQUIRED: CRPS must improve by at least 0.005
    #   REQUIRED: runtime multiplier must stay below 3.0x
    #   ADVISORY: forward-return correlation uplift of at least +0.02
    gates = [
        Gate(
            name="crps_improvement",
            metric="crps",
            threshold=-0.005,
            direction="lower_is_better",
            required=True,
            description="Mean CRPS must drop by at least 0.005 vs Tier 1.",
        ),
        Gate(
            name="runtime_ceiling",
            metric="runtime_multiplier",
            threshold=3.0,
            direction="lower_is_better",
            required=True,
            description="Tier 1+2 runtime cannot exceed 3x Tier 1 baseline.",
        ),
        Gate(
            name="correlation_uplift",
            metric="forward_return_correlation",
            threshold=0.02,
            direction="higher_is_better",
            required=False,
            description="Forward-return correlation lift should be at least +0.02.",
        ),
    ]
    decision = evaluate_gates(deltas=raw_deltas, gates=gates)

    # Compose slice rows.
    slice_rows = []
    for slice_id, arms in grouped.items():
        arm_metrics = {}
        for arm_id in (baseline_arm, candidate_arm):
            if arm_id in arms:
                r = arms[arm_id]
                arm_metrics[arm_id] = {
                    "forward_return_correlation": r["forward_return_correlation"],
                    "crps": r["crps"],
                    "calibration_error_p10_p90": r["calibration_error_p10_p90"],
                    "hit_rate": r["hit_rate"],
                    "runtime_seconds_median": r["runtime_seconds"]["median"],
                }
        slice_rows.append({"slice_id": slice_id, "arm_metrics": arm_metrics})

    verdict = "keep" if decision.keep else "discard"
    rationale = (
        "Tier 1+2 blew the runtime ceiling (37x > 3x) and failed to deliver a "
        "CRPS improvement on enough slices. The 9-method stack is kept as the "
        "engine default only because this was a *measurement* lane, not a "
        "*replacement* lane — see the rejection log entry "
        "`tier2_as_default` for the full context."
        if not decision.keep
        else "All required gates passed."
    )

    preamble = (
        "**Canonical-format port of `retrieval-bench-v1.md`**\n\n"
        "This report is the canonical rendering of the Phase 1A retrieval "
        "benchmark output. The original `retrieval-bench-v1.md` is kept for "
        "historical reference; this canonical copy is what the Phase 2 "
        "review tooling consumes."
    )

    discussion = (
        "**Scope caveat.** This run was budget-capped: 3 of 6 spec slices "
        "(all three SPY regimes) × 1 seed × 8 trials per slice. The other "
        "three slices (`nvda-long-run`, `tsla-long-run`, `btc-long-run`) "
        "were deferred because Tier 1+2 on their ~2k–7k-bar histories takes "
        "> 1 min per trial, which pushed the full sweep outside the "
        "session's wall-clock budget. Before promoting this verdict the "
        "follow-up lane must finish the remaining three slices and run "
        "both seeds (`42` and `314`).\n\n"
        "**Runtime bottleneck: Tier 2.** Tier 1 (DTW + Pearson on SAX+MASS "
        "survivors) runs at 0.12–0.48 s/query on SPY. Tier 2 enrichment "
        "(Bempedelis ×2, Koopman, wavelet spectrum, EMD, TDA, transfer "
        "entropy — on 20 candidates) adds 5–8 s per query. On the 3 SPY "
        "slices the runtime multiplier was 10.6×, 46.0×, and 54.3×.\n\n"
        "**Quality bottleneck: Tier 2 does not pay its cost on this sample.** "
        "Across the three SPY slices Tier 2 reduced CRPS on one slice "
        "(`spy-rate-hike-2022`, ΔCRPS = -0.005) and increased CRPS on the "
        "other two. Correlation lift was mixed."
    )

    report = LaneReport(
        lane_id="retrieval-bench-tiers-v1-lane",
        benchmark_id="retrieval-bench-tiers-v1",
        commit="0c7ebdc",
        timestamp="2026-04-15T05:37:08Z",
        arms=[
            {"arm_id": baseline_arm, "metrics": baseline_agg},
            {"arm_id": candidate_arm, "metrics": candidate_agg},
        ],
        slices=slice_rows,
        deltas=raw_deltas,
        gate_decision=decision,
        verdict=verdict,
        rationale=rationale,
        preamble=preamble,
        discussion=discussion,
        delta_objects=deltas,
        open_questions=[
            "Do the missing three slices (`nvda-long-run`, `tsla-long-run`, `btc-long-run`) change the verdict?",
            "Does seed 314 reproduce seed 42's CRPS flatness?",
            "Can `feature_store` caching close the runtime gap without dropping methods?",
            "Which individual Tier 2 methods contribute to the one slice (`spy-rate-hike-2022`) where CRPS improved?",
        ],
        artifacts=[
            "progress/autoresearch/reports/retrieval-bench/ (raw per-(slice, arm) JSONs)",
            "progress/autoresearch/reports/retrieval-bench-v1.md (original report)",
            "progress/autoresearch/experiments.jsonl (ledger entry)",
            "research/autoresearch/retrieval_bench/slices.yaml (spec)",
        ],
    )
    report.write(OUTPUT_PATH)
    print(f"Wrote canonical retrieval-bench report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
