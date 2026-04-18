"""Tests for finance run standardization — trust + calibration artifacts.

Covers:
1. Trust score computation (known inputs -> expected score)
2. Calibration grade assignment (boundary cases)
3. Decision logic (TRUSTED/REVIEW/REJECTED for each boundary)
4. Round-trip serialization of TrustArtifact and CalibrationArtifact
5. End-to-end: mock BacktestReport -> register -> verify registry has
   run + trust + calibration artifacts + scorecard
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from the_similarity.platform.adapters.trust import (
    TrustArtifact,
    TrustDecision,
    build_trust_artifact,
    compute_calibration_grade,
    compute_decision,
    compute_trust_score,
)
from the_similarity.platform.adapters.calibration import (
    CalibrationArtifact,
    build_calibration_artifact,
)
from the_similarity.platform.adapters.finance import (
    register_backtest_run,
    _coerce_report,
    _enrich_summary,
)
from the_similarity.platform.registry import RunRegistry
from the_similarity.platform.artifacts import RunKind
from the_similarity.platform.contracts import ScorecardKind


# ---------------------------------------------------------------------------
# 1. Trust score computation
# ---------------------------------------------------------------------------


class TestComputeTrustScore:
    """Trust score = 0.4 * hit_rate + 0.3 * coverage + 0.3 * (1 - min(crps, 1))."""

    def test_perfect_metrics(self):
        """Perfect inputs (hit_rate=1, coverage=1, crps=0) should yield 1.0."""
        score = compute_trust_score(hit_rate=1.0, coverage=1.0, crps=0.0)
        assert score == pytest.approx(1.0)

    def test_worst_metrics(self):
        """Worst inputs (hit_rate=0, coverage=0, crps=1) should yield 0.0."""
        score = compute_trust_score(hit_rate=0.0, coverage=0.0, crps=1.0)
        assert score == pytest.approx(0.0)

    def test_typical_metrics(self):
        """hit_rate=0.7, coverage=0.8, crps=0.3 -> 0.4*0.7 + 0.3*0.8 + 0.3*0.7 = 0.73."""
        score = compute_trust_score(hit_rate=0.7, coverage=0.8, crps=0.3)
        expected = 0.4 * 0.7 + 0.3 * 0.8 + 0.3 * (1 - 0.3)
        assert score == pytest.approx(expected)

    def test_crps_clamped_above_one(self):
        """CRPS > 1 should be clamped to 1, making the CRPS component 0."""
        score = compute_trust_score(hit_rate=0.5, coverage=0.5, crps=2.0)
        # 0.4 * 0.5 + 0.3 * 0.5 + 0.3 * 0.0 = 0.35
        assert score == pytest.approx(0.35)

    def test_score_bounded(self):
        """Trust score must always be in [0, 1]."""
        for hr in [0.0, 0.5, 1.0]:
            for cov in [0.0, 0.5, 1.0]:
                for crps_val in [0.0, 0.5, 1.0, 2.0]:
                    score = compute_trust_score(hr, cov, crps_val)
                    assert 0.0 <= score <= 1.0, f"Out of bounds: {score}"


# ---------------------------------------------------------------------------
# 2. Calibration grade assignment
# ---------------------------------------------------------------------------


class TestCalibrationGrade:
    """Letter grade based on mean absolute calibration error across percentiles.

    Contract (see ``the_similarity/platform/adapters/trust.py``):

    - A: < 0.03
    - B: < 0.06
    - C: < 0.10
    - D: < 0.15
    - F: >= 0.15
    """

    def test_grade_a(self):
        """Mean error < 0.03 -> A."""
        # P10=0.10, P50=0.50, P90=0.90 => all errors = 0
        calibration = {"10": 0.10, "50": 0.50, "90": 0.90}
        assert compute_calibration_grade(calibration) == "A"

    def test_grade_a_boundary(self):
        """Mean error = 0.029 -> A (just under the 0.03 cutoff)."""
        # P10: expected=0.10, observed=0.129 => error=0.029
        calibration = {"10": 0.129}
        assert compute_calibration_grade(calibration) == "A"

    def test_grade_b(self):
        """Mean error in [0.03, 0.06) -> B."""
        # P50: expected=0.50, observed=0.455 => error=0.045
        calibration = {"50": 0.455}
        assert compute_calibration_grade(calibration) == "B"

    def test_grade_c(self):
        """Mean error in [0.06, 0.10) -> C."""
        # P50: expected=0.50, observed=0.43 => error=0.07
        calibration = {"50": 0.43}
        assert compute_calibration_grade(calibration) == "C"

    def test_grade_d(self):
        """Mean error in [0.10, 0.15) -> D."""
        # P50: expected=0.50, observed=0.38 => error=0.12
        calibration = {"50": 0.38}
        assert compute_calibration_grade(calibration) == "D"

    def test_grade_f(self):
        """Mean error >= 0.15 -> F."""
        # P50: expected=0.50, observed=0.25 => error=0.25
        calibration = {"50": 0.25}
        assert compute_calibration_grade(calibration) == "F"

    def test_empty_calibration(self):
        """Empty calibration dict -> F (fail-closed)."""
        assert compute_calibration_grade({}) == "F"

    def test_non_numeric_keys_skipped(self):
        """Non-numeric keys are silently skipped."""
        calibration = {"foo": 0.5, "10": 0.10}
        assert compute_calibration_grade(calibration) == "A"


# ---------------------------------------------------------------------------
# 3. Decision logic
# ---------------------------------------------------------------------------


class TestDecisionLogic:
    """Decision: TRUSTED / REVIEW / REJECTED based on trust_score + grade.

    Rule set:

    - trust_score >= 0.7 AND grade in (A, B) -> TRUSTED
    - trust_score >= 0.5 OR  grade == C      -> REVIEW
    - else                                   -> REJECTED
    """

    def test_trusted_high_score_grade_a(self):
        """trust_score >= 0.7 AND grade == A -> TRUSTED."""
        assert compute_decision(0.8, "A") == TrustDecision.TRUSTED

    def test_trusted_high_score_grade_b(self):
        """trust_score >= 0.7 AND grade == B -> TRUSTED."""
        assert compute_decision(0.7, "B") == TrustDecision.TRUSTED

    def test_trusted_boundary(self):
        """trust_score = 0.7 exactly, grade = A -> TRUSTED."""
        assert compute_decision(0.7, "A") == TrustDecision.TRUSTED

    def test_review_high_score_grade_c(self):
        """trust_score >= 0.7 but grade == C -> REVIEW (not TRUSTED)."""
        assert compute_decision(0.8, "C") == TrustDecision.REVIEW

    def test_review_medium_score_grade_b(self):
        """trust_score in [0.5, 0.7) -> REVIEW regardless of grade."""
        assert compute_decision(0.6, "B") == TrustDecision.REVIEW

    def test_review_low_score_grade_c(self):
        """trust_score < 0.5 but grade == C -> REVIEW."""
        assert compute_decision(0.3, "C") == TrustDecision.REVIEW

    def test_review_boundary(self):
        """trust_score = 0.5 exactly -> REVIEW."""
        assert compute_decision(0.5, "F") == TrustDecision.REVIEW

    def test_rejected_grade_f(self):
        """trust_score < 0.5 AND grade == F -> REJECTED."""
        assert compute_decision(0.3, "F") == TrustDecision.REJECTED

    def test_rejected_grade_d(self):
        """trust_score < 0.5 AND grade == D -> REJECTED.

        D does not qualify for the C-grade review escape hatch.
        """
        assert compute_decision(0.3, "D") == TrustDecision.REJECTED

    def test_rejected_zero_score(self):
        """trust_score = 0.0 AND grade == F -> REJECTED."""
        assert compute_decision(0.0, "F") == TrustDecision.REJECTED

    def test_high_score_grade_f(self):
        """trust_score >= 0.7 but grade == F -> REVIEW (not TRUSTED)."""
        assert compute_decision(0.9, "F") == TrustDecision.REVIEW


# ---------------------------------------------------------------------------
# 4. Round-trip serialization
# ---------------------------------------------------------------------------


class TestTrustArtifactSerialization:
    """TrustArtifact to_dict / from_dict round-trip."""

    def _make_artifact(self) -> TrustArtifact:
        return TrustArtifact(
            run_id="abc123",
            trust_score=0.75,
            calibration_grade="B",
            metrics_snapshot={"hit_rate": 0.7, "coverage": 0.8, "crps": 0.2},
            decision=TrustDecision.TRUSTED,
            thresholds={"trust_score_trusted_min": 0.7},
            reasoning="Looks good.",
            created_at="2026-04-15T00:00:00+00:00",
        )

    def test_round_trip(self):
        original = self._make_artifact()
        d = original.to_dict()
        # Ensure JSON serializable
        json_str = json.dumps(d)
        reconstructed = TrustArtifact.from_dict(json.loads(json_str))

        assert reconstructed.run_id == original.run_id
        assert reconstructed.trust_score == original.trust_score
        assert reconstructed.calibration_grade == original.calibration_grade
        assert reconstructed.metrics_snapshot == original.metrics_snapshot
        assert reconstructed.decision == original.decision
        assert reconstructed.thresholds == original.thresholds
        assert reconstructed.reasoning == original.reasoning
        assert reconstructed.created_at == original.created_at

    def test_decision_enum_serializes_as_string(self):
        artifact = self._make_artifact()
        d = artifact.to_dict()
        assert d["decision"] == "trusted"
        assert isinstance(d["decision"], str)


class TestCalibrationArtifactSerialization:
    """CalibrationArtifact to_dict / from_dict round-trip."""

    def _make_artifact(self) -> CalibrationArtifact:
        return CalibrationArtifact(
            run_id="abc123",
            percentiles=[10, 50, 90],
            expected_coverage=[0.10, 0.50, 0.90],
            observed_coverage=[0.12, 0.48, 0.88],
            calibration_errors=[0.02, 0.02, 0.02],
            mean_calibration_error=0.02,
            max_calibration_error=0.02,
            created_at="2026-04-15T00:00:00+00:00",
        )

    def test_round_trip(self):
        original = self._make_artifact()
        d = original.to_dict()
        json_str = json.dumps(d)
        reconstructed = CalibrationArtifact.from_dict(json.loads(json_str))

        assert reconstructed.run_id == original.run_id
        assert reconstructed.percentiles == original.percentiles
        assert reconstructed.expected_coverage == original.expected_coverage
        assert reconstructed.observed_coverage == original.observed_coverage
        assert reconstructed.calibration_errors == original.calibration_errors
        assert reconstructed.mean_calibration_error == pytest.approx(
            original.mean_calibration_error
        )
        assert reconstructed.max_calibration_error == pytest.approx(
            original.max_calibration_error
        )
        assert reconstructed.created_at == original.created_at


class TestBuildCalibrationArtifact:
    """Factory function for CalibrationArtifact."""

    def test_basic_build(self):
        calibration = {"10": 0.12, "50": 0.48, "90": 0.88}
        artifact = build_calibration_artifact("run1", calibration)

        assert artifact.run_id == "run1"
        assert artifact.percentiles == [10, 50, 90]
        assert artifact.expected_coverage == [0.10, 0.50, 0.90]
        assert artifact.observed_coverage == [0.12, 0.48, 0.88]
        assert len(artifact.calibration_errors) == 3
        assert artifact.mean_calibration_error == pytest.approx(0.02)
        assert artifact.max_calibration_error == pytest.approx(0.02)

    def test_empty_calibration(self):
        artifact = build_calibration_artifact("run1", {})
        assert artifact.percentiles == []
        assert artifact.mean_calibration_error == 0.0
        assert artifact.max_calibration_error == 0.0

    def test_non_numeric_keys_skipped(self):
        calibration = {"foo": 0.5, "10": 0.10}
        artifact = build_calibration_artifact("run1", calibration)
        assert artifact.percentiles == [10]


class TestBuildTrustArtifact:
    """Factory function for TrustArtifact."""

    def test_basic_build(self):
        metrics = {
            "hit_rate": 0.8,
            "coverage": 0.85,
            "crps": 0.15,
            "calibration": {"10": 0.10, "50": 0.50, "90": 0.90},
        }
        artifact = build_trust_artifact("run1", metrics)

        assert artifact.run_id == "run1"
        # 0.4*0.8 + 0.3*0.85 + 0.3*0.85 = 0.83
        expected_score = 0.4 * 0.8 + 0.3 * 0.85 + 0.3 * (1 - 0.15)
        assert artifact.trust_score == pytest.approx(expected_score)
        assert artifact.calibration_grade == "A"
        assert artifact.decision == TrustDecision.TRUSTED
        assert len(artifact.reasoning) > 0
        assert len(artifact.thresholds) > 0

    def test_missing_metrics_default_to_zero(self):
        """Missing metrics should default to 0.0 / empty.

        Empty calibration -> grade F, low trust_score -> REJECTED.
        """
        artifact = build_trust_artifact("run1", {})
        assert artifact.trust_score == pytest.approx(0.3)  # 0.3 * (1-0)
        assert artifact.calibration_grade == "F"
        assert artifact.decision == TrustDecision.REJECTED


# ---------------------------------------------------------------------------
# 5. End-to-end: mock BacktestReport -> register -> verify registry
# ---------------------------------------------------------------------------


class TestEndToEndRegistration:
    """Register a mock backtest report and verify the registry state."""

    def _make_report_dict(self) -> Dict[str, Any]:
        """Build a dict mimicking BacktestReport's computed properties."""
        return {
            "hit_rate": 0.75,
            "mean_error": 0.03,
            "crps": 0.2,
            "coverage": 0.82,
            "interval_score": 0.15,
            "profit_factor": 1.5,
            "max_drawdown": 0.08,
            "sharpe": 1.2,
            "n_valid_trials": 90,
            "n_skipped_trials": 10,
            "window_size": 60,
            "forward_bars": 20,
            "calibration": {
                10: 0.12,
                25: 0.27,
                50: 0.52,
                75: 0.73,
                90: 0.88,
            },
        }

    def test_register_creates_run_and_artifacts(self):
        """Full registration flow: run + trust artifact + calibration artifact + scorecard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            report = self._make_report_dict()

            run_id = register_backtest_run(
                report,
                config={"window_size": 60, "forward_bars": 20},
                seed=42,
                db_path=db_path,
                source_id="spy",
            )

            assert run_id is not None
            assert len(run_id) == 32  # UUID4 hex

            # Verify the registry has the run
            with RunRegistry(db_path) as r:
                runs = r.list_runs(kind=RunKind.FINANCE)
                assert len(runs) == 1
                run = runs[0]
                assert run.run_id == run_id
                assert run.summary["pillar"] == "finance"
                # Verify enriched summary fields
                assert "trust_score" in run.summary
                assert "calibration_grade" in run.summary
                assert 0.0 <= run.summary["trust_score"] <= 1.0
                assert run.summary["calibration_grade"] in (
                    "A",
                    "B",
                    "C",
                    "D",
                    "F",
                )

                # Verify artifact records
                artifacts = r.list_artifacts(run_id)
                artifact_names = {a.name for a in artifacts}
                assert "trust" in artifact_names
                assert "calibration" in artifact_names

                # Verify scorecard
                scorecards = r.get_scorecards(run_id)
                assert len(scorecards) == 1
                sc = scorecards[0]
                assert sc.kind == ScorecardKind.BACKTEST
                assert sc.overall_score is not None
                assert "trust_score" in sc.details
                assert "calibration_grade" in sc.details
                assert "decision" in sc.details

    def test_register_with_explicit_run_id(self):
        """Caller can pass a custom run_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            report = self._make_report_dict()

            run_id = register_backtest_run(
                report,
                db_path=db_path,
                run_id="custom_run_id_12345678901234",
            )
            assert run_id == "custom_run_id_12345678901234"

    def test_register_with_provided_registry(self):
        """Caller can pass a pre-opened registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            report = self._make_report_dict()

            with RunRegistry(db_path) as r:
                run_id = register_backtest_run(
                    report,
                    registry=r,
                    seed=42,
                )
                assert run_id is not None
                # Verify in same session
                runs = r.list_runs(kind=RunKind.FINANCE)
                assert len(runs) == 1

    def test_all_metrics_in_summary(self):
        """Verify all expected metrics appear in the registered summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            report = self._make_report_dict()

            run_id = register_backtest_run(report, db_path=db_path)

            with RunRegistry(db_path) as r:
                run = r.get_run(run_id)
                assert run is not None
                s = run.summary
                # All core metrics must be present
                assert "hit_rate" in s
                assert "mean_error" in s
                assert "crps" in s
                assert "coverage" in s
                assert "interval_score" in s
                assert "profit_factor" in s
                assert "max_drawdown" in s
                assert "sharpe" in s
                assert "n_valid_trials" in s
                assert "n_skipped_trials" in s
                assert "calibration" in s
                # Enriched fields
                assert "trust_score" in s
                assert "calibration_grade" in s


class TestEnrichSummary:
    """Test _enrich_summary adds trust_score and calibration_grade."""

    def test_enrich_adds_fields(self):
        summary = {
            "hit_rate": 0.7,
            "coverage": 0.8,
            "crps": 0.3,
            "calibration": {"10": 0.10, "50": 0.50, "90": 0.90},
        }
        result = _enrich_summary(summary)
        assert "trust_score" in result
        assert "calibration_grade" in result
        expected_score = 0.4 * 0.7 + 0.3 * 0.8 + 0.3 * (1 - 0.3)
        assert result["trust_score"] == pytest.approx(expected_score)
        assert result["calibration_grade"] == "A"

    def test_enrich_missing_metrics(self):
        """Missing metrics default to 0.0; empty calibration -> F."""
        summary: Dict[str, Any] = {}
        result = _enrich_summary(summary)
        assert result["trust_score"] == pytest.approx(0.3)
        assert result["calibration_grade"] == "F"


class TestCoerceReport:
    """Test _coerce_report handles both dict and object inputs."""

    def test_dict_input(self):
        report = {
            "hit_rate": 0.7,
            "crps": 0.2,
            "calibration": {10: 0.12, 50: 0.48},
        }
        result = _coerce_report(report)
        assert result["hit_rate"] == 0.7
        assert result["crps"] == 0.2
        # calibration keys should be strings
        assert "10" in result["calibration"]
        assert "50" in result["calibration"]

    def test_object_input(self):
        """Object with attributes is correctly coerced."""

        class FakeReport:
            hit_rate = 0.8
            crps = 0.15
            coverage = 0.85
            calibration = {10: 0.10, 50: 0.50}

        result = _coerce_report(FakeReport())
        assert result["hit_rate"] == 0.8
        assert result["crps"] == 0.15
        assert result["coverage"] == 0.85
        assert "10" in result["calibration"]
