"""Tests for the foundation-bench markdown report writer."""
from __future__ import annotations

from pathlib import Path

from research.autoresearch.foundation_bench.report import write_markdown_report
from research.autoresearch.foundation_bench.run_bench import CellResult, TrialRecord
from research.autoresearch.retrieval_bench.metrics import TrialOutcome


def _mk_cell(slice_id: str, model_id: str, *, fallback: bool, crps: float) -> CellResult:
    """Tiny helper that builds a CellResult with a single synthetic trial.

    The test does not care about the record contents — only that the
    report renderer reads the aggregated fields correctly.
    """
    rec = TrialRecord(
        outcome=TrialOutcome(
            match_forward_returns=[],
            quantile_forecast={10: -0.01, 50: 0.0, 90: 0.01},
            realised_forward_return=0.0,
            runtime_seconds=0.01,
        ),
        fallback_reason="synthetic" if fallback else None,
        adapter_metadata={},
    )
    return CellResult(
        slice_id=slice_id,
        model_id=model_id,
        n_trials=1,
        n_skipped_budget=0,
        any_fallback=fallback,
        fallback_ratio=1.0 if fallback else 0.0,
        crps=crps,
        calibration_error_p10_p90=0.05,
        hit_rate=0.5,
        runtime={"median": 0.01, "mean": 0.01, "p95": 0.01, "n": 1},
        records=[rec],
        status="partial_synthetic_fallback" if fallback else "ok",
    )


def test_report_writes_header_and_per_slice_table(tmp_path: Path):
    cells = [
        _mk_cell("spy-covid-2020", "wavelet_baseline", fallback=False, crps=0.025),
        _mk_cell("spy-covid-2020", "timesfm", fallback=True, crps=0.030),
        _mk_cell("spy-covid-2020", "chronos", fallback=True, crps=0.031),
    ]
    out = tmp_path / "report.md"
    path = write_markdown_report(
        cells, out, benchmark_id="foundation-bench-v1", n_trials=12, seeds=[42]
    )
    text = path.read_text()
    assert "# Foundation-bench v1 — scorecard" in text
    assert "spy-covid-2020" in text
    # Per-slice table columns
    assert "| model |" in text
    # Cross-slice aggregate
    assert "Cross-slice aggregate" in text
    # Fallback summary counts
    assert "Fully synthetic fallback cells" in text


def test_report_flags_all_synthetic_run(tmp_path: Path):
    # When 100% of cells are synthetic fallback, the report must include
    # the explicit fallback note for honest reporting.
    cells = [
        _mk_cell("spy-bull-2016-2019", "timesfm", fallback=True, crps=0.030),
        _mk_cell("spy-bull-2016-2019", "chronos", fallback=True, crps=0.031),
    ]
    out = tmp_path / "report.md"
    path = write_markdown_report(cells, out, benchmark_id="foundation-bench-v1")
    text = path.read_text()
    assert "synthetic fallback path" in text
