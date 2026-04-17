"""Tests for :class:`the_similarity.synthetic.privacy.PrivacyScorecard`.

These tests assert attack behaviour with controlled inputs:

- A well-separated synth set produced from the same distribution as real
  should pass the gate and score ~0 on every risk sub-metric.
- A synth set that is literally the real set (copy attack) should fail
  with near-zero overall score and high memorization.
- The scorecard satisfies :class:`ScorecardProtocol` structurally.
- Univariate payloads and pandas DataFrames are accepted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from the_similarity.synthetic import (
    PrivacyReport,
    Provenance,
    ScorecardProtocol,
    SyntheticDataset,
    iso_now,
)
from the_similarity.synthetic.privacy import PrivacyScorecard


def _ds(array, name: str = "gen") -> SyntheticDataset:
    """Build a SyntheticDataset with a minimal valid Provenance."""
    return SyntheticDataset(
        data=array,
        provenance=Provenance(
            source_id="test",
            generator_name=name,
            generator_version="0.0.0",
            seed=0,
            created_at=iso_now(),
        ),
    )


@pytest.fixture(scope="module")
def rng() -> np.random.Generator:
    return np.random.default_rng(12345)


@pytest.fixture(scope="module")
def real_multivariate(rng) -> np.ndarray:
    # 300 rows × 4 features — enough for p05 percentiles to be stable.
    return rng.normal(size=(300, 4))


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_scorecard_satisfies_protocol():
    assert isinstance(PrivacyScorecard(), ScorecardProtocol)


def test_passed_threshold_is_class_attr():
    assert PrivacyScorecard.passed_threshold == 0.6


# ---------------------------------------------------------------------------
# Happy path — distinct draws from the same distribution
# ---------------------------------------------------------------------------


def test_independent_synth_passes(real_multivariate, rng):
    synth = rng.normal(size=real_multivariate.shape)
    report = PrivacyScorecard().evaluate(
        _ds(real_multivariate, "real"), _ds(synth, "indep")
    )

    assert isinstance(report, PrivacyReport)
    assert report.passed is True
    assert report.overall_score >= 0.6

    # NN leakage ratio should be near 1 — synth spacing matches real spacing.
    assert 0.5 <= report.nn_leakage["leakage_ratio"] <= 1.5
    # Near-dupe fraction should be zero for independent gaussian draws.
    assert report.memorization["near_dupe_frac"] == 0.0
    # MIA AUC should hover around 0.5 for an uninformative attacker.
    assert abs(report.membership_proxy["auc"] - 0.5) < 0.1


# ---------------------------------------------------------------------------
# Failure path — copy attack
# ---------------------------------------------------------------------------


def test_direct_copy_fails(real_multivariate):
    # Synth is identical to real — maximum memorization, zero DCR.
    report = PrivacyScorecard().evaluate(
        _ds(real_multivariate, "real"), _ds(real_multivariate.copy(), "copy")
    )

    assert report.passed is False
    assert report.overall_score <= 0.1
    # sklearn's brute-force L2 can return residuals ~1e-8 for identical
    # rows due to accumulated float error — count bit-clean matches, then
    # require the adaptive near-dupe rule to pick up the rest.
    n = real_multivariate.shape[0]
    assert report.memorization["exact_dupes"] >= 0.5 * n
    assert report.memorization["near_dupe_frac"] == 1.0
    assert report.nn_leakage["p05_dcr"] == pytest.approx(0.0, abs=1e-6)


def test_near_copy_fails(real_multivariate, rng):
    # Synth = real + tiny noise. Below the data-scaled near-eps, so near
    # dupes should be high even though exact dupes are zero.
    noise = rng.normal(scale=1e-6, size=real_multivariate.shape)
    synth = real_multivariate + noise
    report = PrivacyScorecard().evaluate(
        _ds(real_multivariate, "real"), _ds(synth, "near-copy")
    )
    assert report.passed is False
    assert report.memorization["near_dupes"] > 0
    assert report.memorization["near_dupe_frac"] > 0.5


# ---------------------------------------------------------------------------
# Shape handling
# ---------------------------------------------------------------------------


def test_univariate_numpy(real_multivariate, rng):
    real_1d = real_multivariate[:, 0]
    synth_1d = rng.normal(size=real_1d.shape)
    report = PrivacyScorecard().evaluate(_ds(real_1d), _ds(synth_1d))
    assert report.passed is True
    assert "leakage_ratio" in report.nn_leakage


def test_pandas_dataframe(real_multivariate, rng):
    real_df = pd.DataFrame(real_multivariate, columns=list("abcd"))
    synth_df = pd.DataFrame(
        rng.normal(size=real_multivariate.shape), columns=list("abcd")
    )
    report = PrivacyScorecard().evaluate(_ds(real_df), _ds(synth_df))
    assert report.passed is True
    assert 0.0 <= report.overall_score <= 1.0


# ---------------------------------------------------------------------------
# Fail-closed edge cases
# ---------------------------------------------------------------------------


def test_empty_synth_fails_closed(real_multivariate):
    report = PrivacyScorecard().evaluate(
        _ds(real_multivariate), _ds(np.empty((0, real_multivariate.shape[1])))
    )
    assert report.passed is False
    # NaNs coerce to full risk → overall_score pinned to 0.
    assert report.overall_score == 0.0


def test_nonfinite_rows_dropped(rng):
    real = rng.normal(size=(100, 2))
    synth = rng.normal(size=(100, 2))
    synth[0] = np.nan  # should be dropped, not poison the result
    report = PrivacyScorecard().evaluate(_ds(real), _ds(synth))
    assert np.isfinite(report.overall_score)


def test_report_is_value_object(real_multivariate, rng):
    # Mutating the returned metric dict must not leak into a fresh evaluate.
    synth = rng.normal(size=real_multivariate.shape)
    card = PrivacyScorecard()
    r1 = card.evaluate(_ds(real_multivariate), _ds(synth))
    r1.nn_leakage["median_dcr"] = -999.0
    r2 = card.evaluate(_ds(real_multivariate), _ds(synth))
    assert r2.nn_leakage["median_dcr"] != -999.0
