"""Smoke tests for the foundation-bench runner and its utilities.

The tests exercise the runner without touching real parquet data or
the engine — we stub ``load_slice_values`` with a synthetic price series
and point ``--data-root`` at a tmp path.  This keeps the unit-test suite
deterministic and fast (< 1s) while still covering:

* CLI arg parsing + filter resolution (--slice, --model, --smoke, --n-trials)
* ``construct_adapter`` dynamic import
* walk-forward trial loop ordering (paired-positions invariant)
* budget cap -> status = skipped_budget
* per-cell artefact serialization round-trip
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from research.autoresearch.foundation_bench import run_bench
from research.autoresearch.foundation_bench.adapters.base import (
    ForecastResult,
    ar1_cone,
)
from research.autoresearch.foundation_bench.run_bench import (
    BenchSpec,
    CellResult,
    ModelDef,
    SliceDef,
    build_parser,
    construct_adapter,
    evaluate_cell,
    load_spec,
    sample_trial_positions,
    write_cell_artefact,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fake_prices(n: int = 600, seed: int = 0) -> np.ndarray:
    """Deterministic price path used in place of parquet loads."""
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, size=n)))


def _mini_spec() -> BenchSpec:
    """Tiny spec: 1 slice, 2 models, 4 trials. Keeps tests under a second."""
    sd = SliceDef(
        id="tiny",
        symbol="tiny",
        path="does/not/exist.parquet",
        start_date="2020-01-01",
        end_date="2020-12-31",
        regime="synthetic",
        rationale="unit test",
    )
    m_wavelet = ModelDef(
        id="wavelet_baseline",
        adapter_module="research.autoresearch.foundation_bench.adapters.wavelet_baseline",
        adapter_class="WaveletBaselineAdapter",
        type="classical",
        default_config={"wavelet": "db4", "n_levels": 2, "residual_order": 2},
        expect_real_weights=True,
        explainability="medium",
    )
    m_timesfm = ModelDef(
        id="timesfm",
        adapter_module="research.autoresearch.foundation_bench.adapters.timesfm",
        adapter_class="TimesFMAdapter",
        type="foundation",
        default_config={"ctx_len": 256, "horizon_cap": 128},
        expect_real_weights=False,
        explainability="low",
    )
    return BenchSpec(
        id="foundation-bench-v1",
        slices=[sd],
        models=[m_wavelet, m_timesfm],
        query_window=30,
        forward_bars=15,
        top_k=10,
        n_trials=4,
        n_trials_smoke=2,
        seeds=[42],
        min_lookback_multiplier=2,
        per_cell_budget_seconds=180.0,
        percentiles=[10, 25, 50, 75, 90],
        thresholds={},
        data_root_default="",
    )


# ---------------------------------------------------------------------------
# Parser + filters
# ---------------------------------------------------------------------------

def test_parser_defaults_parse_cleanly():
    args = build_parser().parse_args([])
    assert args.smoke is False
    assert args.n_trials is None
    assert args.slice_ids == []
    assert args.model_ids == []


def test_parser_accepts_csv_slices_and_repeated_models():
    args = build_parser().parse_args(
        [
            "--slices", "spy-bull-2016-2019,spy-covid-2020",
            "--model", "timesfm",
            "--model", "wavelet_baseline",
            "--n-trials", "7",
            "--smoke",
        ]
    )
    assert args.slice_csv == "spy-bull-2016-2019,spy-covid-2020"
    assert args.model_ids == ["timesfm", "wavelet_baseline"]
    assert args.n_trials == 7
    assert args.smoke is True


# ---------------------------------------------------------------------------
# Spec loader
# ---------------------------------------------------------------------------

def test_load_spec_merges_slices_and_models():
    spec = load_spec()
    assert spec.id == "foundation-bench-v1"
    assert any(s.id == "spy-covid-2020" for s in spec.slices)
    model_ids = {m.id for m in spec.models}
    assert {"timesfm", "chronos", "moirai", "moment", "wavelet_baseline"} <= model_ids
    assert spec.per_cell_budget_seconds > 0
    assert set(spec.percentiles) == {10, 25, 50, 75, 90}


# ---------------------------------------------------------------------------
# Adapter construction
# ---------------------------------------------------------------------------

def test_construct_adapter_drops_unknown_kwargs():
    """default_config may carry keys the adapter does not accept (e.g.
    horizon for timesfm). construct_adapter must only forward accepted ones."""
    spec = _mini_spec()
    timesfm_def = next(m for m in spec.models if m.id == "timesfm")
    adapter = construct_adapter(timesfm_def, seed=1)
    # ctx_len was accepted; no-op kwarg ``horizon`` would raise if forwarded.
    assert adapter.ctx_len == 256


# ---------------------------------------------------------------------------
# Trial sampling
# ---------------------------------------------------------------------------

def test_sample_trial_positions_is_deterministic():
    a = sample_trial_positions(400, 60, 30, 5, seed=42, min_lookback_multiplier=3)
    b = sample_trial_positions(400, 60, 30, 5, seed=42, min_lookback_multiplier=3)
    assert a == b


def test_sample_trial_positions_raises_on_short_slice():
    with pytest.raises(ValueError):
        sample_trial_positions(50, 60, 30, 5, seed=42)


# ---------------------------------------------------------------------------
# evaluate_cell — smoke
# ---------------------------------------------------------------------------

def test_evaluate_cell_runs_wavelet_smoke(tmp_path: Path):
    spec = _mini_spec()
    slice_def = spec.slices[0]
    model = next(m for m in spec.models if m.id == "wavelet_baseline")
    values = _fake_prices(400, seed=3)
    positions = sample_trial_positions(
        len(values), spec.query_window, spec.forward_bars, 3, seed=42, min_lookback_multiplier=2
    )
    cell = evaluate_cell(slice_def, model, values, positions, spec, seed=42)
    assert cell.n_trials == 3
    assert cell.n_skipped_budget == 0
    # wavelet_baseline is the only adapter that should NOT fall back.
    assert cell.status == "ok"
    assert cell.fallback_ratio == 0.0


def test_evaluate_cell_flags_synthetic_fallback_for_timesfm():
    spec = _mini_spec()
    slice_def = spec.slices[0]
    model = next(m for m in spec.models if m.id == "timesfm")
    values = _fake_prices(400, seed=4)
    positions = sample_trial_positions(
        len(values), spec.query_window, spec.forward_bars, 3, seed=42, min_lookback_multiplier=2
    )
    cell = evaluate_cell(slice_def, model, values, positions, spec, seed=42)
    assert cell.fallback_ratio == 1.0
    assert cell.status == "partial_synthetic_fallback"
    assert cell.any_fallback is True


def test_evaluate_cell_honours_budget_cap():
    """With a 0-second budget, every trial past #0 must be skipped."""
    spec = _mini_spec()
    spec.per_cell_budget_seconds = 0.0  # cap triggers after first trial
    slice_def = spec.slices[0]
    model = next(m for m in spec.models if m.id == "timesfm")
    values = _fake_prices(400, seed=5)
    positions = sample_trial_positions(
        len(values), spec.query_window, spec.forward_bars, 5, seed=42, min_lookback_multiplier=2
    )
    cell = evaluate_cell(slice_def, model, values, positions, spec, seed=42)
    # Budget check fires BEFORE the first adapter call when cumulative >= 0.
    assert cell.n_skipped_budget == len(positions)
    assert cell.n_trials == 0
    # Status taxonomy reflects the skip.
    assert cell.status.startswith("skipped_budget")


# ---------------------------------------------------------------------------
# Artefact serialization
# ---------------------------------------------------------------------------

def test_write_cell_artefact_roundtrips(tmp_path: Path):
    # Synthesize a minimal CellResult with one record
    from research.autoresearch.retrieval_bench.metrics import TrialOutcome
    from research.autoresearch.foundation_bench.run_bench import TrialRecord

    rec = TrialRecord(
        outcome=TrialOutcome(
            match_forward_returns=[],
            quantile_forecast={10: -0.01, 50: 0.0, 90: 0.01},
            realised_forward_return=0.002,
            runtime_seconds=0.05,
        ),
        fallback_reason="synthetic",
        adapter_metadata={"mode": "synthetic_fallback"},
    )
    cell = CellResult(
        slice_id="tiny",
        model_id="timesfm",
        n_trials=1,
        n_skipped_budget=0,
        any_fallback=True,
        fallback_ratio=1.0,
        crps=0.005,
        calibration_error_p10_p90=0.1,
        hit_rate=1.0,
        runtime={"median": 0.05, "mean": 0.05, "p95": 0.05, "n": 1},
        records=[rec],
        status="partial_synthetic_fallback",
        notes="",
    )
    out = write_cell_artefact(cell, tmp_path)
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["metadata"]["benchmark_id"] == "foundation-bench-v1"
    assert payload["result"]["model_id"] == "timesfm"
    assert payload["result"]["trials"][0]["fallback_reason"] == "synthetic"


# ---------------------------------------------------------------------------
# End-to-end smoke via monkey-patched data loader
# ---------------------------------------------------------------------------

def test_runner_smoke_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Invoke the runner with a stubbed data loader and verify that a
    per-cell JSON artefact, a markdown report, and a ledger row are written.

    This is the single highest-value regression gate: if the runner
    wiring breaks, this test fails before the bench is ever invoked on
    real data.
    """
    # --- Patch data loading to produce synthetic prices per slice ------
    def _fake_loader(slice_def, data_root):  # noqa: ANN001
        return _fake_prices(500, seed=abs(hash(slice_def.id)) % 10_000)

    monkeypatch.setattr(run_bench, "load_slice_values", _fake_loader)

    # --- Patch spec with a 1-slice 1-model mini spec so the run is fast
    def _load_spec_mini(slices_path=None, models_path=None):  # noqa: ANN001
        return _mini_spec()

    monkeypatch.setattr(run_bench, "load_spec", _load_spec_mini)

    reports_dir = tmp_path / "reports"
    md_report = tmp_path / "summary.md"
    ledger_path = tmp_path / "experiments.jsonl"

    # Redirect the ledger path so test doesn't pollute the real one.
    monkeypatch.setattr(run_bench, "LEDGER_PATH", ledger_path)

    rc = run_bench.main(
        [
            "--smoke",
            "--reports-dir", str(reports_dir),
            "--report-md", str(md_report),
            "--model", "wavelet_baseline",  # fast + real (no fallback)
        ]
    )
    assert rc == 0
    artefacts = list(reports_dir.glob("*.json"))
    assert artefacts, "per-cell artefact was not written"
    assert md_report.exists()
    assert ledger_path.exists()
    row = json.loads(ledger_path.read_text().strip().splitlines()[-1])
    assert row["benchmark_id"] == "foundation-bench-v1"
    assert row["decision"] == "measured"
