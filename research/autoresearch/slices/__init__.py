"""Canonical benchmark slice catalogue for autoresearch lanes.

See `catalogue.yaml` for the single source of truth.  See
`obsidian_thesim/concepts/benchmark_slices.md` for the human guide.

Public loader API (`loader.py`):

    load_catalogue()                -> Catalogue
    load_slice(slice_id)            -> SliceSpec
    load_regime(regime_class)       -> list[SliceSpec]
    load_cross_asset_pair(pair_id)  -> tuple[SliceSpec, SliceSpec]

Validator (`validate.py`) is the enforcement entry point used by CI.
"""
from __future__ import annotations

__all__: list[str] = []
