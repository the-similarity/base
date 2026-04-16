"""Tests for the synthetic FidelityScorecard.

These cover the public contract (ScorecardProtocol compliance, threshold gate,
family dicts populated, univariate handling) and the fail-closed path. We
test against numpy arrays and pandas DataFrames to lock in the duck-typed
input handling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from the_similarity.synthetic import (
    FidelityReport,
    FidelityScorecard,
    Provenance,
    ScorecardProtocol,
    SyntheticDataset,
    iso_now,
)


def _provenance(name: str = "test") -> Provenance:
    return Provenance(
        source_id="test",
        generator_name=name,
        generator_version="0.0.1",
        seed=0,
        created_at=iso_now(),
    )


def _ar1(n: int, phi: float, sigma: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + sigma * rng.standard_normal()
    return x


def _dataset(arr: np.ndarray, columns: list[str] | None = None) -> SyntheticDataset:
    return SyntheticDataset(data=arr, columns=columns, provenance=_provenance())


# ---------------------------------------------------------------------------
# Protocol + basic shape
# ---------------------------------------------------------------------------


def test_scorecard_satisfies_protocol():
    sc = FidelityScorecard()
    assert isinstance(sc, ScorecardProtocol)


def test_evaluate_returns_fidelity_report():
    rng = np.random.default_rng(0)
    r = rng.standard_normal((500, 2))
    s = rng.standard_normal((500, 2))
    report = FidelityScorecard().evaluate(_dataset(r, ["a", "b"]), _dataset(s, ["a", "b"]))
    assert isinstance(report, FidelityReport)
    assert 0.0 <= report.overall_score <= 1.0


# ---------------------------------------------------------------------------
# Marginals
# ---------------------------------------------------------------------------


def test_identical_distributions_score_high():
    rng = np.random.default_rng(42)
    r = rng.standard_normal((2000, 2))
    # Use a different RNG seed so the samples differ but the distribution is
    # the same — the scorecard should still clear the default 0.7 gate.
    s = np.random.default_rng(43).standard_normal((2000, 2))
    report = FidelityScorecard().evaluate(_dataset(r, ["a", "b"]), _dataset(s, ["a", "b"]))
    assert report.passed is True
    assert report.overall_score >= 0.7


def test_very_different_distributions_fail_gate():
    rng = np.random.default_rng(0)
    r = rng.standard_normal((1000, 1))
    # Shift + scale by a lot — KS should be ~1 and mean diff large.
    s = rng.standard_normal((1000, 1)) * 5 + 10
    report = FidelityScorecard().evaluate(_dataset(r, ["a"]), _dataset(s, ["a"]))
    assert report.passed is False
    assert report.marginals["a__ks"] > 0.5
    assert report.marginals["a__mean_diff"] > 5


def test_marginal_dict_has_all_metrics_per_column():
    rng = np.random.default_rng(1)
    r = rng.standard_normal((500, 1))
    s = rng.standard_normal((500, 1))
    report = FidelityScorecard().evaluate(_dataset(r, ["x"]), _dataset(s, ["x"]))
    for metric in ("ks", "wasserstein", "mean_diff", "std_diff", "skew_diff", "kurt_diff"):
        assert f"x__{metric}" in report.marginals


# ---------------------------------------------------------------------------
# Temporal
# ---------------------------------------------------------------------------


def test_temporal_metrics_present_for_requested_lags():
    r = _ar1(1000, phi=0.6, sigma=1.0, seed=0).reshape(-1, 1)
    s = _ar1(1000, phi=0.6, sigma=1.0, seed=1).reshape(-1, 1)
    sc = FidelityScorecard(temporal_lags=(1, 5, 10))
    report = sc.evaluate(_dataset(r, ["y"]), _dataset(s, ["y"]))
    for lag in (1, 5, 10):
        assert f"y__acf_lag{lag}_diff" in report.temporal
        assert f"y__pacf_lag{lag}_diff" in report.temporal
    assert "acf_mean_diff" in report.temporal
    assert "pacf_mean_diff" in report.temporal


def test_pacf_excluded_when_disabled():
    r = _ar1(500, 0.5, 1.0, 0).reshape(-1, 1)
    s = _ar1(500, 0.5, 1.0, 1).reshape(-1, 1)
    report = FidelityScorecard(include_pacf=False).evaluate(
        _dataset(r, ["y"]), _dataset(s, ["y"])
    )
    assert "pacf_mean_diff" not in report.temporal
    assert not any(k.startswith("y__pacf_") for k in report.temporal)


# ---------------------------------------------------------------------------
# Cross-series
# ---------------------------------------------------------------------------


def test_cross_series_is_none_for_univariate():
    rng = np.random.default_rng(0)
    r = rng.standard_normal((500, 1))
    s = rng.standard_normal((500, 1))
    report = FidelityScorecard().evaluate(_dataset(r, ["x"]), _dataset(s, ["x"]))
    assert report.cross_series is None


def test_cross_series_populated_for_multivariate():
    rng = np.random.default_rng(0)
    # Correlated Gaussian pair on real side; independent on synth side — the
    # Frobenius diff should be clearly nonzero.
    cov = np.array([[1.0, 0.8], [0.8, 1.0]])
    r = rng.multivariate_normal([0, 0], cov, size=1500)
    s = rng.standard_normal((1500, 2))
    report = FidelityScorecard().evaluate(_dataset(r, ["a", "b"]), _dataset(s, ["a", "b"]))
    assert report.cross_series is not None
    assert report.cross_series["corr_frobenius_diff"] > 0.5


# ---------------------------------------------------------------------------
# Tails
# ---------------------------------------------------------------------------


def test_tail_metrics_present():
    rng = np.random.default_rng(0)
    r = rng.standard_normal((2000, 1))
    s = rng.standard_normal((2000, 1))
    report = FidelityScorecard().evaluate(_dataset(r, ["x"]), _dataset(s, ["x"]))
    for k in ("x__p01_ratio", "x__p99_ratio", "x__cvar05_diff", "x__cvar95_diff"):
        assert k in report.tails
    for k in ("p01_ratio_mean", "p99_ratio_mean", "cvar05_mean_diff", "cvar95_mean_diff"):
        assert k in report.tails


# ---------------------------------------------------------------------------
# Input types
# ---------------------------------------------------------------------------


def test_accepts_pandas_dataframe():
    rng = np.random.default_rng(0)
    r = pd.DataFrame(rng.standard_normal((500, 2)), columns=["a", "b"])
    s = pd.DataFrame(rng.standard_normal((500, 2)), columns=["a", "b"])
    report = FidelityScorecard().evaluate(
        SyntheticDataset(data=r, provenance=_provenance()),
        SyntheticDataset(data=s, provenance=_provenance()),
    )
    assert "a__ks" in report.marginals
    assert "b__ks" in report.marginals


def test_accepts_1d_array():
    rng = np.random.default_rng(0)
    r = rng.standard_normal(500)
    s = rng.standard_normal(500)
    report = FidelityScorecard().evaluate(_dataset(r), _dataset(s))
    assert "col0__ks" in report.marginals


# ---------------------------------------------------------------------------
# Threshold & fail-closed
# ---------------------------------------------------------------------------


def test_custom_threshold_tightens_gate():
    rng = np.random.default_rng(0)
    r = rng.standard_normal((1000, 1))
    s = rng.standard_normal((1000, 1))
    # Strict threshold should fail even on the same distribution due to
    # sampling noise in KS / Wasserstein.
    strict = FidelityScorecard(threshold=0.999).evaluate(
        _dataset(r, ["x"]), _dataset(s, ["x"])
    )
    assert strict.passed is False


def test_shape_mismatch_fails_closed():
    r = np.random.default_rng(0).standard_normal((500, 2))
    s = np.random.default_rng(1).standard_normal((500, 3))
    report = FidelityScorecard().evaluate(
        _dataset(r, ["a", "b"]), _dataset(s, ["a", "b", "c"])
    )
    assert report.passed is False
    assert report.overall_score == 0.0


def test_threshold_class_attribute_default():
    assert FidelityScorecard.threshold == 0.7
    assert FidelityScorecard().threshold == 0.7
