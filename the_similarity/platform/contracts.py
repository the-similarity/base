"""Extended contracts for the platform registry spine.

This module defines the richer record types that extend the original
:class:`~the_similarity.platform.artifacts.RunArtifact` into a full
platform-spine schema covering runs, artifacts, scorecards, scenarios,
and datasets.

Design note
-----------
Agent 1 (parallel task) owns the canonical version of this file with the
full five-pillar extensions. This file is a **stub** so the registry and
its tests can import named types without hard-blocking on the parallel
agent's merge. Reconciliation at merge time:

- Field names are aligned with Agent 1's spec (``RunRecord``,
  ``ArtifactRecord``, ``ScorecardSummary``, ``ScenarioSpec``,
  ``DatasetSpec``, ``Provenance``).
- Enums ``RunKind`` (re-exported with finance/events/nl_ts added),
  ``RunStatus``, and ``ScorecardKind`` are defined here; if Agent 1's
  version lands first, replace this file and the registry's imports
  continue to resolve.

Lifecycle
---------
All dataclasses are mutable on construction so runners can build records
incrementally. Once inserted into the registry they are treated as
append-or-replace (upsert on primary key); no in-place mutation of DB
rows is performed from these objects.

Immutability notes
------------------
- ``Provenance`` is a free-form mapping by design — different surfaces
  attach different fields (copies uses ``source_id``/``generator_name``;
  worlds uses ``scenario_name``; finance may add ``ticker``/``asof``).
- ``RunStatus`` values are lowercase strings so they round-trip through
  JSON without a custom encoder (same pattern as :class:`RunKind`).

JSON safety
-----------
:meth:`to_dict` on each dataclass emits only JSON-primitive values and
nested dicts. The registry persists the nested dicts as TEXT columns
(``*_json``) via ``json.dumps`` — no binary blobs, so the DB remains
inspectable via ``sqlite3 registry.db "select * from runs"``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Single source of truth for the run-kind enum is
# :mod:`the_similarity.platform.artifacts` — it was introduced first and
# is already referenced by RunArtifact rows on disk. We re-export here so
# callers that pull from the contracts module see an identical type.
from the_similarity.platform.artifacts import RunKind


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RunStatus(str, Enum):
    """Lifecycle status for a run.

    ``SUCCEEDED`` is the default for newly-registered rows (matches the
    legacy behavior where registering implied success). ``PENDING`` and
    ``RUNNING`` support streaming registration from long-running
    processes; ``FAILED`` captures runs whose artifact paths point to
    partial outputs but that should NOT be considered ship-ready.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ScorecardKind(str, Enum):
    """Kind tag for a scorecard row.

    One run may produce multiple scorecards of different kinds (e.g. a
    finance run might produce both a ``STATISTICAL`` scorecard and a
    ``FIDELITY`` scorecard). The composite PK ``(run_id, kind)`` means
    each kind appears once per run — re-registering upserts.
    """

    FIDELITY = "fidelity"
    STATISTICAL = "statistical"
    BACKTEST = "backtest"
    CALIBRATION = "calibration"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass
class Provenance:
    """Reproducibility record attached to every run.

    This mirrors Agent 1's extended ``Provenance`` shape: a minimal set
    of required fields plus a free-form ``extra`` mapping for
    surface-specific attributes. The dataclass is intentionally loose
    (all fields optional except ``generator_name``) so that legacy
    RunArtifact rows with dict-shaped provenance remain compatible.
    """

    generator_name: str
    version: Optional[str] = None
    seed: Optional[int] = None
    source_id: Optional[str] = None
    created_at: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    # Catch-all for pillar-specific fields (ticker, asof, scenario_name,
    # etc.) so new callers do not need to wait for a schema bump.
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict. Omits None values for a terser on-disk shape."""
        out: Dict[str, Any] = {"generator_name": self.generator_name}
        if self.version is not None:
            out["version"] = self.version
        if self.seed is not None:
            out["seed"] = self.seed
        if self.source_id is not None:
            out["source_id"] = self.source_id
        if self.created_at is not None:
            out["created_at"] = self.created_at
        if self.params:
            out["params"] = self.params
        if self.extra:
            out["extra"] = self.extra
        return out

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Provenance":
        """Reconstruct from a JSON-decoded dict.

        Unknown keys are folded into ``extra`` so that forward-compatible
        readers do not lose information on round-trip.
        """
        known = {
            "generator_name",
            "version",
            "seed",
            "source_id",
            "created_at",
            "params",
            "extra",
        }
        extra = dict(d.get("extra", {}))
        for key, value in d.items():
            if key not in known:
                extra[key] = value
        return cls(
            generator_name=d.get("generator_name", ""),
            version=d.get("version"),
            seed=d.get("seed"),
            source_id=d.get("source_id"),
            created_at=d.get("created_at"),
            params=dict(d.get("params", {})),
            extra=extra,
        )


# ---------------------------------------------------------------------------
# RunRecord
# ---------------------------------------------------------------------------


@dataclass
class RunRecord:
    """Persistent row for a single run on the platform spine.

    This is the extended analog of :class:`RunArtifact` with two new
    indexed dimensions — ``status`` and ``pillar`` — that downstream
    surfaces (UI filters, eval harness) query on.

    Invariants
    ----------
    - ``run_id`` is the primary key. Must be globally unique across the
      registry; use :func:`derive_run_id` for deterministic IDs in
      reproducibility tests, otherwise ``uuid4().hex``.
    - ``kind`` MUST be a :class:`RunKind` (enum, not string) when the
      record is constructed from Python. The registry converts to/from
      the string form when reading SQL rows.
    - ``status`` defaults to :attr:`RunStatus.SUCCEEDED` so legacy
      callers that register a finished run need not set it explicitly.
    - ``pillar`` is an optional free-form tag (``"finance"``,
      ``"synthetic"``, ``"events"``, ``"3d"``, ``"nl_ts"``) used for
      cross-pillar listing. Distinct from ``kind`` so, e.g., a
      ``SWEEP`` run can still carry ``pillar="finance"``.
    """

    run_id: str
    kind: RunKind
    config: Dict[str, Any]
    seed: Optional[int]
    artifact_paths: Dict[str, str]
    summary: Dict[str, Any]
    provenance: Dict[str, Any]
    created_at: str
    status: RunStatus = RunStatus.SUCCEEDED
    pillar: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict. Enums are emitted as string values."""
        return {
            "run_id": self.run_id,
            "kind": self.kind.value,
            "config": self.config,
            "seed": self.seed,
            "artifact_paths": self.artifact_paths,
            "summary": self.summary,
            "provenance": self.provenance,
            "created_at": self.created_at,
            "status": self.status.value,
            "pillar": self.pillar,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunRecord":
        """Reconstruct from a JSON-decoded dict. Unknown keys ignored."""
        status_raw = d.get("status", RunStatus.SUCCEEDED.value)
        return cls(
            run_id=d["run_id"],
            kind=RunKind(d["kind"]),
            config=d["config"],
            seed=d.get("seed"),
            artifact_paths=d["artifact_paths"],
            summary=d["summary"],
            provenance=d["provenance"],
            created_at=d["created_at"],
            status=RunStatus(status_raw),
            pillar=d.get("pillar"),
        )


# ---------------------------------------------------------------------------
# ArtifactRecord
# ---------------------------------------------------------------------------


@dataclass
class ArtifactRecord:
    """A single artifact file belonging to a run.

    Replaces the old opaque ``artifact_paths`` dict entry with a typed
    row so consumers can query by content type, size, and checksum
    without parsing the parent run's JSON blob.

    Composite PK is ``(run_id, name)``. The name is the logical label
    (``"telemetry"``, ``"scorecard"``, ``"plot"``) and the ``path`` is
    the on-disk location (relative to the run dir so runs remain
    portable when moved).
    """

    run_id: str
    name: str
    path: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "path": self.path,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ArtifactRecord":
        return cls(
            run_id=d["run_id"],
            name=d["name"],
            path=d["path"],
            content_type=d.get("content_type"),
            size_bytes=d.get("size_bytes"),
            checksum=d.get("checksum"),
            created_at=d.get("created_at"),
        )


# ---------------------------------------------------------------------------
# ScorecardSummary
# ---------------------------------------------------------------------------


@dataclass
class ScorecardSummary:
    """Headline scorecard for one (run_id, kind) pair.

    Kept lean on purpose — full scorecard payloads live in the on-disk
    artifact file. This table stores only the indexable headlines
    (overall score, pass/fail flag, thresholds, a small details dict)
    so the UI's sort/filter surface stays SQL-native.
    """

    run_id: str
    kind: ScorecardKind
    overall_score: Optional[float] = None
    passed: Optional[bool] = None
    thresholds: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "kind": self.kind.value,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "thresholds": self.thresholds,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScorecardSummary":
        return cls(
            run_id=d["run_id"],
            kind=ScorecardKind(d["kind"]),
            overall_score=d.get("overall_score"),
            passed=d.get("passed"),
            thresholds=dict(d.get("thresholds", {})),
            details=dict(d.get("details", {})),
        )


# ---------------------------------------------------------------------------
# ScenarioSpec / DatasetSpec
# ---------------------------------------------------------------------------


@dataclass
class ScenarioSpec:
    """Registered scenario — the input side of a WORLDS / SWEEP run.

    Scenarios are addressable independently of runs so that many runs can
    reference the same scenario_id without duplicating the scenario body
    into each run's ``config`` blob. Primary key ``scenario_id``.
    """

    scenario_id: str
    name: str
    version: str
    engine: str
    params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "version": self.version,
            "engine": self.engine,
            "params": self.params,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScenarioSpec":
        return cls(
            scenario_id=d["scenario_id"],
            name=d["name"],
            version=d["version"],
            engine=d["engine"],
            params=dict(d.get("params", {})),
            metadata=dict(d.get("metadata", {})),
        )


@dataclass
class DatasetSpec:
    """Registered dataset — the input side of a FINANCE / EVAL run.

    Stored independently of runs so that many runs share one dataset
    reference. ``checksum`` is intended for content-addressed lookup
    (e.g. blake2b of the parquet file) but is optional.
    """

    dataset_id: str
    name: str
    version: str
    source: str
    schema_uri: Optional[str] = None
    n_rows: Optional[int] = None
    n_columns: Optional[int] = None
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "schema_uri": self.schema_uri,
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetSpec":
        return cls(
            dataset_id=d["dataset_id"],
            name=d["name"],
            version=d["version"],
            source=d["source"],
            schema_uri=d.get("schema_uri"),
            n_rows=d.get("n_rows"),
            n_columns=d.get("n_columns"),
            checksum=d.get("checksum"),
            metadata=dict(d.get("metadata", {})),
        )


__all__ = [
    "ArtifactRecord",
    "DatasetSpec",
    "Provenance",
    "RunKind",
    "RunRecord",
    "RunStatus",
    "ScenarioSpec",
    "ScorecardKind",
    "ScorecardSummary",
]
