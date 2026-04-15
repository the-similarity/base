"""Tests for retrieval-bench runner scaffolding.

Covers spec loading, trial sampling, forward-return helpers, and JSON
report serialisation.  Full engine integration is covered separately by
``--smoke`` runs on real parquet data.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from research.autoresearch.retrieval_bench.metrics import TrialOutcome
from research.autoresearch.retrieval_bench.run_bench import (
    ArmResult,
    _forward_return,
    load_spec,
    sample_trial_positions,
    write_arm_report,
)


# ---------------------------------------------------------------------------
# load_spec
# ---------------------------------------------------------------------------

def test_load_spec_parses_real_yaml():
    spec = load_spec()
    assert spec.id == "retrieval-bench-tiers-v1"
    assert len(spec.slices) >= 3
    assert any(s.id == "spy-covid-2020" for s in spec.slices)
    # Both arms must be present and in the expected order
    arm_ids = [a.id for a in spec.arms]
    assert arm_ids == ["tier1_only", "tier1_plus_full"]
    # Tier 1 only must contain exactly the cheap shape methods
    assert set(spec.arms[0].active_methods) == {"dtw", "pearson_warped"}
    # Tier 1+2 must contain all 9 methods
    assert len(spec.arms[1].active_methods) == 9


def test_load_spec_thresholds_present():
    spec = load_spec()
    for key in (
        "min_crps_improvement",
        "min_forward_corr_improvement",
        "max_runtime_multiplier",
        "min_slices_improved",
    ):
        assert key in spec.thresholds


# ---------------------------------------------------------------------------
# sample_trial_positions
# ---------------------------------------------------------------------------

def test_sample_trial_positions_is_reproducible():
    a = sample_trial_positions(n_points=1000, window=60, forward_bars=30, n_trials=20, seed=42)
    b = sample_trial_positions(n_points=1000, window=60, forward_bars=30, n_trials=20, seed=42)
    assert a == b


def test_sample_trial_positions_respects_lookback_and_forward():
    positions = sample_trial_positions(
        n_points=1000, window=60, forward_bars=30, n_trials=50, seed=0,
        min_lookback_multiplier=3,
    )
    # Every position must have >=180 lookback and enough forward room
    for q in positions:
        assert q >= 180
        assert q + 60 + 30 <= 1000


def test_sample_trial_positions_raises_when_too_short():
    with pytest.raises(ValueError):
        sample_trial_positions(n_points=100, window=60, forward_bars=30, n_trials=5, seed=0)


def test_sample_trial_positions_degenerate_returns_full_range():
    # If n_trials exceeds available positions the function returns them all.
    # At n_points=400, window=60, forward_bars=30, min_lookback_multiplier=3:
    # valid range is [180, 310) -> 130 available positions.
    pos = sample_trial_positions(
        n_points=400, window=60, forward_bars=30,
        n_trials=10_000, seed=0, min_lookback_multiplier=3,
    )
    assert len(pos) == 130
    assert pos == list(range(180, 310))


# ---------------------------------------------------------------------------
# _forward_return
# ---------------------------------------------------------------------------

def test_forward_return_pct_change():
    values = np.array([100.0, 101.0, 102.0, 103.0, 110.0])
    # start=0, horizon=5 -> values[0]->values[4] = 110/100 - 1 = 0.10
    assert _forward_return(values, 0, 5) == pytest.approx(0.10)


def test_forward_return_zero_for_out_of_range():
    values = np.array([100.0, 101.0])
    assert _forward_return(values, 0, 10) == 0.0
    assert _forward_return(values, -1, 2) == 0.0


def test_forward_return_zero_for_zero_starting_value():
    values = np.array([0.0, 1.0, 2.0])
    assert _forward_return(values, 0, 3) == 0.0


# ---------------------------------------------------------------------------
# ArmResult serialisation & write_arm_report
# ---------------------------------------------------------------------------

def _mk_arm_result(slice_id="demo", arm_id="tier1_only") -> ArmResult:
    trials = [
        TrialOutcome(
            match_forward_returns=[0.01, 0.02],
            quantile_forecast={10: -0.01, 50: 0.0, 90: 0.01},
            realised_forward_return=0.005,
            runtime_seconds=0.1,
        )
    ]
    return ArmResult(
        slice_id=slice_id,
        arm_id=arm_id,
        arm_label="demo arm",
        n_trials=len(trials),
        forward_return_correlation=0.42,
        crps=0.01,
        calibration_error_p10_p90=0.05,
        hit_rate=0.75,
        runtime={"median": 0.1, "mean": 0.12, "p95": 0.2, "n": 1},
        trials=trials,
    )


def test_arm_result_to_dict_without_trials():
    r = _mk_arm_result()
    d = r.to_dict(include_trials=False)
    assert "trials" not in d
    assert d["crps"] == 0.01
    assert d["runtime_seconds"]["p95"] == 0.2


def test_write_arm_report_roundtrip(tmp_path):
    r = _mk_arm_result()
    path = write_arm_report(r, tmp_path)
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["metadata"]["benchmark_id"] == "retrieval-bench-tiers-v1"
    assert payload["result"]["slice_id"] == "demo"
    assert len(payload["result"]["trials"]) == 1
