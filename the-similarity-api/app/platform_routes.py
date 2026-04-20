"""Customer-facing platform registry routes — mounts at ``/platform/*``.

Purpose
-------
Expose the platform's run registry (the backbone of the Ops Layer — see
``the_similarity/platform/registry.py``) through the public
customer-facing API at :mod:`app.main`. This router is a *thin wrapper*
around :class:`~the_similarity.platform.registry.RunRegistry`; every
endpoint delegates to the registry's CRUD methods and maps between wire
Pydantic models and the registry's contract dataclasses.

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
   The platform ``RunRegistry`` is an *upsert* by design
   (partial-then-enriched workflow), so we guard duplicates at the router
   layer using explicit pre-flight ``get*()`` calls. This is not the same
   as the registry's semantics — the router's POST represents *creation*.
4. **Per-request registry dependency** — the FastAPI dependency opens a
   fresh SQLite connection per request. SQLite WAL mode makes this cheap
   and thread-safe across parallel workers. Tests override the dependency
   to point at a tmp-path DB.
5. **Registry is the single source of truth** — all table DDL, indexes,
   WAL mode, and cascade deletes are owned by
   :class:`~the_similarity.platform.registry.RunRegistry`. This router
   never issues raw SQL or creates companion tables.
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

    def to_artifact(self) -> RunArtifact:
        """Project this record down to the existing :class:`RunArtifact` shape.

        The extension fields (``pillar``, ``status``) are injected into
        ``provenance`` so they survive the registry's JSON round-trip
        without requiring a schema migration.
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
    """Registered dataset — mirrors Agent 1's ``DatasetSpec``."""

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
    """GET /platform/healthz payload."""

    status: str = Field(..., description="Always 'ok' when the registry is reachable.")


# ---------------------------------------------------------------------------
# Wire <-> contract mapping helpers
#
# The registry's contract dataclasses (ArtifactRecord, ScorecardSummary,
# ScenarioSpec, DatasetSpec) use different field names than the wire
# Pydantic models. These helpers translate at the boundary so the router
# never touches raw SQL.
# ---------------------------------------------------------------------------


def _artifact_record_to_wire(rec: ArtifactRecord) -> ArtifactRecordModel:
    """Convert a registry :class:`ArtifactRecord` to the wire model.

    The registry contract uses ``checksum``; the wire model uses ``sha256``.
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
    """Convert a wire :class:`ArtifactRecordModel` to a registry contract."""
    return ArtifactRecord(
        run_id=model.run_id,
        name=model.name,
        path=model.path,
        content_type=model.content_type or "",
        size_bytes=model.size_bytes,
        checksum=model.sha256,
        created_at=model.created_at,
    )


def _scorecard_to_wire(sc: ScorecardSummary) -> ScorecardSummaryModel:
    """Convert a registry :class:`ScorecardSummary` to the wire model.

    The registry contract uses ``kind`` (:class:`ScorecardKind` enum) and
    stores metrics in ``details``; the wire model uses ``name`` (string)
    and ``metrics``. ``thresholds`` from the contract are folded into
    ``metrics`` for the wire response so no data is lost.
    """
    metrics = dict(sc.details or {})
    if sc.thresholds:
        metrics.update(sc.thresholds)
    return ScorecardSummaryModel(
        run_id=sc.run_id,
        name=sc.kind.value,
        passed=sc.passed,
        overall_score=sc.overall_score,
        metrics=metrics,
        # ScorecardSummary contract does not carry created_at; use empty
        # string as a safe default for the wire model's required field.
        created_at="",
    )


def _wire_to_scorecard(model: ScorecardSummaryModel) -> ScorecardSummary:
    """Convert a wire :class:`ScorecardSummaryModel` to a registry contract.

    The wire ``name`` is mapped to the registry ``kind`` (ScorecardKind).
    The wire ``metrics`` dict populates the contract's ``details`` field.
    """
    return ScorecardSummary(
        run_id=model.run_id,
        kind=ScorecardKind(model.name),
        overall_score=model.overall_score,
        passed=model.passed,
        details=model.metrics,
    )


def _scenario_to_wire(spec: ScenarioSpec) -> ScenarioSpecModel:
    """Convert a registry :class:`ScenarioSpec` to the wire model.

    The registry contract stores ``version``, ``engine``, ``params``,
    ``metadata``; the wire model uses ``description``, ``pillar``,
    ``parameters``, ``created_at``. We map metadata fields into the
    wire model's flat structure.
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
    """Convert a wire :class:`ScenarioSpecModel` to a registry contract.

    Stores ``description``, ``pillar``, and ``created_at`` in the
    contract's ``metadata`` dict so they survive the round-trip.
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
        version="1.0",
        engine="unknown",
        params=model.parameters,
        metadata=metadata,
    )


def _dataset_to_wire(spec: DatasetSpec) -> Dict[str, Any]:
    """Convert a registry :class:`DatasetSpec` to the wire dict.

    The wire response uses ``schema`` (not ``columns``) as the key for
    the columns dict.
    """
    return {
        "dataset_id": spec.dataset_id,
        "name": spec.name,
        "description": spec.metadata.get("description"),
        "path": spec.source or spec.metadata.get("path"),
        "schema": spec.metadata.get("columns", {}),
        "version": spec.version,
        "created_at": spec.metadata.get("created_at", ""),
    }


def _wire_to_dataset(body: Dict[str, Any]) -> DatasetSpec:
    """Convert a wire dict to a registry :class:`DatasetSpec`.

    Accepts both ``schema`` and ``columns`` as the key for the columns
    dict. Stores ``description``, ``columns``, and ``created_at`` in the
    contract's ``metadata`` for round-trip fidelity.
    """
    columns = body.get("schema") or body.get("columns", {})
    metadata: Dict[str, Any] = {}
    if body.get("description") is not None:
        metadata["description"] = body["description"]
    if columns:
        metadata["columns"] = columns
    if body.get("created_at"):
        metadata["created_at"] = body["created_at"]
    if body.get("path"):
        metadata["path"] = body["path"]
    return DatasetSpec(
        dataset_id=body["dataset_id"],
        name=body["name"],
        version=body.get("version") or "",
        source=body.get("path") or "",
        metadata=metadata,
    )


def _dataset_from_wire(raw: Dict[str, Any]) -> DatasetSpecModel:
    """Build a DatasetSpecModel from a wire dict, accepting 'schema' alias."""
    normalized = dict(raw)
    if "schema" in normalized and "columns" not in normalized:
        normalized["columns"] = normalized.pop("schema")
    return DatasetSpecModel.model_validate(normalized)


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
    scorecards, scenarios, datasets) and indexes via idempotent DDL.
    No companion table setup is needed here — the registry is the
    single source of truth for schema.

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


def _require_run(registry: RunRegistry, run_id: str) -> RunArtifact:
    """Fetch a run or raise 404 with a JSON detail body.

    Centralized so every handler that parents on ``run_id`` emits an
    identical error shape. The detail string always includes the offending
    id — valuable debugging signal that does not leak internal state.
    """
    artifact = registry.get(run_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"run_id not found: {run_id}",
        )
    return artifact


# ---------------------------------------------------------------------------
# /platform/healthz
# ---------------------------------------------------------------------------


@router.get("/healthz", response_model=HealthzResponse)
def healthz(registry: RunRegistry = Depends(get_registry)) -> HealthzResponse:
    """Registry-backed liveness probe."""
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
    limit: int = Query(50, ge=1, le=200, description="Max rows (default 50, max 200)."),
    offset: int = Query(0, ge=0, description="Row offset for pagination."),
    registry: RunRegistry = Depends(get_registry),
) -> List[RunRecordModel]:
    """Newest-first listing of runs with optional filters."""
    fetch_cap = min(1000, limit + offset + 200)
    artifacts = registry.list(kind=kind, limit=fetch_cap)

    records = [RunRecordModel.from_artifact(a) for a in artifacts]
    if pillar is not None:
        records = [r for r in records if r.pillar == pillar]
    if status_filter is not None:
        records = [r for r in records if r.status == status_filter]

    return records[offset : offset + limit]


@router.post(
    "/runs",
    response_model=RunCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "run_id already exists."}},
)
def create_run(
    body: RunRecordCreate,
    registry: RunRegistry = Depends(get_registry),
) -> RunCreateResponse:
    """Register a new run record."""
    if registry.get(body.run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run_id already exists: {body.run_id}",
        )
    record = RunRecordModel(**body.model_dump(by_alias=True))
    registry.register(record.to_artifact())
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
    return RunRecordModel.from_artifact(_require_run(registry, run_id))


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
    """List every artifact row registered for ``run_id``."""
    _require_run(registry, run_id)
    records = registry.list_artifacts(run_id)
    return [_artifact_record_to_wire(r) for r in records]


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
    """Register an artifact row for ``run_id``."""
    if body.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"body.run_id={body.run_id!r} does not match URL run_id={run_id!r}",
        )
    _require_run(registry, run_id)
    # Check for duplicates — the registry uses upsert semantics, but the
    # router's POST verb represents creation so we guard against it.
    existing = registry.get_artifact(run_id, body.name)
    if existing is not None:
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
    """Return the metadata row for a single named artifact."""
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
    records = registry.get_scorecards(run_id)
    return [_scorecard_to_wire(r) for r in records]


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
    # Check for duplicates — registry uses upsert, but POST = creation.
    existing = registry.get_scorecards(run_id)
    for sc in existing:
        if sc.kind.value == body.name:
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
    """List scenarios newest-first with optional pillar filter."""
    specs = registry.list_scenarios()
    wire = [_scenario_to_wire(s) for s in specs]
    if pillar is not None:
        wire = [s for s in wire if s.pillar == pillar]
    # Sort by created_at DESC to match the original newest-first behavior.
    wire.sort(key=lambda s: s.created_at or "", reverse=True)
    return wire[offset : offset + limit]


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
    existing = registry.get_scenario(body.scenario_id)
    if existing is not None:
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


@router.get("/datasets", response_model=List[Dict[str, Any]])
def list_datasets(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    registry: RunRegistry = Depends(get_registry),
) -> List[Dict[str, Any]]:
    """List datasets newest-first — response uses the 'schema' wire key."""
    specs = registry.list_datasets()
    wire = [_dataset_to_wire(s) for s in specs]
    wire.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return wire[offset : offset + limit]


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
    """Register a new dataset. ``dataset_id`` must be globally unique."""
    try:
        model = _dataset_from_wire(body)
    except Exception as exc:  # pragma: no cover - pydantic validation
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid dataset body: {exc}",
        ) from exc
    existing = registry.get_dataset(model.dataset_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"dataset_id already exists: {model.dataset_id}",
        )
    spec = _wire_to_dataset(body)
    registry.register_dataset(spec)
    # Read back from registry to ensure wire response reflects stored state.
    stored = registry.get_dataset(model.dataset_id)
    return _dataset_to_wire(stored)  # type: ignore[arg-type]


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
    return _dataset_to_wire(spec)


# ---------------------------------------------------------------------------
# /platform/datasets/{dataset_id}/card
# ---------------------------------------------------------------------------


class DatasetCardModel(BaseModel):
    """Rich dataset card — richer than the raw DatasetSpec."""

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
    """Return a rich dataset card for a registered dataset."""
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
        # Fall back to a basic card built from the registry.
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
# /platform/scenarios/{scenario_id}/runs
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
    """List all world runs associated with a given scenario."""
    spec = registry.get_scenario(scenario_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scenario_id not found: {scenario_id}",
        )
    artifacts = registry.list(kind=RunKind.WORLDS, limit=1000)
    matched = [
        RunRecordModel.from_artifact(a)
        for a in artifacts
        if a.config.get("scenario_name") == scenario_id
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
    """Trigger a headless world run for a scenario (PLACEHOLDER)."""
    spec = registry.get_scenario(body.scenario_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scenario_id not found: {body.scenario_id}",
        )
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
