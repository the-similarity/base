"""Customer-facing platform registry routes — mounts at ``/platform/*``.

Purpose
-------
Expose the platform's run registry (the backbone of the Ops Layer — see
``the_similarity/platform/registry.py``) through the public
customer-facing API at :mod:`app.main`. This router is a *thin wrapper*
around :class:`~the_similarity.platform.registry.RunRegistry` plus a small
set of companion tables (artifacts / scorecards / scenarios / datasets)
that will migrate to the shared registry once the platform team's
Agent-2 extension lands.

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

Compatibility with upcoming registry extensions
-----------------------------------------------
Agent 1 is shipping ``the_similarity/platform/contracts.py`` with
dataclasses ``RunRecord``, ``ArtifactRecord``, ``ScorecardSummary``,
``ScenarioSpec``, ``DatasetSpec``. Agent 2 is extending ``registry.py``
with matching ``register_*``/``list_*``/``get_*`` methods. Until those
land the router maintains companion SQLite tables — ``artifacts``,
``scorecards``, ``scenarios``, ``datasets`` — inside the same DB file
so the switchover is a one-line delegation change, not a data migration.

The Pydantic models here are the public wire contract. They intentionally
match the field list from Agent 1's shared spec (see comments on each
model) so the swap to imported dataclasses is mechanical.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.settings import resolve_registry_db
from the_similarity.platform.artifacts import RunArtifact, RunKind
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
# Companion tables
#
# Until Agent 2 extends :class:`RunRegistry` with ``register_artifact`` etc.,
# we maintain the artifact/scorecard/scenario/dataset rows in ancillary
# tables in the SAME SQLite DB file. Co-locating keeps the registry a
# single file per deploy (mirror of the current design invariant) so the
# handover is purely a code change.
#
# Schema is deliberately simple — one row per (parent, name) where
# applicable. JSON columns carry the free-form ``metrics`` / ``parameters``
# / ``schema`` payloads. We re-use the registry's ``_conn`` to avoid
# opening a second connection per request.
# ---------------------------------------------------------------------------

_EXT_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        run_id       TEXT NOT NULL,
        name         TEXT NOT NULL,
        path         TEXT NOT NULL,
        content_type TEXT,
        size_bytes   INTEGER,
        sha256       TEXT,
        created_at   TEXT NOT NULL,
        PRIMARY KEY (run_id, name)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scorecards (
        run_id        TEXT NOT NULL,
        name          TEXT NOT NULL,
        passed        INTEGER,
        overall_score REAL,
        metrics_json  TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        PRIMARY KEY (run_id, name)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scenarios (
        scenario_id     TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        description     TEXT,
        pillar          TEXT,
        parameters_json TEXT NOT NULL,
        created_at      TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS datasets (
        dataset_id  TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        description TEXT,
        path        TEXT,
        schema_json TEXT NOT NULL,
        version     TEXT,
        created_at  TEXT NOT NULL
    );
    """,
]


def _ensure_ext_schema(conn: sqlite3.Connection) -> None:
    """Create the companion tables if missing. Idempotent.

    Invoked on every dependency call because the registry opens a fresh
    connection per request. The ``CREATE TABLE IF NOT EXISTS`` pattern
    means this is a no-op after the first call per-DB-file.
    """
    with conn:
        for ddl in _EXT_SCHEMA_SQL:
            conn.execute(ddl)


# ---------------------------------------------------------------------------
# Registry dependency
# ---------------------------------------------------------------------------


def get_registry() -> Iterator[RunRegistry]:
    """FastAPI dependency yielding a per-request :class:`RunRegistry`.

    Fresh connection per request — the underlying ``sqlite3.Connection``
    is not thread-safe, and FastAPI may dispatch requests across worker
    threads, so sharing a module-level connection would be a latent bug.
    WAL mode keeps the cost negligible.

    Tests override with ``app.dependency_overrides[get_registry]`` to pin
    a tmp-path DB so the production default is never touched.
    """
    registry = RunRegistry(resolve_registry_db())
    # Companion tables live alongside the runs table in the same file.
    _ensure_ext_schema(registry._conn)  # noqa: SLF001 — intentional reach-in
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

    The underlying :meth:`RunRegistry.list` supports only ``kind`` and
    ``limit`` natively. ``pillar`` and ``status`` live inside ``provenance``
    today (not promoted to columns until Agent 2 lands), so we filter them
    in Python after fetching an over-sized page. This is safe for the
    foreseeable registry scale (thousands of rows).

    ``offset`` is applied in Python for the same reason — the registry
    does not expose a SQL ``OFFSET`` parameter today.
    """
    # Over-fetch: we need ``limit + offset`` rows if either extension filter
    # is applied, since filtering happens after the SQL layer. Cap to 1000
    # to prevent a pathological request from pulling the whole DB.
    fetch_cap = min(1000, limit + offset + 200)
    artifacts = registry.list(kind=kind, limit=fetch_cap)

    records = [RunRecordModel.from_artifact(a) for a in artifacts]
    if pillar is not None:
        records = [r for r in records if r.pillar == pillar]
    if status_filter is not None:
        records = [r for r in records if r.status == status_filter]

    # Python-side pagination. Slicing is O(n) but n is small.
    return records[offset : offset + limit]


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

    Distinct from :meth:`RunRegistry.register`'s upsert semantics — this
    endpoint treats an existing ``run_id`` as a 409 conflict because POST
    is the *creation* verb. Updates to an existing run are out of MVP
    scope; Agent 2's extension will expose a PUT/PATCH when needed.
    """
    if registry.get(body.run_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run_id already exists: {body.run_id}",
        )

    # Build a model then project to the underlying RunArtifact shape so the
    # pillar/status extension fields survive in provenance.
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
    """List every artifact row registered for ``run_id``.

    Returns an empty list (not 404) when the run exists but has no
    artifact rows — empty is a valid state for a freshly registered run.
    The 404 branch fires only when the parent run itself is missing.
    """
    _require_run(registry, run_id)
    rows = registry._conn.execute(  # noqa: SLF001 — intentional reach-in
        "SELECT run_id, name, path, content_type, size_bytes, sha256, created_at "
        "FROM artifacts WHERE run_id = ? ORDER BY name",
        (run_id,),
    ).fetchall()
    return [
        ArtifactRecordModel(
            run_id=r[0],
            name=r[1],
            path=r[2],
            content_type=r[3],
            size_bytes=r[4],
            sha256=r[5],
            created_at=r[6],
        )
        for r in rows
    ]


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
    try:
        with registry._conn:  # noqa: SLF001 — intentional reach-in
            registry._conn.execute(  # noqa: SLF001
                "INSERT INTO artifacts "
                "(run_id, name, path, content_type, size_bytes, sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    body.run_id,
                    body.name,
                    body.path,
                    body.content_type,
                    body.size_bytes,
                    body.sha256,
                    body.created_at,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"artifact already exists: run_id={run_id}, name={body.name}",
        ) from exc
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
    row = registry._conn.execute(  # noqa: SLF001
        "SELECT run_id, name, path, content_type, size_bytes, sha256, created_at "
        "FROM artifacts WHERE run_id = ? AND name = ?",
        (run_id, name),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact not found: run_id={run_id}, name={name}",
        )
    return ArtifactRecordModel(
        run_id=row[0],
        name=row[1],
        path=row[2],
        content_type=row[3],
        size_bytes=row[4],
        sha256=row[5],
        created_at=row[6],
    )


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
    rows = registry._conn.execute(  # noqa: SLF001
        "SELECT run_id, name, passed, overall_score, metrics_json, created_at "
        "FROM scorecards WHERE run_id = ? ORDER BY name",
        (run_id,),
    ).fetchall()
    return [
        ScorecardSummaryModel(
            run_id=r[0],
            name=r[1],
            # SQLite stores booleans as 0/1 integers; normalize to bool or None.
            passed=(bool(r[2]) if r[2] is not None else None),
            overall_score=r[3],
            metrics=json.loads(r[4]) if r[4] else {},
            created_at=r[5],
        )
        for r in rows
    ]


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
    try:
        with registry._conn:  # noqa: SLF001
            registry._conn.execute(  # noqa: SLF001
                "INSERT INTO scorecards "
                "(run_id, name, passed, overall_score, metrics_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    body.run_id,
                    body.name,
                    None if body.passed is None else int(body.passed),
                    body.overall_score,
                    json.dumps(body.metrics, separators=(",", ":")),
                    body.created_at,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"scorecard already exists: run_id={run_id}, name={body.name}",
        ) from exc
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
    if pillar is None:
        rows = registry._conn.execute(  # noqa: SLF001
            "SELECT scenario_id, name, description, pillar, parameters_json, created_at "
            "FROM scenarios ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    else:
        rows = registry._conn.execute(  # noqa: SLF001
            "SELECT scenario_id, name, description, pillar, parameters_json, created_at "
            "FROM scenarios WHERE pillar = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (pillar, limit, offset),
        ).fetchall()
    return [
        ScenarioSpecModel(
            scenario_id=r[0],
            name=r[1],
            description=r[2],
            pillar=r[3],
            parameters=json.loads(r[4]) if r[4] else {},
            created_at=r[5],
        )
        for r in rows
    ]


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
    try:
        with registry._conn:  # noqa: SLF001
            registry._conn.execute(  # noqa: SLF001
                "INSERT INTO scenarios "
                "(scenario_id, name, description, pillar, parameters_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    body.scenario_id,
                    body.name,
                    body.description,
                    body.pillar,
                    json.dumps(body.parameters, separators=(",", ":")),
                    body.created_at,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"scenario_id already exists: {body.scenario_id}",
        ) from exc
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
    row = registry._conn.execute(  # noqa: SLF001
        "SELECT scenario_id, name, description, pillar, parameters_json, created_at "
        "FROM scenarios WHERE scenario_id = ?",
        (scenario_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scenario_id not found: {scenario_id}",
        )
    return ScenarioSpecModel(
        scenario_id=row[0],
        name=row[1],
        description=row[2],
        pillar=row[3],
        parameters=json.loads(row[4]) if row[4] else {},
        created_at=row[5],
    )


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
    """List datasets newest-first — response uses the 'schema' wire key."""
    rows = registry._conn.execute(  # noqa: SLF001
        "SELECT dataset_id, name, description, path, schema_json, version, created_at "
        "FROM datasets ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [
        _dataset_to_wire(
            DatasetSpecModel(
                dataset_id=r[0],
                name=r[1],
                description=r[2],
                path=r[3],
                columns=json.loads(r[4]) if r[4] else {},
                version=r[5],
                created_at=r[6],
            )
        )
        for r in rows
    ]


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
    try:
        with registry._conn:  # noqa: SLF001
            registry._conn.execute(  # noqa: SLF001
                "INSERT INTO datasets "
                "(dataset_id, name, description, path, schema_json, version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    model.dataset_id,
                    model.name,
                    model.description,
                    model.path,
                    json.dumps(model.columns, separators=(",", ":")),
                    model.version,
                    model.created_at,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"dataset_id already exists: {model.dataset_id}",
        ) from exc
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
    row = registry._conn.execute(  # noqa: SLF001
        "SELECT dataset_id, name, description, path, schema_json, version, created_at "
        "FROM datasets WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"dataset_id not found: {dataset_id}",
        )
    return _dataset_to_wire(
        DatasetSpecModel(
            dataset_id=row[0],
            name=row[1],
            description=row[2],
            path=row[3],
            columns=json.loads(row[4]) if row[4] else {},
            version=row[5],
            created_at=row[6],
        )
    )


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
        # built from the raw dataset row.
        row = registry._conn.execute(  # noqa: SLF001
            "SELECT dataset_id, name, description, path, schema_json, version, created_at "
            "FROM datasets WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"dataset_id not found: {dataset_id}",
            )
        return DatasetCardModel(
            dataset_id=row[0],
            name=row[1],
            version=row[5] or "",
            source="",
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
    "get_registry",
    "router",
]
