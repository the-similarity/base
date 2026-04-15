"""Loader API for the canonical benchmark slice catalogue.

Purpose
-------
Give every bench lane (retrieval_bench, projector-v2, parameter-sweep,
foundation-model bench, etc.) a single, stable way to resolve slice IDs
into usable ``SliceSpec`` descriptors so they never re-inline date
ranges.  Inline date copies are the root cause of the "one lane fixes
a slice, another lane still runs the broken one" class of bugs.

Public API
----------
* ``load_slice(slice_id, *, catalogue=None) -> SliceSpec``
* ``load_regime(regime_class, *, catalogue=None) -> list[SliceSpec]``
* ``load_cross_asset_pair(pair_id, *, catalogue=None) -> CrossAssetPair``

Each returns an in-memory dataclass whose field names are **stable
contract surfaces** — downstream lanes import these types and depend on
the field names.

Invariants
----------
* The catalogue is parsed once per call (cheap — <0.1ms for the ~25-slice
  catalogue).  Callers that resolve many IDs should pass a pre-loaded
  ``catalogue=`` argument to avoid re-parsing.
* ``SliceSpec`` objects are immutable from the loader's point of view —
  mutating them after load is undefined behaviour.
* Unknown slice IDs raise ``KeyError`` (fail-closed); unknown regime
  classes raise ``ValueError`` to distinguish "typo in ID" from "typo in
  enum".
* ``missing_data: true`` entries still resolve; callers decide whether to
  skip them (bench lanes typically synth-fallback).

Module lifecycle
----------------
Stateless.  Safe to call from multiple threads (no global mutation).
Module-level path constants are imported from ``validate`` so the loader
and validator agree on where the YAML lives.
"""
from __future__ import annotations

# Only the standard library + PyYAML (already a transitive dep).  The
# loader must stay dependency-light so it can be imported from CI jobs
# that don't install the full engine.
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import validate as V


# ---------------------------------------------------------------------------
# Public dataclasses — field names are a stable contract.  Renaming any
# field here is a breaking change for every bench lane that imports it.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SliceSpec:
    """Immutable descriptor for a single catalogue slice.

    Consumed by bench lanes to resolve a slice_id into an enterable
    time-series query.  The ``dataset_path`` is relative to the bench
    lane's ``data_root`` — callers join them before reading.

    ``missing_data=True`` means the parquet file under ``dataset_path``
    is NOT expected to exist in the data mount (usually because the
    dataset's catalog start-date post-dates the slice window).  Bench
    lanes treat these as synth-fallback candidates.
    """

    id: str
    asset: str
    asset_class: str
    dataset_path: str
    timeframe: str
    start_date: str
    end_date: str
    regime_class: str
    description: str
    notes: str
    min_bars: int
    missing_data: bool
    status: str
    successor_id: str | None
    source_bench_lane: str
    # Opaque bag of any extra YAML fields so forward-compat additions do
    # not force a SliceSpec schema bump.  Not part of the contract.
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CrossAssetPair:
    """Immutable descriptor for a cross-asset pair.

    ``left`` and ``right`` are fully-resolved ``SliceSpec`` objects (not
    IDs), so callers can feed them straight into a retriever without a
    second lookup.
    """

    pair_id: str
    description: str
    regime_class: str
    left: SliceSpec
    right: SliceSpec
    join_rule: str
    notes: str
    extras: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _entry_to_spec(entry: V.SliceEntry) -> SliceSpec:
    """Project a parsed ``SliceEntry`` onto the public ``SliceSpec`` surface.

    Done in one place so the validator-side dataclass (``SliceEntry``)
    can evolve without dragging every consumer along.  The extras dict
    gives forward-compat for YAML fields we haven't surfaced yet.
    """
    # Copy the raw YAML dict minus keys we already expose explicitly, so
    # callers that need something exotic (e.g. a per-slice regime-aware
    # widening multiplier) can still pick it up from ``extras``.
    known = {
        "id", "asset", "asset_class", "dataset_path", "timeframe",
        "start", "end", "regime_class", "description", "notes",
        "min_bars", "missing_data", "status", "successor_id",
        "source_bench_lane",
    }
    extras = {k: v for k, v in entry.raw.items() if k not in known}
    return SliceSpec(
        id=entry.id,
        asset=entry.asset,
        asset_class=entry.asset_class,
        dataset_path=entry.dataset_path,
        timeframe=entry.timeframe,
        # Note the rename: catalogue YAML uses start/end (matches the
        # "date window" noun).  Bench lanes historically use
        # start_date/end_date (matches pandas kwargs).  We normalise to
        # the latter at the loader boundary so the bench code does not
        # need adapters.
        start_date=entry.start,
        end_date=entry.end,
        regime_class=entry.regime_class,
        description=entry.description,
        notes=entry.notes,
        min_bars=entry.min_bars,
        missing_data=entry.missing_data,
        status=entry.status,
        successor_id=entry.successor_id,
        source_bench_lane=entry.source_bench_lane,
        extras=extras,
    )


def _ensure_catalogue(catalogue: V.Catalogue | None) -> V.Catalogue:
    """Return the provided catalogue or lazily parse the canonical one."""
    if catalogue is not None:
        return catalogue
    return V.load_catalogue()


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------

def load_slice(
    slice_id: str,
    *,
    catalogue: V.Catalogue | None = None,
) -> SliceSpec:
    """Resolve a single slice ID to its ``SliceSpec``.

    Raises
    ------
    KeyError
        If ``slice_id`` is not present in the catalogue.  Callers should
        treat this as a spec bug (they are referencing a slice that does
        not exist), not as a runtime condition to swallow.
    """
    cat = _ensure_catalogue(catalogue)
    by_id = cat.by_id()
    entry = by_id.get(slice_id)
    if entry is None:
        # Include the set of known IDs truncated to help the human fix
        # the typo quickly.  20 is arbitrary but covers the typical
        # catalogue size without flooding a CI log.
        known = sorted(by_id.keys())
        preview = ", ".join(known[:20])
        more = "" if len(known) <= 20 else f" (+{len(known) - 20} more)"
        raise KeyError(
            f"slice_id '{slice_id}' not in catalogue. "
            f"Known IDs: {preview}{more}"
        )
    return _entry_to_spec(entry)


def load_regime(
    regime_class: str,
    *,
    catalogue: V.Catalogue | None = None,
    regimes_dir: Path | None = None,
) -> list[SliceSpec]:
    """Return every ``SliceSpec`` declared under ``regimes/<class>.yaml``.

    The regime YAML file is the authoritative source — we do NOT just
    filter the catalogue by ``regime_class``.  Reason: the regime files
    let curators exclude a slice from regime-bucket evaluation even if
    it carries the matching class (e.g., dataset-start-limited slices
    that are too short for a regime-level aggregate).

    Raises
    ------
    ValueError
        If ``regime_class`` is not in the catalogue's declared enum.
    FileNotFoundError
        If the regime YAML file is missing despite being enumerated.
    """
    cat = _ensure_catalogue(catalogue)
    if regime_class not in cat.regime_classes:
        raise ValueError(
            f"regime_class '{regime_class}' not in "
            f"catalogue.regime_classes={cat.regime_classes}"
        )

    regimes_dir = regimes_dir if regimes_dir is not None else V.REGIMES_DIR
    path = regimes_dir / f"{regime_class}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"regime file missing: {path}. "
            f"catalogue.regime_classes declares '{regime_class}' but the "
            f"corresponding YAML is not on disk."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    slice_ids = list(data.get("slice_ids", []) or [])
    by_id = cat.by_id()
    specs: list[SliceSpec] = []
    for sid in slice_ids:
        entry = by_id.get(sid)
        if entry is None:
            # Defensive — validator should have caught this, but we'd
            # rather fail-closed at load time than return a partial list.
            raise KeyError(
                f"regime '{regime_class}' lists slice_id '{sid}' that is "
                f"not in the catalogue. Run validate.py and fix the YAML."
            )
        specs.append(_entry_to_spec(entry))
    return specs


def load_cross_asset_pair(
    pair_id: str,
    *,
    catalogue: V.Catalogue | None = None,
    cross_asset_dir: Path | None = None,
) -> CrossAssetPair:
    """Resolve a ``pair_id`` to a fully-populated ``CrossAssetPair``.

    Scans every ``cross_asset/*.yaml`` until the ``pair_id`` matches.
    For the ~handful of pairs in the catalogue this linear scan is
    cheap; if the file count ever crosses ~50 we should add an index
    cache keyed on pair_id.

    Raises
    ------
    KeyError
        If no file declares the given ``pair_id``.
    """
    cat = _ensure_catalogue(catalogue)
    pairs_dir = (
        cross_asset_dir if cross_asset_dir is not None else V.CROSS_ASSET_DIR
    )
    if not pairs_dir.exists():
        raise FileNotFoundError(
            f"cross_asset directory missing: {pairs_dir}"
        )

    seen_ids: list[str] = []
    for yaml_path in sorted(pairs_dir.glob("*.yaml")):
        with yaml_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        pid = data.get("pair_id")
        if not pid:
            continue
        seen_ids.append(pid)
        if pid != pair_id:
            continue

        # Resolve both legs through load_slice so typos / missing IDs
        # raise a meaningful KeyError at load time.
        left = load_slice(data["left"], catalogue=cat)
        right = load_slice(data["right"], catalogue=cat)

        # Strip the keys we surface explicitly; keep everything else in
        # extras for forward-compat (e.g. a future 'vol_scale' field).
        known = {
            "pair_id", "description", "regime_class", "left", "right",
            "join_rule", "notes",
        }
        extras = {k: v for k, v in data.items() if k not in known}
        return CrossAssetPair(
            pair_id=pid,
            description=data.get("description", ""),
            regime_class=data.get("regime_class", ""),
            left=left,
            right=right,
            join_rule=data.get("join_rule", ""),
            notes=data.get("notes", ""),
            extras=extras,
        )

    raise KeyError(
        f"pair_id '{pair_id}' not found in {pairs_dir}. "
        f"Known pair_ids: {sorted(seen_ids)}"
    )


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def load_many(
    slice_ids: list[str],
    *,
    catalogue: V.Catalogue | None = None,
) -> list[SliceSpec]:
    """Resolve a list of slice_ids preserving order.

    Convenience for bench lanes that declare a ``slice_ids: [...]`` list
    in their own spec file; equivalent to ``[load_slice(s) for s in …]``
    but parses the catalogue once.
    """
    cat = _ensure_catalogue(catalogue)
    return [load_slice(sid, catalogue=cat) for sid in slice_ids]
