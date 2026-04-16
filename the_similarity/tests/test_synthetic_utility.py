"""Tests for :class:`the_similarity.synthetic.utility.UtilityScorecard`.

Covers:
- Protocol conformance (runtime-checkable ScorecardProtocol).
- Happy-path: AR(1) real + matching AR(1) synthetic yields small positive
  transfer_gap and ``passed=True``.
- Poor synthetic (pure noise / constant) produces a large or non-finite
  transfer_gap and ``passed=False``.
- DataFrame input path (pandas multi-column → first column used).
- Fail-closed: too-short inputs yield ``passed=False`` with a
  ``reason_too_short`` sentinel instead of raising.
- Determinism: two evaluations on identical inputs match bit-for-bit.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from the_similarity.synthetic import (
    Provenance,
    ScorecardProtocol,
    SyntheticDataset,
    UtilityReport,
    iso_now,
)
from the_similarity.synthetic.utility import UtilityScorecard


def _mk(data, source_id: str = "t") -> SyntheticDataset:
    return SyntheticDataset(
        data=data,
        provenance=Provenance(
            source_id=source_id,
            generator_name="test",
            generator_version="0.0.0",
            seed=0,
            created_at=iso_now(),
        ),
    )


def _ar1(n: int, phi: float = 0.7, sigma: float = 0.5, seed: int = 0) -> np.ndarray:
    """Deterministic AR(1) process for synthetic test fixtures."""
    rng = np.random.default_rng(seed)
    y = np.zeros(n, dtype=np.float64)
    eps = rng.standard_normal(n) * sigma
    for t in range(1, n):
        y[t] = phi * y[t - 1] + eps[t]
    return y


def test_protocol_conformance():
    assert isinstance(UtilityScorecard(), ScorecardProtocol)


def test_happy_path_matching_ar1_passes():
    real = _mk(_ar1(500, seed=0))
    synth = _mk(_ar1(400, seed=1))
    report = UtilityScorecard().evaluate(real, synth)

    assert isinstance(report, UtilityReport)
    for bag in (report.real_baseline, report.trts, report.tstr):
        assert set(bag) == {"mae", "rmse", "r2"}
        for v in bag.values():
            assert math.isfinite(v)
    assert math.isfinite(report.transfer_gap)
    # Matching AR(1) distributions should transfer well — gap well below threshold.
    assert report.transfer_gap < 0.3
    assert report.passed is True


def test_poor_synth_fails():
    real = _mk(_ar1(500, phi=0.9, sigma=0.3, seed=0))
    # Constant synthetic — model cannot learn anything useful to predict a
    # non-constant real test set; TSTR should collapse.
    synth = _mk(np.zeros(400, dtype=np.float64))

    report = UtilityScorecard().evaluate(real, synth)
    # Either transfer_gap explodes above threshold or a metric is NaN
    # (constant target → R² undefined). Either way, fail-closed.
    assert report.passed is False


def test_dataframe_input_uses_first_column():
    base = _ar1(500, seed=0)
    df = pd.DataFrame(
        {"target": base, "noise": np.random.default_rng(9).standard_normal(500)}
    )
    real = _mk(df)
    synth = _mk(pd.DataFrame({"target": _ar1(400, seed=1)}))

    report = UtilityScorecard().evaluate(real, synth)
    assert report.passed is True


def test_too_short_input_fails_closed():
    tiny = np.arange(3.0)
    report = UtilityScorecard().evaluate(_mk(tiny), _mk(tiny))
    assert report.passed is False
    assert math.isnan(report.transfer_gap)
    assert report.real_baseline.get("reason_too_short") == 1.0


def test_deterministic_across_runs():
    real = _mk(_ar1(500, seed=0))
    synth = _mk(_ar1(400, seed=1))
    a = UtilityScorecard().evaluate(real, synth)
    b = UtilityScorecard().evaluate(real, synth)
    assert a.real_baseline == b.real_baseline
    assert a.trts == b.trts
    assert a.tstr == b.tstr
    assert a.transfer_gap == b.transfer_gap
    assert a.passed == b.passed


def test_threshold_is_class_level_and_overridable():
    # Pin threshold low enough to force a fail even on clean data.
    real = _mk(_ar1(500, seed=0))
    synth = _mk(_ar1(400, seed=1))
    strict = UtilityScorecard(THRESHOLD=-1.0)
    report = strict.evaluate(real, synth)
    assert report.passed is False
