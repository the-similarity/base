"""Goodruns surface — save/list/delete curated "good match" records.

Purpose
-------
Let the workstation UI persist a specific query-window ↔ match-window pair
that the user found compelling, together with the full raw
``ScoreBreakdown`` (engine math-names — ``dtw``, ``pearsonWarped``,
``bempedelisR2``, etc. — NOT the UI-facing ``lens1..9`` or legacy
``shape/dynamics/scaling`` aliases). Goodruns are durable: they survive
unpin, session reloads, and full restarts. They are the primitive the
human interlocutor queries over time ("show me my goodruns").

Storage invariants
------------------
- Backed by SQLite in WAL mode at the path returned by
  :func:`resolve_goodruns_db` (override via
  ``THE_SIMILARITY_GOODRUNS_DB`` env var; default
  ``~/.the_similarity/goodruns.db``). Parent dir is created on first
  use; we never delete the file ourselves.
- Schema is a SINGLE table (``goodruns``) — no artifacts, no scorecards.
  Keep it flat so it's easy to grep / sqlite3-query from the command
  line when Claude surfaces records.
- Float arrays (query prices, match prices, forward prices) are stored
  as JSON-encoded TEXT. SQLite's BLOB would be more compact but TEXT
  keeps the DB human-inspectable with ``sqlite3 .dump`` / jq.
- ``id`` is client-supplied (the frontend generates a ULID-like
  ``goodrun-<ms>-<suffix>`` so the same button press is idempotent
  across network retries). We enforce uniqueness with a PRIMARY KEY
  constraint; duplicate POSTs return 409.

Threading
---------
One connection per request (opened in :func:`_connect`, closed when the
request handler returns). SQLite WAL mode makes concurrent reads and a
single writer safe across FastAPI worker threads. We do NOT cache a
module-level connection — that would pin the DB path at import time and
break tests that monkeypatch ``THE_SIMILARITY_GOODRUNS_DB``.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Env resolution — mirrors ``app/settings.py::resolve_registry_db`` style so
# tests can monkeypatch the DB path at runtime.
# ---------------------------------------------------------------------------

ENV_GOODRUNS_DB = "THE_SIMILARITY_GOODRUNS_DB"
"""Env var name for overriding the goodruns SQLite path (tests + prod)."""

DEFAULT_GOODRUNS_DB_PATH = Path("~/.the_similarity/goodruns.db")
"""Default path if ``THE_SIMILARITY_GOODRUNS_DB`` is unset."""


def resolve_goodruns_db() -> Path:
    """Return the goodruns DB path resolved per env-var precedence.

    Resolved at call time (not at import) so tests that
    ``monkeypatch.setenv`` after module import see the override. Parent
    directory is created by :func:`_connect` on first use.
    """
    override = os.environ.get(ENV_GOODRUNS_DB)
    if override:
        return Path(override).expanduser()
    return DEFAULT_GOODRUNS_DB_PATH.expanduser()


# ---------------------------------------------------------------------------
# Schema bootstrap.
#
# Single flat table. Idempotent — safe to call on every request. The
# ``CREATE TABLE IF NOT EXISTS`` + ``CREATE INDEX IF NOT EXISTS`` pattern
# lets us ship new deployments without a separate migration step.
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS goodruns (
    id                       TEXT    PRIMARY KEY,
    saved_at                 TEXT    NOT NULL,
    dataset                  TEXT    NOT NULL,
    horizon                  INTEGER NOT NULL,
    query_start_idx          INTEGER NOT NULL,
    query_end_idx            INTEGER NOT NULL,
    query_start_date         TEXT,
    query_end_date           TEXT,
    query_values_json        TEXT    NOT NULL,
    match_id                 TEXT    NOT NULL,
    match_start_idx          INTEGER NOT NULL,
    match_end_idx            INTEGER NOT NULL,
    match_start_date         TEXT,
    match_end_date           TEXT,
    match_values_json        TEXT    NOT NULL,
    match_after_values_json  TEXT    NOT NULL,
    lens_breakdown_json      TEXT    NOT NULL,
    composite                REAL,
    note                     TEXT
);

CREATE INDEX IF NOT EXISTS idx_goodruns_dataset     ON goodruns(dataset);
CREATE INDEX IF NOT EXISTS idx_goodruns_saved_at    ON goodruns(saved_at);
"""


def _connect() -> sqlite3.Connection:
    """Open a fresh SQLite connection with WAL + row factory configured.

    Called once per request. The caller is responsible for ``close()``;
    the endpoint handlers wrap this in a try/finally to guarantee release
    even if the query raises.
    """
    path = resolve_goodruns_db()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    # WAL = safe concurrent reads, single writer. Set once per connection;
    # SQLite persists the mode on-disk so repeated sets are cheap no-ops.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    # Schema bootstrap is idempotent; running it every connection keeps
    # the "first request on fresh DB" path simple and lets operators
    # delete the file without any provisioning step.
    conn.executescript(_SCHEMA_SQL)
    return conn


# ---------------------------------------------------------------------------
# Wire contracts. The lens breakdown uses ENGINE math names — this is the
# whole point of the feature per the user's spec: ``dtw``,
# ``pearsonWarped``, ``bempedelisR2``, ``bempedelisSmoothness``,
# ``koopman``, ``waveletSpectrum``, ``emd``, ``tda``, ``transferEntropy``.
# We DO NOT accept ``lens1..9`` here — the frontend is responsible for
# supplying raw scoreBreakdown fields. A save without a real breakdown
# (e.g. synthetic-mode analog) must not reach this endpoint; the drawer
# disables the Save button when scoreBreakdown is null.
# ---------------------------------------------------------------------------


class LensBreakdown(BaseModel):
    """Per-method similarity scores keyed by engine math names.

    Every field is a 0..1 score produced by the corresponding engine
    method. ``bempedelisR2`` + ``bempedelisSmoothness`` are the two
    sub-scores of the Bempedelis multifractal method; the UI collapses
    them into a single "scaling" lens, but the saved record preserves
    both so the math names are faithful.
    """

    dtw: float
    pearsonWarped: float
    bempedelisR2: float
    bempedelisSmoothness: float
    koopman: float
    waveletSpectrum: float
    emd: float
    tda: float
    transferEntropy: float


class GoodrunWindow(BaseModel):
    """A single bar-indexed window (either the query or the match)."""

    start_idx: int = Field(..., ge=0)
    end_idx: int = Field(..., ge=0)
    start_date: str | None = None
    end_date: str | None = None
    values: list[float]


class GoodrunCreate(BaseModel):
    """Payload for ``POST /goodruns`` — everything the UI sends."""

    id: str = Field(..., min_length=3, max_length=128)
    dataset: str = Field(..., min_length=1)
    horizon: int = Field(..., ge=1)
    query: GoodrunWindow
    match_id: str = Field(..., min_length=1)
    match: GoodrunWindow
    match_after_values: list[float]
    lens_breakdown: LensBreakdown
    composite: float | None = None
    note: str | None = None


class GoodrunRecord(BaseModel):
    """On-the-wire shape returned by GET endpoints."""

    id: str
    saved_at: str
    dataset: str
    horizon: int
    query: GoodrunWindow
    match_id: str
    match: GoodrunWindow
    match_after_values: list[float]
    lens_breakdown: LensBreakdown
    composite: float | None
    note: str | None


# ---------------------------------------------------------------------------
# Row <-> wire translation. Kept local because the schema is flat enough
# that a dedicated adapter module would be overkill.
# ---------------------------------------------------------------------------


def _row_to_record(row: sqlite3.Row) -> GoodrunRecord:
    """Hydrate a ``GoodrunRecord`` from a SQLite row.

    The JSON-encoded list columns are parsed back into Python lists.
    Any malformed JSON raises at this boundary rather than at the
    endpoint — a corrupted row should 500, not silently return empty
    arrays.
    """
    data: dict[str, Any] = dict(row)
    return GoodrunRecord(
        id=data["id"],
        saved_at=data["saved_at"],
        dataset=data["dataset"],
        horizon=data["horizon"],
        query=GoodrunWindow(
            start_idx=data["query_start_idx"],
            end_idx=data["query_end_idx"],
            start_date=data["query_start_date"],
            end_date=data["query_end_date"],
            values=json.loads(data["query_values_json"]),
        ),
        match_id=data["match_id"],
        match=GoodrunWindow(
            start_idx=data["match_start_idx"],
            end_idx=data["match_end_idx"],
            start_date=data["match_start_date"],
            end_date=data["match_end_date"],
            values=json.loads(data["match_values_json"]),
        ),
        match_after_values=json.loads(data["match_after_values_json"]),
        lens_breakdown=LensBreakdown(**json.loads(data["lens_breakdown_json"])),
        composite=data["composite"],
        note=data["note"],
    )


# ---------------------------------------------------------------------------
# Router. Mounted at the root of the public API (no prefix) — goodruns are
# a top-level feature, not part of the platform registry.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/goodruns", tags=["goodruns"])


@router.post("", response_model=GoodrunRecord, status_code=201)
def create_goodrun(payload: GoodrunCreate) -> GoodrunRecord:
    """Save a new goodrun. Idempotency is by client-supplied ``id``.

    Duplicate id → 409. The client should regenerate the id on retry
    only when it intends to create a second record for the same pair.
    """
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = _connect()
    try:
        # Pre-flight uniqueness check — cheaper than catching IntegrityError
        # for the narrow case we care about, and gives us a clean 409 body.
        existing = conn.execute(
            "SELECT id FROM goodruns WHERE id = ?",
            (payload.id,),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"goodrun id '{payload.id}' already exists")

        conn.execute(
            """
            INSERT INTO goodruns (
                id, saved_at, dataset, horizon,
                query_start_idx, query_end_idx, query_start_date, query_end_date, query_values_json,
                match_id,
                match_start_idx, match_end_idx, match_start_date, match_end_date, match_values_json,
                match_after_values_json,
                lens_breakdown_json, composite, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.id,
                saved_at,
                payload.dataset,
                payload.horizon,
                payload.query.start_idx,
                payload.query.end_idx,
                payload.query.start_date,
                payload.query.end_date,
                json.dumps(payload.query.values),
                payload.match_id,
                payload.match.start_idx,
                payload.match.end_idx,
                payload.match.start_date,
                payload.match.end_date,
                json.dumps(payload.match.values),
                json.dumps(payload.match_after_values),
                payload.lens_breakdown.model_dump_json(),
                payload.composite,
                payload.note,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM goodruns WHERE id = ?",
            (payload.id,),
        ).fetchone()
        # The row must exist — we just inserted it inside this transaction.
        # If SQLite returns None the DB is corrupt; fail loud.
        assert row is not None, "row missing after successful INSERT"
        return _row_to_record(row)
    finally:
        conn.close()


@router.get("", response_model=list[GoodrunRecord])
def list_goodruns(dataset: str | None = None, limit: int = 200) -> list[GoodrunRecord]:
    """List goodruns, newest first. Optional filter by dataset.

    ``limit`` is capped at 1000 to keep response payloads reasonable;
    pagination is not implemented yet because we expect individual
    users to accumulate dozens, not thousands, of goodruns. Add a
    cursor if that assumption breaks.
    """
    limit = max(1, min(limit, 1000))
    conn = _connect()
    try:
        if dataset is not None:
            rows = conn.execute(
                "SELECT * FROM goodruns WHERE dataset = ? ORDER BY saved_at DESC LIMIT ?",
                (dataset, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM goodruns ORDER BY saved_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_record(r) for r in rows]
    finally:
        conn.close()


@router.get("/{goodrun_id}", response_model=GoodrunRecord)
def get_goodrun(goodrun_id: str) -> GoodrunRecord:
    """Fetch one goodrun by id. 404 when not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM goodruns WHERE id = ?",
            (goodrun_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"goodrun '{goodrun_id}' not found")
        return _row_to_record(row)
    finally:
        conn.close()


@router.delete("/{goodrun_id}")
def delete_goodrun(goodrun_id: str) -> Response:
    """Remove a goodrun. 404 when it never existed so the UI can react.

    Returns an empty 204 response on success. We construct the
    :class:`Response` manually rather than using ``status_code=204`` on
    the decorator because FastAPI's route builder rejects a typed
    return annotation alongside a body-less status code.
    """
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM goodruns WHERE id = ?", (goodrun_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"goodrun '{goodrun_id}' not found")
        conn.commit()
        return Response(status_code=204)
    finally:
        conn.close()
