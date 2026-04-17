"""Tests for the synthetic.contracts module.

Covers dataclass field shapes, asdict roundtrips, runtime_checkable Protocol
behavior, and Scorecard.passed gate logic.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from the_similarity.synthetic import contracts as C


# ---------------------------------------------------------------------------
# Dataclass shapes
# ---------------------------------------------------------------------------


def test_provenance_fields():
    fields = {f.name for f in dataclasses.fields(C.Provenance)}
    assert fields == {
        "source_id",
        "generator_name",
        "generator_version",
        "seed",
        "created_at",
        "params",
    }


def test_synthetic_dataset_fields():
    fields = {f.name for f in dataclasses.fields(C.SyntheticDataset)}
    assert fields == {"data", "index", "columns", "provenance"}


def test_fidelity_report_fields():
    fields = {f.name for f in dataclasses.fields(C.FidelityReport)}
    assert fields == {
        "marginals",
        "temporal",
        "cross_series",
        "tails",
        "overall_score",
        "passed",
    }


def test_privacy_report_fields():
    fields = {f.name for f in dataclasses.fields(C.PrivacyReport)}
    assert fields == {
        "nn_leakage",
        "memorization",
        "membership_proxy",
        "overall_score",
        "passed",
    }


def test_utility_report_fields():
    fields = {f.name for f in dataclasses.fields(C.UtilityReport)}
    assert fields == {
        "trts",
        "tstr",
        "real_baseline",
        "transfer_gap",
        "passed",
    }


def test_scorecard_fields():
    fields = {f.name for f in dataclasses.fields(C.Scorecard)}
    assert fields == {"dataset", "fidelity", "privacy", "utility"}


# ---------------------------------------------------------------------------
# asdict roundtrips
# ---------------------------------------------------------------------------


def test_provenance_asdict_roundtrip():
    p = C.Provenance(
        source_id="spy-2020",
        generator_name="gaussian_copula",
        generator_version="0.1.0",
        seed=7,
        created_at=C.iso_now(),
        params={"lag": 3, "tail": 0.1},
    )
    d = dataclasses.asdict(p)
    assert d["seed"] == 7
    assert d["params"] == {"lag": 3, "tail": 0.1}
    p2 = C.Provenance(**d)
    assert p2 == p


def test_fidelity_report_asdict_roundtrip():
    r = C.FidelityReport(
        marginals={"ks": 0.02},
        temporal={"acf_mae": 0.05},
        cross_series={"corr_fro": 0.1},
        tails={"tail_dep": 0.2},
        overall_score=0.92,
        passed=True,
    )
    d = dataclasses.asdict(r)
    assert d["overall_score"] == pytest.approx(0.92)
    assert d["passed"] is True
    assert C.FidelityReport(**d) == r


def test_scorecard_asdict_contains_nested():
    dset = C.SyntheticDataset(
        data=[[1.0, 2.0]],
        provenance=C.Provenance(
            source_id="x",
            generator_name="real",
            generator_version="0.0.0",
            seed=0,
            created_at=C.iso_now(),
        ),
    )
    sc = C.Scorecard(dataset=dset)
    d = dataclasses.asdict(sc)
    assert "dataset" in d and "provenance" in d["dataset"]
    assert d["fidelity"] is None


# ---------------------------------------------------------------------------
# iso_now
# ---------------------------------------------------------------------------


def test_iso_now_parseable():
    ts = C.iso_now()
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Protocol runtime_checkable
# ---------------------------------------------------------------------------


def test_generator_protocol_runtime_checkable():
    class Impl:
        name = "toy"
        version = "0.0.0"

        def fit(self, real):  # noqa: D401
            return None

        def sample(self, n, seed):
            return real  # noqa: F821 — unused, runtime-shape only

    # isinstance checks are allowed because the Protocol is runtime_checkable.
    assert isinstance(Impl(), C.GeneratorProtocol)


def test_generator_protocol_rejects_missing_method():
    class Broken:
        name = "toy"
        version = "0.0.0"

        # no fit / sample

    assert not isinstance(Broken(), C.GeneratorProtocol)


def test_scorecard_protocol_runtime_checkable():
    class Impl:
        def evaluate(self, real, synth):
            return C.FidelityReport()

    assert isinstance(Impl(), C.ScorecardProtocol)


# ---------------------------------------------------------------------------
# Scorecard.passed gate logic
# ---------------------------------------------------------------------------


def _ds():
    return C.SyntheticDataset(
        data=[[0.0]],
        provenance=C.Provenance(
            source_id="x",
            generator_name="real",
            generator_version="0.0.0",
            seed=0,
            created_at=C.iso_now(),
        ),
    )


def test_scorecard_passed_false_when_empty():
    # No reports present -> cannot pass (fail-closed).
    assert C.Scorecard(dataset=_ds()).passed is False


def test_scorecard_passed_requires_all_present_to_pass():
    sc = C.Scorecard(
        dataset=_ds(),
        fidelity=C.FidelityReport(overall_score=0.95, passed=True),
        privacy=C.PrivacyReport(overall_score=0.9, passed=True),
        utility=C.UtilityReport(passed=True),
    )
    assert sc.passed is True


def test_scorecard_passed_false_if_any_fails():
    sc = C.Scorecard(
        dataset=_ds(),
        fidelity=C.FidelityReport(passed=True),
        privacy=C.PrivacyReport(passed=False),
    )
    assert sc.passed is False


def test_scorecard_passed_ignores_missing_reports():
    # Only fidelity present & passing → overall passes.
    sc = C.Scorecard(dataset=_ds(), fidelity=C.FidelityReport(passed=True))
    assert sc.passed is True
