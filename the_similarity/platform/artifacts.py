"""Unified run artifact model — one shape for every run on the platform.

Every surface that produces a "run" (synthetic copies generation, worlds
simulation, parameter sweeps, evaluation harness) emits a single
`artifact.json` file that conforms to `RunArtifact`. This is the single
contract stitching the Python engine, the TypeScript worlds runner, the
run registry (SQLite), the HTTP API, and the UI together.

Lifecycle
---------
1. A runner produces outputs on disk (CSV, JSONL, scorecards, plots).
2. The runner builds a `RunArtifact` describing *what was produced* and
   *how to reproduce it*, never the bulk data itself.
3. The runner calls :func:`write_artifact` to materialize
   `<run_dir>/artifact.json`.
4. Downstream consumers (registry, API, harness) read via
   :func:`read_artifact` and never re-derive the shape.

Immutability
------------
`RunArtifact` is a plain dataclass, not frozen, so runners can construct
it incrementally. Once written to disk, it MUST be treated as immutable —
the registry agent keys rows off `run_id` and never rewrites artifacts.
Reissuing a run means producing a new `run_id`, not mutating an existing
artifact.

Field contract (frozen — changing any of these is a breaking change)
--------------------------------------------------------------------
- ``run_id``        — UUID4 hex (no dashes). Primary key in the registry.
- ``kind``          — :class:`RunKind`. Drives dispatch in consumers.
- ``config``        — JSON-serializable dict. The *inputs* to the run
                      (e.g. scenario ID + params, generator name + params).
- ``seed``          — optional int RNG seed. ``None`` for runs where a
                      seed is not meaningful (e.g. eval over a corpus).
- ``artifact_paths``— logical name → path (relative to the run dir).
                      Example: ``{"telemetry": "run.jsonl",
                      "scorecard": "scorecard.json"}``.
                      Paths are relative so runs remain portable when the
                      parent directory is moved or rehosted.
- ``summary``       — small dict of headline numbers safe to index in the
                      UI without loading the bulk artifacts (e.g.
                      ``{"fidelity_score": 0.87, "n_ticks": 2048}``).
- ``provenance``    — reproducibility record. Embeds the existing
                      :class:`the_similarity.synthetic.contracts.Provenance`
                      shape (``source_id``, ``generator_name``,
                      ``generator_version``, ``seed``, ``created_at``,
                      ``params``) for copies runs, OR the worlds-runner
                      provenance shape (``generator_name``, ``version``,
                      ``seed``, ``scenario_name``, ``scenario``,
                      ``params``, ``created_at``) for worlds runs. Stored
                      as a free-form dict so both shapes fit without a
                      union type on the Python side.
- ``created_at``    — ISO-8601 UTC timestamp, seconds precision. Indexed
                      by the registry for recency queries.

JSON safety
-----------
:meth:`RunArtifact.to_dict` emits only JSON-primitive values (enum ->
string, nested dicts left as-is). Callers are responsible for ensuring
nested ``config``, ``summary``, and ``provenance`` dicts contain only
JSON-serializable values — we do *not* run a coercion pass so that
non-serializable values fail loudly at ``json.dumps`` rather than
silently being converted.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# RunKind
# ---------------------------------------------------------------------------


class RunKind(str, Enum):
    """The four kinds of run the platform recognizes.

    Values are lowercase strings so they round-trip through JSON without a
    custom encoder. Inheriting from ``str`` makes ``RunKind.COPIES ==
    "copies"`` true, which keeps consumers that read raw JSON (TS worlds
    side, jq queries) symmetric with the Python API.

    Members
    -------
    COPIES:
        A synthetic-copies generation run — produced by
        ``the_similarity.synthetic``.
    WORLDS:
        A headless worlds simulation run — produced by the TS worlds
        runner (``the-similarity-fractal/src/sim/headless``).
    SWEEP:
        A parameter sweep — one parent run that spawns many child runs
        of kind COPIES/WORLDS/EVAL. The child `run_id`s are referenced
        from the parent's ``artifact_paths`` / ``summary``.
    EVAL:
        An evaluation-harness run — scores one or more existing runs
        (by `run_id`) and emits a scorecard artifact.
    """

    COPIES = "copies"
    WORLDS = "worlds"
    SWEEP = "sweep"
    EVAL = "eval"


# ---------------------------------------------------------------------------
# RunArtifact
# ---------------------------------------------------------------------------


@dataclass
class RunArtifact:
    """Canonical on-disk record describing a single run.

    See module docstring for the field contract. This dataclass is the
    source of truth — the JSON schema shipped alongside
    (`artifacts_schema.json`) is hand-written to match, and the TS
    worlds side validates against that schema without importing Python.
    """

    run_id: str
    kind: RunKind
    config: Dict[str, Any]
    seed: Optional[int]
    artifact_paths: Dict[str, str]
    summary: Dict[str, Any]
    provenance: Dict[str, Any]
    created_at: str

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-safe dict.

        The enum ``kind`` serializes to its string value; every other
        field passes through unchanged. Nested dicts are NOT copied —
        callers that mutate the returned dict will mutate the source
        artifact's dicts too. This is intentional: artifacts are treated
        as immutable once written, so copying would be wasted work in
        the common case.
        """
        return {
            "run_id": self.run_id,
            "kind": self.kind.value,
            "config": self.config,
            "seed": self.seed,
            "artifact_paths": self.artifact_paths,
            "summary": self.summary,
            "provenance": self.provenance,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunArtifact":
        """Reconstruct a :class:`RunArtifact` from a JSON-decoded dict.

        Unknown keys are ignored (forward compatibility — a newer writer
        may add fields that an older reader does not know about). Missing
        required keys raise ``KeyError`` at access time; we do not
        validate here because the JSON schema is the validation surface.
        """
        return cls(
            run_id=d["run_id"],
            kind=RunKind(d["kind"]),
            config=d["config"],
            seed=d.get("seed"),
            artifact_paths=d["artifact_paths"],
            summary=d["summary"],
            provenance=d["provenance"],
            created_at=d["created_at"],
        )


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------


ARTIFACT_FILENAME = "artifact.json"
"""Canonical filename for the unified artifact inside every run directory."""


def write_artifact(run_dir: Path | str, artifact: RunArtifact) -> Path:
    """Write ``artifact`` to ``<run_dir>/artifact.json`` (pretty-printed).

    Creates ``run_dir`` if it does not exist. The file is written with
    2-space indentation and a trailing newline so it diffs cleanly in git
    and is easy to read in a terminal.

    Parameters
    ----------
    run_dir:
        Directory to write into. May be a :class:`pathlib.Path` or a
        string path. Created (with parents) if missing.
    artifact:
        The :class:`RunArtifact` to serialize.

    Returns
    -------
    Path
        Absolute path of the written ``artifact.json``.
    """
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    out = run_path / ARTIFACT_FILENAME
    # Write pretty-printed so the file is inspectable by a human without
    # jq/tooling. `sort_keys=False` because field order in `to_dict` is
    # the canonical display order (matches the schema).
    out.write_text(
        json.dumps(artifact.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return out


def read_artifact(path: Path | str) -> RunArtifact:
    """Load a :class:`RunArtifact` from ``artifact.json`` on disk.

    ``path`` may be the directory containing ``artifact.json`` or the
    file itself — we detect which. This keeps callers terse regardless
    of whether they hold a run-dir handle or a direct file path.
    """
    p = Path(path)
    if p.is_dir():
        p = p / ARTIFACT_FILENAME
    data = json.loads(p.read_text(encoding="utf-8"))
    return RunArtifact.from_dict(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def new_run_id() -> str:
    """Return a new run identifier — UUID4 hex (no dashes, 32 chars).

    Hex form (rather than the dash-separated canonical UUID form) keeps
    `run_id` safe to use unquoted in file paths, URLs, and SQL LIKE
    expressions without escaping.
    """
    return uuid.uuid4().hex


def iso_now() -> str:
    """Canonical ISO-8601 UTC timestamp for ``RunArtifact.created_at``.

    Seconds precision so values sort lexicographically and round-trip
    through JSON cleanly. Mirrors
    :func:`the_similarity.synthetic.contracts.iso_now` — duplicated here
    so this module is importable without pulling in the synthetic
    package's numpy/pandas dependencies.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "ARTIFACT_FILENAME",
    "RunArtifact",
    "RunKind",
    "iso_now",
    "new_run_id",
    "read_artifact",
    "write_artifact",
]
