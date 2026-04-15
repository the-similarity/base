"""Unit tests for ``research.autoresearch.core``.

Covers the five public modules — ledger, metrics_delta, gates, report,
rejection_log — one test class per module. These tests are deliberately
fast (no real data, no disk IO outside ``tmp_path``) so they stay in
the default ``pytest`` run with the rest of the engine tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


class TestLedger:
    def test_entry_round_trip(self, tmp_path: Path) -> None:
        from research.autoresearch.core.ledger import (
            LedgerEntry,
            append_entry,
            iter_entries,
            utc_timestamp,
        )

        ledger = tmp_path / "experiments.jsonl"
        entry = LedgerEntry(
            run_id="test-run-1",
            timestamp=utc_timestamp(),
            benchmark_id="unit-test-bench",
            lane_id="unit-test-lane",
            status="ok",
            decision="keep",
            summary="smoke",
            metrics_before={"crps": 0.1},
            metrics_after={"crps": 0.09},
            slices=["slice-a"],
            artifacts=["report.md"],
        )
        append_entry(entry, ledger)
        rows = list(iter_entries(ledger))
        assert len(rows) == 1
        assert rows[0]["run_id"] == "test-run-1"
        assert rows[0]["decision"] == "keep"

    def test_validate_rejects_bad_status(self) -> None:
        from research.autoresearch.core.ledger import LedgerEntry

        entry = LedgerEntry(
            run_id="x",
            timestamp="2026-04-14T00:00:00Z",
            benchmark_id="b",
            lane_id="l",
            status="BOGUS",
            decision="keep",
            summary="",
            metrics_before={},
            metrics_after={},
        )
        with pytest.raises(ValueError):
            entry.validate()

    def test_entries_for_lane_filters(self, tmp_path: Path) -> None:
        from research.autoresearch.core.ledger import (
            LedgerEntry,
            append_entry,
            entries_for_lane,
        )

        ledger = tmp_path / "experiments.jsonl"
        for i, lane in enumerate(["lane-a", "lane-b", "lane-a"]):
            append_entry(
                LedgerEntry(
                    run_id=f"r{i}",
                    timestamp=f"2026-04-14T00:00:0{i}Z",
                    benchmark_id="b",
                    lane_id=lane,
                    status="ok",
                    decision="keep",
                    summary="",
                    metrics_before={},
                    metrics_after={},
                ),
                ledger,
            )
        lane_a = entries_for_lane("lane-a", ledger)
        assert len(lane_a) == 2
        assert {r["run_id"] for r in lane_a} == {"r0", "r2"}

    def test_latest_run_picks_max_timestamp(self, tmp_path: Path) -> None:
        from research.autoresearch.core.ledger import (
            LedgerEntry,
            append_entry,
            latest_run,
        )

        ledger = tmp_path / "experiments.jsonl"
        for ts, rid in [
            ("2026-04-14T00:00:00Z", "old"),
            ("2026-04-14T12:00:00Z", "new"),
            ("2026-04-14T06:00:00Z", "mid"),
        ]:
            append_entry(
                LedgerEntry(
                    run_id=rid,
                    timestamp=ts,
                    benchmark_id="b",
                    lane_id="L",
                    status="ok",
                    decision="keep",
                    summary="",
                    metrics_before={},
                    metrics_after={},
                ),
                ledger,
            )
        latest = latest_run("L", ledger)
        assert latest is not None
        assert latest["run_id"] == "new"

    def test_compare_runs_emits_metric_deltas(self, tmp_path: Path) -> None:
        from research.autoresearch.core.ledger import (
            LedgerEntry,
            append_entry,
            compare_runs,
        )

        ledger = tmp_path / "experiments.jsonl"
        append_entry(
            LedgerEntry(
                run_id="a",
                timestamp="2026-04-14T00:00:00Z",
                benchmark_id="b",
                lane_id="L",
                status="ok",
                decision="baseline",
                summary="",
                metrics_before={"crps": 0.20},
                metrics_after={"crps": 0.20, "hit_rate": 0.50},
            ),
            ledger,
        )
        append_entry(
            LedgerEntry(
                run_id="b",
                timestamp="2026-04-14T01:00:00Z",
                benchmark_id="b",
                lane_id="L",
                status="ok",
                decision="keep",
                summary="",
                metrics_before={"crps": 0.20},
                metrics_after={"crps": 0.16, "hit_rate": 0.55},
            ),
            ledger,
        )
        result = compare_runs("a", "b", ledger)
        assert result["run_a"]["run_id"] == "a"
        assert result["run_b"]["run_id"] == "b"
        crps_delta = result["metric_deltas"]["crps"][2]
        assert crps_delta is not None
        assert crps_delta == pytest.approx(-0.04, abs=1e-6)

    def test_append_accepts_raw_dict_for_backcompat(self, tmp_path: Path) -> None:
        from research.autoresearch.core.ledger import append_entry, iter_entries

        ledger = tmp_path / "experiments.jsonl"
        append_entry({"run_id": "legacy", "lane_id": "L"}, ledger)
        rows = list(iter_entries(ledger))
        assert rows[0]["run_id"] == "legacy"


# ---------------------------------------------------------------------------
# Metrics delta
# ---------------------------------------------------------------------------


class TestMetricsDelta:
    def test_delta_sign_respects_direction(self) -> None:
        from research.autoresearch.core.metrics_delta import compute_delta

        # CRPS lower is better -> an improvement is a negative raw delta
        # but a positive "win score".
        d = compute_delta(0.20, 0.15, direction="lower_is_better")
        assert d.raw_delta == pytest.approx(-0.05, abs=1e-6)
        assert d.is_improvement is True

    def test_delta_for_higher_is_better(self) -> None:
        from research.autoresearch.core.metrics_delta import compute_delta

        d = compute_delta(0.50, 0.55, direction="higher_is_better")
        assert d.raw_delta == pytest.approx(0.05, abs=1e-6)
        assert d.is_improvement is True

    def test_paired_bootstrap_significance_detects_shift(self) -> None:
        from research.autoresearch.core.metrics_delta import paired_bootstrap

        baseline = [0.20, 0.19, 0.21, 0.20, 0.19, 0.22, 0.18, 0.21]
        candidate = [0.15, 0.14, 0.16, 0.15, 0.14, 0.17, 0.13, 0.16]
        result = paired_bootstrap(
            baseline, candidate, direction="lower_is_better", n_resamples=500, seed=42
        )
        assert result.mean_delta < 0
        assert result.p_value < 0.05
        assert result.significant is True

    def test_paired_bootstrap_flat_is_insignificant(self) -> None:
        from research.autoresearch.core.metrics_delta import paired_bootstrap

        baseline = [0.20, 0.19, 0.21, 0.20]
        candidate = [0.20, 0.19, 0.21, 0.20]
        result = paired_bootstrap(
            baseline, candidate, direction="lower_is_better", n_resamples=200, seed=42
        )
        assert result.mean_delta == pytest.approx(0.0, abs=1e-9)
        assert result.significant is False

    def test_compute_delta_requires_valid_direction(self) -> None:
        from research.autoresearch.core.metrics_delta import compute_delta

        with pytest.raises(ValueError):
            compute_delta(0.0, 0.0, direction="sideways")


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


class TestGates:
    def test_required_gate_failing_blocks_keep(self) -> None:
        from research.autoresearch.core.gates import Gate, evaluate_gates

        gates = [
            Gate(
                name="crps_improvement",
                metric="crps",
                threshold=-0.01,
                direction="lower_is_better",
                required=True,
            )
        ]
        # candidate CRPS barely worse -> required gate fails -> discard.
        decision = evaluate_gates(
            deltas={"crps": 0.005}, gates=gates
        )
        assert decision.keep is False
        assert any("crps" in r for r in decision.reasons)

    def test_optional_gate_contributes_when_required_passes(self) -> None:
        from research.autoresearch.core.gates import Gate, evaluate_gates

        gates = [
            Gate(
                name="crps_improvement",
                metric="crps",
                threshold=-0.01,
                direction="lower_is_better",
                required=True,
            ),
            Gate(
                name="hit_rate_lift",
                metric="hit_rate",
                threshold=0.02,
                direction="higher_is_better",
                required=False,
            ),
        ]
        decision = evaluate_gates(
            deltas={"crps": -0.05, "hit_rate": 0.01}, gates=gates
        )
        # required gate passes -> keep=True even though optional failed.
        assert decision.keep is True
        assert decision.gate_results["crps_improvement"].passed is True
        assert decision.gate_results["hit_rate_lift"].passed is False

    def test_missing_metric_fails_required_gate(self) -> None:
        from research.autoresearch.core.gates import Gate, evaluate_gates

        gates = [
            Gate(
                name="crps_improvement",
                metric="crps",
                threshold=-0.01,
                direction="lower_is_better",
                required=True,
            )
        ]
        decision = evaluate_gates(deltas={}, gates=gates)
        assert decision.keep is False

    def test_empty_gates_defaults_to_keep(self) -> None:
        from research.autoresearch.core.gates import evaluate_gates

        decision = evaluate_gates(deltas={"crps": 0.0}, gates=[])
        assert decision.keep is True
        assert decision.gate_results == {}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class TestReport:
    def test_render_minimal_report_has_required_sections(self) -> None:
        from research.autoresearch.core.gates import Gate, evaluate_gates
        from research.autoresearch.core.report import LaneReport

        gates = [
            Gate(
                name="crps_improvement",
                metric="crps",
                threshold=-0.01,
                direction="lower_is_better",
                required=True,
            )
        ]
        decision = evaluate_gates(deltas={"crps": -0.02}, gates=gates)
        report = LaneReport(
            lane_id="unit-test-lane",
            benchmark_id="unit-test-bench",
            commit="abc123",
            timestamp="2026-04-14T00:00:00Z",
            arms=[
                {"arm_id": "baseline", "metrics": {"crps": 0.20}},
                {"arm_id": "candidate", "metrics": {"crps": 0.18}},
            ],
            slices=[
                {
                    "slice_id": "slice-a",
                    "arm_metrics": {
                        "baseline": {"crps": 0.20},
                        "candidate": {"crps": 0.18},
                    },
                }
            ],
            deltas={"crps": -0.02},
            gate_decision=decision,
            verdict="keep",
            rationale="CRPS improved.",
            artifacts=["report.md"],
            open_questions=["Does it hold on BTC?"],
        )
        md = report.render()
        for section in (
            "# Lane report",
            "## Metadata",
            "## Slice × arm scorecard",
            "## Deltas",
            "## Gates",
            "## Verdict",
            "## Open questions",
            "## Artifacts",
        ):
            assert section in md, f"Missing section: {section}"
        # Gate decision rendered
        assert "crps_improvement" in md
        # Verdict rendered
        assert "KEEP" in md

    def test_write_report_creates_file(self, tmp_path: Path) -> None:
        from research.autoresearch.core.gates import evaluate_gates
        from research.autoresearch.core.report import LaneReport

        decision = evaluate_gates(deltas={}, gates=[])
        report = LaneReport(
            lane_id="L",
            benchmark_id="B",
            commit="c",
            timestamp="2026-04-14T00:00:00Z",
            arms=[{"arm_id": "a", "metrics": {}}],
            slices=[],
            deltas={},
            gate_decision=decision,
            verdict="keep",
            rationale="r",
        )
        out = tmp_path / "out.md"
        path = report.write(out)
        assert path.exists()
        assert path.read_text(encoding="utf-8").startswith("# Lane report")


# ---------------------------------------------------------------------------
# Rejection log
# ---------------------------------------------------------------------------


class TestRejectionLog:
    def test_append_and_read_round_trip(self, tmp_path: Path) -> None:
        from research.autoresearch.core.rejection_log import (
            RejectionEntry,
            append_rejection,
            iter_rejections,
        )

        path = tmp_path / "rejections.jsonl"
        entry = RejectionEntry(
            direction_id="test_direction",
            lane_id="unit-test-lane",
            summary="Does not improve CRPS.",
            killed_at="2026-04-14T00:00:00Z",
            evidence_refs=["run-1"],
            revisit_conditions=["On a shift-rich slice"],
        )
        append_rejection(entry, path)
        rows = list(iter_rejections(path))
        assert len(rows) == 1
        assert rows[0]["direction_id"] == "test_direction"
        assert rows[0]["revisit_conditions"] == ["On a shift-rich slice"]

    def test_is_rejected_matches_on_direction_id(self, tmp_path: Path) -> None:
        from research.autoresearch.core.rejection_log import (
            RejectionEntry,
            append_rejection,
            is_rejected,
        )

        path = tmp_path / "rejections.jsonl"
        append_rejection(
            RejectionEntry(
                direction_id="tier2_as_default",
                lane_id="retrieval-bench",
                summary="x",
                killed_at="2026-04-14T00:00:00Z",
                evidence_refs=[],
                revisit_conditions=[],
            ),
            path,
        )
        assert is_rejected("tier2_as_default", path) is True
        assert is_rejected("nonexistent_direction", path) is False

    def test_validation_requires_revisit_conditions_list(self) -> None:
        from research.autoresearch.core.rejection_log import RejectionEntry

        with pytest.raises(ValueError):
            RejectionEntry(
                direction_id="d",
                lane_id="l",
                summary="s",
                killed_at="2026-04-14T00:00:00Z",
                evidence_refs=[],
                revisit_conditions="not a list",  # type: ignore[arg-type]
            ).validate()

    def test_rejection_preserves_order(self, tmp_path: Path) -> None:
        from research.autoresearch.core.rejection_log import (
            RejectionEntry,
            append_rejection,
            iter_rejections,
        )

        path = tmp_path / "rejections.jsonl"
        for i in range(3):
            append_rejection(
                RejectionEntry(
                    direction_id=f"d{i}",
                    lane_id="L",
                    summary="",
                    killed_at=f"2026-04-14T00:00:0{i}Z",
                    evidence_refs=[],
                    revisit_conditions=[],
                ),
                path,
            )
        ids = [r["direction_id"] for r in iter_rejections(path)]
        assert ids == ["d0", "d1", "d2"]
