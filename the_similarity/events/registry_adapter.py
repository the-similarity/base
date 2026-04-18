"""Events pillar -> platform registry adapter.

Registers an :class:`~the_similarity.events.contracts.EventSeries` as a
:class:`~the_similarity.platform.artifacts.RunArtifact` with
``kind=RunKind.EVENTS`` in the platform registry.

Why a separate adapter?
-----------------------
Follows the same pattern as ``platform.adapters.copies`` and
``platform.adapters.finance``: the event contracts are decoupled from
the registry so batch pipelines that only need the schema don't pull
in SQLite or the registry module. The adapter bridges the two.

The adapter is idempotent: re-registering the same ``run_id`` upserts
the registry row without side effects.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from the_similarity.events.contracts import EventSeries
from the_similarity.platform.artifacts import (
    RunArtifact,
    RunKind,
    iso_now,
    new_run_id,
)
from the_similarity.platform.registry import RunRegistry


def register_event_series(
    series: EventSeries,
    *,
    registry: Optional[RunRegistry] = None,
    db_path: Optional[str] = None,
    run_id: Optional[str] = None,
    seed: Optional[int] = None,
) -> str:
    """Register an :class:`EventSeries` with the platform registry.

    Creates a :class:`RunArtifact` with ``kind=RunKind.EVENTS`` and
    writes it to the registry. The event data itself is NOT persisted
    by this adapter — callers should use :func:`save_events` to write
    the series to disk first if persistence is needed.

    Parameters
    ----------
    series:
        The event series to register.
    registry:
        Optional pre-opened :class:`RunRegistry`. When ``None``, a
        registry is opened against ``db_path`` (or the default path)
        and closed on exit.
    db_path:
        Optional SQLite path override. Only used when ``registry`` is
        ``None``.
    run_id:
        Optional explicit run ID. Defaults to a fresh UUID4 hex.
    seed:
        Optional RNG seed (rarely meaningful for event ingestion, but
        included for API consistency with other adapters).

    Returns
    -------
    str
        The ``run_id`` written to the registry.
    """
    resolved_id = run_id or new_run_id()

    # Build a summary dict with headline stats for the registry listing.
    # This lets the UI show event count, type distribution, and date range
    # without loading the full event dataset.
    event_types: Dict[str, int] = {}
    timestamps: list[str] = []
    for event in series.events:
        event_types[event.event_type] = event_types.get(event.event_type, 0) + 1
        if event.timestamp:
            timestamps.append(event.timestamp)

    summary: Dict[str, Any] = {
        "pillar": "events",
        "n_events": len(series.events),
        "event_types": event_types,
    }
    if timestamps:
        # Lexicographic sort works for ISO-8601 strings.
        summary["date_range"] = {
            "start": min(timestamps),
            "end": max(timestamps),
        }

    config: Dict[str, Any] = {
        "name": series.name,
        "version": series.version,
    }

    provenance: Dict[str, Any] = dict(series.provenance)
    provenance.setdefault("generator_name", "event_ingestion")
    provenance.setdefault("created_at", iso_now())

    artifact = RunArtifact(
        run_id=resolved_id,
        kind=RunKind.EVENTS,
        config=config,
        seed=seed,
        artifact_paths={},
        summary=summary,
        provenance=provenance,
        created_at=iso_now(),
    )

    if registry is not None:
        return registry.register(artifact)

    # Open a temporary registry connection if none was provided.
    resolved_db: Path
    if db_path is not None:
        resolved_db = Path(db_path).expanduser()
    else:
        env_value = os.environ.get("THE_SIMILARITY_REGISTRY_DB")
        resolved_db = (
            Path(env_value).expanduser()
            if env_value
            else Path("~/.the_similarity/registry.db").expanduser()
        )

    with RunRegistry(resolved_db) as r:
        return r.register(artifact)


__all__ = ["register_event_series"]
