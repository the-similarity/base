"""Tests for the curated finance feature presets."""

from __future__ import annotations

import pytest

from the_similarity.finance import (
    MACRO_US_CORREIA_2015,
    FeaturePreset,
    MacroVariable,
    get_preset,
    list_presets,
)


def test_correia_preset_has_six_variables() -> None:
    """The Correia 2015 'primary case' is exactly 6 variables.

    Catching a drift here is important: the paper's results (Sharpe 1.27,
    MaxDD -16.7%) are reproducible only with the exact six-variable set.
    Adding a seventh would silently invalidate the citation.
    """
    assert len(MACRO_US_CORREIA_2015.variables) == 6


def test_correia_preset_has_canonical_codes() -> None:
    """Variable codes match the paper's notation, in declared order."""
    assert MACRO_US_CORREIA_2015.codes() == (
        "FED",
        "STY",
        "LTY",
        "TERM",
        "MRP",
        "FX",
    )


def test_correia_preset_window_size_matches_paper() -> None:
    """20 trading days = 1 month, the paper's regime window."""
    assert MACRO_US_CORREIA_2015.window_size == 20


def test_correia_preset_variables_have_transforms() -> None:
    """Every variable documents its standardisation transform.

    Without this, reviewers cannot reproduce results because the analog
    matching distance is computed on transformed (not raw) values.
    """
    for var in MACRO_US_CORREIA_2015.variables:
        assert isinstance(var, MacroVariable)
        assert var.transform, f"{var.code} missing transform"
        assert var.description


def test_list_presets_returns_macro_us() -> None:
    """The Correia preset is registered and discoverable by name."""
    assert "macro_us_correia_2015" in list_presets()


def test_list_presets_is_sorted() -> None:
    """Stable ordering for snapshot tests / CLI output."""
    names = list_presets()
    assert names == sorted(names)


def test_get_preset_round_trip() -> None:
    """get_preset(name) returns the registered FeaturePreset."""
    preset = get_preset("macro_us_correia_2015")
    assert isinstance(preset, FeaturePreset)
    assert preset is MACRO_US_CORREIA_2015


def test_get_preset_unknown_name_lists_alternatives() -> None:
    """KeyError message lists available presets so callers self-correct."""
    with pytest.raises(KeyError, match="macro_us_correia_2015"):
        get_preset("does-not-exist")
