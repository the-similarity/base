"""Platform layer — unified run artifact model and operational surface.

The `platform` package is the *Ops Layer* of the synthetic environment platform.
It exposes a single, cross-language run artifact contract (`RunArtifact`) that
the Python side (synthetic copies, evaluation harness) and the TypeScript side
(worlds runner) both emit. Every run — dataset generation, world simulation,
parameter sweep, or evaluation — writes exactly one `artifact.json` file in
this shape. Downstream surfaces (registry, API, harness, UI) read only this
shape.

Public exports
--------------
Legacy artifact shape (still the on-disk format):

- :class:`RunArtifact` — the artifact dataclass (on-disk source of truth).
- :class:`RunKind`     — enum of supported run types (extended to cover
  the finance/events/nl_ts pillars).
- :func:`write_artifact` / :func:`read_artifact` — canonical on-disk I/O.
- :func:`new_run_id`   — canonical UUID4-hex run identifier.

Unified platform object model (from :mod:`the_similarity.platform.contracts`):

- :class:`RunRecord` — canonical run row (superset of ``RunArtifact``,
  adds ``status`` + ``pillar``). Used by the registry and the API.
- :class:`RunStatus` — run lifecycle state (pending/running/succeeded/failed).
- :class:`ArtifactRecord` — file-level metadata (content type, size,
  checksum) for one artifact belonging to a run.
- :class:`ScorecardSummary` — condensed scorecard row indexed by the UI.
- :class:`ScorecardKind` — fidelity/privacy/utility/controllability/
  calibration/backtest.
- :class:`Provenance` — cross-pillar reproducibility record (adds
  ``env`` to the synthetic shape; backward-compatible loader).
- :class:`ScenarioSpec` — worlds/simulation scenario definition.
- :class:`DatasetSpec` — dataset registration row.

Stability
---------
All exported dataclass field names, enum values, and JSON-schema keys
are a stable public API. The dataclasses in
:mod:`the_similarity.platform.contracts` are additive to — not
replacements for — :class:`RunArtifact`; both shapes co-exist and the
contracts module provides explicit interop helpers
(``RunRecord.from_run_artifact``) so legacy artifact.json files load
cleanly. Changing any existing field is a breaking change for
registry rows, the HTTP API, and TS-side validators.
"""
from __future__ import annotations

from the_similarity.platform.artifacts import (
    RunArtifact,
    RunKind,
    iso_now,
    new_run_id,
    read_artifact,
    write_artifact,
)
from the_similarity.platform.contracts import (
    ArtifactRecord,
    DatasetSpec,
    Provenance,
    RunRecord,
    RunStatus,
    ScenarioSpec,
    ScorecardKind,
    ScorecardSummary,
)
from the_similarity.platform.registry import RunRegistry

__all__ = [
    # Legacy artifact shape
    "RunArtifact",
    "RunKind",
    "RunRegistry",
    "iso_now",
    "new_run_id",
    "read_artifact",
    "write_artifact",
    # Unified platform object model
    "ArtifactRecord",
    "DatasetSpec",
    "Provenance",
    "RunRecord",
    "RunStatus",
    "ScenarioSpec",
    "ScorecardKind",
    "ScorecardSummary",
]
