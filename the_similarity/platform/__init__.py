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
- :class:`RunArtifact` — the artifact dataclass (source of truth).
- :class:`RunKind`     — enum of supported run types.
- :func:`write_artifact` / :func:`read_artifact` — canonical on-disk I/O.
- :func:`new_run_id`   — canonical UUID4-hex run identifier.

Stability
---------
`RunArtifact`'s field names and `RunKind`'s values are a stable public API —
the JSON schema in `artifacts_schema.json` is generated to match. Changing
either is a breaking change for downstream consumers (registry DB rows, TS
validators). Extend via additive, optional fields only.
"""
from __future__ import annotations

from the_similarity.platform.artifacts import (
    RunArtifact,
    RunKind,
    new_run_id,
    read_artifact,
    write_artifact,
)

__all__ = [
    "RunArtifact",
    "RunKind",
    "new_run_id",
    "read_artifact",
    "write_artifact",
]
