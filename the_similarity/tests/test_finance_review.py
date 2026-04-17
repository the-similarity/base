"""Tests for the finance review subpackage.

Covers:
- ReviewArtifact round-trip serialization (to_dict / from_dict / file I/O)
- Risk flag detection (each flag individually + combined)
- Signal summary generation (normal + missing fields)
- API endpoint logic (via TestClient when FastAPI is available, else unit tests)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from the_similarity.finance.review import ReviewArtifact, ReviewStatus
from the_similarity.finance.risk_flags import (
    HIGH_CRPS,
    HIGH_DRAWDOWN,
    HIGH_SKIP_RATE,
    LOW_COVERAGE,
    LOW_HIT_RATE,
    LOW_TRIAL_COUNT,
    POOR_CALIBRATION,
    detect_risk_flags,
)
from the_similarity.finance.signal_summary import generate_signal_summary


# =========================================================================
# ReviewArtifact serialization
# =========================================================================


class TestReviewArtifactSerialization:
    """Round-trip tests for ReviewArtifact to_dict / from_dict."""

    def _make_review(self, **overrides) -> ReviewArtifact:
        """Factory for a ReviewArtifact with sensible defaults."""
        defaults = dict(
            review_id="abc123def456",
            run_id="run000111",
            reviewer="test-agent-v1",
            status=ReviewStatus.PENDING,
            signal_summary="SPY 60-bar window found 8 analogues",
            trust_decision="REVIEW",
            calibration_context={"p10": 0.08, "p50": 0.02, "p90": 0.12},
            risk_flags=["low_trial_count"],
            notes="Needs more data",
            realized_outcome=None,
            created_at="2026-04-15T10:00:00Z",
            updated_at=None,
        )
        defaults.update(overrides)
        return ReviewArtifact(**defaults)

    def test_round_trip_basic(self):
        """to_dict -> from_dict produces an identical artifact."""
        review = self._make_review()
        d = review.to_dict()
        restored = ReviewArtifact.from_dict(d)

        assert restored.review_id == review.review_id
        assert restored.run_id == review.run_id
        assert restored.reviewer == review.reviewer
        assert restored.status == review.status
        assert restored.signal_summary == review.signal_summary
        assert restored.trust_decision == review.trust_decision
        assert restored.calibration_context == review.calibration_context
        assert restored.risk_flags == review.risk_flags
        assert restored.notes == review.notes
        assert restored.realized_outcome == review.realized_outcome
        assert restored.created_at == review.created_at
        assert restored.updated_at == review.updated_at

    def test_round_trip_with_realized_outcome(self):
        """Realized outcome dict survives round-trip."""
        review = self._make_review(
            realized_outcome={"actual_return": 0.05, "hit": True, "notes": "rose 5%"},
            updated_at="2026-04-16T10:00:00Z",
        )
        restored = ReviewArtifact.from_dict(review.to_dict())
        assert restored.realized_outcome == {
            "actual_return": 0.05,
            "hit": True,
            "notes": "rose 5%",
        }
        assert restored.updated_at == "2026-04-16T10:00:00Z"

    def test_enum_serializes_to_string(self):
        """Status enum serializes to its string value in to_dict."""
        review = self._make_review(status=ReviewStatus.APPROVED)
        d = review.to_dict()
        assert d["status"] == "approved"
        assert isinstance(d["status"], str)

    def test_from_dict_coerces_string_status(self):
        """from_dict accepts status as a raw string."""
        d = self._make_review().to_dict()
        d["status"] = "flagged"
        restored = ReviewArtifact.from_dict(d)
        assert restored.status == ReviewStatus.FLAGGED

    def test_from_dict_invalid_status_raises(self):
        """from_dict raises ValueError on an unknown status."""
        d = self._make_review().to_dict()
        d["status"] = "invalid_status"
        with pytest.raises(ValueError):
            ReviewArtifact.from_dict(d)

    def test_from_dict_missing_required_field_raises(self):
        """from_dict raises KeyError when required fields are missing."""
        d = self._make_review().to_dict()
        del d["run_id"]
        with pytest.raises(KeyError):
            ReviewArtifact.from_dict(d)

    def test_from_dict_tolerates_missing_optional_fields(self):
        """from_dict handles missing optional fields gracefully."""
        d = {
            "review_id": "abc",
            "run_id": "run1",
            "reviewer": "agent",
            "status": "pending",
            "signal_summary": "summary",
            "trust_decision": "REVIEW",
        }
        review = ReviewArtifact.from_dict(d)
        assert review.calibration_context == {}
        assert review.risk_flags == []
        assert review.notes == ""
        assert review.realized_outcome is None
        assert review.updated_at is None

    def test_from_dict_ignores_unknown_keys(self):
        """from_dict ignores extra keys for forward compatibility."""
        d = self._make_review().to_dict()
        d["future_field"] = "something"
        restored = ReviewArtifact.from_dict(d)
        assert restored.review_id == "abc123def456"

    def test_new_review_id_unique(self):
        """new_review_id generates unique IDs."""
        ids = {ReviewArtifact.new_review_id() for _ in range(100)}
        assert len(ids) == 100

    def test_new_review_id_format(self):
        """new_review_id returns a 32-char hex string."""
        rid = ReviewArtifact.new_review_id()
        assert len(rid) == 32
        assert all(c in "0123456789abcdef" for c in rid)


class TestReviewArtifactFileIO:
    """File read/write round-trip tests."""

    def test_write_and_read(self):
        """write_review -> read_review round-trips."""
        review = ReviewArtifact(
            review_id="file_test_id",
            run_id="run_file_test",
            reviewer="human@example.com",
            status=ReviewStatus.APPROVED,
            signal_summary="Test signal",
            trust_decision="TRUSTED",
            calibration_context={"p50": 0.01},
            risk_flags=[],
            notes="All good",
            created_at="2026-04-15T12:00:00Z",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "review.json"
            review.write_review(path)

            assert path.exists()
            restored = ReviewArtifact.read_review(path)

            assert restored.review_id == review.review_id
            assert restored.status == ReviewStatus.APPROVED
            assert restored.trust_decision == "TRUSTED"
            assert restored.calibration_context == {"p50": 0.01}

    def test_read_nonexistent_raises(self):
        """read_review raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            ReviewArtifact.read_review("/nonexistent/path/review.json")

    def test_write_creates_parent_dirs(self):
        """write_review creates parent directories."""
        review = ReviewArtifact(
            review_id="dir_test",
            run_id="run_dir",
            reviewer="agent",
            status=ReviewStatus.PENDING,
            signal_summary="test",
            trust_decision="REVIEW",
            created_at="2026-04-15T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "a" / "b" / "c" / "review.json"
            result = review.write_review(path)
            assert result.exists()
            assert result == path


# =========================================================================
# Risk flag detection
# =========================================================================


class TestRiskFlagDetection:
    """Tests for detect_risk_flags with each flag individually and combined."""

    def test_empty_summary_no_flags(self):
        """Empty summary dict produces no flags."""
        assert detect_risk_flags({}) == []

    def test_healthy_summary_no_flags(self):
        """A healthy summary with all metrics above thresholds produces no flags."""
        summary = {
            "n_valid_trials": 50,
            "n_skipped_trials": 5,
            "hit_rate": 0.65,
            "max_drawdown": 0.15,
            "coverage": 0.85,
            "crps": 0.25,
            "calibration": 0.08,
        }
        assert detect_risk_flags(summary) == []

    def test_low_trial_count(self):
        """Triggers when n_valid_trials < 20."""
        flags = detect_risk_flags({"n_valid_trials": 15})
        assert LOW_TRIAL_COUNT in flags

    def test_low_trial_count_boundary(self):
        """Exactly 20 trials should NOT flag."""
        flags = detect_risk_flags({"n_valid_trials": 20})
        assert LOW_TRIAL_COUNT not in flags

    def test_high_skip_rate(self):
        """Triggers when skip rate > 0.3."""
        flags = detect_risk_flags(
            {
                "n_valid_trials": 10,
                "n_skipped_trials": 10,  # 50% skip rate
            }
        )
        assert HIGH_SKIP_RATE in flags

    def test_high_skip_rate_uses_n_trials(self):
        """Uses n_trials field if available instead of computing."""
        flags = detect_risk_flags(
            {
                "n_skipped_trials": 4,
                "n_trials": 10,  # 40% skip rate
            }
        )
        assert HIGH_SKIP_RATE in flags

    def test_high_skip_rate_boundary(self):
        """Exactly 30% skip rate should NOT flag."""
        flags = detect_risk_flags(
            {
                "n_valid_trials": 70,
                "n_skipped_trials": 30,
            }
        )
        assert HIGH_SKIP_RATE not in flags

    def test_poor_calibration_scalar(self):
        """Triggers when scalar calibration error > 0.15."""
        flags = detect_risk_flags({"calibration": 0.20})
        assert POOR_CALIBRATION in flags

    def test_poor_calibration_dict(self):
        """Triggers when mean of calibration dict values > 0.15."""
        flags = detect_risk_flags(
            {
                "calibration": {"p10": 0.20, "p50": 0.25, "p90": 0.10},
            }
        )
        # Mean = (0.20 + 0.25 + 0.10) / 3 = 0.183 > 0.15
        assert POOR_CALIBRATION in flags

    def test_good_calibration_dict(self):
        """Does not trigger when mean calibration is within threshold."""
        flags = detect_risk_flags(
            {
                "calibration": {"p10": 0.05, "p50": 0.02, "p90": 0.08},
            }
        )
        assert POOR_CALIBRATION not in flags

    def test_low_hit_rate(self):
        """Triggers when hit_rate < 0.5."""
        flags = detect_risk_flags({"hit_rate": 0.45})
        assert LOW_HIT_RATE in flags

    def test_low_hit_rate_boundary(self):
        """Exactly 0.5 should NOT flag."""
        flags = detect_risk_flags({"hit_rate": 0.5})
        assert LOW_HIT_RATE not in flags

    def test_high_drawdown(self):
        """Triggers when max_drawdown > 0.3."""
        flags = detect_risk_flags({"max_drawdown": 0.35})
        assert HIGH_DRAWDOWN in flags

    def test_high_drawdown_boundary(self):
        """Exactly 0.3 should NOT flag."""
        flags = detect_risk_flags({"max_drawdown": 0.3})
        assert HIGH_DRAWDOWN not in flags

    def test_low_coverage(self):
        """Triggers when coverage < 0.7."""
        flags = detect_risk_flags({"coverage": 0.60})
        assert LOW_COVERAGE in flags

    def test_low_coverage_boundary(self):
        """Exactly 0.7 should NOT flag."""
        flags = detect_risk_flags({"coverage": 0.7})
        assert LOW_COVERAGE not in flags

    def test_high_crps(self):
        """Triggers when crps > 0.5."""
        flags = detect_risk_flags({"crps": 0.55})
        assert HIGH_CRPS in flags

    def test_high_crps_boundary(self):
        """Exactly 0.5 should NOT flag."""
        flags = detect_risk_flags({"crps": 0.5})
        assert HIGH_CRPS not in flags

    def test_multiple_flags_combined(self):
        """Multiple flags fire simultaneously."""
        summary = {
            "n_valid_trials": 5,
            "n_skipped_trials": 8,
            "hit_rate": 0.3,
            "max_drawdown": 0.5,
            "coverage": 0.4,
            "crps": 0.8,
            "calibration": 0.25,
        }
        flags = detect_risk_flags(summary)
        assert LOW_TRIAL_COUNT in flags
        assert HIGH_SKIP_RATE in flags
        assert POOR_CALIBRATION in flags
        assert LOW_HIT_RATE in flags
        assert HIGH_DRAWDOWN in flags
        assert LOW_COVERAGE in flags
        assert HIGH_CRPS in flags
        assert len(flags) == 7

    def test_flag_order_is_deterministic(self):
        """Flags appear in declaration order regardless of input order."""
        summary = {
            "crps": 0.8,
            "hit_rate": 0.3,
            "n_valid_trials": 5,
        }
        flags = detect_risk_flags(summary)
        # Declaration order: LOW_TRIAL_COUNT, then LOW_HIT_RATE, then HIGH_CRPS
        assert flags.index(LOW_TRIAL_COUNT) < flags.index(LOW_HIT_RATE)
        assert flags.index(LOW_HIT_RATE) < flags.index(HIGH_CRPS)


# =========================================================================
# Signal summary generation
# =========================================================================


class TestSignalSummary:
    """Tests for generate_signal_summary."""

    def test_full_summary(self):
        """All fields present produces the expected template."""
        summary = generate_signal_summary(
            {"symbol": "SPY", "window_size": 60},
            {"n_valid_trials": 8, "hit_rate": 0.72, "calibration": 0.08, "crps": 0.31},
        )
        assert "SPY" in summary
        assert "60-bar" in summary
        assert "8 analogues" in summary
        assert "72%" in summary
        assert "good" in summary
        assert "0.31" in summary

    def test_missing_symbol(self):
        """Missing symbol renders as N/A."""
        summary = generate_signal_summary(
            {"window_size": 60},
            {"n_valid_trials": 8, "hit_rate": 0.72, "calibration": 0.08, "crps": 0.31},
        )
        assert "N/A" in summary
        assert "60-bar" in summary

    def test_missing_window_size(self):
        """Missing window_size renders as N/A."""
        summary = generate_signal_summary(
            {"symbol": "SPY"},
            {"n_valid_trials": 8},
        )
        assert "SPY" in summary
        assert "N/A" in summary

    def test_missing_all_metrics(self):
        """Missing all metrics renders as N/A for each."""
        summary = generate_signal_summary({"symbol": "QQQ"}, {})
        assert "QQQ" in summary
        assert summary.count("N/A") >= 3  # trials, hit_rate, crps at minimum

    def test_empty_config_and_metrics(self):
        """Completely empty inputs still produce a readable string."""
        summary = generate_signal_summary({}, {})
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_calibration_grades(self):
        """Test each calibration grade threshold."""
        # Excellent: < 0.05
        s = generate_signal_summary({}, {"calibration": 0.03})
        assert "excellent" in s

        # Good: < 0.10
        s = generate_signal_summary({}, {"calibration": 0.07})
        assert "good" in s

        # Fair: < 0.15
        s = generate_signal_summary({}, {"calibration": 0.12})
        assert "fair" in s

        # Poor: >= 0.15
        s = generate_signal_summary({}, {"calibration": 0.20})
        assert "poor" in s

    def test_calibration_dict_grade(self):
        """Calibration as dict computes mean for grading."""
        s = generate_signal_summary(
            {}, {"calibration": {"p10": 0.02, "p50": 0.01, "p90": 0.03}}
        )
        # Mean = 0.02 -> excellent
        assert "excellent" in s

    def test_hit_rate_formatting(self):
        """Hit rate formats as percentage without decimal."""
        s = generate_signal_summary({}, {"hit_rate": 0.6543})
        assert "65%" in s


# =========================================================================
# API endpoint tests (via TestClient)
# =========================================================================


class TestFinanceReviewAPI:
    """Test the finance review API endpoints via FastAPI TestClient.

    These tests use the TestClient to exercise the full request/response
    cycle including Pydantic validation, SQLite companion table creation,
    and JSON serialization. The registry DB is overridden to use a
    temporary file.
    """

    @pytest.fixture
    def client(self, tmp_path):
        """Create a TestClient with a temporary registry DB."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI TestClient not available")

        from the_similarity.platform.registry import RunRegistry
        from the_similarity.platform.artifacts import RunKind, iso_now, new_run_id

        db_path = tmp_path / "test_registry.db"
        registry = RunRegistry(db_path)

        # Register a test run so review endpoints have a parent run.
        from the_similarity.platform.contracts import RunRecord, RunStatus

        self._test_run_id = new_run_id()
        record = RunRecord(
            run_id=self._test_run_id,
            kind=RunKind.FINANCE,
            config={"symbol": "SPY", "window_size": 60},
            seed=42,
            status=RunStatus.SUCCEEDED,
            summary={"hit_rate": 0.72},
            created_at=iso_now(),
            pillar="finance",
        )
        registry.register_run(record)
        registry.close()

        # Import the app and override the registry dependency.
        from app.main import app
        from app.platform_routes import get_registry

        def _override_registry():
            r = RunRegistry(db_path)
            try:
                yield r
            finally:
                r.close()

        app.dependency_overrides[get_registry] = _override_registry
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    def test_create_review(self, client):
        """POST /platform/runs/{run_id}/review creates a review."""
        resp = client.post(
            f"/platform/runs/{self._test_run_id}/review",
            json={
                "reviewer": "test-agent",
                "status": "pending",
                "signal_summary": "Test signal",
                "trust_decision": "REVIEW",
                "risk_flags": ["low_trial_count"],
                "notes": "Test notes",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["run_id"] == self._test_run_id
        assert data["reviewer"] == "test-agent"
        assert data["status"] == "pending"
        assert data["risk_flags"] == ["low_trial_count"]
        assert len(data["review_id"]) == 32

    def test_create_review_duplicate_409(self, client):
        """Creating a second review for the same run returns 409."""
        body = {
            "reviewer": "agent",
            "status": "pending",
            "signal_summary": "s",
            "trust_decision": "REVIEW",
        }
        resp1 = client.post(f"/platform/runs/{self._test_run_id}/review", json=body)
        assert resp1.status_code == 201

        resp2 = client.post(f"/platform/runs/{self._test_run_id}/review", json=body)
        assert resp2.status_code == 409

    def test_create_review_missing_run_404(self, client):
        """Creating a review for a nonexistent run returns 404."""
        resp = client.post(
            "/platform/runs/nonexistent_run_id/review",
            json={
                "reviewer": "agent",
                "signal_summary": "s",
                "trust_decision": "REVIEW",
            },
        )
        assert resp.status_code == 404

    def test_get_review(self, client):
        """GET /platform/runs/{run_id}/review returns the review."""
        # Create first.
        client.post(
            f"/platform/runs/{self._test_run_id}/review",
            json={
                "reviewer": "agent",
                "signal_summary": "Test",
                "trust_decision": "TRUSTED",
                "status": "approved",
            },
        )
        # Get.
        resp = client.get(f"/platform/runs/{self._test_run_id}/review")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["trust_decision"] == "TRUSTED"

    def test_get_review_missing_404(self, client):
        """GET review for a run with no review returns 404."""
        resp = client.get(f"/platform/runs/{self._test_run_id}/review")
        assert resp.status_code == 404

    def test_update_review(self, client):
        """PUT /platform/runs/{run_id}/review updates fields."""
        # Create.
        client.post(
            f"/platform/runs/{self._test_run_id}/review",
            json={
                "reviewer": "agent",
                "signal_summary": "Initial",
                "trust_decision": "REVIEW",
                "status": "pending",
            },
        )
        # Update.
        resp = client.put(
            f"/platform/runs/{self._test_run_id}/review",
            json={
                "status": "approved",
                "trust_decision": "TRUSTED",
                "notes": "Looks good after manual review",
                "realized_outcome": {"actual_return": 0.03, "hit": True},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["trust_decision"] == "TRUSTED"
        assert data["notes"] == "Looks good after manual review"
        assert data["realized_outcome"]["actual_return"] == 0.03
        assert data["updated_at"] is not None

    def test_update_review_missing_404(self, client):
        """PUT review for a run with no review returns 404."""
        resp = client.put(
            f"/platform/runs/{self._test_run_id}/review",
            json={"status": "approved"},
        )
        assert resp.status_code == 404

    def test_list_reviews(self, client):
        """GET /platform/reviews returns all reviews."""
        # Create a review.
        client.post(
            f"/platform/runs/{self._test_run_id}/review",
            json={
                "reviewer": "agent",
                "signal_summary": "s",
                "trust_decision": "REVIEW",
                "status": "pending",
            },
        )
        resp = client.get("/platform/reviews")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["run_id"] == self._test_run_id

    def test_list_reviews_filter_by_status(self, client):
        """GET /platform/reviews?status=pending filters correctly."""
        client.post(
            f"/platform/runs/{self._test_run_id}/review",
            json={
                "reviewer": "agent",
                "signal_summary": "s",
                "trust_decision": "REVIEW",
                "status": "pending",
            },
        )
        # Filter for approved — should be empty since we created pending.
        resp = client.get("/platform/reviews?status=approved")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

        # Filter for pending — should find our review.
        resp = client.get("/platform/reviews?status=pending")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
