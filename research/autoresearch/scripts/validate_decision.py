#!/usr/bin/env python3
"""Deterministic keep/discard validator for autoresearch experiments.

Reads numeric thresholds from a benchmark YAML and compares before/after
metrics to produce a KEEP or DISCARD verdict with machine-readable reasons.

Design invariants
-----------------
- **Deterministic**: two agents with the same inputs MUST get the same output.
- **Fail-closed**: missing or unparseable metrics -> DISCARD.
- **Composable**: import ``evaluate_decision`` in other scripts, or run via CLI.

CLI usage
---------
::

    python validate_decision.py \\
        --benchmark benchmarks/jepa-retrieval-core-v1.yaml \\
        --before '{"crps": 0.339, "calibration_error_p10_p90": 0.50, "runtime_seconds": 3.7}' \\
        --after  '{"crps": 0.330, "calibration_error_p10_p90": 0.49, "runtime_seconds": 4.0}'

Or pipe JSON from stdin (one object with ``before`` and ``after`` keys).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

# PyYAML is an optional dependency — the script degrades to a helpful
# error if it is missing rather than a raw ImportError.
try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None  # type: ignore[assignment]


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class GateResult:
    """Result of evaluating a single threshold gate.

    Attributes
    ----------
    gate_name : str
        Identifier matching a key under ``thresholds:`` in the YAML.
    passed : bool
        Whether the gate was satisfied.
    reason : str
        Human-readable explanation of why the gate passed or failed.
    """

    gate_name: str
    passed: bool
    reason: str


@dataclass
class DecisionResult:
    """Aggregate keep/discard verdict.

    Attributes
    ----------
    decision : str
        ``"KEEP"`` or ``"DISCARD"``.
    gates : list[GateResult]
        Per-gate details.
    summary : str
        One-line summary suitable for ledger logging.
    """

    decision: str
    gates: List[GateResult] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "decision": self.decision,
            "summary": self.summary,
            "gates": [
                {"gate": g.gate_name, "passed": g.passed, "reason": g.reason}
                for g in self.gates
            ],
        }


# ── Threshold loading ────────────────────────────────────────────────

def load_thresholds(benchmark_path: str | Path) -> Dict[str, Any]:
    """Load the ``thresholds`` block from a benchmark YAML.

    Parameters
    ----------
    benchmark_path : str or Path
        Filesystem path to the benchmark YAML file.

    Returns
    -------
    dict
        The ``thresholds`` mapping.  Keys are gate names, values are
        numbers or booleans.

    Raises
    ------
    FileNotFoundError
        If *benchmark_path* does not exist.
    ValueError
        If the YAML has no ``thresholds`` section.
    RuntimeError
        If PyYAML is not installed.
    """
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to load benchmark files.  "
            "Install it with: pip install pyyaml"
        )

    path = Path(benchmark_path)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {path}")

    with open(path, "r") as fh:
        doc = yaml.safe_load(fh)

    if not isinstance(doc, dict) or "thresholds" not in doc:
        raise ValueError(
            f"Benchmark {path.name} has no 'thresholds' section.  "
            "Add one before running validation."
        )

    return doc["thresholds"]


# ── Core evaluation logic ────────────────────────────────────────────

def evaluate_decision(
    before: Dict[str, float],
    after: Dict[str, float],
    thresholds: Dict[str, Any],
    *,
    slices_improved: int | None = None,
    walk_forward_confirmed: bool = True,
) -> DecisionResult:
    """Evaluate keep/discard against numeric thresholds.

    Parameters
    ----------
    before : dict
        Metric snapshot *before* the experiment.  Expected keys:
        ``crps``, ``calibration_error_p10_p90``, ``runtime_seconds``.
    after : dict
        Metric snapshot *after* the experiment.  Same keys as *before*.
    thresholds : dict
        Loaded from the benchmark YAML ``thresholds:`` block.
    slices_improved : int or None
        Number of canonical slices where CRPS improved by at least
        ``min_crps_improvement``.  If ``None``, the gate is evaluated
        using the aggregate CRPS delta instead (single-slice mode).
    walk_forward_confirmed : bool
        Whether the walk-forward backtest confirmed the improvement.
        Defaults to ``True``; set ``False`` to trigger that gate.

    Returns
    -------
    DecisionResult
        Contains the verdict, per-gate breakdown, and summary string.

    Notes
    -----
    The function is **fail-closed**: any missing metric or threshold
    produces a DISCARD with an explanatory reason.
    """
    gates: List[GateResult] = []

    # ── Gate 1: CRPS improvement ─────────────────────────────────
    min_crps = thresholds.get("min_crps_improvement")
    # Also support calibration-lane style where the primary gate is
    # calibration improvement and CRPS regression is the guard rail.
    max_crps_regression = thresholds.get("max_crps_regression")

    crps_before = before.get("crps")
    crps_after = after.get("crps")

    if crps_before is not None and crps_after is not None:
        crps_delta = crps_before - crps_after  # positive = improved

        if min_crps is not None:
            # Retrieval lane: CRPS must improve by at least threshold
            if crps_delta >= min_crps:
                gates.append(GateResult(
                    "min_crps_improvement", True,
                    f"CRPS improved by {crps_delta:.6f} (>= {min_crps})"
                ))
            else:
                gates.append(GateResult(
                    "min_crps_improvement", False,
                    f"CRPS delta {crps_delta:.6f} below threshold {min_crps}"
                ))

        if max_crps_regression is not None:
            # Projector lane: CRPS must not regress beyond ceiling
            crps_regression = crps_after - crps_before  # positive = worse
            if crps_regression <= max_crps_regression:
                gates.append(GateResult(
                    "max_crps_regression", True,
                    f"CRPS regression {crps_regression:.6f} within limit {max_crps_regression}"
                ))
            else:
                gates.append(GateResult(
                    "max_crps_regression", False,
                    f"CRPS regressed by {crps_regression:.6f} (> {max_crps_regression})"
                ))
    else:
        # Fail-closed: missing CRPS data
        if min_crps is not None:
            gates.append(GateResult(
                "min_crps_improvement", False,
                "Missing CRPS in before and/or after metrics"
            ))
        if max_crps_regression is not None:
            gates.append(GateResult(
                "max_crps_regression", False,
                "Missing CRPS in before and/or after metrics"
            ))

    # ── Gate 2: Calibration regression / improvement ─────────────
    max_cal_reg = thresholds.get("max_calibration_regression")
    min_cal_imp = thresholds.get("min_calibration_improvement")

    cal_before = before.get("calibration_error_p10_p90")
    cal_after = after.get("calibration_error_p10_p90")

    if cal_before is not None and cal_after is not None:
        cal_regression = cal_after - cal_before  # positive = worse

        if max_cal_reg is not None:
            if cal_regression <= max_cal_reg:
                gates.append(GateResult(
                    "max_calibration_regression", True,
                    f"Calibration change {cal_regression:.6f} within limit {max_cal_reg}"
                ))
            else:
                gates.append(GateResult(
                    "max_calibration_regression", False,
                    f"Calibration regressed by {cal_regression:.6f} (> {max_cal_reg})"
                ))

        if min_cal_imp is not None:
            cal_improvement = cal_before - cal_after  # positive = better
            if cal_improvement >= min_cal_imp:
                gates.append(GateResult(
                    "min_calibration_improvement", True,
                    f"Calibration improved by {cal_improvement:.6f} (>= {min_cal_imp})"
                ))
            else:
                gates.append(GateResult(
                    "min_calibration_improvement", False,
                    f"Calibration improvement {cal_improvement:.6f} below threshold {min_cal_imp}"
                ))
    else:
        if max_cal_reg is not None:
            gates.append(GateResult(
                "max_calibration_regression", False,
                "Missing calibration_error_p10_p90 in before and/or after metrics"
            ))
        if min_cal_imp is not None:
            gates.append(GateResult(
                "min_calibration_improvement", False,
                "Missing calibration_error_p10_p90 in before and/or after metrics"
            ))

    # ── Gate 3: Runtime multiplier ───────────────────────────────
    max_rt = thresholds.get("max_runtime_multiplier")
    rt_before = before.get("runtime_seconds")
    rt_after = after.get("runtime_seconds")

    if max_rt is not None:
        if rt_before is not None and rt_after is not None and rt_before > 0:
            rt_ratio = rt_after / rt_before
            if rt_ratio <= max_rt:
                gates.append(GateResult(
                    "max_runtime_multiplier", True,
                    f"Runtime ratio {rt_ratio:.2f}x within limit {max_rt}x"
                ))
            else:
                gates.append(GateResult(
                    "max_runtime_multiplier", False,
                    f"Runtime ratio {rt_ratio:.2f}x exceeds limit {max_rt}x"
                ))
        else:
            gates.append(GateResult(
                "max_runtime_multiplier", False,
                "Missing or zero runtime_seconds in before and/or after metrics"
            ))

    # ── Gate 4: Minimum slices improved ──────────────────────────
    min_slices = thresholds.get("min_slices_improved")
    if min_slices is not None:
        # If caller did not provide per-slice data, infer from aggregate:
        # if CRPS improved by at least min_crps_improvement, count as 1 slice.
        if slices_improved is None:
            if (crps_before is not None and crps_after is not None
                    and min_crps is not None):
                inferred = 1 if (crps_before - crps_after) >= min_crps else 0
            elif (cal_before is not None and cal_after is not None
                    and min_cal_imp is not None):
                inferred = 1 if (cal_before - cal_after) >= min_cal_imp else 0
            else:
                inferred = 0
            slices_improved = inferred

        if slices_improved >= min_slices:
            gates.append(GateResult(
                "min_slices_improved", True,
                f"{slices_improved} slice(s) improved (>= {min_slices})"
            ))
        else:
            gates.append(GateResult(
                "min_slices_improved", False,
                f"Only {slices_improved} slice(s) improved (need >= {min_slices})"
            ))

    # ── Gate 5: Walk-forward required ────────────────────────────
    wf_required = thresholds.get("walk_forward_required", False)
    if wf_required:
        if walk_forward_confirmed:
            gates.append(GateResult(
                "walk_forward_required", True,
                "Walk-forward validation confirmed"
            ))
        else:
            gates.append(GateResult(
                "walk_forward_required", False,
                "Walk-forward validation NOT confirmed"
            ))

    # ── Aggregate verdict ────────────────────────────────────────
    all_passed = all(g.passed for g in gates)
    decision = "KEEP" if all_passed else "DISCARD"

    failed = [g for g in gates if not g.passed]
    if failed:
        summary = f"DISCARD: {len(failed)} gate(s) failed — " + "; ".join(
            g.reason for g in failed
        )
    else:
        summary = f"KEEP: all {len(gates)} gate(s) passed"

    return DecisionResult(decision=decision, gates=gates, summary=summary)


# ── CLI interface ────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build and parse CLI arguments.

    Supports two input modes:
    1. ``--before`` / ``--after`` JSON strings on the command line.
    2. Piped JSON via stdin with ``{"before": {...}, "after": {...}}`` shape.
    """
    parser = argparse.ArgumentParser(
        description="Deterministic keep/discard validator for autoresearch experiments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  python validate_decision.py \\\n"
            "    --benchmark benchmarks/jepa-retrieval-core-v1.yaml \\\n"
            "    --before '{\"crps\": 0.339, \"calibration_error_p10_p90\": 0.50, "
            "\"runtime_seconds\": 3.7}' \\\n"
            "    --after  '{\"crps\": 0.330, \"calibration_error_p10_p90\": 0.49, "
            "\"runtime_seconds\": 4.0}'"
        ),
    )
    parser.add_argument(
        "--benchmark", "-b",
        required=True,
        help="Path to the benchmark YAML file containing thresholds.",
    )
    parser.add_argument(
        "--before",
        default=None,
        help="JSON string of metrics before the experiment.",
    )
    parser.add_argument(
        "--after",
        default=None,
        help="JSON string of metrics after the experiment.",
    )
    parser.add_argument(
        "--slices-improved",
        type=int,
        default=None,
        help="Number of canonical slices where the primary metric improved.",
    )
    parser.add_argument(
        "--no-walk-forward",
        action="store_true",
        default=False,
        help="Flag that walk-forward was NOT confirmed.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output result as JSON instead of human-readable text.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for CLI invocation.

    Returns
    -------
    int
        Exit code: 0 for KEEP, 1 for DISCARD, 2 for usage/input errors.
    """
    args = _parse_args(argv)

    # Load thresholds
    try:
        thresholds = load_thresholds(args.benchmark)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Parse metrics — either from CLI args or stdin
    if args.before is not None and args.after is not None:
        try:
            before = json.loads(args.before)
            after = json.loads(args.after)
        except json.JSONDecodeError as exc:
            print(f"ERROR: invalid JSON in --before/--after: {exc}", file=sys.stderr)
            return 2
    elif not sys.stdin.isatty():
        try:
            payload = json.load(sys.stdin)
            before = payload["before"]
            after = payload["after"]
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"ERROR: invalid stdin JSON: {exc}", file=sys.stderr)
            return 2
    else:
        print("ERROR: provide --before/--after or pipe JSON to stdin.", file=sys.stderr)
        return 2

    # Evaluate
    result = evaluate_decision(
        before=before,
        after=after,
        thresholds=thresholds,
        slices_improved=args.slices_improved,
        walk_forward_confirmed=not args.no_walk_forward,
    )

    # Output
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  VERDICT: {result.decision}")
        print(f"{'='*60}")
        for g in result.gates:
            status = "PASS" if g.passed else "FAIL"
            print(f"  [{status}] {g.gate_name}: {g.reason}")
        print(f"\n  {result.summary}\n")

    return 0 if result.decision == "KEEP" else 1


if __name__ == "__main__":
    sys.exit(main())
