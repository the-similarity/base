"""Customer-facing platform registry routes — mounts at ``/platform/*``.

Purpose
-------
Expose the platform's run registry (the backbone of the Ops Layer — see
``the_similarity/platform/registry.py``) through the public
customer-facing API at :mod:`app.main`. This router is a *thin wrapper*
around :class:`~the_similarity.platform.registry.RunRegistry` — every
endpoint delegates to registry methods for CRUD, filtering, and
pagination. No raw SQL is executed in this module.

Endpoints (all prefixed ``/platform`` by mount in ``app/main.py``)
------------------------------------------------------------------
- ``GET  /platform/healthz``                              — registry liveness.
- ``GET  /platform/runs``                                 — list runs w/ filters.
- ``GET  /platform/runs/{run_id}``                        — full run record.
- ``POST /platform/runs``                                 — register a run.
- ``GET  /platform/runs/{run_id}/artifacts``              — list artifact rows.
- ``POST /platform/runs/{run_id}/artifacts``              — register artifact.
- ``GET  /platform/runs/{run_id}/artifacts/{name}``       — artifact metadata.
- ``GET  /platform/runs/{run_id}/scorecards``             — scorecard summaries.
- ``POST /platform/runs/{run_id}/scorecards``             — register scorecard.
- ``GET  /platform/scenarios`` / ``/{id}``                — list / fetch scenarios.
- ``POST /platform/scenarios``                            — register scenario.
- ``GET  /platform/datasets`` / ``/{id}``                 — list / fetch datasets.
- ``POST /platform/datasets``                             — register dataset.

Design invariants
-----------------
1. **Thin over the registry** — no business logic in the handler. Every
   endpoint boils down to (validate -> registry call -> shape). Runner
   execution lives in the standalone platform API at
   ``the_similarity/platform/api/routes.py``; this router is read/write
   ONLY over already-computed records.
2. **Fail-closed 404** — missing runs/artifacts/scenarios/datasets ALWAYS
   return HTTP 404 with a JSON body of the form ``{"detail": "..."}``.
   Never mask a missing record as an empty list on a singular GET.
3. **409 on duplicate PK** — POSTing an id that already exists returns 409.
   The platform `RunRegistry.register()` is an *upsert* by design
   (partial-then-enriched workflow), so we guard duplicates at the router
   layer using explicit pre-flight `get()` calls. This is not the same as
   the registry's semantics — the router's POST represents *creation*.
4. **Per-request registry dependency** — the FastAPI dependency opens a
   fresh SQLite connection per request. SQLite WAL mode makes this cheap
   and thread-safe across parallel workers. Tests override the dependency
   to point at a tmp-path DB.

Registry delegation
-------------------
All storage operations delegate to :class:`RunRegistry` methods
(``register_run``, ``list_runs``, ``get_run``, ``register_artifact``,
``list_artifacts``, ``get_artifact``, ``register_scorecard``,
``get_scorecards``, ``register_scenario``, ``list_scenarios``,
``get_scenario``, ``register_dataset``, ``list_datasets``,
``get_dataset``). The registry owns the SQLite schema, WAL mode,
indexes, and cascade deletes — this module never touches ``_conn``
directly.

The Pydantic models here are the public wire contract. Adapter functions
(``_artifact_record_to_wire``, ``_wire_to_artifact_record``, etc.)
translate between wire shapes and the registry's contract dataclasses
at the boundary.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.settings import resolve_registry_db
from the_similarity.platform.artifacts import RunArtifact, RunKind
from the_similarity.platform.contracts import (
    ArtifactRecord,
    DatasetSpec,
    RunRecord,
    RunStatus,
    ScenarioSpec,
    ScorecardKind,
    ScorecardSummary,
)
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Router — ``/platform`` prefix applied at mount time in app/main.py so tests
# can exercise this router against a custom prefix if they ever need to.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/platform", tags=["platform"])


# ---------------------------------------------------------------------------
# Pydantic wire models
#
# Every model mirrors the field list we expect Agent 1's
# ``the_similarity.platform.contracts`` module to expose. ``ConfigDict(
# use_enum_values=True)`` on :class:`RunRecordModel` ensures ``kind``
# round-trips as the lowercase string form (matches ``RunArtifact``).
# ---------------------------------------------------------------------------


class RunRecordModel(BaseModel):
    """Wire shape for a platform run row.

    Mirrors :class:`the_similarity.platform.artifacts.RunArtifact` with two
    additional fields (``pillar``, ``status``) that Agent 1's ``RunRecord``
    dataclass adds on top of the existing artifact. Defaults are chosen so
    existing :class:`RunArtifact` values round-trip without the new fields:

    - ``pillar`` defaults to ``None`` — will be populated post-landing by
      runs that know their product pillar (finance, synthetic-data,
      world-events, etc.).
    - ``status`` defaults to ``"complete"`` — the current registry only
      stores finished runs, so any existing row is by definition complete.
    """

    model_config = ConfigDict(use_enum_values=True)

    run_id: str = Field(
        ..., description="UUID4 hex (no dashes). Primary key in the registry."
    )
    kind: RunKind = Field(
        ..., description="Run kind — one of copies, worlds, sweep, eval."
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Run inputs (generator name + params, scenario, etc.).",
    )
    seed: Optional[int] = Field(
        None,
        description="RNG seed. None when a seed is not meaningful for this kind.",
    )
    artifact_paths: Dict[str, str] = Field(
        default_factory=dict,
        description="Logical artifact name -> relative path inside the run dir.",
    )
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Headline numbers safe to index without loading bulk data.",
    )
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="Reproducibility record (generator, version, seed, scenario...).",
    )
    created_at: str = Field(
        ..., description="ISO-8601 UTC timestamp, seconds precision."
    )
    # -- Agent-1 extensions --------------------------------------------------
    pillar: Optional[str] = Field(
        None,
        description=(
            "Product pillar — finance / synthetic-data / three-d / "
            "world-events / nl-ts. Stored in ``provenance`` for back-compat."
        ),
    )
    status: str = Field(
        "complete",
        description=(
            "Run lifecycle state: 'pending', 'running', 'complete', 'failed'. "
            "Stored in ``provenance`` for back-compat."
        ),
    )

    @classmethod
    def from_artifact(cls, artifact: RunArtifact) -> "RunRecordModel":
        """Build from an existing :class:`RunArtifact` (old records)."""
        prov = artifact.provenance or {}
        return cls(
            run_id=artifact.run_id,
            kind=artifact.kind,
            config=artifact.config,
            seed=artifact.seed,
            artifact_paths=artifact.artifact_paths,
            summary=artifact.summary,
            provenance=prov,
            created_at=artifact.created_at,
            # Extension fields are stored inside provenance as flat keys so
            # the underlying artifact.json stays backward-compatible.
            pillar=prov.get("pillar"),
            status=prov.get("status", "complete"),
        )

    @classmethod
    def from_run_record(cls, record: "RunRecord") -> "RunRecordModel":
        """Build from a :class:`RunRecord` (the registry's canonical row).

        Maps the registry's ``RunStatus`` enum values back to the API's
        wire values. The registry stores ``"succeeded"`` where the API
        wire contract uses ``"complete"`` — translate at the boundary.
        """
        # Registry status -> wire status mapping.
        _db_to_wire_status = {"succeeded": "complete"}
        wire_status = _db_to_wire_status.get(record.status.value, record.status.value)

        return cls(
            run_id=record.run_id,
            kind=record.kind,
            config=record.config,
            seed=record.seed,
            artifact_paths=record.artifact_paths,
            summary=record.summary,
            provenance=record.provenance,
            created_at=record.created_at,
            pillar=record.pillar,
            status=wire_status,
        )

    def to_run_record(self) -> "RunRecord":
        """Project this wire model to a :class:`RunRecord` for registry storage.

        Maps the wire ``status`` values back to the registry's
        ``RunStatus`` enum. The wire uses ``"complete"`` where the
        registry stores ``"succeeded"``.
        """
        # Wire status -> registry status mapping.
        _wire_to_db_status = {"complete": "succeeded"}
        db_status_str = _wire_to_db_status.get(self.status, self.status)

        return RunRecord(
            run_id=self.run_id,
            kind=RunKind(self.kind) if not isinstance(self.kind, RunKind) else self.kind,
            config=self.config,
            seed=self.seed,
            status=RunStatus(db_status_str),
            summary=self.summary,
            created_at=self.created_at,
            pillar=self.pillar or "unknown",
            artifact_paths=self.artifact_paths,
            provenance=self.provenance,
        )

    def to_artifact(self) -> RunArtifact:
        """Project this record down to the existing :class:`RunArtifact` shape.

        The extension fields (``pillar``, ``status``) are injected into
        ``provenance`` so they survive the registry's JSON round-trip
        without requiring a schema migration. Agent 2's registry extension
        will later promote them to first-class columns.
        """
        prov = dict(self.provenance or {})
        if self.pillar is not None:
            prov["pillar"] = self.pillar
        prov["status"] = self.status
        return RunArtifact(
            run_id=self.run_id,
            kind=RunKind(self.kind) if not isinstance(self.kind, RunKind) else self.kind,
            config=self.config,
            seed=self.seed,
            artifact_paths=self.artifact_paths,
            summary=self.summary,
            provenance=prov,
            created_at=self.created_at,
        )


class RunRecordCreate(BaseModel):
    """POST /platform/runs body.

    Subset of :class:`RunRecordModel` where most fields default so simple
    callers can register a minimal run without wiring every provenance
    field. ``run_id`` is mandatory — the platform's run identity is
    owned by the producing surface (runner, CLI, or upstream service),
    not the API gateway.
    """

    model_config = ConfigDict(use_enum_values=True)

    run_id: str
    kind: RunKind
    config: Dict[str, Any] = Field(default_factory=dict)
    seed: Optional[int] = None
    artifact_paths: Dict[str, str] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp. Clients must supply to keep "
        "ordering deterministic — we do not clock-stamp server-side.",
    )
    pillar: Optional[str] = None
    status: str = "complete"


class RunCreateResponse(BaseModel):
    """POST /platform/runs return shape — ``{run_id}`` per spec."""

    run_id: str


class ArtifactRecordModel(BaseModel):
    """Metadata row for a single logical artifact inside a run.

    Mirrors Agent 1's ``ArtifactRecord`` dataclass. Distinct from the
    ``artifact_paths`` dict on :class:`RunRecordModel`: each row here
    describes ONE named artifact in detail (size, content type, checksum),
    whereas ``artifact_paths`` is a compact name->path lookup for the
    UI. Runs with many artifacts emit N :class:`ArtifactRecordModel` rows.
    """

    run_id: str = Field(..., description="Parent run_id.")
    name: str = Field(..., description="Logical artifact name (e.g. 'scorecard').")
    path: str = Field(..., description="Relative path inside the run dir.")
    content_type: Optional[str] = Field(
        None, description="MIME type — 'application/json', 'text/csv', etc."
    )
    size_bytes: Optional[int] = Field(
        None, ge=0, description="File size in bytes, if measurable."
    )
    sha256: Optional[str] = Field(
        None, description="Optional SHA-256 hex digest for integrity checks."
    )
    created_at: str = Field(..., description="ISO-8601 UTC creation timestamp.")


class ScorecardSummaryModel(BaseModel):
    """Scorecard readout for a run — mirrors Agent 1's ``ScorecardSummary``.

    Decoupled from :class:`RunRecordModel.summary` because a single run may
    carry multiple scorecards (fidelity, privacy, utility, or evaluation
    scorecards from different harnesses). Each row is one scorecard.
    """

    run_id: str = Field(..., description="Parent run_id.")
    name: str = Field(
        ...,
        description="Scorecard name — 'fidelity', 'privacy', 'utility', etc.",
    )
    passed: Optional[bool] = Field(
        None, description="Gate decision if the scorecard emits one."
    )
    overall_score: Optional[float] = Field(
        None, description="Aggregate score in [0, 1] (higher is better)."
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metric-name -> value map, free-form per scorecard kind.",
    )
    created_at: str = Field(..., description="ISO-8601 UTC creation timestamp.")


class ScenarioSpecModel(BaseModel):
    """Platform scenario definition — mirrors Agent 1's ``ScenarioSpec``.

    A scenario is the reproducible input to a worlds/sweep run. Two runs
    with the same scenario_id are expected to be comparable.
    """

    scenario_id: str = Field(..., description="Primary key. Stable across runs.")
    name: str = Field(..., description="Human-readable display name.")
    description: Optional[str] = None
    pillar: Optional[str] = Field(
        None, description="Product pillar this scenario belongs to."
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Scenario inputs (seed grid, bounds, etc.)."
    )
    created_at: str = Field(..., description="ISO-8601 UTC creation timestamp.")


class DatasetSpecModel(BaseModel):
    """Registered dataset — mirrors Agent 1's ``DatasetSpec``.

    A :class:`DatasetSpec` describes a corpus available to the platform
    (path, schema, version). Runs reference datasets by ``dataset_id``
    in their config to keep runs reproducible across pipeline changes.
    """

    # ``populate_by_name=True`` lets construction accept either the python
    # attribute name (``schema_``) or the wire alias (``schema``).
    # ``ser_by_alias``-aware responses are handled by FastAPI's default
    # ``response_model`` serializer which uses by_alias on emit.
    #
    # Naming note: the wire contract uses ``schema`` (per Agent 1's spec)
    # but ``schema`` collides with Pydantic v1's deprecated ``.schema()``
    # method and triggers Pydantic v2 schema-build warnings on generic
    # container attributes. We sidestep that by handling the alias at the
    # serializer boundary (see :func:`_dataset_to_wire` /
    # :func:`_dataset_from_wire`) rather than via ``Field(alias=...)``.
    model_config = ConfigDict()

    dataset_id: str = Field(..., description="Primary key. Stable across refreshes.")
    name: str = Field(..., description="Human-readable display name.")
    description: Optional[str] = None
    path: Optional[str] = Field(
        None, description="Absolute or repo-relative path to the data source."
    )
    # Stored on the python attr as ``columns`` to avoid the ``schema``
    # collision. The wire boundary translates to/from the ``schema`` key.
    columns: Dict[str, Any] = Field(
        default_factory=dict,
        description="Columns / dtypes / constraints as a free-form dict. "
        "Wire key is 'schema' — translated at the router boundary.",
    )
    version: Optional[str] = None
    created_at: str = Field(..., description="ISO-8601 UTC creation timestamp.")


class HealthzResponse(BaseModel):
    """GET /platform/healthz payload.

    Independent of the main ``/health`` endpoint — this one round-trips
    through the registry so a 200 guarantees the SQLite DB is readable.
    """

    status: str = Field(..., description="Always 'ok' when the registry is reachable.")


# ---------------------------------------------------------------------------
# Registry dependency
# ---------------------------------------------------------------------------


def get_registry() -> Iterator[RunRegistry]:
    """FastAPI dependency yielding a per-request :class:`RunRegistry`.

    Fresh connection per request — the underlying ``sqlite3.Connection``
    is not thread-safe, and FastAPI may dispatch requests across worker
    threads, so sharing a module-level connection would be a latent bug.
    WAL mode keeps the cost negligible.

    The registry's ``__init__`` creates all tables (runs, artifacts,
    scorecards, scenarios, datasets) via idempotent DDL, so no
    companion-table setup is needed here.

    Tests override with ``app.dependency_overrides[get_registry]`` to pin
    a tmp-path DB so the production default is never touched.
    """
    registry = RunRegistry(resolve_registry_db())
    try:
        yield registry
    finally:
        registry.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_run(registry: RunRegistry, run_id: str) -> RunRecord:
    """Fetch a run or raise 404 with a JSON detail body.

    Centralized so every handler that parents on ``run_id`` emits an
    identical error shape. The detail string always includes the offending
    id — valuable debugging signal that does not leak internal state.
    """
    record = registry.get_run(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"run_id not found: {run_id}",
        )
    return record


# ---------------------------------------------------------------------------
# /platform/healthz
# ---------------------------------------------------------------------------


@router.get("/healthz", response_model=HealthzResponse)
def healthz(registry: RunRegistry = Depends(get_registry)) -> HealthzResponse:
    """Registry-backed liveness probe.

    A 200 guarantees:
    1. SQLite file exists and is reachable.
    2. The ``runs`` table exists (created during registry init).
    3. A single ``SELECT`` succeeds — confirms the DB is not corrupt.

    If any of those fail the dependency or this query raises and FastAPI
    emits 500. That *is* the intended signal — a broken registry is not
    live, and we do not want orchestrators to treat us as healthy.
    """
    # Cheapest round-trip that still exercises the schema. ``limit=1`` is
    # ignored by the query planner on an empty table and bounded at 1 on
    # a populated one — constant time either way.
    registry.list(limit=1)
    return HealthzResponse(status="ok")


# ---------------------------------------------------------------------------
# /platform/runs — list + create
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=List[RunRecordModel])
def list_runs(
    kind: Optional[RunKind] = Query(None, description="Filter by run kind."),
    pillar: Optional[str] = Query(None, description="Filter by product pillar."),
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by run status ('pending', 'running', 'complete', 'failed').",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Max rows (default 50, max 200).",
    ),
    offset: int = Query(0, ge=0, description="Row offset for pagination."),
    registry: RunRegistry = Depends(get_registry),
) -> List[RunRecordModel]:
    """Newest-first listing of runs with optional filters.

    The underlying :meth:`RunRegistry.list_runs` supports ``kind``,
    ``pillar``, ``status``, ``limit``, and ``offset`` natively at the
    SQL layer, so filtering and pagination are pushed down to the DB.
    """
    # Map the wire ``status`` string to the ``RunStatus`` enum so the
    # registry can filter at the SQL level. The wire uses "complete" while
    # the registry uses "succeeded" — translate at the boundary.
    db_status: Optional[str] = None
    if status_filter is not None:
        # Wire -> registry status mapping. The API wire contract uses
        # "complete" while the registry stores "succeeded". Map at the
        # boundary so callers keep using the documented wire values.
        _wire_to_db_status = {"complete": "succeeded"}
        db_status = _wire_to_db_status.get(status_filter, status_filter)

    records = registry.list_runs(
        kind=kind,
        pillar=pillar,
        status=db_status,
        limit=limit,
        offset=offset,
    )
    return [RunRecordModel.from_run_record(r) for r in records]


@router.post(
    "/runs",
    response_model=RunCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "run_id already exists."},
    },
)
def create_run(
    body: RunRecordCreate,
    registry: RunRegistry = Depends(get_registry),
) -> RunCreateResponse:
    """Register a new run record.

    Distinct from :meth:`RunRegistry.register_run`'s upsert semantics — this
    endpoint treats an existing ``run_id`` as a 409 conflict because POST
    is the *creation* verb. Updates to an existing run are out of MVP
    scope; Agent 2's extension will expose a PUT/PATCH when needed.
    """
    if registry.get_run(body.run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run_id already exists: {body.run_id}",
        )

    # Build a wire model then project to the RunRecord contract for the
    # registry. The RunRecord carries pillar/status as first-class columns.
    wire_model = RunRecordModel(**body.model_dump(by_alias=True))
    registry.register_run(wire_model.to_run_record())
    return RunCreateResponse(run_id=body.run_id)


@router.get(
    "/runs/{run_id}",
    response_model=RunRecordModel,
    responses={404: {"description": "run_id not found."}},
)
def get_run(
    run_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> RunRecordModel:
    """Full run record by id. 404 if unknown."""
    return RunRecordModel.from_run_record(_require_run(registry, run_id))


# ---------------------------------------------------------------------------
# Wire <-> contract adapters for artifacts and scorecards
#
# The registry's contract types have slightly different field names from the
# API wire models. These adapters translate at the boundary so:
# - The wire shape (API contract) stays frozen for external consumers.
# - The registry contract types (internal) are the single source of truth.
# ---------------------------------------------------------------------------


def _artifact_record_to_wire(rec: ArtifactRecord) -> ArtifactRecordModel:
    """Convert a registry :class:`ArtifactRecord` to the API wire model.

    Field mapping: ``checksum`` (registry) -> ``sha256`` (wire).
    ``content_type`` may be ``None`` in the wire model but is required
    by the contract — we pass it through unchanged.
    """
    return ArtifactRecordModel(
        run_id=rec.run_id,
        name=rec.name,
        path=rec.path,
        content_type=rec.content_type,
        size_bytes=rec.size_bytes,
        sha256=rec.checksum,
        created_at=rec.created_at or "",
    )


def _wire_to_artifact_record(model: ArtifactRecordModel) -> ArtifactRecord:
    """Convert an API wire model to a registry :class:`ArtifactRecord`.

    Field mapping: ``sha256`` (wire) -> ``checksum`` (registry).
    """
    return ArtifactRecord(
        run_id=model.run_id,
        name=model.name,
        path=model.path,
        content_type=model.content_type or "",
        created_at=model.created_at,
        size_bytes=model.size_bytes,
        checksum=model.sha256,
    )


def _scorecard_to_wire(sc: ScorecardSummary) -> ScorecardSummaryModel:
    """Convert a registry :class:`ScorecardSummary` to the API wire model.

    Field mapping: ``kind`` (ScorecardKind enum) -> ``name`` (string),
    ``details`` -> ``metrics``. The ``thresholds`` field from the contract
    is not exposed on the wire model; ``created_at`` is not stored in the
    registry's scorecard table so we emit an empty string.
    """
    return ScorecardSummaryModel(
        run_id=sc.run_id,
        name=sc.kind.value,
        passed=sc.passed,
        overall_score=sc.overall_score,
        metrics=sc.details,
        created_at="",  # Registry scorecard table does not store created_at.
    )


def _wire_to_scorecard(model: ScorecardSummaryModel) -> ScorecardSummary:
    """Convert an API wire model to a registry :class:`ScorecardSummary`.

    Field mapping: ``name`` (string) -> ``kind`` (ScorecardKind enum),
    ``metrics`` -> ``details``.
    """
    return ScorecardSummary(
        run_id=model.run_id,
        kind=ScorecardKind(model.name),
        overall_score=model.overall_score,
        passed=model.passed,
        details=model.metrics,
    )


def _scenario_to_wire(spec: ScenarioSpec) -> ScenarioSpecModel:
    """Convert a registry :class:`ScenarioSpec` to the API wire model.

    The registry's scenario contract has ``version``, ``engine``,
    ``params``, ``metadata`` while the wire model has ``description``,
    ``pillar``, ``parameters``, ``created_at``. We map via metadata:

    - ``description`` <- ``metadata.get("description")``
    - ``pillar`` <- ``metadata.get("pillar")``
    - ``parameters`` <- ``params``
    - ``created_at`` <- ``metadata.get("created_at", "")``
    """
    return ScenarioSpecModel(
        scenario_id=spec.scenario_id,
        name=spec.name,
        description=spec.metadata.get("description"),
        pillar=spec.metadata.get("pillar"),
        parameters=spec.params,
        created_at=spec.metadata.get("created_at", ""),
    )


def _wire_to_scenario(model: ScenarioSpecModel) -> ScenarioSpec:
    """Convert an API wire model to a registry :class:`ScenarioSpec`.

    Stores wire-only fields (``description``, ``pillar``, ``created_at``)
    inside the contract's ``metadata`` dict so they survive the round-trip.
    """
    metadata: Dict[str, Any] = {}
    if model.description is not None:
        metadata["description"] = model.description
    if model.pillar is not None:
        metadata["pillar"] = model.pillar
    if model.created_at:
        metadata["created_at"] = model.created_at
    return ScenarioSpec(
        scenario_id=model.scenario_id,
        name=model.name,
        version="",  # Wire model does not carry version.
        engine="",  # Wire model does not carry engine.
        params=model.parameters,
        metadata=metadata,
    )


def _dataset_spec_to_wire(spec: DatasetSpec) -> DatasetSpecModel:
    """Convert a registry :class:`DatasetSpec` to the API wire model.

    Field mapping:
    - ``source`` -> ``path`` (wire model field)
    - ``metadata.get("description")`` -> ``description``
    - ``metadata`` carries extra fields for round-trip.
    - ``columns`` <- ``metadata.get("columns", {})``
    """
    return DatasetSpecModel(
        dataset_id=spec.dataset_id,
        name=spec.name,
        description=spec.metadata.get("description"),
        path=spec.source,
        columns=spec.metadata.get("columns", {}),
        version=spec.version,
        created_at=spec.metadata.get("created_at", ""),
    )


def _wire_to_dataset_spec(model: DatasetSpecModel) -> DatasetSpec:
    """Convert an API wire model to a registry :class:`DatasetSpec`.

    Stores wire-only fields (``description``, ``columns``, ``created_at``)
    inside the contract's ``metadata`` dict so they survive the round-trip.
    """
    metadata: Dict[str, Any] = {}
    if model.description is not None:
        metadata["description"] = model.description
    if model.columns:
        metadata["columns"] = model.columns
    if model.created_at:
        metadata["created_at"] = model.created_at
    return DatasetSpec(
        dataset_id=model.dataset_id,
        name=model.name,
        version=model.version or "",
        source=model.path or "",
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# /platform/runs/{run_id}/artifacts
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/artifacts",
    response_model=List[ArtifactRecordModel],
    responses={404: {"description": "run_id not found."}},
)
def list_artifacts(
    run_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> List[ArtifactRecordModel]:
    """List every artifact row registered for ``run_id``.

    Returns an empty list (not 404) when the run exists but has no
    artifact rows — empty is a valid state for a freshly registered run.
    The 404 branch fires only when the parent run itself is missing.
    """
    _require_run(registry, run_id)
    records = registry.list_artifacts(run_id)
    return [_artifact_record_to_wire(rec) for rec in records]


@router.post(
    "/runs/{run_id}/artifacts",
    response_model=ArtifactRecordModel,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "run_id not found."},
        409: {"description": "(run_id, name) pair already registered."},
    },
)
def create_artifact(
    run_id: str,
    body: ArtifactRecordModel,
    registry: RunRegistry = Depends(get_registry),
) -> ArtifactRecordModel:
    """Register an artifact row for ``run_id``.

    Guards:
    1. Body's ``run_id`` must match the URL's ``run_id`` — mismatches are
       422 via FastAPI validation below (check runs before insert).
    2. The parent run must exist.
    3. ``(run_id, name)`` is the composite PK — duplicate insert is 409.
    """
    if body.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"body.run_id={body.run_id!r} does not match URL run_id={run_id!r}",
        )
    _require_run(registry, run_id)

    # Check for duplicates — the registry uses upsert semantics but the
    # router's POST represents *creation*, so we guard duplicates here.
    if registry.get_artifact(run_id, body.name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"artifact already exists: run_id={run_id}, name={body.name}",
        )
    registry.register_artifact(_wire_to_artifact_record(body))
    return body


@router.get(
    "/runs/{run_id}/artifacts/{name}",
    response_model=ArtifactRecordModel,
    responses={404: {"description": "run_id or artifact name missing."}},
)
def get_artifact(
    run_id: str,
    name: str,
    registry: RunRegistry = Depends(get_registry),
) -> ArtifactRecordModel:
    """Return the metadata row for a single named artifact.

    This endpoint does NOT stream bytes — the existing platform API at
    ``the_similarity/platform/api/routes.py::get_run_artifact`` covers
    that path. Here we return only the registry row for UI consumers
    (sidebar listings, hash verification workflows).
    """
    _require_run(registry, run_id)
    rec = registry.get_artifact(run_id, name)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact not found: run_id={run_id}, name={name}",
        )
    return _artifact_record_to_wire(rec)


# ---------------------------------------------------------------------------
# /platform/runs/{run_id}/scorecards
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/scorecards",
    response_model=List[ScorecardSummaryModel],
    responses={404: {"description": "run_id not found."}},
)
def list_scorecards(
    run_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> List[ScorecardSummaryModel]:
    """Every scorecard summary row registered for ``run_id``."""
    _require_run(registry, run_id)
    summaries = registry.get_scorecards(run_id)
    return [_scorecard_to_wire(sc) for sc in summaries]


@router.post(
    "/runs/{run_id}/scorecards",
    response_model=ScorecardSummaryModel,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "run_id not found."},
        409: {"description": "(run_id, name) pair already registered."},
    },
)
def create_scorecard(
    run_id: str,
    body: ScorecardSummaryModel,
    registry: RunRegistry = Depends(get_registry),
) -> ScorecardSummaryModel:
    """Register a scorecard summary under ``run_id``."""
    if body.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"body.run_id={body.run_id!r} does not match URL run_id={run_id!r}",
        )
    _require_run(registry, run_id)

    # Check for duplicates — the registry uses upsert semantics but the
    # router's POST represents *creation*, so we guard duplicates here.
    existing = registry.get_scorecards(run_id)
    if any(sc.kind.value == body.name for sc in existing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"scorecard already exists: run_id={run_id}, name={body.name}",
        )
    registry.register_scorecard(_wire_to_scorecard(body))
    return body


# ---------------------------------------------------------------------------
# /platform/scenarios
# ---------------------------------------------------------------------------


@router.get("/scenarios", response_model=List[ScenarioSpecModel])
def list_scenarios(
    pillar: Optional[str] = Query(None, description="Filter by product pillar."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    registry: RunRegistry = Depends(get_registry),
) -> List[ScenarioSpecModel]:
    """List scenarios newest-first with optional pillar filter.

    The registry's :meth:`list_scenarios` returns all scenarios ordered
    by name. We convert to wire models and apply pillar filtering +
    pagination in Python. This is acceptable at the current scale
    (hundreds of scenarios, not millions).
    """
    all_specs = registry.list_scenarios()
    wire_models = [_scenario_to_wire(s) for s in all_specs]

    # Apply pillar filter if requested.
    if pillar is not None:
        wire_models = [m for m in wire_models if m.pillar == pillar]

    # Sort newest-first by created_at (the registry sorts by name).
    wire_models.sort(key=lambda m: m.created_at or "", reverse=True)

    # Apply pagination.
    return wire_models[offset : offset + limit]


@router.post(
    "/scenarios",
    response_model=ScenarioSpecModel,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "scenario_id already exists."}},
)
def create_scenario(
    body: ScenarioSpecModel,
    registry: RunRegistry = Depends(get_registry),
) -> ScenarioSpecModel:
    """Register a new scenario. ``scenario_id`` must be globally unique."""
    # Check for duplicates — the registry uses upsert semantics but the
    # router's POST represents *creation*.
    if registry.get_scenario(body.scenario_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"scenario_id already exists: {body.scenario_id}",
        )
    registry.register_scenario(_wire_to_scenario(body))
    return body


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioSpecModel,
    responses={404: {"description": "scenario_id not found."}},
)
def get_scenario(
    scenario_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> ScenarioSpecModel:
    """Fetch a single scenario by id."""
    spec = registry.get_scenario(scenario_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scenario_id not found: {scenario_id}",
        )
    return _scenario_to_wire(spec)


# ---------------------------------------------------------------------------
# /platform/datasets
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Dataset wire translation
#
# The external spec uses ``schema`` as the JSON key for the columns/dtypes
# dict, but ``schema`` collides with Pydantic v1's ``BaseModel.schema()``
# method and triggers v2 schema-build warnings on Dict-typed aliased
# fields. We translate at the boundary:
#   - Incoming: accept both ``schema`` (canonical wire) and ``columns``
#     (python-native form).
#   - Outgoing: always emit ``schema`` so API consumers match the spec.
#
# The companion SQLite column is ``schema_json`` regardless — the DB is an
# implementation detail, not the public contract.
# ---------------------------------------------------------------------------


def _dataset_from_wire(raw: Dict[str, Any]) -> DatasetSpecModel:
    """Build a DatasetSpecModel from a wire dict, accepting 'schema' alias."""
    normalized = dict(raw)  # shallow copy — do not mutate caller's dict
    if "schema" in normalized and "columns" not in normalized:
        normalized["columns"] = normalized.pop("schema")
    return DatasetSpecModel.model_validate(normalized)


def _dataset_to_wire(model: DatasetSpecModel) -> Dict[str, Any]:
    """Serialize to the wire shape with the canonical 'schema' key."""
    payload = model.model_dump()
    payload["schema"] = payload.pop("columns", {})
    return payload


@router.get("/datasets", response_model=List[Dict[str, Any]])
def list_datasets(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    registry: RunRegistry = Depends(get_registry),
) -> List[Dict[str, Any]]:
    """List datasets newest-first — response uses the 'schema' wire key.

    The registry's :meth:`list_datasets` returns all datasets ordered
    by name. We convert to wire models and apply pagination in Python,
    sorting newest-first by created_at.
    """
    all_specs = registry.list_datasets()
    wire_models = [_dataset_spec_to_wire(s) for s in all_specs]

    # Sort newest-first by created_at.
    wire_models.sort(key=lambda m: m.created_at or "", reverse=True)

    # Apply pagination.
    paginated = wire_models[offset : offset + limit]
    return [_dataset_to_wire(m) for m in paginated]


@router.post(
    "/datasets",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "dataset_id already exists."}},
)
def create_dataset(
    body: Dict[str, Any],
    registry: RunRegistry = Depends(get_registry),
) -> Dict[str, Any]:
    """Register a new dataset. ``dataset_id`` must be globally unique.

    Accepts a raw dict (not a Pydantic model on the request) so the wire
    alias (``schema``) bypasses Pydantic's alias warnings entirely.
    Validation runs via :func:`_dataset_from_wire` which goes through the
    Pydantic model — errors surface as FastAPI validation errors.
    """
    try:
        model = _dataset_from_wire(body)
    except Exception as exc:  # pragma: no cover - pydantic validation
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid dataset body: {exc}",
        ) from exc

    # Check for duplicates — the registry uses upsert semantics but the
    # router's POST represents *creation*.
    if registry.get_dataset(model.dataset_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"dataset_id already exists: {model.dataset_id}",
        )
    registry.register_dataset(_wire_to_dataset_spec(model))
    return _dataset_to_wire(model)


@router.get(
    "/datasets/{dataset_id}",
    response_model=Dict[str, Any],
    responses={404: {"description": "dataset_id not found."}},
)
def get_dataset(
    dataset_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> Dict[str, Any]:
    """Fetch a single dataset by id — response uses the 'schema' wire key."""
    spec = registry.get_dataset(dataset_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"dataset_id not found: {dataset_id}",
        )
    return _dataset_to_wire(_dataset_spec_to_wire(spec))


# ---------------------------------------------------------------------------
# /platform/datasets/{dataset_id}/card
# ---------------------------------------------------------------------------


class DatasetCardModel(BaseModel):
    """Rich dataset card — richer than the raw DatasetSpec.

    Surfaces generation method, scorecard summary, privacy status,
    and file paths in a single response for UI dataset-detail views.
    """

    dataset_id: str
    name: str
    version: str
    source: str
    n_rows: Optional[int] = None
    n_columns: Optional[int] = None
    checksum: Optional[str] = None
    source_run_id: Optional[str] = None
    generation_method: str = "unknown"
    scorecard_summary: Dict[str, Any] = Field(default_factory=dict)
    privacy_status: str = "unknown"
    file_paths: Dict[str, str] = Field(default_factory=dict)
    promoted: bool = False


@router.get(
    "/datasets/{dataset_id}/card",
    response_model=DatasetCardModel,
    responses={404: {"description": "dataset_id not found."}},
)
def get_dataset_card(
    dataset_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> DatasetCardModel:
    """Return a rich dataset card for a registered dataset.

    The card combines the raw :class:`DatasetSpec` fields with scorecard
    summary highlights, privacy status, and file paths extracted from
    the dataset's metadata. This is the endpoint the UI's dataset detail
    view should hit — it provides everything needed for a single-request
    render without client-side joins.

    Falls back to a basic card (no scorecard/privacy info) for datasets
    that were registered without metadata (e.g. non-synthetic datasets).
    """
    try:
        from the_similarity.synthetic.catalog import (
            get_dataset_card as _get_card,
        )

        card = _get_card(dataset_id, registry)
        return DatasetCardModel(**card)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"dataset_id not found: {dataset_id}",
        )
    except ImportError:
        # If the catalog module is not available, fall back to a basic card
        # built from the raw dataset row via the registry.
        spec = registry.get_dataset(dataset_id)
        if spec is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"dataset_id not found: {dataset_id}",
            )
        return DatasetCardModel(
            dataset_id=spec.dataset_id,
            name=spec.name,
            version=spec.version or "",
            source=spec.source or "",
        )


# ---------------------------------------------------------------------------
# /platform/scenarios/{scenario_id}/runs — list world runs for a scenario
# ---------------------------------------------------------------------------


@router.get(
    "/scenarios/{scenario_id}/runs",
    response_model=List[RunRecordModel],
    responses={404: {"description": "scenario_id not found."}},
)
def list_scenario_runs(
    scenario_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    registry: RunRegistry = Depends(get_registry),
) -> List[RunRecordModel]:
    """List all world runs associated with a given scenario.

    Filters runs by ``kind=worlds`` and checks that
    ``config["scenario_name"]`` matches the ``scenario_id``. The
    scenario must exist in the scenarios table — returns 404 otherwise.

    Implementation note: the filtering is done in Python after fetching
    all worlds runs, which is acceptable at the current scale (hundreds
    of runs, not millions). A dedicated SQL join would be premature
    until the table grows.
    """
    # Verify the scenario exists.
    if registry.get_scenario(scenario_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scenario_id not found: {scenario_id}",
        )

    # Fetch all worlds runs and filter by scenario_name in config.
    records = registry.list_runs(kind=RunKind.WORLDS, limit=1000)
    matched = [
        RunRecordModel.from_run_record(r)
        for r in records
        if r.config.get("scenario_name") == scenario_id
    ]
    return matched[offset : offset + limit]


# ---------------------------------------------------------------------------
# /platform/worlds/run — trigger a world run (PLACEHOLDER)
# ---------------------------------------------------------------------------


class WorldRunRequest(BaseModel):
    """POST /platform/worlds/run request body."""

    scenario_id: str = Field(..., description="Scenario to run.")
    seed: Optional[int] = Field(None, description="RNG seed override.")
    steps: Optional[int] = Field(None, description="Number of simulation steps.")


class WorldRunResponse(BaseModel):
    """POST /platform/worlds/run response — stub until shelling out is wired."""

    run_id: Optional[str] = Field(None, description="Run ID if execution succeeded.")
    status: str = Field(..., description="'placeholder' until headless runner is wired.")
    message: str = Field(..., description="Human-readable status message.")


@router.post(
    "/worlds/run",
    response_model=WorldRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"description": "scenario_id not found."}},
)
def trigger_world_run(
    body: WorldRunRequest,
    registry: RunRegistry = Depends(get_registry),
) -> WorldRunResponse:
    """Trigger a headless world run for a scenario.

    **PLACEHOLDER** — accepts the request parameters and validates the
    scenario exists, but does not actually shell out to the headless
    runner yet. Returns a 202 Accepted with a stub response indicating
    the endpoint is not yet wired to execution.

    When fully implemented, this will:
    1. Resolve the scenario params from the registry.
    2. Shell out to ``node src/sim/headless/runner.js --scenario <path>
       --seed <seed> --steps <steps>``.
    3. Register the resulting telemetry via the worlds adapter.
    4. Return the ``run_id`` of the registered run.
    """
    # Validate that the scenario exists.
    if registry.get_scenario(body.scenario_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scenario_id not found: {body.scenario_id}",
        )

    # PLACEHOLDER: return a stub response indicating the endpoint is
    # not yet wired to the headless runner.
    return WorldRunResponse(
        run_id=None,
        status="placeholder",
        message=(
            f"World run for scenario '{body.scenario_id}' accepted but "
            f"execution is not yet wired. Seed={body.seed}, steps={body.steps}."
        ),
    )


__all__ = [
    "ArtifactRecordModel",
    "DatasetCardModel",
    "DatasetSpecModel",
    "HealthzResponse",
    "RunCreateResponse",
    "RunRecordCreate",
    "RunRecordModel",
    "ScenarioSpecModel",
    "ScorecardSummaryModel",
    "WorldRunRequest",
    "WorldRunResponse",
    "get_registry",
    "router",
]
