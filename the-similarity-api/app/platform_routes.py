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

import sqlite3
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

    Mirrors :class:`the_similarity.platform.contracts.ArtifactRecord`
    field-for-field so the API's wire contract is registry-truth. Each
    row describes ONE named artifact in detail (size, content type,
    checksum), whereas ``RunRecordModel.artifact_paths`` is a compact
    name->path lookup for the UI. Runs with many artifacts emit N
    :class:`ArtifactRecordModel` rows.

    Field-name lock-in
    ------------------
    The integrity-hash field is named ``checksum`` (SHA-256 hex)
    because that is the column name on the registry's ``artifacts``
    table. An earlier drafting of this model used ``sha256``; that was
    schema drift and is now resolved. Any TS consumer that still sends
    ``sha256`` will get a Pydantic validation error — the rename is
    deliberate so callers converge on the registry-truth field name.
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
    checksum: Optional[str] = Field(
        None,
        description=(
            "Optional SHA-256 hex digest for integrity checks. "
            "Matches the registry ``artifacts.checksum`` column name."
        ),
    )
    created_at: str = Field(..., description="ISO-8601 UTC creation timestamp.")


class ScorecardSummaryModel(BaseModel):
    """Scorecard readout for a run — mirrors the registry's ``scorecards`` table.

    Decoupled from :class:`RunRecordModel.summary` because a single run may
    carry multiple scorecards (fidelity, privacy, utility, or evaluation
    scorecards from different harnesses). Each row is one scorecard.

    Field-name lock-in
    ------------------
    Matches :class:`the_similarity.platform.contracts.ScorecardSummary`
    field-for-field:

    - ``kind`` (not ``name``) — one of :class:`ScorecardKind`
      (``fidelity``, ``privacy``, ``utility``, ``controllability``,
      ``calibration``, ``backtest``). Composite primary key with
      ``run_id`` in the registry.
    - ``details`` (not ``metrics``) — condensed metric snapshot
      matching the registry's ``details_json`` column.
    - ``thresholds`` — numeric gate configuration, stored in the
      registry's ``thresholds_json`` column.

    An earlier draft of this model used ``name`` / ``metrics`` and
    added a ``created_at`` field. The registry carries no ``created_at``
    on scorecards (the parent run's timestamp is authoritative), so
    that field has been removed from the wire contract.
    """

    model_config = ConfigDict(use_enum_values=True)

    run_id: str = Field(..., description="Parent run_id.")
    kind: ScorecardKind = Field(
        ...,
        description=(
            "Scorecard kind — one of fidelity, privacy, utility, "
            "controllability, calibration, backtest. Composite PK with "
            "run_id in the registry."
        ),
    )
    overall_score: Optional[float] = Field(
        None, description="Aggregate score in [0, 1] (higher is better)."
    )
    passed: Optional[bool] = Field(
        None, description="Gate decision if the scorecard emits one."
    )
    thresholds: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Numeric thresholds used for the gate (matches the registry's "
            "``thresholds_json`` column)."
        ),
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Condensed metric snapshot. Full detail lives on-disk as an "
            "artifact; matches the registry's ``details_json`` column."
        ),
    )


class ScenarioSpecModel(BaseModel):
    """Platform scenario definition — mirrors the registry's ``scenarios`` table.

    A scenario is the reproducible input to a worlds/sweep run. Two runs
    with the same scenario_id are expected to be comparable.

    Field-name lock-in
    ------------------
    Tracks :class:`the_similarity.platform.contracts.ScenarioSpec`
    field-for-field:

    - ``version`` — semantic version bumped when engine behaviour changes.
    - ``engine`` — engine identifier (``"small_village"``, ``"boom_bust"``,
      ``"queue.mm1"``); the worlds runner dispatches on this.
    - ``params`` (not ``parameters``) — default parameter block; run
      configs override selectively. Stored in the registry's
      ``params_json`` column.
    - ``metadata`` (replaces ``description``/``pillar``/``created_at``) —
      free-form tags for filtering / UI. Stored in ``metadata_json``.

    An earlier draft used ``description`` / ``pillar`` / ``parameters``
    / ``created_at``; none of those columns exist on the registry's
    ``scenarios`` table, so that drift has been resolved in favour of
    the registry fields. Consumers that still want a display
    description or pillar tag should place the value inside
    ``metadata`` (e.g. ``{"description": "...", "pillar": "finance"}``).
    """

    scenario_id: str = Field(..., description="Primary key. Stable across runs.")
    name: str = Field(..., description="Human-readable display name.")
    version: str = Field(
        ...,
        description=(
            "Semantic version (``v1.0``, ``2024-04-15``) — bump when the "
            "engine behaviour changes."
        ),
    )
    engine: str = Field(
        ...,
        description=(
            "Engine identifier the worlds runner dispatches on "
            "(``small_village``, ``boom_bust``, ``queue.mm1``, ...)."
        ),
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Default scenario parameters; run configs override selectively. "
            "Matches the registry's ``params_json`` column."
        ),
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form tags (authors, references, pillar, description). "
            "Matches the registry's ``metadata_json`` column."
        ),
    )


class DatasetSpecModel(BaseModel):
    """Registered dataset — mirrors the registry's ``datasets`` table.

    A dataset describes a corpus available to the platform (source
    path/URL, schema, version, checksum). Runs reference datasets by
    ``dataset_id`` in their config to keep runs reproducible across
    pipeline changes.

    Field-name lock-in
    ------------------
    Matches :class:`the_similarity.platform.contracts.DatasetSpec`
    field-for-field:

    - ``source`` (not ``path``) — filesystem path, URL, or
      ``synthetic:<run_id>`` pointer. The registry's column is
      ``source TEXT NOT NULL``; this is the load-bearing address.
    - ``schema_uri`` (not a ``schema`` dict) — optional URI to a JSON
      schema document describing the columns. Holding only the URI
      keeps the registry row compact; full schema bytes stay on disk.
    - ``n_rows`` / ``n_columns`` — lazy scan outputs, optional.
    - ``checksum`` — optional SHA-256 hex of the source file(s).
    - ``metadata`` (replaces ``description``/``created_at``) — free-form
      tags (pillar, tickers, date range, license). Display hints like
      a human description live here now.

    An earlier draft exposed ``description`` / ``path`` / ``schema``
    (dict) / ``created_at``; none of those match the registry and the
    ``schema`` alias forced a translation shim at every boundary. The
    drift is now resolved in favour of the registry columns. Consumers
    that carried a schema dict should move it to an artifact on disk
    and point ``schema_uri`` at the artifact URL.
    """

    dataset_id: str = Field(..., description="Primary key. Stable across refreshes.")
    name: str = Field(..., description="Human-readable display name.")
    version: str = Field(
        ..., description="Semantic version (``v1.0``, ``2024-04-15``)."
    )
    source: str = Field(
        ...,
        description=(
            "Filesystem path, URL, or ``synthetic:<run_id>`` pointer. "
            "Matches the registry's ``source`` column."
        ),
    )
    schema_uri: Optional[str] = Field(
        None,
        description=(
            "Optional URI to a JSON schema describing the columns. "
            "Matches the registry's ``schema_uri`` column — a URI, "
            "not an inline schema dict."
        ),
    )
    n_rows: Optional[int] = Field(
        None, ge=0, description="Row count — populated lazily after a scan."
    )
    n_columns: Optional[int] = Field(
        None, ge=0, description="Column count — populated lazily after a scan."
    )
    checksum: Optional[str] = Field(
        None, description="Optional SHA-256 hex of the source file(s)."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form tags (pillar, tickers, date range, license, "
            "description). Matches the registry's ``metadata_json`` column."
        ),
    )


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

def _ensure_ext_schema(conn: sqlite3.Connection) -> None:  # pragma: no cover
    """Deprecated no-op retained for API backward compatibility.

    The registry-truth schema (``artifacts``, ``scorecards``,
    ``scenarios``, ``datasets``) is created by
    :class:`RunRegistry._init_schema` on first connect. Earlier
    revisions of this router maintained *companion* tables with drifted
    column names (``sha256``, ``metrics_json``, ``parameters_json``,
    ``schema_json``) here; that drift caused silent schema conflicts
    against the registry's DDL. We now delegate every CRUD call to the
    registry's ``register_*``/``list_*`` methods, so no companion
    tables exist and no DDL needs to fire on request setup.

    The function is kept as a no-op so the test fixture in
    ``the-similarity-api/tests/test_platform_routes.py`` (which
    imports and calls it) does not break while we migrate.
    """
    # Intentionally empty — see docstring. Signature preserved for
    # downstream importers.
    del conn


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

    Implementation note
    -------------------
    Delegates to :meth:`RunRegistry.list_artifacts` so the route reads
    through the same code path the registry persists. The dataclass
    returned carries the registry-truth ``checksum`` column; we map it
    directly onto :attr:`ArtifactRecordModel.checksum` with no renaming.
    """
    _require_run(registry, run_id)
    records = registry.list_artifacts(run_id)
    return [
        ArtifactRecordModel(
            run_id=a.run_id,
            name=a.name,
            path=a.path,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            checksum=a.checksum,
            created_at=a.created_at,
        )
        for a in records
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

    Implementation note
    -------------------
    :meth:`RunRegistry.register_artifact` is an *upsert* by design (the
    registry sees partial-then-enriched registrations as a normal path).
    The route, however, treats POST as creation — so we pre-flight via
    :meth:`RunRegistry.list_artifacts` to surface duplicates as 409
    before the upsert silently replaces the existing row.
    """
    if body.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"body.run_id={body.run_id!r} does not match URL run_id={run_id!r}",
        )
    _require_run(registry, run_id)
    # Pre-flight duplicate check — the registry upserts on (run_id, name)
    # so we must detect an existing row ourselves to honour the router's
    # POST = creation contract.
    existing_names = {a.name for a in registry.list_artifacts(run_id)}
    if body.name in existing_names:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"artifact already exists: run_id={run_id}, name={body.name}",
        )
    # ``ArtifactRecord.content_type`` is typed as ``str`` in the contract
    # but the underlying SQLite column is nullable; runners that omit it
    # pass ``None``. We forward the value unchanged — Python's dataclass
    # runtime does not enforce annotations, and the registry row handles
    # ``NULL`` correctly on round-trip.
    registry.register_artifact(
        ArtifactRecord(
            run_id=body.run_id,
            name=body.name,
            path=body.path,
            content_type=body.content_type,  # type: ignore[arg-type]
            size_bytes=body.size_bytes,
            checksum=body.checksum,
            created_at=body.created_at,
        )
    )
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

    Implementation note
    -------------------
    The registry exposes only a ``list_artifacts(run_id)`` bulk accessor
    (no per-name getter); we filter the list in Python. The list is
    tiny in practice (one run emits a handful of named artifacts) so an
    O(n) scan is cheaper than adding a second SELECT-by-name to the
    registry surface.
    """
    _require_run(registry, run_id)
    for artifact in registry.list_artifacts(run_id):
        if artifact.name == name:
            return ArtifactRecordModel(
                run_id=artifact.run_id,
                name=artifact.name,
                path=artifact.path,
                content_type=artifact.content_type,
                size_bytes=artifact.size_bytes,
                checksum=artifact.checksum,
                created_at=artifact.created_at,
            )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"artifact not found: run_id={run_id}, name={name}",
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
    """Every scorecard summary row registered for ``run_id``.

    Implementation note
    -------------------
    Delegates to :meth:`RunRegistry.get_scorecards` so the wire shape
    tracks the registry row shape one-for-one (``kind``, ``thresholds``,
    ``details``). The registry handles INTEGER->bool coercion for the
    ``passed`` column internally.
    """
    _require_run(registry, run_id)
    summaries = registry.get_scorecards(run_id)
    return [
        ScorecardSummaryModel(
            run_id=s.run_id,
            kind=s.kind,
            overall_score=s.overall_score,
            passed=s.passed,
            thresholds=s.thresholds,
            details=s.details,
        )
        for s in summaries
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
    """Register a scorecard summary under ``run_id``.

    Implementation note
    -------------------
    :meth:`RunRegistry.register_scorecard` is an upsert on the composite
    ``(run_id, kind)`` primary key. The router treats POST as creation,
    so we pre-flight via :meth:`RunRegistry.get_scorecards` to surface
    an existing row as a 409 rather than silently replacing it.
    """
    if body.run_id != run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"body.run_id={body.run_id!r} does not match URL run_id={run_id!r}",
        )
    _require_run(registry, run_id)
    # ``body.kind`` may be either a ``ScorecardKind`` or a bare string
    # depending on whether Pydantic's ``use_enum_values=True`` emitted
    # the raw string at validation time. Normalize here so we compare
    # and persist the enum uniformly.
    kind_value = body.kind.value if isinstance(body.kind, ScorecardKind) else body.kind
    kind_enum = ScorecardKind(kind_value)
    existing_kinds = {s.kind.value for s in registry.get_scorecards(run_id)}
    if kind_enum.value in existing_kinds:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"scorecard already exists: run_id={run_id}, kind={kind_enum.value}",
        )
    registry.register_scorecard(
        ScorecardSummary(
            run_id=body.run_id,
            kind=kind_enum,
            thresholds=body.thresholds,
            details=body.details,
            overall_score=body.overall_score,
            passed=body.passed,
        )
    )
    return body


# ---------------------------------------------------------------------------
# /platform/scenarios
# ---------------------------------------------------------------------------


def _scenario_to_model(spec: ScenarioSpec) -> ScenarioSpecModel:
    """Project a registry :class:`ScenarioSpec` to the wire model.

    Kept as a helper so list/get handlers stay short and the
    dataclass-to-model translation lives in one place.
    """
    return ScenarioSpecModel(
        scenario_id=spec.scenario_id,
        name=spec.name,
        version=spec.version,
        engine=spec.engine,
        params=spec.params,
        metadata=spec.metadata,
    )


@router.get("/scenarios", response_model=List[ScenarioSpecModel])
def list_scenarios(
    engine: Optional[str] = Query(
        None,
        description=(
            "Filter by engine identifier (e.g. ``small_village``, "
            "``boom_bust``). Replaces the earlier ``pillar`` filter "
            "which had no matching column on the registry."
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    registry: RunRegistry = Depends(get_registry),
) -> List[ScenarioSpecModel]:
    """List registered scenarios.

    The registry's :meth:`RunRegistry.list_scenarios` returns every row
    ordered by ``name ASC`` (stable for deterministic UI grids). We
    apply ``engine`` filtering + Python-side pagination here because
    the registry does not expose either knob directly.
    """
    specs = registry.list_scenarios()
    if engine is not None:
        specs = [s for s in specs if s.engine == engine]
    sliced = specs[offset : offset + limit]
    return [_scenario_to_model(s) for s in sliced]


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
    """Register a new scenario. ``scenario_id`` must be globally unique.

    Implementation note
    -------------------
    :meth:`RunRegistry.register_scenario` is an upsert; the router
    pre-flights a ``list_scenarios`` scan so a duplicate ``scenario_id``
    surfaces as a 409 rather than silently replacing the existing row.
    """
    existing_ids = {s.scenario_id for s in registry.list_scenarios()}
    if body.scenario_id in existing_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"scenario_id already exists: {body.scenario_id}",
        )
    registry.register_scenario(
        ScenarioSpec(
            scenario_id=body.scenario_id,
            name=body.name,
            version=body.version,
            engine=body.engine,
            params=body.params,
            metadata=body.metadata,
        )
    )
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
    """Fetch a single scenario by id.

    Implementation note
    -------------------
    The registry has no per-id getter on scenarios, so we linear-scan
    :meth:`RunRegistry.list_scenarios`. The table is small (dozens of
    rows in practice); if this ever becomes a hot path, add a dedicated
    ``get_scenario`` method to the registry.
    """
    for spec in registry.list_scenarios():
        if spec.scenario_id == scenario_id:
            return _scenario_to_model(spec)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"scenario_id not found: {scenario_id}",
    )


# ---------------------------------------------------------------------------
# /platform/datasets
# ---------------------------------------------------------------------------


def _dataset_to_model(spec: DatasetSpec) -> DatasetSpecModel:
    """Project a registry :class:`DatasetSpec` to the wire model.

    Kept as a helper so list/get handlers stay short and the
    dataclass-to-model translation lives in one place. No alias
    translation is required anymore — the wire contract tracks the
    registry columns directly.
    """
    return DatasetSpecModel(
        dataset_id=spec.dataset_id,
        name=spec.name,
        version=spec.version,
        source=spec.source,
        schema_uri=spec.schema_uri,
        n_rows=spec.n_rows,
        n_columns=spec.n_columns,
        checksum=spec.checksum,
        metadata=spec.metadata,
    )


@router.get("/datasets", response_model=List[DatasetSpecModel])
def list_datasets(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    registry: RunRegistry = Depends(get_registry),
) -> List[DatasetSpecModel]:
    """List registered datasets.

    Ordering is ``name ASC`` (registry default — the ``datasets`` table
    has no ``created_at`` column). Python-side pagination applies
    offset/limit to the full list because the registry does not expose
    either knob directly.
    """
    specs = registry.list_datasets()
    sliced = specs[offset : offset + limit]
    return [_dataset_to_model(s) for s in sliced]


@router.post(
    "/datasets",
    response_model=DatasetSpecModel,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "dataset_id already exists."}},
)
def create_dataset(
    body: DatasetSpecModel,
    registry: RunRegistry = Depends(get_registry),
) -> DatasetSpecModel:
    """Register a new dataset. ``dataset_id`` must be globally unique.

    Implementation note
    -------------------
    :meth:`RunRegistry.register_dataset` upserts on ``dataset_id``; the
    router pre-flights a ``list_datasets`` scan so a duplicate id
    surfaces as a 409 rather than silently replacing the existing row.
    """
    existing_ids = {d.dataset_id for d in registry.list_datasets()}
    if body.dataset_id in existing_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"dataset_id already exists: {body.dataset_id}",
        )
    registry.register_dataset(
        DatasetSpec(
            dataset_id=body.dataset_id,
            name=body.name,
            version=body.version,
            source=body.source,
            schema_uri=body.schema_uri,
            n_rows=body.n_rows,
            n_columns=body.n_columns,
            checksum=body.checksum,
            metadata=body.metadata,
        )
    )
    return body


@router.get(
    "/datasets/{dataset_id}",
    response_model=DatasetSpecModel,
    responses={404: {"description": "dataset_id not found."}},
)
def get_dataset(
    dataset_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> DatasetSpecModel:
    """Fetch a single dataset by id.

    Implementation note
    -------------------
    No per-id accessor on the registry — we linear-scan list_datasets.
    The table is small (dozens of rows); if this becomes a hot path,
    add a dedicated ``get_dataset`` method to the registry.
    """
    for spec in registry.list_datasets():
        if spec.dataset_id == dataset_id:
            return _dataset_to_model(spec)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"dataset_id not found: {dataset_id}",
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
        # If the catalog module is not available, fall back to a basic
        # card built from the registry-truth ``DatasetSpec`` row. No raw
        # SQL — delegate to ``list_datasets`` so the column set tracks
        # the registry automatically.
        for spec in registry.list_datasets():
            if spec.dataset_id == dataset_id:
                return DatasetCardModel(
                    dataset_id=spec.dataset_id,
                    name=spec.name,
                    version=spec.version,
                    source=spec.source,
                    n_rows=spec.n_rows,
                    n_columns=spec.n_columns,
                    checksum=spec.checksum,
                )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"dataset_id not found: {dataset_id}",
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
    row = registry._conn.execute(  # noqa: SLF001
        "SELECT scenario_id FROM scenarios WHERE scenario_id = ?",
        (scenario_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scenario_id not found: {scenario_id}",
        )

    # Fetch all worlds runs and filter by scenario_name in config.
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
    row = registry._conn.execute(  # noqa: SLF001
        "SELECT scenario_id FROM scenarios WHERE scenario_id = ?",
        (body.scenario_id,),
    ).fetchone()
    if row is None:
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
