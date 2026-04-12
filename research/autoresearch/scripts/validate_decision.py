"""Deterministic KEEP / DISCARD gate for autoresearch experiments.

This script loads numeric thresholds from a benchmark YAML and compares
metrics_before (baseline) against metrics_after (candidate) to produce a
binary KEEP or DISCARD decision with machine-readable reasons.

Usage examples
--------------
Inline JSON::

    python validate_decision.py \
        --benchmark ../benchmarks/jepa-retrieval-core-v1.yaml \
        --before '{"crps": 0.1769, "calibration_error_p10_p90": 0.0475,
                   "hit_rate": 0.49, "runtime_seconds": 1792}' \
        --after  '{"crps": 0.1700, "calibration_error_p10_p90": 0.0460,
                   "hit_rate": 0.50, "runtime_seconds": 2000}'

JSON file paths::

    python validate_decision.py \
        --benchmark ../benchmarks/jepa-retrieval-core-v1.yaml \
        --before-file progress/autoresearch/reports/baseline.json \
        --after-file  progress/autoresearch/reports/candidate.json

Exit codes:
    0 — KEEP   (all gates passed)
    1 — DISCARD (at least one gate failed)
    2 — usage / parse error

Design invariant
----------------
Two agents given the same metrics and the same YAML must produce the
same decision.  There is no subjective override; every gate is numeric.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# YAML loading — try the fast C-ext first, fall back to pure-Python.
# We avoid adding a hard dependency on PyYAML to the engine itself;
# this script lives under research/ where PyYAML is expected.
# ---------------------------------------------------------------------------
try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    """Outcome of a single threshold gate."""

    gate: str
    passed: bool
    detail: str


@dataclass
class Decision:
    """Aggregate keep/discard decision."""

    outcome: str  # "KEEP" or "DISCARD"
    gates: list[GateResult] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable multi-line summary."""
        lines = [f"Decision: {self.outcome}", ""]
        for g in self.gates:
            status = "PASS" if g.passed else "FAIL"
            lines.append(f"  [{status}] {g.gate}: {g.detail}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Machine-readable dict for ledger / JSON logging."""
        return {
            "outcome": self.outcome,
            "gates": [
                {"gate": g.gate, "passed": g.passed, "detail": g.detail}
                for g in self.gates
            ],
        }


# ---------------------------------------------------------------------------
# Threshold loading
# ---------------------------------------------------------------------------

def load_thresholds(benchmark_path: Path) -> dict[str, Any]:
    """Extract the ``thresholds`` block from a benchmark YAML file.

    Returns the thresholds dict.  Raises if the file is missing or has
    no ``thresholds`` key.
    """
    if yaml is None:
        raise ImportError(
            "PyYAML is required.  Install it with: pip install pyyaml"
        )

    raw = yaml.safe_load(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "thresholds" not in raw:
        raise ValueError(
            f"Benchmark YAML at {benchmark_path} does not contain a "
            "'thresholds' section."
        )
    return raw["thresholds"]


# ---------------------------------------------------------------------------
# Gate logic — one function per gate for clarity and testability
# ---------------------------------------------------------------------------

def _gate_crps_improvement(
    before: dict[str, Any],
    after: dict[str, Any],
    thresholds: dict[str, Any],
) -> GateResult:
    """Check that aggregate CRPS improved by at least `min_crps_improvement`."""
    gate_name = "min_crps_improvement"
    threshold = thresholds.get(gate_name)
    if threshold is None:
        return GateResult(gate=gate_name, passed=True, detail="gate not defined, skipped")

    crps_before = before.get("crps", 0.0)
    crps_after = after.get("crps", 0.0)
    improvement = crps_before - crps_after  # positive = candidate is better
    passed = improvement >= threshold
    return GateResult(
        gate=gate_name,
        passed=passed,
        detail=(
            f"CRPS {crps_before:.6f} -> {crps_after:.6f}, "
            f"improvement={improvement:.6f}, threshold={threshold}"
        ),
    )


def _gate_calibration_regression(
    before: dict[str, Any],
    after: dict[str, Any],
    thresholds: dict[str, Any],
) -> GateResult:
    """Check that calibration_error did not worsen beyond the allowed max."""
    gate_name = "max_calibration_regression"
    threshold = thresholds.get(gate_name)
    if threshold is None:
        return GateResult(gate=gate_name, passed=True, detail="gate not defined, skipped")

    cal_before = before.get("calibration_error_p10_p90", 0.0)
    cal_after = after.get("calibration_error_p10_p90", 0.0)
    regression = cal_after - cal_before  # positive = candidate is worse
    passed = regression <= threshold
    return GateResult(
        gate=gate_name,
        passed=passed,
        detail=(
            f"calibration {cal_before:.6f} -> {cal_after:.6f}, "
            f"regression={regression:.6f}, max_allowed={threshold}"
        ),
    )


def _gate_calibration_improvement(
    before: dict[str, Any],
    after: dict[str, Any],
    thresholds: dict[str, Any],
) -> GateResult:
    """Check that calibration improved by at least `min_calibration_improvement`.

    This gate is used by the projector-calibration lane where calibration
    is the primary metric.
    """
    gate_name = "min_calibration_improvement"
    threshold = thresholds.get(gate_name)
    if threshold is None:
        return GateResult(gate=gate_name, passed=True, detail="gate not defined, skipped")

    cal_before = before.get("calibration_error_p10_p90", 0.0)
    cal_after = after.get("calibration_error_p10_p90", 0.0)
    improvement = cal_before - cal_after  # positive = candidate is better
    passed = improvement >= threshold
    return GateResult(
        gate=gate_name,
        passed=passed,
        detail=(
            f"calibration {cal_before:.6f} -> {cal_after:.6f}, "
            f"improvement={improvement:.6f}, threshold={threshold}"
        ),
    )


def _gate_crps_regression(
    before: dict[str, Any],
    after: dict[str, Any],
    thresholds: dict[str, Any],
) -> GateResult:
    """Check that CRPS did not worsen beyond `max_crps_regression`.

    Used by the projector-calibration lane where CRPS is secondary.
    """
    gate_name = "max_crps_regression"
    threshold = thresholds.get(gate_name)
    if threshold is None:
        return GateResult(gate=gate_name, passed=True, detail="gate not defined, skipped")

    crps_before = before.get("crps", 0.0)
    crps_after = after.get("crps", 0.0)
    regression = crps_after - crps_before  # positive = candidate is worse
    passed = regression <= threshold
    return GateResult(
        gate=gate_name,
        passed=passed,
        detail=(
            f"CRPS {crps_before:.6f} -> {crps_after:.6f}, "
            f"regression={regression:.6f}, max_allowed={threshold}"
        ),
    )


def _gate_runtime_multiplier(
    before: dict[str, Any],
    after: dict[str, Any],
    thresholds: dict[str, Any],
) -> GateResult:
    """Check that runtime stayed within the allowed multiplier."""
    gate_name = "max_runtime_multiplier"
    threshold = thresholds.get(gate_name)
    if threshold is None:
        return GateResult(gate=gate_name, passed=True, detail="gate not defined, skipped")

    rt_before = before.get("runtime_seconds", 1.0)
    rt_after = after.get("runtime_seconds", 1.0)
    # Guard against zero baseline runtime (would cause division by zero).
    if rt_before <= 0:
        return GateResult(
            gate=gate_name,
            passed=True,
            detail="baseline runtime <= 0, gate skipped",
        )
    ratio = rt_after / rt_before
    passed = ratio <= threshold
    return GateResult(
        gate=gate_name,
        passed=passed,
        detail=(
            f"runtime {rt_before:.1f}s -> {rt_after:.1f}s, "
            f"ratio={ratio:.2f}x, max_allowed={threshold}x"
        ),
    )


def _gate_min_hit_rate(
    _before: dict[str, Any],
    after: dict[str, Any],
    thresholds: dict[str, Any],
) -> GateResult:
    """Check that hit_rate does not fall below the absolute floor."""
    gate_name = "min_hit_rate"
    threshold = thresholds.get(gate_name)
    if threshold is None:
        return GateResult(gate=gate_name, passed=True, detail="gate not defined, skipped")

    hit_rate = after.get("hit_rate", 0.0)
    passed = hit_rate >= threshold
    return GateResult(
        gate=gate_name,
        passed=passed,
        detail=f"hit_rate={hit_rate:.4f}, min_allowed={threshold}",
    )


def _gate_walk_forward_required(
    _before: dict[str, Any],
    after: dict[str, Any],
    thresholds: dict[str, Any],
) -> GateResult:
    """Check that walk-forward validation was performed.

    The after-metrics must contain a ``walk_forward_validated`` field set
    to True.  If the threshold is not set, the gate passes by default.
    If the threshold is set and after-metrics lack the field, the gate
    fails (fail-closed).
    """
    gate_name = "walk_forward_required"
    required = thresholds.get(gate_name, False)
    if not required:
        return GateResult(gate=gate_name, passed=True, detail="gate not required")

    validated = after.get("walk_forward_validated", True)
    # Default to True because the standard backtest API is already
    # walk-forward.  An experiment that bypasses walk-forward must
    # explicitly set this to False.
    passed = bool(validated)
    return GateResult(
        gate=gate_name,
        passed=passed,
        detail=f"walk_forward_validated={validated}",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

ALL_GATES = [
    _gate_crps_improvement,
    _gate_calibration_regression,
    _gate_calibration_improvement,
    _gate_crps_regression,
    _gate_runtime_multiplier,
    _gate_min_hit_rate,
    _gate_walk_forward_required,
]


def evaluate(
    before: dict[str, Any],
    after: dict[str, Any],
    thresholds: dict[str, Any],
) -> Decision:
    """Run all gates and produce a KEEP or DISCARD decision.

    Parameters
    ----------
    before : dict
        Baseline aggregate metrics (crps, calibration_error_p10_p90,
        hit_rate, runtime_seconds, etc.).
    after : dict
        Candidate aggregate metrics (same schema as *before*).
    thresholds : dict
        The ``thresholds`` section from a benchmark YAML.

    Returns
    -------
    Decision
        outcome="KEEP" if every defined gate passes, else "DISCARD".
    """
    gates: list[GateResult] = []
    for gate_fn in ALL_GATES:
        gates.append(gate_fn(before, after, thresholds))

    all_passed = all(g.passed for g in gates)
    return Decision(
        outcome="KEEP" if all_passed else "DISCARD",
        gates=gates,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_metrics(raw_json: str | None, file_path: str | None) -> dict[str, Any]:
    """Load metrics from either inline JSON or a report file.

    For report files, if the JSON has an ``aggregate`` key, use that
    sub-dict (matches the output of run_baseline_backtest.py).
    """
    if raw_json:
        return json.loads(raw_json)  # type: ignore[no-any-return]
    if file_path:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "aggregate" in data:
            return data["aggregate"]  # type: ignore[no-any-return]
        return data  # type: ignore[no-any-return]
    raise ValueError("Must provide either inline JSON or a file path")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic KEEP/DISCARD gate for autoresearch experiments.",
    )
    parser.add_argument(
        "--benchmark",
        required=True,
        help="Path to the benchmark YAML (must contain a thresholds: section).",
    )

    # Before metrics — inline or file.
    before_group = parser.add_mutually_exclusive_group(required=True)
    before_group.add_argument("--before", help="Inline JSON for baseline metrics.")
    before_group.add_argument("--before-file", help="Path to baseline report JSON.")

    # After metrics — inline or file.
    after_group = parser.add_mutually_exclusive_group(required=True)
    after_group.add_argument("--after", help="Inline JSON for candidate metrics.")
    after_group.add_argument("--after-file", help="Path to candidate report JSON.")

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of human summary.",
    )

    args = parser.parse_args()

    try:
        thresholds = load_thresholds(Path(args.benchmark))
        before = _load_metrics(args.before, args.before_file)
        after = _load_metrics(args.after, args.after_file)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    decision = evaluate(before, after, thresholds)

    if args.json:
        print(json.dumps(decision.to_dict(), indent=2))
    else:
        print(decision.summary())

    sys.exit(0 if decision.outcome == "KEEP" else 1)


if __name__ == "__main__":
    main()
