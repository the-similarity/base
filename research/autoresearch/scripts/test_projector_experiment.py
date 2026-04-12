"""Tests for the projector-calibration experiment runner.

These tests verify the helper functions in run_projector_experiment.py
without running actual backtests (which are expensive). The backtest
API itself is tested in the_similarity/tests/.

Test strategy:
- Unit-test pure functions (calibration_error, build_config, aggregate,
  compare_to_baseline, write_report, append_ledger).
- Mock the backtest API for the end-to-end run path.
- Verify report/ledger file formats match the expected schema.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
from research.autoresearch.scripts.run_projector_experiment import (
    AggregateReport,
    DatasetReport,
    aggregate,
    append_ledger_entry,
    build_config,
    calibration_error_p10_p90,
    compare_to_baseline,
    write_report,
)
from the_similarity.config import Config


# ---------------------------------------------------------------------------
# calibration_error_p10_p90
# ---------------------------------------------------------------------------


class TestCalibrationErrorP10P90:
    """Tests for the calibration error metric computation."""

    def test_perfect_calibration(self) -> None:
        """When P10 containment = 0.10 and P90 = 0.90, error should be 0."""
        cal = {10: 0.10, 25: 0.25, 50: 0.50, 75: 0.75, 90: 0.90}
        assert calibration_error_p10_p90(cal) == 0.0

    def test_imperfect_calibration(self) -> None:
        """Verify correct computation for non-ideal calibration."""
        # P10 containment is 0.15 (delta = 0.05), P90 is 0.85 (delta = 0.05)
        cal = {10: 0.15, 90: 0.85}
        result = calibration_error_p10_p90(cal)
        assert abs(result - 0.05) < 1e-10

    def test_asymmetric_calibration(self) -> None:
        """P10 off by 0.10, P90 off by 0.02 -> mean = 0.06."""
        cal = {10: 0.20, 90: 0.88}
        result = calibration_error_p10_p90(cal)
        expected = (0.10 + 0.02) / 2  # = 0.06
        assert abs(result - expected) < 1e-10

    def test_missing_percentiles(self) -> None:
        """When neither P10 nor P90 is present, return 0.0."""
        cal = {25: 0.25, 50: 0.50, 75: 0.75}
        assert calibration_error_p10_p90(cal) == 0.0

    def test_partial_percentiles(self) -> None:
        """When only P10 is present, compute error from P10 alone."""
        cal = {10: 0.20}
        result = calibration_error_p10_p90(cal)
        assert abs(result - 0.10) < 1e-10


# ---------------------------------------------------------------------------
# build_config
# ---------------------------------------------------------------------------


class TestBuildConfig:
    """Tests for Config construction from CLI arguments."""

    def test_default_config(self) -> None:
        """When no overrides are given, Config should use defaults."""
        args = argparse.Namespace(
            confidence_decay_rate=None,
            koopman_blend_weight=None,
        )
        config = build_config(args)
        assert config.confidence_decay_rate == 0.0
        assert config.koopman_blend_weight == 0.0

    def test_override_decay_rate(self) -> None:
        """CLI override should set the decay rate."""
        args = argparse.Namespace(
            confidence_decay_rate=0.05,
            koopman_blend_weight=None,
        )
        config = build_config(args)
        assert config.confidence_decay_rate == 0.05
        assert config.koopman_blend_weight == 0.0

    def test_override_koopman(self) -> None:
        """CLI override should set the Koopman blend weight."""
        args = argparse.Namespace(
            confidence_decay_rate=None,
            koopman_blend_weight=0.15,
        )
        config = build_config(args)
        assert config.confidence_decay_rate == 0.0
        assert config.koopman_blend_weight == 0.15

    def test_override_both(self) -> None:
        """Both overrides should be applied simultaneously."""
        args = argparse.Namespace(
            confidence_decay_rate=0.03,
            koopman_blend_weight=0.20,
        )
        config = build_config(args)
        assert config.confidence_decay_rate == 0.03
        assert config.koopman_blend_weight == 0.20


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


class TestAggregate:
    """Tests for multi-dataset aggregation."""

    def _make_report(
        self,
        hit_rate: float = 0.60,
        crps: float = 0.05,
        cal_err: float = 0.03,
        mean_error: float = 0.02,
        runtime: float = 10.0,
    ) -> DatasetReport:
        return DatasetReport(
            dataset_path="test/data.parquet",
            series_name="test",
            n_valid_trials=100,
            n_skipped_trials=0,
            hit_rate=hit_rate,
            mean_error=mean_error,
            crps=crps,
            calibration={10: 0.10, 90: 0.90},
            calibration_error_p10_p90=cal_err,
            runtime_seconds=runtime,
        )

    def test_single_report(self) -> None:
        """Aggregate of one report should equal the report itself."""
        report = self._make_report(hit_rate=0.55, crps=0.04)
        agg = aggregate([report])
        assert agg.datasets_evaluated == 1
        assert agg.hit_rate == 0.55
        assert agg.crps == 0.04

    def test_two_reports_averaged(self) -> None:
        """Aggregate of two reports should average hit_rate and crps, sum runtime."""
        r1 = self._make_report(hit_rate=0.60, crps=0.04, runtime=10.0)
        r2 = self._make_report(hit_rate=0.50, crps=0.06, runtime=20.0)
        agg = aggregate([r1, r2])
        assert agg.datasets_evaluated == 2
        assert abs(agg.hit_rate - 0.55) < 1e-10
        assert abs(agg.crps - 0.05) < 1e-10
        assert abs(agg.runtime_seconds - 30.0) < 1e-10

    def test_empty_reports_raises(self) -> None:
        """Aggregating zero reports should raise ValueError."""
        with pytest.raises(ValueError, match="Cannot aggregate zero"):
            aggregate([])


# ---------------------------------------------------------------------------
# compare_to_baseline
# ---------------------------------------------------------------------------


class TestCompareToBaseline:
    """Tests for baseline comparison and decision logic."""

    def _make_aggregate(
        self,
        crps: float = 0.05,
        cal_err: float = 0.03,
        hit_rate: float = 0.55,
    ) -> AggregateReport:
        return AggregateReport(
            datasets_evaluated=1,
            hit_rate=hit_rate,
            mean_error=0.02,
            crps=crps,
            calibration_error_p10_p90=cal_err,
            runtime_seconds=10.0,
        )

    def _write_baseline(self, tmp_path: Path, crps: float, cal_err: float, hit_rate: float) -> str:
        """Write a minimal baseline report to a temp file."""
        baseline = {
            "aggregate": {
                "crps": crps,
                "calibration_error_p10_p90": cal_err,
                "hit_rate": hit_rate,
            }
        }
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps(baseline), encoding="utf-8")
        return str(path)

    def test_improvement_in_crps(self, tmp_path: Path) -> None:
        """Lower CRPS than baseline should yield 'keep'."""
        baseline_path = self._write_baseline(tmp_path, crps=0.06, cal_err=0.03, hit_rate=0.55)
        current = self._make_aggregate(crps=0.04, cal_err=0.03, hit_rate=0.55)
        result = compare_to_baseline(current, baseline_path)
        assert result["decision"] == "keep"
        assert result["crps_improved"] is True

    def test_improvement_in_calibration(self, tmp_path: Path) -> None:
        """Lower calibration error should yield 'keep'."""
        baseline_path = self._write_baseline(tmp_path, crps=0.05, cal_err=0.08, hit_rate=0.55)
        current = self._make_aggregate(crps=0.05, cal_err=0.04, hit_rate=0.55)
        result = compare_to_baseline(current, baseline_path)
        assert result["decision"] == "keep"
        assert result["calibration_improved"] is True

    def test_hard_regression_crps(self, tmp_path: Path) -> None:
        """CRPS worsening >10% should force discard."""
        baseline_path = self._write_baseline(tmp_path, crps=0.05, cal_err=0.03, hit_rate=0.55)
        # CRPS worsens from 0.05 to 0.06 = +20% relative
        current = self._make_aggregate(crps=0.06, cal_err=0.02, hit_rate=0.55)
        result = compare_to_baseline(current, baseline_path)
        assert result["decision"] == "discard"
        assert result["hard_regression"] is True

    def test_hard_regression_hit_rate(self, tmp_path: Path) -> None:
        """Hit rate below 45% should force discard regardless of other metrics."""
        baseline_path = self._write_baseline(tmp_path, crps=0.05, cal_err=0.03, hit_rate=0.55)
        current = self._make_aggregate(crps=0.03, cal_err=0.01, hit_rate=0.44)
        result = compare_to_baseline(current, baseline_path)
        assert result["decision"] == "discard"
        assert result["hard_regression"] is True

    def test_no_improvement(self, tmp_path: Path) -> None:
        """No improvement in either primary metric should yield discard."""
        baseline_path = self._write_baseline(tmp_path, crps=0.05, cal_err=0.03, hit_rate=0.55)
        current = self._make_aggregate(crps=0.05, cal_err=0.03, hit_rate=0.55)
        result = compare_to_baseline(current, baseline_path)
        assert result["decision"] == "discard"

    def test_missing_baseline_file(self) -> None:
        """Missing baseline file should return 'retry' decision."""
        current = self._make_aggregate()
        result = compare_to_baseline(current, "/nonexistent/baseline.json")
        assert result["decision"] == "retry"


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------


class TestWriteReport:
    """Tests for report file writing."""

    def test_creates_file(self, tmp_path: Path) -> None:
        """Report should be written as valid JSON."""
        path = tmp_path / "reports" / "test-report.json"
        payload = {"test": True, "value": 42}
        write_report(path, payload)

        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["test"] is True
        assert loaded["value"] == 42

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Parent directories should be created automatically."""
        path = tmp_path / "deep" / "nested" / "report.json"
        write_report(path, {"ok": True})
        assert path.exists()


# ---------------------------------------------------------------------------
# append_ledger_entry
# ---------------------------------------------------------------------------


class TestAppendLedgerEntry:
    """Tests for JSONL ledger appending."""

    def test_appends_valid_jsonl(self, tmp_path: Path) -> None:
        """Ledger entry should be valid JSONL conforming to the schema."""
        ledger_path = tmp_path / "experiments.jsonl"
        current = AggregateReport(
            datasets_evaluated=1,
            hit_rate=0.55,
            mean_error=0.02,
            crps=0.04,
            calibration_error_p10_p90=0.03,
            runtime_seconds=10.0,
        )

        append_ledger_entry(
            ledger_path=ledger_path,
            run_id="test-run-001",
            benchmark_id="projector-calibration-core-v1",
            lane_id="projector-calibration-lane-v1",
            branch="feat/test",
            report_name="test-report.json",
            current=current,
            baseline_metrics={"crps": 0.05},
            decision="keep",
            summary="Test experiment.",
            config_overrides={"confidence_decay_rate": 0.03},
        )

        assert ledger_path.exists()
        lines = ledger_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["run_id"] == "test-run-001"
        assert entry["benchmark_id"] == "projector-calibration-core-v1"
        assert entry["lane_id"] == "projector-calibration-lane-v1"
        assert entry["status"] == "ok"
        assert entry["decision"] == "keep"
        assert entry["metrics_after"]["crps"] == 0.04
        assert entry["metrics_before"]["crps"] == 0.05

    def test_appends_multiple_entries(self, tmp_path: Path) -> None:
        """Multiple calls should append separate lines."""
        ledger_path = tmp_path / "experiments.jsonl"
        current = AggregateReport(
            datasets_evaluated=1, hit_rate=0.55, mean_error=0.02,
            crps=0.04, calibration_error_p10_p90=0.03, runtime_seconds=10.0,
        )
        for i in range(3):
            append_ledger_entry(
                ledger_path=ledger_path,
                run_id=f"test-run-{i:03d}",
                benchmark_id="projector-calibration-core-v1",
                lane_id="projector-calibration-lane-v1",
                branch="feat/test",
                report_name=f"report-{i}.json",
                current=current,
                baseline_metrics={},
                decision="keep",
                summary=f"Run {i}",
                config_overrides={},
            )

        lines = ledger_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
