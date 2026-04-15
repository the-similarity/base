"""Tests for research.autoresearch.slices.loader.

Covers the three public entry points (``load_slice``, ``load_regime``,
``load_cross_asset_pair``), their error modes, and the ``load_many``
convenience.  Each test either hits the REAL repo catalogue (happy
paths that should always resolve) or writes a synthetic catalogue to
``tmp_path`` for isolation.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from research.autoresearch.slices import loader as L
from research.autoresearch.slices import validate as V


# ---------------------------------------------------------------------------
# Synthetic catalogue fixture — mirrors test_validate.py so the two test
# suites stay in lock-step on schema expectations.
# ---------------------------------------------------------------------------

_BASE_CATALOGUE = {
    "version": 1,
    "schema_revision": 1,
    "data_root_default": "the-similarity-data/data",
    "regime_classes": ["calm", "crisis", "trend", "mean_reverting"],
    "asset_classes": ["equity_index", "equity_single", "crypto"],
    "slices": [
        {
            "id": "synth-calm-1",
            "asset": "spy",
            "asset_class": "equity_index",
            "dataset_path": "stocks/spy/1d.parquet",
            "timeframe": "1d",
            "start": "2015-01-02",
            "end": "2015-12-31",
            "regime_class": "calm",
            "description": "synthetic calm",
            "missing_data": True,
        },
        {
            "id": "synth-crisis-1",
            "asset": "btc_usdt",
            "asset_class": "crypto",
            "dataset_path": "crypto/btc_usdt/1d.parquet",
            "timeframe": "1d",
            "start": "2020-02-19",
            "end": "2020-06-30",
            "regime_class": "crisis",
            "description": "synthetic crisis",
            "missing_data": True,
            # Intentionally odd extra key to prove extras pass-through.
            "custom_vol_multiplier": 1.7,
        },
    ],
}


@pytest.fixture()
def tmp_catalogue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a synthetic catalogue + regime + pair files and point the
    validator module at them.  Yields the ``slices/`` directory so tests
    can inspect / mutate it directly."""
    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "regimes").mkdir()
    (slices_dir / "cross_asset").mkdir()

    (slices_dir / "catalogue.yaml").write_text(yaml.safe_dump(_BASE_CATALOGUE))
    (slices_dir / "regimes" / "calm.yaml").write_text(
        yaml.safe_dump({"regime_class": "calm", "slice_ids": ["synth-calm-1"]})
    )
    (slices_dir / "regimes" / "crisis.yaml").write_text(
        yaml.safe_dump({"regime_class": "crisis", "slice_ids": ["synth-crisis-1"]})
    )

    # Pair file referencing both synthetic slices (they don't overlap in
    # date but that's the validator's problem, not the loader's).
    (slices_dir / "cross_asset" / "synth-pair.yaml").write_text(yaml.safe_dump({
        "pair_id": "synth-pair-1",
        "description": "synthetic pair for loader tests",
        "regime_class": "crisis",
        "left": "synth-calm-1",
        "right": "synth-crisis-1",
        "join_rule": "intersection",
        "notes": "no-op",
        "custom_field": "preserved-in-extras",
    }))

    monkeypatch.setattr(V, "CATALOGUE_PATH", slices_dir / "catalogue.yaml")
    monkeypatch.setattr(V, "REGIMES_DIR", slices_dir / "regimes")
    monkeypatch.setattr(V, "CROSS_ASSET_DIR", slices_dir / "cross_asset")
    return slices_dir


# ---------------------------------------------------------------------------
# load_slice
# ---------------------------------------------------------------------------

def test_load_slice_happy_path_real_catalogue():
    """An ID known to be in the real catalogue resolves with the right
    regime class.  Protects against accidental rename / delete of a
    LEGACY 1A slice — those IDs are append-only."""
    spec = L.load_slice("spy-covid-2020")
    assert spec.id == "spy-covid-2020"
    assert spec.regime_class == "crisis"
    assert spec.asset == "spy"
    assert spec.start_date == "2019-06-01"
    assert spec.end_date == "2020-12-31"


def test_load_slice_synthetic_catalogue(tmp_catalogue):
    spec = L.load_slice("synth-calm-1")
    assert spec.id == "synth-calm-1"
    assert spec.missing_data is True
    assert spec.regime_class == "calm"


def test_load_slice_unknown_id_raises_keyerror(tmp_catalogue):
    with pytest.raises(KeyError) as exc_info:
        L.load_slice("nope")
    # Error message must list known IDs to help the human fix the typo.
    assert "synth-calm-1" in str(exc_info.value)


def test_load_slice_exposes_extras(tmp_catalogue):
    """Extra YAML keys not on the dataclass surface are preserved in extras."""
    spec = L.load_slice("synth-crisis-1")
    assert spec.extras.get("custom_vol_multiplier") == 1.7


def test_load_slice_field_rename_start_to_start_date(tmp_catalogue):
    """Catalogue YAML uses ``start`` / ``end``; loader surfaces them as
    ``start_date`` / ``end_date`` to match pandas-style kwargs used by
    bench lanes."""
    spec = L.load_slice("synth-calm-1")
    assert spec.start_date == "2015-01-02"
    assert spec.end_date == "2015-12-31"


# ---------------------------------------------------------------------------
# load_regime
# ---------------------------------------------------------------------------

def test_load_regime_returns_all_slices_under_bucket(tmp_catalogue):
    specs = L.load_regime("calm")
    assert [s.id for s in specs] == ["synth-calm-1"]
    assert specs[0].regime_class == "calm"


def test_load_regime_preserves_file_order(tmp_catalogue):
    """When the regime YAML lists multiple slice IDs, the order is preserved."""
    # Add a second calm slice.
    data = dict(_BASE_CATALOGUE)
    data["slices"] = _BASE_CATALOGUE["slices"] + [{
        "id": "synth-calm-2",
        "asset": "aapl",
        "asset_class": "equity_single",
        "dataset_path": "stocks/aapl/1d.parquet",
        "timeframe": "1d",
        "start": "2016-01-02",
        "end": "2016-06-30",
        "regime_class": "calm",
        "description": "second calm",
        "missing_data": True,
    }]
    (tmp_catalogue / "catalogue.yaml").write_text(yaml.safe_dump(data))
    (tmp_catalogue / "regimes" / "calm.yaml").write_text(yaml.safe_dump({
        "regime_class": "calm",
        "slice_ids": ["synth-calm-2", "synth-calm-1"],  # reversed on purpose
    }))
    specs = L.load_regime("calm")
    assert [s.id for s in specs] == ["synth-calm-2", "synth-calm-1"]


def test_load_regime_unknown_enum_raises_valueerror(tmp_catalogue):
    with pytest.raises(ValueError):
        L.load_regime("chaotic")


def test_load_regime_missing_yaml_raises_filenotfound(tmp_catalogue):
    # Declare "trend" in the catalogue enum without a matching YAML file.
    # We simulate by deleting a regime YAML that the catalogue enum lists.
    (tmp_catalogue / "regimes" / "calm.yaml").unlink()
    with pytest.raises(FileNotFoundError):
        L.load_regime("calm")


def test_load_regime_real_catalogue_all_four_buckets_nonempty():
    """Every declared regime class in the real catalogue must have at
    least one slice.  Empty buckets mean the curator forgot to populate
    the file, which would silently skip that regime in every bench."""
    cat = V.load_catalogue()
    for regime in cat.regime_classes:
        specs = L.load_regime(regime)
        assert specs, f"regime '{regime}' has no slices — populate its YAML"


# ---------------------------------------------------------------------------
# load_cross_asset_pair
# ---------------------------------------------------------------------------

def test_load_pair_resolves_legs_to_specs(tmp_catalogue):
    pair = L.load_cross_asset_pair("synth-pair-1")
    assert pair.pair_id == "synth-pair-1"
    assert pair.left.id == "synth-calm-1"
    assert pair.right.id == "synth-crisis-1"
    assert pair.join_rule == "intersection"


def test_load_pair_exposes_extras(tmp_catalogue):
    pair = L.load_cross_asset_pair("synth-pair-1")
    assert pair.extras.get("custom_field") == "preserved-in-extras"


def test_load_pair_unknown_id_raises_keyerror(tmp_catalogue):
    with pytest.raises(KeyError):
        L.load_cross_asset_pair("not-a-pair")


def test_load_pair_real_catalogue_pairs():
    """All pair files in the repo must resolve cleanly."""
    for pid in (
        "spy-vs-nvda-covid",
        "btc-vs-eth-crypto-winter-2022",
        "spy-vs-btc-covid-rally",
    ):
        pair = L.load_cross_asset_pair(pid)
        assert pair.pair_id == pid
        assert pair.left.id
        assert pair.right.id


# ---------------------------------------------------------------------------
# load_many
# ---------------------------------------------------------------------------

def test_load_many_preserves_order(tmp_catalogue):
    specs = L.load_many(["synth-crisis-1", "synth-calm-1"])
    assert [s.id for s in specs] == ["synth-crisis-1", "synth-calm-1"]


def test_load_many_reuses_single_catalogue_parse(tmp_catalogue, monkeypatch):
    """Passing a preloaded catalogue must short-circuit disk reads.  We
    prove this by counting calls to ``V.load_catalogue`` — load_many
    with a catalogue argument should call it zero times."""
    cat = V.load_catalogue()
    call_count = {"n": 0}
    real = V.load_catalogue

    def _spy(path=None):
        call_count["n"] += 1
        return real(path)

    monkeypatch.setattr(V, "load_catalogue", _spy)
    L.load_many(["synth-calm-1", "synth-crisis-1"], catalogue=cat)
    assert call_count["n"] == 0


def test_load_many_unknown_id_raises(tmp_catalogue):
    with pytest.raises(KeyError):
        L.load_many(["synth-calm-1", "does-not-exist"])
