"""Unit tests for retrieval-bench metric helpers.

These tests are engine-free — the metric module has no ``the_similarity``
imports, so the tests can run under any Python environment with numpy.
"""
from __future__ import annotations

import numpy as np
import pytest

from research.autoresearch.retrieval_bench.metrics import (
    TrialOutcome,
    calibration_error_p10_p90,
    empirical_crps,
    forward_return_correlation,
    hit_rate,
    summarise_runtimes,
)


def _trial(match_fwds, quantiles, realised, runtime=0.1):
    """Helper to build a TrialOutcome with defaults."""
    return TrialOutcome(
        match_forward_returns=list(match_fwds),
        quantile_forecast=dict(quantiles),
        realised_forward_return=float(realised),
        runtime_seconds=float(runtime),
    )


# ---------------------------------------------------------------------------
# forward_return_correlation
# ---------------------------------------------------------------------------

def test_forward_return_correlation_returns_zero_for_too_few_trials():
    trials = [_trial([0.01], {50: 0.0}, 0.02)]
    assert forward_return_correlation(trials) == 0.0


def test_forward_return_correlation_positive_when_aligned():
    # Mean of matches tracks realised perfectly
    trials = [
        _trial([0.01, 0.02], {}, 0.03),
        _trial([0.02, 0.03], {}, 0.04),
        _trial([0.03, 0.04], {}, 0.05),
        _trial([-0.01, 0.0], {}, -0.005),
    ]
    r = forward_return_correlation(trials)
    assert r > 0.9


def test_forward_return_correlation_zero_when_no_variance():
    trials = [
        _trial([0.01], {}, 0.01),
        _trial([0.01], {}, 0.02),
        _trial([0.01], {}, 0.03),
    ]
    # x has zero variance -> correlation undefined -> 0.0
    assert forward_return_correlation(trials) == 0.0


# ---------------------------------------------------------------------------
# empirical_crps
# ---------------------------------------------------------------------------

def test_empirical_crps_zero_for_no_trials():
    assert empirical_crps([]) == 0.0


def test_empirical_crps_small_when_realised_in_interior():
    # A tight, well-centred forecast should have modest CRPS.
    trials = [
        _trial([], {10: -0.01, 50: 0.0, 90: 0.01}, 0.0),
        _trial([], {10: -0.01, 50: 0.0, 90: 0.01}, 0.001),
    ]
    v = empirical_crps(trials)
    assert v >= 0.0
    assert v < 0.01


def test_empirical_crps_larger_when_realised_far_from_forecast():
    # Realised far outside the quantile band -> larger CRPS.
    trials_centered = [_trial([], {10: -0.01, 50: 0.0, 90: 0.01}, 0.0)]
    trials_far = [_trial([], {10: -0.01, 50: 0.0, 90: 0.01}, 0.2)]
    assert empirical_crps(trials_far) > empirical_crps(trials_centered)


# ---------------------------------------------------------------------------
# calibration_error_p10_p90
# ---------------------------------------------------------------------------

def test_calibration_zero_when_coverage_exactly_80_percent():
    # 8 of 10 realised inside [p10, p90] -> coverage = 0.80 -> error = 0
    inside = [_trial([], {10: -1.0, 90: 1.0}, 0.0) for _ in range(8)]
    outside = [_trial([], {10: -1.0, 90: 1.0}, 5.0) for _ in range(2)]
    assert calibration_error_p10_p90(inside + outside) == pytest.approx(0.0, abs=1e-9)


def test_calibration_error_increases_with_overconfidence():
    # 0/10 inside -> coverage 0.0 -> error 0.80
    outside_only = [_trial([], {10: -0.01, 90: 0.01}, 0.5) for _ in range(10)]
    assert calibration_error_p10_p90(outside_only) == pytest.approx(0.80, abs=1e-9)


# ---------------------------------------------------------------------------
# hit_rate
# ---------------------------------------------------------------------------

def test_hit_rate_correct_direction():
    # 3 positive-positive (hit), 1 positive-negative (miss) -> 0.75
    trials = [
        _trial([], {50: 0.01}, 0.05),
        _trial([], {50: 0.01}, 0.02),
        _trial([], {50: 0.01}, 0.001),
        _trial([], {50: 0.01}, -0.02),
    ]
    assert hit_rate(trials) == pytest.approx(0.75)


def test_hit_rate_skips_trivial_zero_trials():
    # Zero p50 AND zero realised -> skipped, counts only the second trial.
    trials = [
        _trial([], {50: 0.0}, 0.0),
        _trial([], {50: 0.01}, 0.05),
    ]
    assert hit_rate(trials) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# summarise_runtimes
# ---------------------------------------------------------------------------

def test_summarise_runtimes_empty_returns_zero_struct():
    out = summarise_runtimes([])
    assert out == {"median": 0.0, "mean": 0.0, "p95": 0.0, "n": 0}


def test_summarise_runtimes_reports_median_and_p95():
    out = summarise_runtimes([0.1, 0.2, 0.3, 0.4, 1.0])
    assert out["n"] == 5
    assert out["median"] == pytest.approx(0.3)
    assert out["mean"] == pytest.approx(0.4)
    # p95 of 5-element sample is close to the max via linear interpolation.
    assert out["p95"] == pytest.approx(np.percentile([0.1, 0.2, 0.3, 0.4, 1.0], 95))
