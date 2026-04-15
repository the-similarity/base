"""Tests for the synthetic.fidelity scorecard module.

Skipped if `the_similarity.synthetic.fidelity` has not landed yet. Checks
that:
- Evaluating real-vs-real (i.e. synth is a copy of real) yields a high
  overall_score (> 0.9) with passed=True.
- Evaluating real-vs-pure-noise yields a low score with passed=False.
- Returned FidelityReport has marginals / temporal / tails dicts.
"""
from __future__ import annotations

import numpy as np
import pytest

fidelity = pytest.importorskip("the_similarity.synthetic.fidelity")

from the_similarity.synthetic import contracts as C  # noqa: E402


_SCORECARD_CANDIDATES = (
    "FidelityScorecard",
    "FidelityScorer",
    "Fidelity",
)


def _get_scorecard():
    for name in _SCORECARD_CANDIDATES:
        cls = getattr(fidelity, name, None)
        if cls is not None:
            return cls()
    # Fallback: module-level `evaluate` function with callable shape.
    fn = getattr(fidelity, "evaluate", None)
    if callable(fn):
        class _Fn:
            def evaluate(self, real, synth):
                return fn(real, synth)

        return _Fn()
    pytest.skip(
        f"No FidelityScorecard found in the_similarity.synthetic.fidelity "
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
    rng = np.random.default_rng(0)
    return rng.standard_normal((500, 2))


def test_real_vs_real_scores_high(real_arr):
    sc = _get_scorecard()
    real = _mk(real_arr, "real")
    synth = _mk(real_arr.copy(), "real_copy")
    rep = sc.evaluate(real, synth)
    assert isinstance(rep, C.FidelityReport)
    assert rep.overall_score > 0.9, (
        f"real-vs-real fidelity should be > 0.9, got {rep.overall_score}"
    )
    assert rep.passed is True


def test_random_noise_scores_low(real_arr):
    sc = _get_scorecard()
    real = _mk(real_arr, "real")
    rng = np.random.default_rng(99)
    # Pathological synth: uniform on a wildly different range.
    noise = rng.uniform(low=-1000.0, high=1000.0, size=real_arr.shape)
    synth = _mk(noise, "noise")
    rep = sc.evaluate(real, synth)
    assert isinstance(rep, C.FidelityReport)
    assert rep.overall_score < 0.5, (
        f"noise fidelity should be < 0.5, got {rep.overall_score}"
    )
    assert rep.passed is False


def test_report_has_metric_dicts(real_arr):
    sc = _get_scorecard()
    real = _mk(real_arr, "real")
    synth = _mk(real_arr.copy(), "real_copy")
    rep = sc.evaluate(real, synth)
    assert isinstance(rep.marginals, dict)
    assert isinstance(rep.temporal, dict)
    assert isinstance(rep.tails, dict)
