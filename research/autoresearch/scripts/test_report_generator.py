"""Tests for the autoresearch report generator.

Covers: generate_report, save_report, validate_report, compare_reports.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from report_generator import (
    compare_reports,
    generate_report,
    save_report,
    validate_report,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_BEFORE = {
    "spy-1d": {"crps": 0.30, "calibration_error": 0.10, "hit_rate": 0.50, "mean_error": 0.02, "runtime_seconds": 2.0},
    "btc-1d": {"crps": 0.35, "calibration_error": 0.12, "hit_rate": 0.45, "mean_error": 0.03, "runtime_seconds": 3.0},
}

SAMPLE_AFTER = {
    "spy-1d": {"crps": 0.25, "calibration_error": 0.08, "hit_rate": 0.55, "mean_error": 0.018, "runtime_seconds": 2.5},
    "btc-1d": {"crps": 0.30, "calibration_error": 0.10, "hit_rate": 0.50, "mean_error": 0.025, "runtime_seconds": 3.5},
}


def _make_report(**overrides) -> dict:
    """Helper to build a valid report with optional overrides."""
    kwargs = dict(
        run_id="test-run-001",
        benchmark_id="jepa-retrieval-core-v1",
        metrics_before=SAMPLE_BEFORE,
        metrics_after=SAMPLE_AFTER,
        lane_id="jepa-retrieval-lane-v1",
        branch="feat/test",
        commit="abc1234",
        artifacts=["progress/autoresearch/reports/test.json"],
    )
    kwargs.update(overrides)
    return generate_report(**kwargs)


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Tests for ``generate_report``."""

    def test_required_keys_present(self):
        report = _make_report()
        required = [
            "report_id", "run_id", "benchmark_id", "lane_id",
            "timestamp", "datasets_used", "backtest_metrics",
            "aggregate_metrics", "recommendation", "rationale",
        ]
        for key in required:
            assert key in report, f"Missing key: {key}"

    def test_datasets_used_sorted(self):
        report = _make_report()
        assert report["datasets_used"] == ["btc-1d", "spy-1d"]

    def test_backtest_metrics_structure(self):
        report = _make_report()
        bm = report["backtest_metrics"]
        assert "before" in bm and "after" in bm
        assert len(bm["before"]) == 2
        assert len(bm["after"]) == 2
        # Each entry has the required metric keys.
        for entry in bm["before"] + bm["after"]:
            assert "dataset" in entry
            assert "crps" in entry
            assert "hit_rate" in entry

    def test_aggregate_deltas_computed(self):
        report = _make_report()
        deltas = report["aggregate_metrics"]["deltas"]
        # CRPS should decrease (negative delta = improvement).
        assert deltas["crps"] < 0
        # Hit rate should increase.
        assert deltas["hit_rate"] > 0

    def test_recommendation_keep_on_improvement(self):
        """Large CRPS improvement triggers 'keep'."""
        report = _make_report()
        # The sample data has a clear improvement.
        assert report["recommendation"] == "keep"

    def test_recommendation_discard_on_regression(self):
        """Large CRPS regression triggers 'discard'."""
        # Swap before/after so experiment is worse.
        report = _make_report(metrics_before=SAMPLE_AFTER, metrics_after=SAMPLE_BEFORE)
        assert report["recommendation"] == "discard"

    def test_recommendation_needs_review_on_marginal(self):
        """Tiny difference triggers 'needs_review'."""
        marginal = {
            "spy-1d": {"crps": 0.300, "calibration_error": 0.10, "hit_rate": 0.50, "mean_error": 0.02, "runtime_seconds": 2.0},
        }
        slightly_better = {
            "spy-1d": {"crps": 0.299, "calibration_error": 0.10, "hit_rate": 0.50, "mean_error": 0.02, "runtime_seconds": 2.0},
        }
        report = _make_report(metrics_before=marginal, metrics_after=slightly_better)
        assert report["recommendation"] == "needs_review"

    def test_retrieval_metrics_included(self):
        report = _make_report(
            retrieval_metrics={
                "top_k_overlap": 0.8,
                "rank_correlation": 0.9,
                "rank_lift_summary": "Top-1 unchanged.",
            }
        )
        rc = report["retrieval_comparison"]
        assert rc is not None
        assert rc["top_k_overlap"] == 0.8
        assert rc["rank_correlation"] == 0.9

    def test_retrieval_metrics_none_by_default(self):
        report = _make_report()
        assert report["retrieval_comparison"] is None

    def test_branch_and_commit(self):
        report = _make_report(branch="feat/x", commit="deadbeef")
        assert report["branch"] == "feat/x"
        assert report["commit"] == "deadbeef"

    def test_artifacts_list(self):
        report = _make_report(artifacts=["a.json", "b.png"])
        assert report["artifacts"] == ["a.json", "b.png"]


# ---------------------------------------------------------------------------
# validate_report
# ---------------------------------------------------------------------------


class TestValidateReport:
    """Tests for ``validate_report``."""

    def test_valid_report_no_errors(self):
        report = _make_report()
        errors = validate_report(report)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_required_key(self):
        report = _make_report()
        del report["run_id"]
        errors = validate_report(report)
        assert any("run_id" in e for e in errors)

    def test_invalid_recommendation(self):
        report = _make_report()
        report["recommendation"] = "maybe"
        errors = validate_report(report)
        assert any("recommendation" in e.lower() or "maybe" in e for e in errors)

    def test_empty_datasets_used(self):
        report = _make_report()
        report["datasets_used"] = []
        errors = validate_report(report)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# save_report
# ---------------------------------------------------------------------------


class TestSaveReport:
    """Tests for ``save_report``."""

    def test_creates_file(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_report(report, output_dir=tmpdir)
            assert path.exists()
            assert path.suffix == ".json"
            loaded = json.loads(path.read_text(encoding="utf-8"))
            assert loaded["run_id"] == "test-run-001"

    def test_filename_from_run_id(self):
        report = _make_report(run_id="exp-jepa-2026-04-12")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_report(report, output_dir=tmpdir)
            assert "exp-jepa-2026-04-12" in path.name

    def test_idempotent_overwrite(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = save_report(report, output_dir=tmpdir)
            p2 = save_report(report, output_dir=tmpdir)
            assert p1 == p2
            assert p1.exists()


# ---------------------------------------------------------------------------
# compare_reports
# ---------------------------------------------------------------------------


class TestCompareReports:
    """Tests for ``compare_reports``."""

    def test_comparison_structure(self):
        a = _make_report(run_id="run-a")
        b = _make_report(run_id="run-b", metrics_before=SAMPLE_AFTER, metrics_after=SAMPLE_BEFORE)
        comparison = compare_reports(a, b)
        assert comparison["report_a_run_id"] == "run-a"
        assert comparison["report_b_run_id"] == "run-b"
        assert "aggregate_after_comparison" in comparison

    def test_metric_deltas_computed(self):
        a = _make_report(run_id="run-a")
        b = _make_report(run_id="run-b")
        comparison = compare_reports(a, b)
        # Same metrics → deltas should be zero.
        for key in ("crps", "hit_rate", "mean_error"):
            assert comparison["aggregate_after_comparison"][key]["delta"] == pytest.approx(0.0)

    def test_dataset_overlap(self):
        a = _make_report(run_id="run-a")
        extra_after = dict(SAMPLE_AFTER)
        extra_after["eth-1d"] = {"crps": 0.4, "calibration_error": 0.15, "hit_rate": 0.40, "mean_error": 0.04, "runtime_seconds": 1.0}
        b = _make_report(run_id="run-b", metrics_after=extra_after)
        comparison = compare_reports(a, b)
        assert "btc-1d" in comparison["datasets_shared"]
        assert "spy-1d" in comparison["datasets_shared"]
        assert "eth-1d" in comparison["datasets_only_b"]

    def test_recommendations_included(self):
        a = _make_report(run_id="run-a")
        b = _make_report(run_id="run-b")
        comparison = compare_reports(a, b)
        assert "recommendation_a" in comparison
        assert "recommendation_b" in comparison
