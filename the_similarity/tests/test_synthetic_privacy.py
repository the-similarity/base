"""Tests for the synthetic.privacy scorecard module.

Skipped if `the_similarity.synthetic.privacy` has not landed yet. Verifies:
- Identical-copy synth (synth == real, verbatim) fails privacy — low
  overall_score, passed=False — because every synth row has a zero-distance
  neighbor in real.
- Independent-noise synth passes privacy — no row in real is near any row in
  synth.
"""
from __future__ import annotations

import numpy as np
import pytest

privacy = pytest.importorskip("the_similarity.synthetic.privacy")

from the_similarity.synthetic import contracts as C  # noqa: E402


_SCORECARD_CANDIDATES = (
    "PrivacyScorecard",
    "PrivacyScorer",
    "Privacy",
)


def _get_scorecard():
    for name in _SCORECARD_CANDIDATES:
        cls = getattr(privacy, name, None)
        if cls is not None:
            return cls()
    fn = getattr(privacy, "evaluate", None)
    if callable(fn):
        class _Fn:
            def evaluate(self, real, synth):
                return fn(real, synth)

        return _Fn()
    pytest.skip(
        f"No PrivacyScorecard found in the_similarity.synthetic.privacy "
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
    return rng.standard_normal((300, 2))


def test_identical_copy_fails_privacy(real_arr):
    sc = _get_scorecard()
    real = _mk(real_arr, "real")
    # Attack: synth is literally the real dataset → zero-distance NN.
    synth = _mk(real_arr.copy(), "verbatim_copy")
    rep = sc.evaluate(real, synth)
    assert isinstance(rep, C.PrivacyReport)
    assert rep.passed is False, (
        "verbatim copy must fail privacy (memorization is trivial)"
    )
    assert rep.overall_score < 0.5, (
        f"verbatim copy privacy score should be < 0.5, got {rep.overall_score}"
    )


def test_independent_noise_passes_privacy(real_arr):
    sc = _get_scorecard()
    real = _mk(real_arr, "real")
    rng = np.random.default_rng(7)
    synth_arr = rng.standard_normal(real_arr.shape)
    synth = _mk(synth_arr, "independent_noise")
    rep = sc.evaluate(real, synth)
    assert isinstance(rep, C.PrivacyReport)
    assert rep.passed is True, (
        f"independent noise should pass privacy, got passed={rep.passed}"
    )
    assert rep.overall_score > 0.5, (
        f"independent-noise privacy score should be > 0.5, got "
        f"{rep.overall_score}"
    )
