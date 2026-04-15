"""Tests for research.autoresearch.slices.validate.

These tests exercise the structural invariants the validator enforces.
Each test builds a synthetic catalogue in a temp directory rather than
using the repo catalogue, so the tests remain authoritative even as the
real catalogue grows.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest
import yaml

from research.autoresearch.slices import validate as V


# ---------------------------------------------------------------------------
# Fixture — build a minimal valid catalogue on disk for each test.
# Tests that want to provoke a violation copy this dict and mutate one
# field before re-dumping it.
# ---------------------------------------------------------------------------

_BASE_CATALOGUE = {
    "version": 1,
    "schema_revision": 1,
    "data_root_default": "the-similarity-data/data",
    "regime_classes": ["calm", "crisis", "trend", "mean_reverting"],
    "asset_classes": ["equity_index", "equity_single", "crypto"],
    "slices": [
        {
            "id": "test-calm-1",
            "asset": "spy",
            "asset_class": "equity_index",
            "dataset_path": "stocks/spy/1d.parquet",
            "timeframe": "1d",
            "start": "2015-01-02",
            "end": "2015-12-31",
            "regime_class": "calm",
            "description": "test calm",
            "missing_data": True,  # skip disk check
        },
        {
            "id": "test-crisis-1",
            "asset": "spy",
            "asset_class": "equity_index",
            "dataset_path": "stocks/spy/1d.parquet",
            "timeframe": "1d",
            "start": "2020-02-19",
            "end": "2020-04-30",
            "regime_class": "crisis",
            "description": "test crisis",
            "missing_data": True,
        },
    ],
}


@pytest.fixture()
def tmp_catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Write ``_BASE_CATALOGUE`` to a temp dir and point the validator at it."""
    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "regimes").mkdir()
    (slices_dir / "cross_asset").mkdir()

    cat_path = slices_dir / "catalogue.yaml"
    cat_path.write_text(yaml.safe_dump(_BASE_CATALOGUE))

    # Minimal regime files matching the two catalogue entries.
    (slices_dir / "regimes" / "calm.yaml").write_text(
        yaml.safe_dump({"regime_class": "calm", "slice_ids": ["test-calm-1"]})
    )
    (slices_dir / "regimes" / "crisis.yaml").write_text(
        yaml.safe_dump({"regime_class": "crisis", "slice_ids": ["test-crisis-1"]})
    )

    # Redirect the validator's module-level paths to the temp tree so
    # the tests run in isolation from the real catalogue.
    monkeypatch.setattr(V, "CATALOGUE_PATH", cat_path)
    monkeypatch.setattr(V, "REGIMES_DIR", slices_dir / "regimes")
    monkeypatch.setattr(V, "CROSS_ASSET_DIR", slices_dir / "cross_asset")
    return slices_dir


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_minimal_catalogue_passes(tmp_catalogue):
    """A catalogue that respects all invariants yields zero violations."""
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert violations == []


def test_real_catalogue_passes_without_data_check():
    """The live repo catalogue must always pass structural invariants.

    Data-file existence is intentionally gated off because parquet files
    are outside the git repo.
    """
    violations = V.run_all_validators(check_data_files=False)
    assert violations == [], f"real catalogue has violations: {violations}"


# ---------------------------------------------------------------------------
# Invariant 1 — duplicate IDs
# ---------------------------------------------------------------------------

def test_duplicate_slice_id_is_violation(tmp_catalogue):
    cat = V.load_catalogue()
    # Inject a duplicate by appending a second copy of test-calm-1.
    dup = dict(_BASE_CATALOGUE)
    dup["slices"] = _BASE_CATALOGUE["slices"] + [
        dict(_BASE_CATALOGUE["slices"][0])
    ]
    (tmp_catalogue / "catalogue.yaml").write_text(yaml.safe_dump(dup))
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("duplicate slice id 'test-calm-1'" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 2/3 — dates
# ---------------------------------------------------------------------------

def test_start_after_end_is_violation(tmp_catalogue):
    data = dict(_BASE_CATALOGUE)
    data["slices"] = [dict(_BASE_CATALOGUE["slices"][0])]
    data["slices"][0]["start"] = "2021-01-01"
    data["slices"][0]["end"] = "2020-01-01"
    (tmp_catalogue / "catalogue.yaml").write_text(yaml.safe_dump(data))
    # Also trim the regime file to only the surviving slice.
    (tmp_catalogue / "regimes" / "crisis.yaml").write_text(
        yaml.safe_dump({"regime_class": "crisis", "slice_ids": []})
    )
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("must be strictly <" in v for v in violations)


def test_future_end_date_is_violation(tmp_catalogue):
    data = dict(_BASE_CATALOGUE)
    data["slices"] = [dict(_BASE_CATALOGUE["slices"][0])]
    data["slices"][0]["end"] = "2099-12-31"
    (tmp_catalogue / "catalogue.yaml").write_text(yaml.safe_dump(data))
    (tmp_catalogue / "regimes" / "crisis.yaml").write_text(
        yaml.safe_dump({"regime_class": "crisis", "slice_ids": []})
    )
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("is after today" in v for v in violations)


def test_non_iso_date_is_violation(tmp_catalogue):
    data = dict(_BASE_CATALOGUE)
    data["slices"] = [dict(_BASE_CATALOGUE["slices"][0])]
    data["slices"][0]["start"] = "01/02/2015"  # US-format, invalid for fromisoformat
    (tmp_catalogue / "catalogue.yaml").write_text(yaml.safe_dump(data))
    (tmp_catalogue / "regimes" / "crisis.yaml").write_text(
        yaml.safe_dump({"regime_class": "crisis", "slice_ids": []})
    )
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("not ISO YYYY-MM-DD" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 4 — regime enum
# ---------------------------------------------------------------------------

def test_unknown_regime_class_is_violation(tmp_catalogue):
    data = dict(_BASE_CATALOGUE)
    data["slices"] = [dict(_BASE_CATALOGUE["slices"][0])]
    data["slices"][0]["regime_class"] = "chaotic"
    (tmp_catalogue / "catalogue.yaml").write_text(yaml.safe_dump(data))
    (tmp_catalogue / "regimes" / "crisis.yaml").write_text(
        yaml.safe_dump({"regime_class": "crisis", "slice_ids": []})
    )
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("regime_class 'chaotic'" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 6 — regime files must agree with catalogue
# ---------------------------------------------------------------------------

def test_regime_file_with_missing_slice_id_is_violation(tmp_catalogue):
    (tmp_catalogue / "regimes" / "calm.yaml").write_text(
        yaml.safe_dump({"regime_class": "calm", "slice_ids": ["does-not-exist"]})
    )
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("not in catalogue" in v for v in violations)


def test_regime_file_with_mismatched_class_is_violation(tmp_catalogue):
    # calm.yaml lists test-crisis-1 whose regime_class is 'crisis' — mismatch.
    (tmp_catalogue / "regimes" / "calm.yaml").write_text(
        yaml.safe_dump({"regime_class": "calm", "slice_ids": ["test-crisis-1"]})
    )
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("file expects 'calm'" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 7 — cross-asset pair files
# ---------------------------------------------------------------------------

def test_pair_with_unknown_leg_is_violation(tmp_catalogue):
    (tmp_catalogue / "cross_asset" / "pair.yaml").write_text(yaml.safe_dump({
        "pair_id": "pair-1",
        "left": "test-calm-1",
        "right": "ghost-slice",
        "join_rule": "intersection",
    }))
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("right 'ghost-slice' not in catalogue" in v for v in violations)


def test_pair_with_bad_join_rule_is_violation(tmp_catalogue):
    (tmp_catalogue / "cross_asset" / "pair.yaml").write_text(yaml.safe_dump({
        "pair_id": "pair-1",
        "left": "test-calm-1",
        "right": "test-crisis-1",
        "join_rule": "mystery_join",
    }))
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("join_rule 'mystery_join'" in v for v in violations)


def test_pair_with_no_date_overlap_is_violation(tmp_catalogue):
    # test-calm-1 is 2015, test-crisis-1 is 2020 — they have no overlap.
    (tmp_catalogue / "cross_asset" / "pair.yaml").write_text(yaml.safe_dump({
        "pair_id": "pair-1",
        "left": "test-calm-1",
        "right": "test-crisis-1",
        "join_rule": "intersection",
    }))
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("no date overlap" in v for v in violations)


def test_duplicate_pair_id_is_violation(tmp_catalogue):
    (tmp_catalogue / "cross_asset" / "pair-a.yaml").write_text(yaml.safe_dump({
        "pair_id": "pair-x",
        "left": "test-calm-1",
        "right": "test-calm-1",  # same leg twice is allowed by validator (overlap ok)
        "join_rule": "intersection",
    }))
    (tmp_catalogue / "cross_asset" / "pair-b.yaml").write_text(yaml.safe_dump({
        "pair_id": "pair-x",
        "left": "test-calm-1",
        "right": "test-calm-1",
        "join_rule": "intersection",
    }))
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("duplicate pair_id 'pair-x'" in v for v in violations)


# ---------------------------------------------------------------------------
# Invariant 5 — dataset_path existence (opt-in)
# ---------------------------------------------------------------------------

def test_check_data_files_skips_missing_data_entries(tmp_catalogue, tmp_path):
    # Even with check_data_files=True, missing_data entries don't violate.
    # Since all test entries are missing_data=True, no violations expected.
    violations = V.run_all_validators(
        today=_dt.date(2026, 4, 14),
        data_root=tmp_path / "no-such-dir",
        check_data_files=True,
    )
    assert violations == []


def test_check_data_files_flags_nonexistent_paths(tmp_catalogue, tmp_path):
    # Drop missing_data flags so the existence check actually runs.
    data = dict(_BASE_CATALOGUE)
    data["slices"] = [
        {**dict(_BASE_CATALOGUE["slices"][0]), "missing_data": False}
    ]
    (tmp_catalogue / "catalogue.yaml").write_text(yaml.safe_dump(data))
    (tmp_catalogue / "regimes" / "crisis.yaml").write_text(
        yaml.safe_dump({"regime_class": "crisis", "slice_ids": []})
    )
    violations = V.run_all_validators(
        today=_dt.date(2026, 4, 14),
        data_root=tmp_path / "no-such-dir",
        check_data_files=True,
    )
    assert any("dataset_path does not exist" in v for v in violations)


# ---------------------------------------------------------------------------
# Deprecated-status guardrail
# ---------------------------------------------------------------------------

def test_deprecated_without_successor_is_violation(tmp_catalogue):
    data = dict(_BASE_CATALOGUE)
    data["slices"] = [
        {**dict(_BASE_CATALOGUE["slices"][0]), "status": "deprecated"}
    ]
    (tmp_catalogue / "catalogue.yaml").write_text(yaml.safe_dump(data))
    (tmp_catalogue / "regimes" / "crisis.yaml").write_text(
        yaml.safe_dump({"regime_class": "crisis", "slice_ids": []})
    )
    violations = V.run_all_validators(today=_dt.date(2026, 4, 14))
    assert any("requires successor_id" in v for v in violations)
