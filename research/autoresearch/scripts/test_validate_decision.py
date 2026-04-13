"""Tests for the deterministic keep/discard validation script.

Covers gate-level logic, aggregate verdicts, edge cases (missing data,
zero runtime), and CLI integration.  All tests are self-contained and
do not require benchmark YAML files on disk — they construct thresholds
dicts directly, except for the CLI integration tests which use a temp file.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from validate_decision import (
    DecisionResult,
    GateResult,
    evaluate_decision,
    load_thresholds,
    main,
)


# ── Shared fixtures ──────────────────────────────────────────────────

# Standard JEPA retrieval thresholds
JEPA_THRESHOLDS = {
    "min_crps_improvement": 0.005,
    "max_calibration_regression": 0.02,
    "max_runtime_multiplier": 2.0,
    "min_slices_improved": 1,
    "walk_forward_required": True,
}

# Standard projector calibration thresholds
PROJECTOR_THRESHOLDS = {
    "min_calibration_improvement": 0.005,
    "max_crps_regression": 0.01,
    "max_runtime_multiplier": 2.0,
    "min_slices_improved": 1,
    "walk_forward_required": True,
}

BASELINE_BEFORE = {
    "crps": 0.339,
    "calibration_error_p10_p90": 0.50,
    "runtime_seconds": 3.7,
}


# ── KEEP scenarios ───────────────────────────────────────────────────

class TestKeepDecisions:
    """Scenarios that should produce a KEEP verdict."""

    def test_clear_improvement(self):
        """Significant CRPS drop, stable calibration, reasonable runtime."""
        after = {
            "crps": 0.330,
            "calibration_error_p10_p90": 0.49,
            "runtime_seconds": 4.0,
        }
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "KEEP"
        assert all(g.passed for g in result.gates)

    def test_exact_threshold_boundary(self):
        """CRPS improves by exactly min_crps_improvement — should KEEP."""
        after = {
            "crps": 0.339 - 0.005,  # exactly at threshold
            "calibration_error_p10_p90": 0.50,
            "runtime_seconds": 3.7,
        }
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "KEEP"

    def test_calibration_improves_greatly(self):
        """Large calibration improvement with modest CRPS improvement."""
        after = {
            "crps": 0.333,
            "calibration_error_p10_p90": 0.30,
            "runtime_seconds": 3.7,
        }
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "KEEP"

    def test_runtime_at_exact_multiplier(self):
        """Runtime exactly at the 2.0x ceiling — should KEEP."""
        after = {
            "crps": 0.330,
            "calibration_error_p10_p90": 0.50,
            "runtime_seconds": 7.4,  # exactly 2.0x
        }
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "KEEP"


# ── DISCARD scenarios ────────────────────────────────────────────────

class TestDiscardDecisions:
    """Scenarios that should produce a DISCARD verdict."""

    def test_crps_insufficient_improvement(self):
        """CRPS improves but not enough to cross min_crps_improvement."""
        after = {
            "crps": 0.337,  # only 0.002 improvement
            "calibration_error_p10_p90": 0.49,
            "runtime_seconds": 3.7,
        }
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "DISCARD"
        failed_gates = [g.gate_name for g in result.gates if not g.passed]
        assert "min_crps_improvement" in failed_gates

    def test_crps_worsens(self):
        """CRPS gets worse — should DISCARD."""
        after = {
            "crps": 0.345,
            "calibration_error_p10_p90": 0.49,
            "runtime_seconds": 3.7,
        }
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "DISCARD"

    def test_calibration_regression_too_large(self):
        """Calibration regresses beyond max_calibration_regression."""
        after = {
            "crps": 0.330,
            "calibration_error_p10_p90": 0.53,  # 0.03 regression > 0.02 limit
            "runtime_seconds": 3.7,
        }
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "DISCARD"
        failed_gates = [g.gate_name for g in result.gates if not g.passed]
        assert "max_calibration_regression" in failed_gates

    def test_runtime_too_slow(self):
        """Runtime exceeds 2.0x multiplier."""
        after = {
            "crps": 0.330,
            "calibration_error_p10_p90": 0.50,
            "runtime_seconds": 8.0,  # 2.16x
        }
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "DISCARD"
        failed_gates = [g.gate_name for g in result.gates if not g.passed]
        assert "max_runtime_multiplier" in failed_gates

    def test_walk_forward_not_confirmed(self):
        """Walk-forward not confirmed — should DISCARD."""
        after = {
            "crps": 0.330,
            "calibration_error_p10_p90": 0.49,
            "runtime_seconds": 3.7,
        }
        result = evaluate_decision(
            BASELINE_BEFORE, after, JEPA_THRESHOLDS,
            walk_forward_confirmed=False,
        )
        assert result.decision == "DISCARD"
        failed_gates = [g.gate_name for g in result.gates if not g.passed]
        assert "walk_forward_required" in failed_gates

    def test_no_slices_improved(self):
        """Explicit slices_improved=0 — should DISCARD."""
        after = {
            "crps": 0.330,
            "calibration_error_p10_p90": 0.49,
            "runtime_seconds": 3.7,
        }
        result = evaluate_decision(
            BASELINE_BEFORE, after, JEPA_THRESHOLDS,
            slices_improved=0,
        )
        assert result.decision == "DISCARD"
        failed_gates = [g.gate_name for g in result.gates if not g.passed]
        assert "min_slices_improved" in failed_gates


# ── Projector calibration lane ───────────────────────────────────────

class TestProjectorLane:
    """Tests using projector-calibration thresholds."""

    def test_projector_keep(self):
        """Calibration improves, CRPS stable."""
        before = {"crps": 0.20, "calibration_error_p10_p90": 0.10, "runtime_seconds": 10.0}
        after = {"crps": 0.20, "calibration_error_p10_p90": 0.09, "runtime_seconds": 10.0}
        result = evaluate_decision(before, after, PROJECTOR_THRESHOLDS)
        assert result.decision == "KEEP"

    def test_projector_discard_crps_regresses(self):
        """Calibration improves but CRPS regresses too much."""
        before = {"crps": 0.20, "calibration_error_p10_p90": 0.10, "runtime_seconds": 10.0}
        after = {"crps": 0.22, "calibration_error_p10_p90": 0.08, "runtime_seconds": 10.0}
        result = evaluate_decision(before, after, PROJECTOR_THRESHOLDS)
        assert result.decision == "DISCARD"
        failed_gates = [g.gate_name for g in result.gates if not g.passed]
        assert "max_crps_regression" in failed_gates

    def test_projector_discard_calibration_not_enough(self):
        """Calibration improvement below threshold."""
        before = {"crps": 0.20, "calibration_error_p10_p90": 0.10, "runtime_seconds": 10.0}
        after = {"crps": 0.20, "calibration_error_p10_p90": 0.098, "runtime_seconds": 10.0}
        result = evaluate_decision(before, after, PROJECTOR_THRESHOLDS)
        assert result.decision == "DISCARD"


# ── Edge cases ───────────────────────────────────────────────────────

class TestEdgeCases:
    """Missing data, zero runtime, empty thresholds."""

    def test_missing_crps(self):
        """Missing CRPS in after — fail-closed DISCARD."""
        after = {"calibration_error_p10_p90": 0.49, "runtime_seconds": 3.7}
        result = evaluate_decision(BASELINE_BEFORE, after, JEPA_THRESHOLDS)
        assert result.decision == "DISCARD"

    def test_missing_calibration(self):
        """Missing calibration — fail-closed DISCARD."""
        before = {"crps": 0.339, "runtime_seconds": 3.7}
        after = {"crps": 0.330, "runtime_seconds": 3.7}
        result = evaluate_decision(before, after, JEPA_THRESHOLDS)
        assert result.decision == "DISCARD"

    def test_zero_runtime_before(self):
        """Zero runtime in before — fail-closed on runtime gate."""
        before = {"crps": 0.339, "calibration_error_p10_p90": 0.50, "runtime_seconds": 0.0}
        after = {"crps": 0.330, "calibration_error_p10_p90": 0.49, "runtime_seconds": 3.7}
        result = evaluate_decision(before, after, JEPA_THRESHOLDS)
        assert result.decision == "DISCARD"
        failed_gates = [g.gate_name for g in result.gates if not g.passed]
        assert "max_runtime_multiplier" in failed_gates

    def test_empty_thresholds(self):
        """No thresholds at all — vacuously KEEP (no gates to fail)."""
        result = evaluate_decision(BASELINE_BEFORE, BASELINE_BEFORE, {})
        assert result.decision == "KEEP"
        assert len(result.gates) == 0


# ── Serialization ────────────────────────────────────────────────────

class TestSerialization:
    """DecisionResult.to_dict() round-trip."""

    def test_to_dict_structure(self):
        result = evaluate_decision(
            BASELINE_BEFORE,
            {"crps": 0.330, "calibration_error_p10_p90": 0.49, "runtime_seconds": 4.0},
            JEPA_THRESHOLDS,
        )
        d = result.to_dict()
        assert d["decision"] in ("KEEP", "DISCARD")
        assert isinstance(d["gates"], list)
        assert all("gate" in g and "passed" in g and "reason" in g for g in d["gates"])
        # Should be JSON-serializable
        json.dumps(d)


# ── YAML loader ──────────────────────────────────────────────────────

class TestLoadThresholds:
    """Tests for load_thresholds() with real temp files."""

    def test_valid_yaml(self, tmp_path: Path):
        """Round-trip: write YAML, load it, check thresholds."""
        yaml_content = textwrap.dedent("""\
            id: test-bench
            thresholds:
              min_crps_improvement: 0.01
              max_runtime_multiplier: 1.5
        """)
        p = tmp_path / "bench.yaml"
        p.write_text(yaml_content)
        t = load_thresholds(p)
        assert t["min_crps_improvement"] == 0.01
        assert t["max_runtime_multiplier"] == 1.5

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_thresholds(tmp_path / "nope.yaml")

    def test_no_thresholds_section(self, tmp_path: Path):
        p = tmp_path / "bench.yaml"
        p.write_text("id: test\nscorecard: {}\n")
        with pytest.raises(ValueError, match="no 'thresholds' section"):
            load_thresholds(p)


# ── CLI integration ──────────────────────────────────────────────────

class TestCLI:
    """End-to-end CLI tests using main()."""

    @pytest.fixture()
    def benchmark_file(self, tmp_path: Path) -> Path:
        """Write a temporary benchmark YAML for CLI tests."""
        content = textwrap.dedent("""\
            id: cli-test
            thresholds:
              min_crps_improvement: 0.005
              max_calibration_regression: 0.02
              max_runtime_multiplier: 2.0
              min_slices_improved: 1
              walk_forward_required: true
        """)
        p = tmp_path / "bench.yaml"
        p.write_text(content)
        return p

    def test_cli_keep(self, benchmark_file: Path):
        """CLI returns 0 for KEEP."""
        exit_code = main([
            "--benchmark", str(benchmark_file),
            "--before", json.dumps(BASELINE_BEFORE),
            "--after", json.dumps({
                "crps": 0.330,
                "calibration_error_p10_p90": 0.49,
                "runtime_seconds": 4.0,
            }),
        ])
        assert exit_code == 0

    def test_cli_discard(self, benchmark_file: Path):
        """CLI returns 1 for DISCARD."""
        exit_code = main([
            "--benchmark", str(benchmark_file),
            "--before", json.dumps(BASELINE_BEFORE),
            "--after", json.dumps({
                "crps": 0.338,  # not enough improvement
                "calibration_error_p10_p90": 0.50,
                "runtime_seconds": 3.7,
            }),
        ])
        assert exit_code == 1

    def test_cli_json_output(self, benchmark_file: Path, capsys):
        """CLI --json flag produces parseable JSON."""
        main([
            "--benchmark", str(benchmark_file),
            "--before", json.dumps(BASELINE_BEFORE),
            "--after", json.dumps({
                "crps": 0.330,
                "calibration_error_p10_p90": 0.49,
                "runtime_seconds": 4.0,
            }),
            "--json",
        ])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["decision"] == "KEEP"

    def test_cli_no_walk_forward_flag(self, benchmark_file: Path):
        """--no-walk-forward triggers the walk-forward gate failure."""
        exit_code = main([
            "--benchmark", str(benchmark_file),
            "--before", json.dumps(BASELINE_BEFORE),
            "--after", json.dumps({
                "crps": 0.330,
                "calibration_error_p10_p90": 0.49,
                "runtime_seconds": 4.0,
            }),
            "--no-walk-forward",
        ])
        assert exit_code == 1

    def test_cli_missing_benchmark(self):
        """Missing benchmark file returns exit code 2."""
        exit_code = main([
            "--benchmark", "/nonexistent/path.yaml",
            "--before", "{}",
            "--after", "{}",
        ])
        assert exit_code == 2

    def test_cli_bad_json(self, benchmark_file: Path):
        """Malformed JSON returns exit code 2."""
        exit_code = main([
            "--benchmark", str(benchmark_file),
            "--before", "not-json",
            "--after", "{}",
        ])
        assert exit_code == 2
