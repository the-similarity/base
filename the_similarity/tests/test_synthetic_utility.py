"""Tests for the synthetic.utility (TSTR) scorecard module.

Skipped if `the_similarity.synthetic.utility` has not landed yet. Verifies:
- Passing the real dataset as the synth (synth == real) yields a near-zero
  transfer_gap and passed=True — a model trained on "synth" (which is real)
  matches the real baseline exactly.
- Pathological noise synth produces a large transfer_gap and passed=False.
"""
from __future__ import annotations

import numpy as np
import pytest

utility = pytest.importorskip("the_similarity.synthetic.utility")

from the_similarity.synthetic import contracts as C  # noqa: E402


_SCORECARD_CANDIDATES = (
    "UtilityScorecard",
    "UtilityScorer",
    "UtilityBenchmark",
    "Utility",
)


def _get_scorecard():
    for name in _SCORECARD_CANDIDATES:
        cls = getattr(utility, name, None)
        if cls is not None:
            return cls()
    fn = getattr(utility, "evaluate", None)
    if callable(fn):
        class _Fn:
            def evaluate(self, real, synth):
                return fn(real, synth)

        return _Fn()
    pytest.skip(
        f"No UtilityScorecard found in the_similarity.synthetic.utility "
        f"(tried: {_SCORECARD_CANDIDATES})"
    )


def _mk(arr: np.ndarray, tag: str) -> C.SyntheticDataset:
    prov = C.Provenance(
        source_id="fixture",
        generator_name=tag,
        generator_version="0.0.0",
        seed=0,
        created_at=C.iso_now(),
    )
    return C.SyntheticDataset(data=arr, provenance=prov)


@pytest.fixture
def real_arr() -> np.ndarray:
    # Structured signal: last column is a (mostly) deterministic function of
    # the first two — so a downstream TSTR model has something to learn.
    rng = np.random.default_rng(0)
    n = 400
    x1 = rng.standard_normal(n)
    x2 = rng.standard_normal(n)
    y = (0.7 * x1 - 0.3 * x2 + 0.1 * rng.standard_normal(n) > 0).astype(float)
    return np.column_stack([x1, x2, y])


def test_real_as_synth_transfer_gap_near_zero(real_arr):
    sc = _get_scorecard()
    real = _mk(real_arr, "real")
    # "Synth" == real → TSTR should match TRTR baseline.
    synth = _mk(real_arr.copy(), "real_as_synth")
    rep = sc.evaluate(real, synth)
    assert isinstance(rep, C.UtilityReport)
    assert abs(rep.transfer_gap) < 0.15, (
        f"real-as-synth transfer_gap should be ~0, got {rep.transfer_gap}"
    )
    assert rep.passed is True


def test_random_noise_large_transfer_gap(real_arr):
    sc = _get_scorecard()
    real = _mk(real_arr, "real")
    rng = np.random.default_rng(99)
    noise = rng.standard_normal(real_arr.shape)
    # Force last column (the "label") to pure noise too.
    synth = _mk(noise, "noise")
    rep = sc.evaluate(real, synth)
    assert isinstance(rep, C.UtilityReport)
    assert rep.transfer_gap > 0.1, (
        f"noise synth transfer_gap should be large, got {rep.transfer_gap}"
    )
    assert rep.passed is False
