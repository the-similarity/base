"""Ablation comparison — Tier 1 vs Tier 1+2 decision engine.

.. deprecated::
    Lane-specific comparison code is frozen. New lanes MUST use
    :mod:`research.autoresearch.core.gates` (declarative keep/discard) and
    :mod:`research.autoresearch.core.metrics_delta` (paired bootstrap).
    This module remains for the existing retrieval-bench callers only.

Reads the per-(slice, arm) JSON artefacts written by ``run_bench`` and
produces:

1. A ``ComparisonRow`` per slice containing the deltas (Tier 1+2 minus
   Tier 1 baseline) for every primary and secondary metric.
2. An aggregate verdict (``keep`` or ``discard``) obtained by applying the
   thresholds declared in ``slices.yaml``.

The decision logic is documented inline so two agents reading the same
artefacts always reach the same verdict, per the autoresearch rule:
``keep_if`` and ``discard_if`` are orthogonal and the first matching
gate fires.  The function ``decide`` enforces that.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ComparisonRow:
    """Per-slice comparison of the two arms.

    All delta fields are ``tier1_plus_full - tier1_only`` so a positive delta
    means Tier 1+2 improved on that metric (sign handled per metric direction).
    """
    slice_id: str
    tier1_only: dict
    tier1_plus_full: dict

    # Deltas (Tier1+2 minus Tier1-only, signed per metric direction):
    d_forward_return_correlation: float = 0.0   # higher is better -> positive = win
    d_crps: float = 0.0                          # lower is better  -> negative = win
    d_calibration_error: float = 0.0             # lower is better  -> negative = win
    d_hit_rate: float = 0.0                      # higher is better -> positive = win
    runtime_ratio: float = 1.0                   # tier1_plus / tier1_only median runtime

    crps_improved: bool = False                  # strict improvement beyond threshold
    corr_improved: bool = False


@dataclass
class Verdict:
    """Lane decision bundle."""
    decision: str                                # "keep" | "discard"
    rationale: str
    slices_crps_improved: int
    slices_corr_improved: int
    mean_d_crps: float
    mean_d_corr: float
    mean_runtime_ratio: float
    rows: list[ComparisonRow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Artefact loader
# ---------------------------------------------------------------------------

def load_arm_reports(reports_dir: str | Path) -> dict[str, dict[str, dict]]:
    """Group JSON reports by ``slice_id`` -> ``arm_id`` -> ``result dict``.

    ``run_bench`` writes one file per (slice, arm).  We stitch them back
    together here so the comparator can iterate slice-wise.
    """
    reports_dir = Path(reports_dir)
    if not reports_dir.exists():
        raise FileNotFoundError(f"Reports directory not found: {reports_dir}")

    grouped: dict[str, dict[str, dict]] = {}
    for json_path in sorted(reports_dir.glob("*.json")):
        payload = json.loads(json_path.read_text())
        result = payload.get("result") or {}
        slice_id = result.get("slice_id")
        arm_id = result.get("arm_id")
        if not slice_id or not arm_id:
            continue
        grouped.setdefault(slice_id, {})[arm_id] = result
    return grouped


# ---------------------------------------------------------------------------
# Row + verdict construction
# ---------------------------------------------------------------------------

def build_comparison_rows(
    grouped: dict[str, dict[str, dict]],
    baseline_arm: str = "tier1_only",
    experiment_arm: str = "tier1_plus_full",
    thresholds: dict | None = None,
) -> list[ComparisonRow]:
    """Build per-slice ComparisonRows from the grouped report dict.

    Slices missing either arm are skipped — the comparator cannot say
    anything meaningful when only one arm ran.
    """
    thresholds = thresholds or {}
    min_d_crps = float(thresholds.get("min_crps_improvement", 0.005))
    min_d_corr = float(thresholds.get("min_forward_corr_improvement", 0.02))

    rows: list[ComparisonRow] = []
    for slice_id in sorted(grouped.keys()):
        arms = grouped[slice_id]
        a = arms.get(baseline_arm)
        b = arms.get(experiment_arm)
        if a is None or b is None:
            continue

        # Runtime ratio: guard against division-by-zero for degenerate
        # tier1_only runs that timed out to 0.
        a_rt = float(a.get("runtime_seconds", {}).get("median", 0.0)) or 1e-9
        b_rt = float(b.get("runtime_seconds", {}).get("median", 0.0))
        runtime_ratio = b_rt / a_rt

        row = ComparisonRow(
            slice_id=slice_id,
            tier1_only=a,
            tier1_plus_full=b,
            d_forward_return_correlation=float(b["forward_return_correlation"])
            - float(a["forward_return_correlation"]),
            d_crps=float(b["crps"]) - float(a["crps"]),
            d_calibration_error=float(b["calibration_error_p10_p90"])
            - float(a["calibration_error_p10_p90"]),
            d_hit_rate=float(b["hit_rate"]) - float(a["hit_rate"]),
            runtime_ratio=runtime_ratio,
        )
        # CRPS lower is better -> improvement means delta is negative by at
        # least ``min_d_crps`` (i.e. Tier 1+2 CRPS is meaningfully LESS).
        row.crps_improved = row.d_crps <= -min_d_crps
        # Correlation higher is better -> improvement when delta >= threshold.
        row.corr_improved = row.d_forward_return_correlation >= min_d_corr
        rows.append(row)
    return rows


def decide(rows: Iterable[ComparisonRow], thresholds: dict | None = None) -> Verdict:
    """Apply the spec's decision gates and produce a Verdict.

    Gates (in order):
      1. DISCARD if ``runtime_ratio`` median exceeds ``max_runtime_multiplier``
         AND ``slices_crps_improved`` is below threshold (cost without gain).
      2. KEEP if at least ``min_slices_improved`` slices have strict CRPS
         improvement (delta <= -min_crps_improvement).
      3. KEEP if correlation improves on at least ``min_slices_improved``
         slices (secondary win pathway).
      4. DISCARD otherwise.
    """
    thresholds = thresholds or {}
    max_runtime_multiplier = float(thresholds.get("max_runtime_multiplier", 3.0))
    min_slices_improved = int(thresholds.get("min_slices_improved", 3))

    rows_list = list(rows)
    n = len(rows_list)
    slices_crps_improved = sum(1 for r in rows_list if r.crps_improved)
    slices_corr_improved = sum(1 for r in rows_list if r.corr_improved)

    # Mean metrics across rows (guarded for empty input).
    if rows_list:
        mean_d_crps = sum(r.d_crps for r in rows_list) / n
        mean_d_corr = sum(r.d_forward_return_correlation for r in rows_list) / n
        mean_runtime_ratio = sum(r.runtime_ratio for r in rows_list) / n
    else:
        mean_d_crps = mean_d_corr = 0.0
        mean_runtime_ratio = 1.0

    # --- Gate 1: runtime blowout without compensating CRPS wins -> DISCARD
    if mean_runtime_ratio > max_runtime_multiplier and slices_crps_improved < min_slices_improved:
        return Verdict(
            decision="discard",
            rationale=(
                f"Tier 1+2 is {mean_runtime_ratio:.1f}x slower than Tier 1 "
                f"(> {max_runtime_multiplier:.1f}x budget) and only "
                f"{slices_crps_improved}/{n} slices improved CRPS "
                f"(< {min_slices_improved} required)."
            ),
            slices_crps_improved=slices_crps_improved,
            slices_corr_improved=slices_corr_improved,
            mean_d_crps=mean_d_crps,
            mean_d_corr=mean_d_corr,
            mean_runtime_ratio=mean_runtime_ratio,
            rows=rows_list,
        )

    # --- Gate 2: CRPS-majority win -> KEEP
    if slices_crps_improved >= min_slices_improved:
        return Verdict(
            decision="keep",
            rationale=(
                f"Tier 1+2 improved CRPS on {slices_crps_improved}/{n} slices "
                f"(>= {min_slices_improved} required).  Runtime multiplier "
                f"{mean_runtime_ratio:.1f}x remains within budget."
            ),
            slices_crps_improved=slices_crps_improved,
            slices_corr_improved=slices_corr_improved,
            mean_d_crps=mean_d_crps,
            mean_d_corr=mean_d_corr,
            mean_runtime_ratio=mean_runtime_ratio,
            rows=rows_list,
        )

    # --- Gate 3: correlation-majority win -> KEEP (secondary pathway)
    if slices_corr_improved >= min_slices_improved:
        return Verdict(
            decision="keep",
            rationale=(
                f"Tier 1+2 improved forward-return correlation on "
                f"{slices_corr_improved}/{n} slices; CRPS neutral."
            ),
            slices_crps_improved=slices_crps_improved,
            slices_corr_improved=slices_corr_improved,
            mean_d_crps=mean_d_crps,
            mean_d_corr=mean_d_corr,
            mean_runtime_ratio=mean_runtime_ratio,
            rows=rows_list,
        )

    # --- Gate 4: default -> DISCARD (no improvement established)
    return Verdict(
        decision="discard",
        rationale=(
            f"Neither CRPS nor correlation improved on enough slices "
            f"(crps={slices_crps_improved}, corr={slices_corr_improved}, "
            f"min={min_slices_improved})."
        ),
        slices_crps_improved=slices_crps_improved,
        slices_corr_improved=slices_corr_improved,
        mean_d_crps=mean_d_crps,
        mean_d_corr=mean_d_corr,
        mean_runtime_ratio=mean_runtime_ratio,
        rows=rows_list,
    )
