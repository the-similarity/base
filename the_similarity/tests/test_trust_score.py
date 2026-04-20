"""Tests for the trust score computation in the platform trust adapter.

Covers:
- ``compute_trust_score`` bounds and edge cases
- ``compute_calibration_grade`` grading logic
- ``compute_decision`` gate logic
- ``build_trust_artifact`` integration (round-trip, version field)
- ``UNCALIBRATED`` flag presence
- ``TRUST_SCORE_VERSION`` field in serialized output
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
# UNCALIBRATED flag
# ---------------------------------------------------------------------------


class TestUncalibratedFlag:
    """Ensure the UNCALIBRATED sentinel is set so downstream code can gate."""

    def test_uncalibrated_is_true(self):
        assert UNCALIBRATED is True

    def test_trust_score_version_is_string(self):
        assert isinstance(TRUST_SCORE_VERSION, str)
        # Semantic version: at least "X.Y.Z"
        parts = TRUST_SCORE_VERSION.split(".")
        assert len(parts) == 3, "TRUST_SCORE_VERSION must be semver (X.Y.Z)"


# ---------------------------------------------------------------------------
# compute_trust_score
# ---------------------------------------------------------------------------


class TestComputeTrustScore:
    """Verify that compute_trust_score always returns values in [0, 1]."""

    def test_all_zeros(self):
        score = compute_trust_score(hit_rate=0.0, coverage=0.0, crps=0.0)
        # crps=0 -> crps_inv=1.0, so score = 0.3 * 1.0 = 0.3
        assert score == pytest.approx(0.3)
        assert 0.0 <= score <= 1.0

    def test_all_ones(self):
        score = compute_trust_score(hit_rate=1.0, coverage=1.0, crps=1.0)
        # crps=1 -> crps_inv=0.0, so score = 0.4 + 0.3 = 0.7
        assert score == pytest.approx(0.7)

    def test_perfect_score(self):
        # Best possible: hit_rate=1, coverage=1, crps=0 (perfect calibration)
        score = compute_trust_score(hit_rate=1.0, coverage=1.0, crps=0.0)
        assert score == pytest.approx(1.0)
        assert 0.0 <= score <= 1.0

    def test_worst_score(self):
        # Worst possible: hit_rate=0, coverage=0, crps>=1
        score = compute_trust_score(hit_rate=0.0, coverage=0.0, crps=1.0)
        assert score == pytest.approx(0.0)
        assert 0.0 <= score <= 1.0

    def test_crps_above_one_is_clamped(self):
        """CRPS > 1 should be clamped to 1, yielding crps_inv = 0."""
        score_at_one = compute_trust_score(hit_rate=0.5, coverage=0.5, crps=1.0)
        score_at_five = compute_trust_score(hit_rate=0.5, coverage=0.5, crps=5.0)
        assert score_at_one == pytest.approx(score_at_five)

    def test_crps_negative_not_clamped_below(self):
        """Negative CRPS (unusual but possible) gives crps_inv > 1,
        which can push trust_score above 1.0. This is a known limitation
        of the uncalibrated formula — inputs are expected to be >= 0."""
        score = compute_trust_score(hit_rate=1.0, coverage=1.0, crps=-0.5)
        # 0.4 + 0.3 + 0.3*(1-(-0.5)) = 0.4 + 0.3 + 0.45 = 1.15
        # Documents the known lack of lower-bound clamping on CRPS.
        assert score > 1.0

    def test_midrange_values(self):
        score = compute_trust_score(hit_rate=0.6, coverage=0.8, crps=0.3)
        # 0.4*0.6 + 0.3*0.8 + 0.3*(1-0.3) = 0.24 + 0.24 + 0.21 = 0.69
        assert score == pytest.approx(0.69)
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize(
        "hit_rate,coverage,crps",
        [
            (0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0),
            (0.5, 0.5, 0.5),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 1.0, 0.0),
            (0.3, 0.7, 0.9),
        ],
    )
    def test_bounded_for_valid_inputs(self, hit_rate, coverage, crps):
        """For inputs in [0,1], trust_score must be in [0,1]."""
        score = compute_trust_score(hit_rate=hit_rate, coverage=coverage, crps=crps)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# compute_calibration_grade
# ---------------------------------------------------------------------------


class TestComputeCalibrationGrade:
    def test_empty_calibration_is_poor(self):
        assert compute_calibration_grade({}) == "poor"

    def test_perfect_calibration_is_excellent(self):
        calib = {"10": 0.10, "25": 0.25, "50": 0.50, "75": 0.75, "90": 0.90}
        assert compute_calibration_grade(calib) == "excellent"

    def test_slightly_off_is_good(self):
        # Mean abs error ~ 0.07 (between 0.05 and 0.10)
        calib = {"10": 0.17, "50": 0.57, "90": 0.97}
        assert compute_calibration_grade(calib) == "good"

    def test_moderately_off_is_fair(self):
        # Mean abs error ~ 0.15 (between 0.10 and 0.20)
        calib = {"10": 0.25, "50": 0.65, "90": 0.75}
        assert compute_calibration_grade(calib) == "fair"

    def test_badly_off_is_poor(self):
        # Mean abs error >= 0.20
        calib = {"10": 0.50, "50": 0.80, "90": 0.60}
        assert compute_calibration_grade(calib) == "poor"

    def test_non_numeric_keys_skipped(self):
        calib = {"foo": 0.5, "bar": 0.3}
        assert compute_calibration_grade(calib) == "poor"

    def test_mixed_keys_only_numeric_used(self):
        calib = {"50": 0.50, "invalid": 0.99}
        # Only "50" used: error = |0.50 - 0.50| = 0.0 -> excellent
        assert compute_calibration_grade(calib) == "excellent"


# ---------------------------------------------------------------------------
# compute_decision
# ---------------------------------------------------------------------------


class TestComputeDecision:
    def test_high_score_good_grade_is_trusted(self):
        assert compute_decision(0.8, "excellent") == TrustDecision.TRUSTED
        assert compute_decision(0.7, "good") == TrustDecision.TRUSTED

    def test_high_score_poor_grade_is_review(self):
        # Score >= 0.7 but grade not excellent/good -> second clause
        # trust_score >= 0.5 -> REVIEW
        assert compute_decision(0.8, "fair") == TrustDecision.REVIEW
        assert compute_decision(0.8, "poor") == TrustDecision.REVIEW

    def test_mid_score_is_review(self):
        assert compute_decision(0.5, "poor") == TrustDecision.REVIEW
        assert compute_decision(0.6, "poor") == TrustDecision.REVIEW

    def test_fair_grade_forces_review(self):
        # Even a low score with fair grade -> REVIEW
        assert compute_decision(0.3, "fair") == TrustDecision.REVIEW

    def test_low_score_poor_grade_is_rejected(self):
        assert compute_decision(0.2, "poor") == TrustDecision.REJECTED
        assert compute_decision(0.0, "poor") == TrustDecision.REJECTED
        assert compute_decision(0.49, "poor") == TrustDecision.REJECTED

    def test_boundary_0_7_with_good_is_trusted(self):
        assert compute_decision(0.7, "good") == TrustDecision.TRUSTED

    def test_boundary_0_5_is_review(self):
        assert compute_decision(0.5, "poor") == TrustDecision.REVIEW

    def test_just_below_0_5_poor_is_rejected(self):
        assert compute_decision(0.4999, "poor") == TrustDecision.REJECTED


# ---------------------------------------------------------------------------
# build_trust_artifact + round-trip
# ---------------------------------------------------------------------------


class TestBuildTrustArtifact:
    def test_basic_build(self):
        metrics = {
            "hit_rate": 0.65,
            "coverage": 0.80,
            "crps": 0.20,
            "calibration": {"10": 0.10, "50": 0.50, "90": 0.90},
        }
        artifact = build_trust_artifact("run-123", metrics)
        assert isinstance(artifact, TrustArtifact)
        assert artifact.run_id == "run-123"
        assert 0.0 <= artifact.trust_score <= 1.0
        assert artifact.calibration_grade in ("excellent", "good", "fair", "poor")
        assert isinstance(artifact.decision, TrustDecision)
        assert artifact.uncalibrated is True
        assert len(artifact.reasoning) > 0

    def test_missing_metrics_default_to_zero(self):
        artifact = build_trust_artifact("run-empty", {})
        # hit_rate=0, coverage=0, crps=0 -> score = 0.3
        assert artifact.trust_score == pytest.approx(0.3)
        assert artifact.calibration_grade == "poor"

    def test_high_crps_clamped(self):
        metrics = {"hit_rate": 0.5, "coverage": 0.5, "crps": 10.0}
        artifact = build_trust_artifact("run-high-crps", metrics)
        # crps clamped to 1 -> crps_inv=0 -> score = 0.4*0.5 + 0.3*0.5 = 0.35
        assert artifact.trust_score == pytest.approx(0.35)

    def test_to_dict_contains_version(self):
        metrics = {"hit_rate": 0.7, "coverage": 0.8, "crps": 0.1}
        artifact = build_trust_artifact("run-v", metrics)
        d = artifact.to_dict()
        assert "trust_score_version" in d
        assert d["trust_score_version"] == TRUST_SCORE_VERSION

    def test_round_trip(self):
        metrics = {
            "hit_rate": 0.55,
            "coverage": 0.70,
            "crps": 0.30,
            "calibration": {"25": 0.25, "75": 0.75},
        }
        original = build_trust_artifact("run-rt", metrics)
        d = original.to_dict()
        restored = TrustArtifact.from_dict(d)
        assert restored.run_id == original.run_id
        assert restored.trust_score == pytest.approx(original.trust_score)
        assert restored.calibration_grade == original.calibration_grade
        assert restored.decision == original.decision
        assert restored.uncalibrated == original.uncalibrated

    def test_thresholds_recorded(self):
        artifact = build_trust_artifact("run-t", {"hit_rate": 0.5})
        assert "trust_score_trusted_min" in artifact.thresholds
        assert "trust_score_review_min" in artifact.thresholds
        assert artifact.thresholds["trust_weight_hit_rate"] == 0.4
