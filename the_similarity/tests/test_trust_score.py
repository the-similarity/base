"""Tests for the trust score computation in the platform trust adapter.

Covers:
- :func:`compute_trust_score` — boundedness, edge cases, known values
- :func:`compute_calibration_grade` — grade thresholds, empty/invalid input
- :func:`compute_decision` — decision gate logic
- :func:`build_trust_artifact` — end-to-end factory, version tracking
- Module-level ``UNCALIBRATED`` and ``TRUST_SCORE_VERSION`` flags

The trust score formula (v1) is an uncalibrated heuristic:

    trust_score = 0.4 * hit_rate + 0.3 * coverage + 0.3 * (1 - min(crps, 1))

These tests lock down the current behavior so any future calibration
effort can verify it doesn't regress existing semantics.
"""

from __future__ import annotations

import pytest

from the_similarity.platform.adapters.trust import (
    TRUST_SCORE_VERSION,
    UNCALIBRATED,
    TrustArtifact,
    TrustDecision,
    build_trust_artifact,
    compute_calibration_grade,
    compute_decision,
    compute_trust_score,
)


# ---------------------------------------------------------------------------
# Module flags
# ---------------------------------------------------------------------------


class TestModuleFlags:
    """Verify the UNCALIBRATED and TRUST_SCORE_VERSION module constants."""

    def test_uncalibrated_flag_is_true(self):
        """The flag must remain True until the formula is empirically calibrated."""
        assert UNCALIBRATED is True

    def test_trust_score_version_is_string(self):
        """Version must be a non-empty string for registry storage."""
        assert isinstance(TRUST_SCORE_VERSION, str)
        assert len(TRUST_SCORE_VERSION) > 0

    def test_trust_score_version_is_v1(self):
        """Current version is '1'. Bump this test when the formula changes."""
        assert TRUST_SCORE_VERSION == "1"


# ---------------------------------------------------------------------------
# compute_trust_score
# ---------------------------------------------------------------------------


class TestComputeTrustScore:
    """Tests for the composite trust score formula."""

    def test_perfect_inputs_yield_one(self):
        """hit_rate=1, coverage=1, crps=0 -> trust_score = 1.0."""
        score = compute_trust_score(hit_rate=1.0, coverage=1.0, crps=0.0)
        assert score == pytest.approx(1.0)

    def test_worst_inputs_yield_zero(self):
        """hit_rate=0, coverage=0, crps>=1 -> trust_score = 0.0."""
        score = compute_trust_score(hit_rate=0.0, coverage=0.0, crps=1.0)
        assert score == pytest.approx(0.0)

    def test_crps_above_one_clamped(self):
        """CRPS values > 1 are clamped to 1 before inversion."""
        score_at_1 = compute_trust_score(hit_rate=0.5, coverage=0.5, crps=1.0)
        score_at_5 = compute_trust_score(hit_rate=0.5, coverage=0.5, crps=5.0)
        assert score_at_1 == pytest.approx(score_at_5)

    def test_crps_zero_gives_full_crps_component(self):
        """crps=0 means the CRPS inversion component contributes its full weight (0.3)."""
        score = compute_trust_score(hit_rate=0.0, coverage=0.0, crps=0.0)
        # Only the CRPS inversion component is non-zero: 0.3 * 1.0 = 0.3.
        assert score == pytest.approx(0.3)

    def test_result_always_in_unit_interval(self):
        """Trust score must be in [0, 1] for all valid input combinations."""
        test_values = [0.0, 0.25, 0.5, 0.75, 1.0]
        crps_values = [0.0, 0.25, 0.5, 0.75, 1.0, 2.0, 10.0]
        for hr in test_values:
            for cov in test_values:
                for crps in crps_values:
                    score = compute_trust_score(
                        hit_rate=hr, coverage=cov, crps=crps
                    )
                    assert 0.0 <= score <= 1.0, (
                        f"Out of bounds: score={score} for "
                        f"hr={hr}, cov={cov}, crps={crps}"
                    )

    def test_known_midpoint_value(self):
        """Spot-check a known intermediate value."""
        # hit_rate=0.6, coverage=0.8, crps=0.2
        # = 0.4*0.6 + 0.3*0.8 + 0.3*(1-0.2) = 0.24 + 0.24 + 0.24 = 0.72
        score = compute_trust_score(hit_rate=0.6, coverage=0.8, crps=0.2)
        assert score == pytest.approx(0.72)

    def test_hit_rate_zero_coverage_one_crps_zero(self):
        """Edge case: good calibration but zero directional accuracy."""
        # 0.4*0 + 0.3*1 + 0.3*1 = 0.6
        score = compute_trust_score(hit_rate=0.0, coverage=1.0, crps=0.0)
        assert score == pytest.approx(0.6)

    def test_hit_rate_one_coverage_zero_crps_one(self):
        """Edge case: perfect direction but terrible calibration."""
        # 0.4*1 + 0.3*0 + 0.3*0 = 0.4
        score = compute_trust_score(hit_rate=1.0, coverage=0.0, crps=1.0)
        assert score == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# compute_calibration_grade
# ---------------------------------------------------------------------------


class TestComputeCalibrationGrade:
    """Tests for calibration grade assignment."""

    def test_empty_calibration_returns_poor(self):
        """No calibration data -> default to poor (fail-closed)."""
        assert compute_calibration_grade({}) == "poor"

    def test_perfect_calibration_is_excellent(self):
        """Exact match between expected and observed -> excellent."""
        cal = {"10": 0.10, "25": 0.25, "50": 0.50, "75": 0.75, "90": 0.90}
        assert compute_calibration_grade(cal) == "excellent"

    def test_slight_miscalibration_is_good(self):
        """Mean abs error ~0.06 -> good (below 0.10 but above 0.05)."""
        cal = {"10": 0.16, "50": 0.56, "90": 0.96}
        grade = compute_calibration_grade(cal)
        assert grade == "good"

    def test_moderate_miscalibration_is_fair(self):
        """Mean abs error ~0.15 -> fair (below 0.20 but above 0.10)."""
        cal = {"10": 0.25, "50": 0.65, "90": 0.75}
        grade = compute_calibration_grade(cal)
        assert grade == "fair"

    def test_severe_miscalibration_is_poor(self):
        """Mean abs error >= 0.20 -> poor."""
        cal = {"10": 0.40, "50": 0.80, "90": 0.99}
        grade = compute_calibration_grade(cal)
        assert grade == "poor"

    def test_non_numeric_keys_skipped(self):
        """Non-numeric percentile keys are silently ignored."""
        cal = {"abc": 0.5, "10": 0.10}
        # Only the "10" entry counts: |0.10 - 0.10| = 0 -> excellent.
        assert compute_calibration_grade(cal) == "excellent"

    def test_all_non_numeric_keys_returns_poor(self):
        """If all keys are non-numeric, no errors are computable -> poor."""
        cal = {"abc": 0.5, "xyz": 0.8}
        assert compute_calibration_grade(cal) == "poor"


# ---------------------------------------------------------------------------
# compute_decision
# ---------------------------------------------------------------------------


class TestComputeDecision:
    """Tests for the trust decision gate."""

    def test_high_score_excellent_grade_is_trusted(self):
        assert compute_decision(0.8, "excellent") == TrustDecision.TRUSTED

    def test_high_score_good_grade_is_trusted(self):
        assert compute_decision(0.7, "good") == TrustDecision.TRUSTED

    def test_high_score_fair_grade_is_review(self):
        """Score >= 0.7 but grade is fair -> REVIEW (grade gate fails)."""
        assert compute_decision(0.8, "fair") == TrustDecision.REVIEW

    def test_high_score_poor_grade_is_review(self):
        """Score >= 0.7 but grade is poor -> REVIEW (score alone >= 0.5)."""
        assert compute_decision(0.7, "poor") == TrustDecision.REVIEW

    def test_mid_score_any_grade_is_review(self):
        """Score in [0.5, 0.7) -> REVIEW regardless of grade."""
        assert compute_decision(0.5, "poor") == TrustDecision.REVIEW
        assert compute_decision(0.6, "excellent") == TrustDecision.REVIEW

    def test_low_score_fair_grade_is_review(self):
        """Score < 0.5 but grade == fair -> REVIEW (grade clause)."""
        assert compute_decision(0.3, "fair") == TrustDecision.REVIEW

    def test_low_score_poor_grade_is_rejected(self):
        """Score < 0.5 and grade poor -> REJECTED."""
        assert compute_decision(0.3, "poor") == TrustDecision.REJECTED

    def test_zero_score_poor_grade_is_rejected(self):
        assert compute_decision(0.0, "poor") == TrustDecision.REJECTED

    def test_boundary_at_0_7_with_good_grade(self):
        """Exactly 0.7 with good grade should be TRUSTED."""
        assert compute_decision(0.7, "good") == TrustDecision.TRUSTED

    def test_boundary_just_below_0_7_with_good_grade(self):
        """Just below 0.7 with good grade -> REVIEW."""
        assert compute_decision(0.699, "good") == TrustDecision.REVIEW

    def test_boundary_at_0_5_with_poor_grade(self):
        """Exactly 0.5 with poor grade -> REVIEW."""
        assert compute_decision(0.5, "poor") == TrustDecision.REVIEW

    def test_boundary_just_below_0_5_with_poor_grade(self):
        """Just below 0.5 with poor grade -> REJECTED."""
        assert compute_decision(0.499, "poor") == TrustDecision.REJECTED


# ---------------------------------------------------------------------------
# build_trust_artifact (end-to-end factory)
# ---------------------------------------------------------------------------


class TestBuildTrustArtifact:
    """Tests for the artifact factory function."""

    def test_basic_construction(self):
        """Factory produces a valid TrustArtifact with expected fields."""
        metrics = {
            "hit_rate": 0.65,
            "coverage": 0.80,
            "crps": 0.15,
            "calibration": {"10": 0.10, "50": 0.50, "90": 0.90},
        }
        artifact = build_trust_artifact("run-001", metrics)

        assert isinstance(artifact, TrustArtifact)
        assert artifact.run_id == "run-001"
        assert 0.0 <= artifact.trust_score <= 1.0
        assert artifact.calibration_grade in (
            "excellent", "good", "fair", "poor"
        )
        assert isinstance(artifact.decision, TrustDecision)
        assert artifact.uncalibrated is True
        assert artifact.trust_score_version == TRUST_SCORE_VERSION

    def test_version_in_serialized_dict(self):
        """to_dict must include trust_score_version."""
        metrics = {"hit_rate": 0.5, "coverage": 0.5, "crps": 0.5}
        artifact = build_trust_artifact("run-002", metrics)
        d = artifact.to_dict()

        assert "trust_score_version" in d
        assert d["trust_score_version"] == TRUST_SCORE_VERSION

    def test_round_trip_serialization(self):
        """to_dict -> from_dict must preserve all fields."""
        metrics = {
            "hit_rate": 0.7,
            "coverage": 0.85,
            "crps": 0.1,
            "calibration": {"10": 0.12, "50": 0.48, "90": 0.92},
        }
        original = build_trust_artifact("run-003", metrics)
        restored = TrustArtifact.from_dict(original.to_dict())

        assert restored.run_id == original.run_id
        assert restored.trust_score == pytest.approx(original.trust_score)
        assert restored.calibration_grade == original.calibration_grade
        assert restored.decision == original.decision
        assert restored.uncalibrated == original.uncalibrated
        assert restored.trust_score_version == original.trust_score_version

    def test_from_dict_without_version_defaults_to_v1(self):
        """Legacy dicts without trust_score_version should default to '1'."""
        metrics = {"hit_rate": 0.5, "coverage": 0.5, "crps": 0.5}
        artifact = build_trust_artifact("run-004", metrics)
        d = artifact.to_dict()
        # Simulate a legacy dict that lacks the version key.
        del d["trust_score_version"]
        restored = TrustArtifact.from_dict(d)
        assert restored.trust_score_version == "1"

    def test_missing_metrics_default_to_zero(self):
        """Empty metrics snapshot -> hit_rate=0, coverage=0, crps=0."""
        artifact = build_trust_artifact("run-005", {})
        # 0.4*0 + 0.3*0 + 0.3*(1-0) = 0.3
        assert artifact.trust_score == pytest.approx(0.3)

    def test_thresholds_recorded_in_artifact(self):
        """The artifact's thresholds dict must include all decision parameters."""
        artifact = build_trust_artifact("run-006", {"hit_rate": 0.5})
        t = artifact.thresholds
        assert "trust_score_trusted_min" in t
        assert "trust_score_review_min" in t
        assert "trust_weight_hit_rate" in t
        assert "trust_weight_coverage" in t
        assert "trust_weight_crps_inv" in t

    def test_reasoning_is_non_empty_string(self):
        """Every artifact must have a human-readable reasoning."""
        artifact = build_trust_artifact("run-007", {"hit_rate": 0.8})
        assert isinstance(artifact.reasoning, str)
        assert len(artifact.reasoning) > 0

    def test_edge_case_crps_above_one(self):
        """CRPS > 1 must not push trust_score below 0."""
        artifact = build_trust_artifact(
            "run-008",
            {"hit_rate": 0.0, "coverage": 0.0, "crps": 100.0},
        )
        assert artifact.trust_score == pytest.approx(0.0)
        assert artifact.trust_score >= 0.0

    def test_edge_case_full_coverage(self):
        """coverage=1.0 contributes its full weight (0.3)."""
        artifact = build_trust_artifact(
            "run-009",
            {"hit_rate": 0.0, "coverage": 1.0, "crps": 1.0},
        )
        # 0.4*0 + 0.3*1 + 0.3*0 = 0.3
        assert artifact.trust_score == pytest.approx(0.3)
