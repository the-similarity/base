"""SQLite-backed run registry — the platform's persistent memory.

Every run that lands a :class:`~the_similarity.platform.artifacts.RunArtifact`
also lands a row in this registry. The registry is the single index downstream
surfaces (CLI, HTTP API, eval harness, UI) consult to answer:

- "What runs of kind/pillar/status X exist, newest first?"
- "Show me the full record for run_id Y."
- "How does run A's summary differ from run B's?"
- "Which artifacts belong to this run?"
- "What scorecards has this run accumulated?"

Design constraints (deliberate)
-------------------------------
- **stdlib sqlite3 only** — no SQLAlchemy, no migrations framework, no async
  driver. The DB must be openable with ``sqlite3 registry.db`` on any
  developer's laptop and survive years of agent churn without code support.
- **WAL journal mode** — set on every connection so concurrent readers do
  not block writers. This matters because the orchestrator may run many
  worktree agents that all want to register their runs concurrently.
- **JSON columns as TEXT** — config / artifact_paths / summary / provenance
  are stored as JSON-encoded TEXT, not blobs. Trade-off: we lose JSON1
  query support unless explicitly enabled per-connection, but we gain
  human-readability (``sqlite3 registry.db "select * from runs"`` is
  inspectable) and zero-friction portability.
- **Upsert on every primary key** — re-registering the same ID is a
  *replace*, not an error. Re-registration is a normal path: a runner may
  register early with a partial record, then the eval harness re-registers
  the same ID later with enriched data.
- **Idempotent schema migrations** — the registry was originally shipped
  with a single ``runs`` table. The spine extension adds columns and
  sibling tables. All DDL is ``CREATE TABLE IF NOT EXISTS`` + guarded
  ``ALTER TABLE ADD COLUMN`` (SQLite has no ``ADD COLUMN IF NOT EXISTS``,
  so the add is wrapped in a try/except on ``sqlite3.OperationalError``).

Concurrency
-----------
Each :class:`RunRegistry` instance owns one ``sqlite3.Connection``. The
connection is *not* thread-safe — instantiate one per thread, or use the
context-manager form (``with RunRegistry(path) as r: ...``) to bound the
lifetime to a single block. WAL mode handles cross-process concurrency
safely.

Schema (current)
----------------

    runs(
        run_id              TEXT PRIMARY KEY,
        kind                TEXT NOT NULL,
        config_json         TEXT NOT NULL,
        seed                INTEGER,
        artifact_paths_json TEXT NOT NULL,
        summary_json        TEXT NOT NULL,
        provenance_json     TEXT NOT NULL,
        created_at          TEXT NOT NULL,
        status              TEXT NOT NULL DEFAULT 'succeeded',
        pillar              TEXT
    )

    artifacts(
        run_id        TEXT NOT NULL,
        name          TEXT NOT NULL,
        path          TEXT NOT NULL,
        content_type  TEXT,
        size_bytes    INTEGER,
        checksum      TEXT,
        created_at    TEXT,
        PRIMARY KEY (run_id, name),
        FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )

    scorecards(
        run_id           TEXT NOT NULL,
        kind             TEXT NOT NULL,
        overall_score    REAL,
        passed           INTEGER,
        thresholds_json  TEXT,
        details_json     TEXT,
        PRIMARY KEY (run_id, kind),
        FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )

    scenarios(
        scenario_id   TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        version       TEXT NOT NULL,
        engine        TEXT NOT NULL,
        params_json   TEXT NOT NULL,
        metadata_json TEXT NOT NULL
    )

    datasets(
        dataset_id    TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        version       TEXT NOT NULL,
        source        TEXT NOT NULL,
        schema_uri    TEXT,
        n_rows        INTEGER,
        n_columns     INTEGER,
        checksum      TEXT,
        metadata_json TEXT NOT NULL
    )

Indexes: ``idx_runs_kind_created``, ``idx_runs_pillar``, ``idx_runs_status``,
``idx_artifacts_run_id``, ``idx_scorecards_kind``.

Backward compatibility
----------------------
The original :meth:`register` / :meth:`get` / :meth:`list` / :meth:`delete`
/ :meth:`compare` methods accept and return :class:`RunArtifact` exactly as
before. Internally, they adapt to the richer :class:`RunRecord` schema
transparently — a ``RunArtifact`` corresponds to a ``RunRecord`` with
``status=SUCCEEDED`` and ``pillar=None``.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from the_similarity.platform.artifacts import RunArtifact, RunKind
from the_similarity.platform.contracts import (
    ArtifactRecord,
    DatasetSpec,
    Feedback,
    RunRecord,
    RunStatus,
    ScenarioSpec,
    ScorecardKind,
    ScorecardSummary,
    Setup,
)


# ---------------------------------------------------------------------------
# Migrations directory + filename pattern. Migrations are plain SQL files
# named ``NNNN_<slug>.sql`` (four-digit version prefix) under
# ``the_similarity/platform/migrations/``. The runner discovers them in
# sorted order and applies each inside its own transaction. Applied
# versions are recorded in a ``schema_migrations`` table so re-runs are
# no-ops.
#
# This is intentionally NOT Alembic — the spine has a tiny migration
# surface (a few setups/feedback tables) and a plain-SQL story keeps the
# DB inspectable from the command line and removes a dependency.
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_FILENAME_PATTERN = re.compile(r"^(\d{4})_.+\.sql$")

_CREATE_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def _split_sql_statements(text: str) -> List[str]:
    """Split a SQL script into individual statements for ``execute()``.

    Why we don't use ``executescript()``: it issues an implicit COMMIT
    before running, which dissolves any active transaction (including a
    SAVEPOINT). For atomic migration application we need to keep the
    outer SAVEPOINT alive, so we drive each statement through
    ``execute()`` instead.

    Splitter rules (deliberately minimal — migration files own the
    invariants, not the splitter):

    1. Strip ``--`` line comments.
    2. Split on ``;`` followed by whitespace/EOL.
    3. Drop empty fragments (trailing semicolons, blank trailing
       segments).

    This is NOT a full SQL parser. Migrations MUST avoid embedded
    semicolons inside string literals or trigger bodies — both are
    unnecessary for the spine's flat schema and would require a real
    tokenizer to handle correctly.
    """
    # Remove ``--`` line comments without touching string literals.
    # SQLite's own statement parser does the right thing here at run
    # time; this strip is purely so the splitter sees clean SQL.
    no_comments = []
    for line in text.splitlines():
        idx = line.find("--")
        if idx == -1:
            no_comments.append(line)
        else:
            no_comments.append(line[:idx])
    cleaned = "\n".join(no_comments)
    return [stmt.strip() for stmt in cleaned.split(";") if stmt.strip()]


# ---------------------------------------------------------------------------
# DDL — all idempotent. The registry supports three DB generations:
#   v0: original schema (only the `runs` table with 8 columns).
#   v1: v0 + `status`, `pillar` columns + sibling tables.
# A v0 DB opened by a v1 registry is migrated in place on first connect.
# ---------------------------------------------------------------------------

_CREATE_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    kind                TEXT NOT NULL,
    config_json         TEXT NOT NULL,
    seed                INTEGER,
    artifact_paths_json TEXT NOT NULL,
    summary_json        TEXT NOT NULL,
    provenance_json     TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'succeeded',
    pillar              TEXT
);
"""

# Composite index on (kind, created_at DESC) covers the dominant read path:
# `SELECT ... WHERE kind = ? ORDER BY created_at DESC LIMIT N` (the `list`
# method's hot path). DESC ordering in the index spec lets SQLite skip a
# sort step. We include kind=None queries by falling back to a plain
# ORDER BY on the unindexed `created_at` column — acceptable because the
# table is small (thousands of rows, not millions) for the foreseeable
# future.
_CREATE_IDX_RUNS_KIND_CREATED = (
    "CREATE INDEX IF NOT EXISTS idx_runs_kind_created ON runs (kind, created_at DESC);"
)
_CREATE_IDX_RUNS_PILLAR = "CREATE INDEX IF NOT EXISTS idx_runs_pillar ON runs (pillar);"
_CREATE_IDX_RUNS_STATUS = "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs (status);"

_CREATE_ARTIFACTS_SQL = """
CREATE TABLE IF NOT EXISTS artifacts (
    run_id        TEXT NOT NULL,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    content_type  TEXT,
    size_bytes    INTEGER,
    checksum      TEXT,
    created_at    TEXT,
    PRIMARY KEY (run_id, name),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
"""
_CREATE_IDX_ARTIFACTS_RUN_ID = (
    "CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts (run_id);"
)

_CREATE_SCORECARDS_SQL = """
CREATE TABLE IF NOT EXISTS scorecards (
    run_id          TEXT NOT NULL,
    kind            TEXT NOT NULL,
    overall_score   REAL,
    passed          INTEGER,
    thresholds_json TEXT,
    details_json    TEXT,
    PRIMARY KEY (run_id, kind),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
"""
_CREATE_IDX_SCORECARDS_KIND = (
    "CREATE INDEX IF NOT EXISTS idx_scorecards_kind ON scorecards (kind);"
)

_CREATE_SCENARIOS_SQL = """
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    version       TEXT NOT NULL,
    engine        TEXT NOT NULL,
    params_json   TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
"""

_CREATE_DATASETS_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id    TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    version       TEXT NOT NULL,
    source        TEXT NOT NULL,
    schema_uri    TEXT,
    n_rows        INTEGER,
    n_columns     INTEGER,
    checksum      TEXT,
    metadata_json TEXT NOT NULL
);
"""

# Upsert statement for runs — preserved columns match the v0 shape plus
# the two new columns. ON CONFLICT replaces every column so partial
# re-registration (with different fields) lands deterministically.
_UPSERT_RUN_SQL = """
INSERT INTO runs (
    run_id, kind, config_json, seed,
    artifact_paths_json, summary_json, provenance_json, created_at,
    status, pillar
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(run_id) DO UPDATE SET
    kind                = excluded.kind,
    config_json         = excluded.config_json,
    seed                = excluded.seed,
    artifact_paths_json = excluded.artifact_paths_json,
    summary_json        = excluded.summary_json,
    provenance_json     = excluded.provenance_json,
    created_at          = excluded.created_at,
    status              = excluded.status,
    pillar              = excluded.pillar
;
"""

_SELECT_RUN_BY_ID_SQL = """
SELECT run_id, kind, config_json, seed,
       artifact_paths_json, summary_json, provenance_json, created_at,
       status, pillar
FROM runs
WHERE run_id = ?
;
"""

# Columns-only SELECT we compose dynamic WHERE clauses against.
_RUN_COLUMNS_SQL = (
    "SELECT run_id, kind, config_json, seed, "
    "artifact_paths_json, summary_json, provenance_json, created_at, "
    "status, pillar FROM runs"
)

_DELETE_RUN_SQL = "DELETE FROM runs WHERE run_id = ?;"

_UPSERT_ARTIFACT_SQL = """
INSERT INTO artifacts (
    run_id, name, path, content_type, size_bytes, checksum, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(run_id, name) DO UPDATE SET
    path         = excluded.path,
    content_type = excluded.content_type,
    size_bytes   = excluded.size_bytes,
    checksum     = excluded.checksum,
    created_at   = excluded.created_at
;
"""

_SELECT_ARTIFACTS_BY_RUN_SQL = (
    "SELECT run_id, name, path, content_type, size_bytes, checksum, created_at "
    "FROM artifacts WHERE run_id = ? ORDER BY name ASC;"
)

_SELECT_ARTIFACT_BY_PK_SQL = (
    "SELECT run_id, name, path, content_type, size_bytes, checksum, created_at "
    "FROM artifacts WHERE run_id = ? AND name = ?;"
)

_DELETE_ARTIFACTS_BY_RUN_SQL = "DELETE FROM artifacts WHERE run_id = ?;"

_UPSERT_SCORECARD_SQL = """
INSERT INTO scorecards (
    run_id, kind, overall_score, passed, thresholds_json, details_json
) VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(run_id, kind) DO UPDATE SET
    overall_score   = excluded.overall_score,
    passed          = excluded.passed,
    thresholds_json = excluded.thresholds_json,
    details_json    = excluded.details_json
;
"""

_SELECT_SCORECARDS_BY_RUN_SQL = (
    "SELECT run_id, kind, overall_score, passed, thresholds_json, details_json "
    "FROM scorecards WHERE run_id = ? ORDER BY kind ASC;"
)

_DELETE_SCORECARDS_BY_RUN_SQL = "DELETE FROM scorecards WHERE run_id = ?;"

_UPSERT_SCENARIO_SQL = """
INSERT INTO scenarios (
    scenario_id, name, version, engine, params_json, metadata_json
) VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(scenario_id) DO UPDATE SET
    name          = excluded.name,
    version       = excluded.version,
    engine        = excluded.engine,
    params_json   = excluded.params_json,
    metadata_json = excluded.metadata_json
;
"""

_SELECT_SCENARIOS_SQL = (
    "SELECT scenario_id, name, version, engine, params_json, metadata_json "
    "FROM scenarios ORDER BY name ASC;"
)

_SELECT_SCENARIO_BY_ID_SQL = (
    "SELECT scenario_id, name, version, engine, params_json, metadata_json "
    "FROM scenarios WHERE scenario_id = ?;"
)

_UPSERT_DATASET_SQL = """
INSERT INTO datasets (
    dataset_id, name, version, source, schema_uri,
    n_rows, n_columns, checksum, metadata_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(dataset_id) DO UPDATE SET
    name          = excluded.name,
    version       = excluded.version,
    source        = excluded.source,
    schema_uri    = excluded.schema_uri,
    n_rows        = excluded.n_rows,
    n_columns     = excluded.n_columns,
    checksum      = excluded.checksum,
    metadata_json = excluded.metadata_json
;
"""

_SELECT_DATASETS_SQL = (
    "SELECT dataset_id, name, version, source, schema_uri, "
    "n_rows, n_columns, checksum, metadata_json FROM datasets ORDER BY name ASC;"
)

_SELECT_DATASET_BY_ID_SQL = (
    "SELECT dataset_id, name, version, source, schema_uri, "
    "n_rows, n_columns, checksum, metadata_json FROM datasets WHERE dataset_id = ?;"
)


# ---------------------------------------------------------------------------
# Setup scanner v1 — setups + feedback SQL.
#
# The schema itself is created by ``migrations/0001_setups.sql`` and
# ``migrations/0002_feedback.sql`` via the migration runner; the
# constants below are the application-level UPSERT/SELECT surface the
# CRUD methods bind against.
#
# ``region_series`` is stored as JSON-encoded TEXT (a list of floats) so
# the DB stays human-inspectable from ``sqlite3 .dump``. A BLOB would be
# more compact but the v1 setups corpus is tiny (setups per user, not
# millions of rows) and grep-ability is worth more than bytes here.
# ---------------------------------------------------------------------------

_UPSERT_SETUP_SQL = """
INSERT INTO setups (
    id, user_id, name, instrument, timeframe,
    region_start_ts, region_end_ts, region_series_json,
    created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    user_id            = excluded.user_id,
    name               = excluded.name,
    instrument         = excluded.instrument,
    timeframe          = excluded.timeframe,
    region_start_ts    = excluded.region_start_ts,
    region_end_ts      = excluded.region_end_ts,
    region_series_json = excluded.region_series_json,
    updated_at         = excluded.updated_at
;
"""

_SELECT_SETUP_BY_ID_SQL = (
    "SELECT id, user_id, name, instrument, timeframe, "
    "region_start_ts, region_end_ts, region_series_json, "
    "created_at, updated_at FROM setups WHERE id = ?;"
)

_SELECT_SETUPS_BY_USER_SQL = (
    "SELECT id, user_id, name, instrument, timeframe, "
    "region_start_ts, region_end_ts, region_series_json, "
    "created_at, updated_at FROM setups WHERE user_id = ? "
    "ORDER BY updated_at DESC LIMIT ? OFFSET ?;"
)

_DELETE_SETUP_SQL = "DELETE FROM setups WHERE id = ?;"

_INSERT_FEEDBACK_SQL = """
INSERT INTO feedback (
    id, user_id, setup_id, alert_id, analog_id,
    kind, thumb, free_text, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    user_id    = excluded.user_id,
    setup_id   = excluded.setup_id,
    alert_id   = excluded.alert_id,
    analog_id  = excluded.analog_id,
    kind       = excluded.kind,
    thumb      = excluded.thumb,
    free_text  = excluded.free_text
;
"""

_SELECT_FEEDBACK_BY_USER_SQL = (
    "SELECT id, user_id, setup_id, alert_id, analog_id, "
    "kind, thumb, free_text, created_at FROM feedback WHERE user_id = ? "
    "ORDER BY created_at DESC LIMIT ? OFFSET ?;"
)

_SELECT_FEEDBACK_BY_USER_SETUP_SQL = (
    "SELECT id, user_id, setup_id, alert_id, analog_id, "
    "kind, thumb, free_text, created_at FROM feedback "
    "WHERE user_id = ? AND setup_id = ? "
    "ORDER BY created_at DESC LIMIT ? OFFSET ?;"
)


# ---------------------------------------------------------------------------
# Deterministic run_id helper
# ---------------------------------------------------------------------------


def derive_run_id(
    kind: Union[RunKind, str],
    config: Dict[str, Any],
    seed: Optional[int] = None,
) -> str:
    """Return a deterministic UUID5-style hex id from (kind, config, seed).

    Use this when reproducibility matters — identical inputs MUST map to
    the same ``run_id`` so rerunning a pipeline does not create duplicate
    rows. For non-reproducible runs, prefer
    :func:`the_similarity.platform.artifacts.new_run_id` (UUID4 hex).

    Implementation note
    -------------------
    We canonicalize ``config`` via ``json.dumps(..., sort_keys=True)`` so
    semantically equal dicts with different key orders produce the same
    hash. The hash itself is ``uuid5`` with a fixed namespace rather than
    blake2b — uuid5 is stable across Python versions and produces a
    32-char hex string symmetric with :func:`new_run_id`.
    """
    kind_value = kind.value if isinstance(kind, RunKind) else str(kind)
    # Canonical form: sort_keys gives key-order invariance; default float
    # formatting is safe because config values coming from JSON are
    # already round-tripped to Python floats with deterministic repr.
    payload = json.dumps(
        {"kind": kind_value, "config": config, "seed": seed},
        sort_keys=True,
        separators=(",", ":"),
    )
    # Fixed namespace UUID — arbitrary but stable so the derivation
    # formula never shifts. Generated once offline via uuid.uuid4().
    namespace = uuid.UUID("6f4c4a64-1f2b-4a11-9f3a-8f0e2a1c3b5d")
    return uuid.uuid5(namespace, payload).hex


# ---------------------------------------------------------------------------
# RunRegistry
# ---------------------------------------------------------------------------


class RunRegistry:
    """SQLite-backed index of every run on the platform spine.

    Lifecycle
    ---------
    Construct with a path to the DB file (created if missing, with parent
    directories). The constructor opens a single :class:`sqlite3.Connection`,
    enables WAL journal mode, and ensures every table and index exists. If
    the DB was created by the v0 registry (only the ``runs`` table with
    eight columns), the constructor migrates it in place by adding the
    ``status`` and ``pillar`` columns and creating the sibling tables.

    Close the connection by calling :meth:`close` or by using the instance
    as a context manager::

        with RunRegistry(db_path) as r:
            r.register_run(record)
            ...
        # connection auto-closed on exit

    Thread safety
    -------------
    A single ``RunRegistry`` is safe to share across threads. Each
    thread that touches ``self._conn`` lazily gets its OWN
    ``sqlite3.Connection`` via ``threading.local``, so SQLite's
    ``check_same_thread`` guard never trips even when FastAPI's
    ``run_in_threadpool`` hops requests across worker threads.

    Why per-thread connections instead of a single shared connection
    with a lock: the registry is consumed by long-lived HTTP handlers
    (see ``state_routes.py``). A single connection + module lock
    serializes every request, negating WAL's reader/writer
    concurrency. Per-thread connections let reads run in parallel and
    WAL's write-ahead log handles the rest. Cross-process concurrency
    is still fine — WAL mode handles that too.
    """

    def __init__(self, db_path: Union[str, Path]) -> None:
        # Keep the original path on the instance for debugging / repr only —
        # SQLite holds the open file descriptor internally once we connect.
        self.db_path: Path = Path(db_path).expanduser()
        # Create parent directories on first use. This makes the registry
        # usable straight from the CLI default (``~/.the_similarity/registry.db``)
        # without a separate `mkdir -p` step.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Per-thread connection storage. The ``_conn`` property below
        # creates a connection on demand for the current thread and
        # caches it here, so callers can still write ``self._conn``
        # everywhere without thinking about the thread model.
        self._thread_local: threading.local = threading.local()
        # Track every connection we hand out so ``close()`` can clean
        # them up cross-thread (each thread's own close on exit is
        # the happy path; this list covers the shutdown edge case).
        self._conns: List[sqlite3.Connection] = []
        self._conns_lock: threading.Lock = threading.Lock()

        # Initialize the schema on the current thread — this also
        # creates the first thread's connection eagerly so any caller
        # assumption that __init__ made the file valid still holds.
        self._init_schema()

    # -- per-thread connection ---------------------------------------------

    @property
    def _conn(self) -> sqlite3.Connection:
        """Return this thread's connection, creating one if needed.

        Each thread that touches the registry lazily gets its own
        ``sqlite3.Connection`` pointed at the same DB file. WAL mode
        keeps concurrent readers/writers from blocking each other at
        the DB level; the per-thread handle keeps Python's sqlite3
        ``check_same_thread`` guard from tripping on a shared one.
        """
        conn = getattr(self._thread_local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path))
            self._configure_connection(conn)
            self._thread_local.conn = conn
            with self._conns_lock:
                self._conns.append(conn)
        return conn

    # -- connection pragma -------------------------------------------------

    @staticmethod
    def _configure_connection(conn: sqlite3.Connection) -> None:
        """Apply the WAL + FK pragmas every registry connection needs.

        Kept separate so tests and downstream tooling that open raw
        connections (e.g. for migrations) pick up the same settings.
        """
        # WAL journal mode is the headline concurrency setting: writers do
        # not block readers and vice versa. Set per-connection (it persists
        # in the DB file but we re-set defensively in case the file was
        # created by a different tool).
        conn.execute("PRAGMA journal_mode=WAL;")
        # Foreign keys default off in sqlite3; enable so ON DELETE CASCADE
        # from `runs` to `artifacts`/`scorecards` actually fires.
        conn.execute("PRAGMA foreign_keys=ON;")

    # -- schema ------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create every table and index if missing; migrate v0 → v1 if needed.

        Idempotent end to end:

        - ``CREATE TABLE IF NOT EXISTS`` for every table.
        - Guarded ``ALTER TABLE ADD COLUMN`` for ``status`` and ``pillar``
          on the original ``runs`` table. SQLite has no
          ``ADD COLUMN IF NOT EXISTS``, so we attempt the alter and
          swallow ``sqlite3.OperationalError`` when the column already
          exists (the error message contains "duplicate column name").
        """
        with self._conn:
            # Create v0 `runs` table if missing. The full DDL includes the
            # v1 columns; existing v0 DBs will skip this and proceed to
            # the ALTER path below.
            self._conn.execute(_CREATE_RUNS_SQL)

            # Migrate legacy DBs: the v0 `runs` table predates `status` /
            # `pillar`. Attempt to add each column; ignore the specific
            # OperationalError SQLite raises when the column already
            # exists so the migration is idempotent on repeated opens.
            self._maybe_add_column(
                "runs", "status", "TEXT NOT NULL DEFAULT 'succeeded'"
            )
            self._maybe_add_column("runs", "pillar", "TEXT")

            # Sibling tables. All idempotent via IF NOT EXISTS.
            self._conn.execute(_CREATE_ARTIFACTS_SQL)
            self._conn.execute(_CREATE_SCORECARDS_SQL)
            self._conn.execute(_CREATE_SCENARIOS_SQL)
            self._conn.execute(_CREATE_DATASETS_SQL)

            # Indexes.
            self._conn.execute(_CREATE_IDX_RUNS_KIND_CREATED)
            self._conn.execute(_CREATE_IDX_RUNS_PILLAR)
            self._conn.execute(_CREATE_IDX_RUNS_STATUS)
            self._conn.execute(_CREATE_IDX_ARTIFACTS_RUN_ID)
            self._conn.execute(_CREATE_IDX_SCORECARDS_KIND)

            # Apply numbered migrations from
            # ``the_similarity/platform/migrations/``. The runner is a no-op
            # for already-applied versions, so calling it on every connect
            # is cheap and keeps the schema state self-healing across
            # parallel agent / orchestrator processes that may share a DB.
            self._apply_migrations()

    def _apply_migrations(self) -> None:
        """Run any pending migrations from the ``migrations/`` directory.

        Discovers files matching ``NNNN_<slug>.sql`` (sorted by version
        prefix), applies each inside its own transaction, and records the
        version in ``schema_migrations``. Already-applied versions are
        skipped — re-running this method is idempotent.

        Failure mode
        ------------
        A migration file that fails to apply rolls back its transaction and
        propagates the exception upward — the registry is then in an
        unusable state for that connection, but the DB on disk remains
        consistent (the partially-applied DDL is rolled back).
        """
        # Bootstrap the version-tracking table itself. Idempotent via
        # ``CREATE TABLE IF NOT EXISTS`` so it's safe to run on every
        # connect.
        self._conn.execute(_CREATE_SCHEMA_MIGRATIONS_SQL)

        # Read the set of already-applied versions so the runner is
        # cheap on warm DBs (one round-trip per connect, not per file).
        applied: set[str] = {
            row[0]
            for row in self._conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }

        # Discover migration files. ``sorted()`` over filenames is
        # equivalent to numeric sort because the four-digit prefix is
        # zero-padded.
        if not _MIGRATIONS_DIR.is_dir():
            return
        for path in sorted(_MIGRATIONS_DIR.iterdir()):
            match = _MIGRATION_FILENAME_PATTERN.match(path.name)
            if match is None:
                continue
            version = match.group(1)
            if version in applied:
                continue

            # Apply the file's SQL inside one transaction. We deliberately
            # avoid ``executescript()`` here because it issues its own
            # COMMIT before running, which would dissolve any outer
            # transaction (including the SAVEPOINT we use for atomicity).
            # Instead we split on semicolons, strip comments, and run each
            # statement via ``execute()`` inside one explicit savepoint so
            # the DDL + the version-record INSERT land atomically.
            sql_text = path.read_text(encoding="utf-8")
            statements = _split_sql_statements(sql_text)
            try:
                self._conn.execute("SAVEPOINT migration")
                for stmt in statements:
                    self._conn.execute(stmt)
                self._conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) "
                    "VALUES (?, ?)",
                    (
                        version,
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    ),
                )
                self._conn.execute("RELEASE SAVEPOINT migration")
            except Exception:
                # Roll back the savepoint so the DB returns to its
                # pre-migration state, then release the named point.
                # ``ROLLBACK TO`` does NOT release the savepoint — the
                # subsequent RELEASE is required to clean up the named
                # frame on the savepoint stack.
                self._conn.execute("ROLLBACK TO SAVEPOINT migration")
                self._conn.execute("RELEASE SAVEPOINT migration")
                raise

    def _maybe_add_column(self, table: str, column: str, decl: str) -> None:
        """``ALTER TABLE table ADD COLUMN column decl`` — idempotent.

        SQLite's ``ALTER TABLE ... ADD COLUMN`` has no IF NOT EXISTS
        clause before version 3.35, and even recent versions don't ship
        it for the ADD COLUMN variant. We catch
        :class:`sqlite3.OperationalError` and re-raise unless the message
        signals the "duplicate column name" case — this narrows the
        silent-swallow surface so genuine DDL errors still fail loud.
        """
        try:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        except sqlite3.OperationalError as exc:
            # The message on modern SQLite is
            # 'duplicate column name: <col>'. Be defensive and also accept
            # variants that some builds produce.
            msg = str(exc).lower()
            if "duplicate column" in msg or "already exists" in msg:
                return
            raise

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> "RunRegistry":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Close on context exit regardless of exception state — the
        # connection holds a file descriptor that should not leak.
        self.close()

    def close(self) -> None:
        """Close every per-thread SQLite connection we've opened.

        Safe to call multiple times. Each thread that touched this
        registry may have opened its own connection (see the `_conn`
        property docstring); we iterate the tracking list and close
        them all. Subsequent operations on this instance will raise
        ``sqlite3.ProgrammingError`` on any attempt to reuse the
        closed handles.
        """
        with self._conns_lock:
            conns = list(self._conns)
            self._conns.clear()
        for conn in conns:
            try:
                conn.close()
            except sqlite3.ProgrammingError:
                # Already closed — make close() idempotent.
                pass
        # Drop the thread-local reference on this thread. Other
        # threads' TLS slots will clear naturally on next access
        # (the property checks for a closed connection? no — once
        # closed, calls raise. Consumers should not reuse the
        # registry after close()).
        if hasattr(self._thread_local, "conn"):
            del self._thread_local.conn

    # ======================================================================
    # Runs — new RunRecord API
    # ======================================================================

    def register_run(self, record: RunRecord) -> str:
        """Insert or update a run row. Returns ``record.run_id``.

        Idempotent on ``run_id`` — re-registering replaces every column.
        This matches the legacy :meth:`register` semantics so callers
        migrating to the new API keep the same upsert guarantees.
        """
        config_json = json.dumps(record.config, separators=(",", ":"))
        paths_json = json.dumps(record.artifact_paths, separators=(",", ":"))
        summary_json = json.dumps(record.summary, separators=(",", ":"))
        provenance_json = json.dumps(record.provenance, separators=(",", ":"))

        with self._conn:
            self._conn.execute(
                _UPSERT_RUN_SQL,
                (
                    record.run_id,
                    record.kind.value,
                    config_json,
                    record.seed,
                    paths_json,
                    summary_json,
                    provenance_json,
                    record.created_at,
                    record.status.value,
                    record.pillar,
                ),
            )
        return record.run_id

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """Return the :class:`RunRecord` for ``run_id`` or ``None`` if absent."""
        cursor = self._conn.execute(_SELECT_RUN_BY_ID_SQL, (run_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_run_record(row)

    def list_runs(
        self,
        kind: Optional[Union[RunKind, str]] = None,
        pillar: Optional[str] = None,
        status: Optional[Union[RunStatus, str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RunRecord]:
        """Return runs newest-first, with optional filters.

        Filters are composed **dynamically and parameterized** — never
        string-concatenated into the SQL — so user-supplied values cannot
        inject. Pagination via ``limit`` / ``offset``.
        """
        # Build WHERE clause dynamically. Each (clause, param) pair is
        # appended only when the caller passed a non-None filter, then
        # joined with AND and interpolated into the SELECT. The literal
        # column names are safe (they are module-owned constants); the
        # values are always bound as parameters.
        clauses: List[str] = []
        params: List[Any] = []
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind.value if isinstance(kind, RunKind) else str(kind))
        if pillar is not None:
            clauses.append("pillar = ?")
            params.append(pillar)
        if status is not None:
            clauses.append("status = ?")
            params.append(
                status.value if isinstance(status, RunStatus) else str(status)
            )

        sql = _RUN_COLUMNS_SQL
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        cursor = self._conn.execute(sql, tuple(params))
        return [self._row_to_run_record(row) for row in cursor.fetchall()]

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and cascade to its artifacts + scorecards.

        Returns ``True`` if a row was removed, ``False`` otherwise.
        Foreign keys are enabled per connection so the cascade fires at
        the DB layer, but we also issue explicit deletes so the behavior
        is robust even if FK enforcement is ever disabled (some tooling
        opens the DB without the PRAGMA).
        """
        with self._conn:
            # Explicit cascades first — safe even if FK PRAGMA is off.
            self._conn.execute(_DELETE_ARTIFACTS_BY_RUN_SQL, (run_id,))
            self._conn.execute(_DELETE_SCORECARDS_BY_RUN_SQL, (run_id,))
            cursor = self._conn.execute(_DELETE_RUN_SQL, (run_id,))
        return cursor.rowcount > 0

    # ======================================================================
    # Artifacts
    # ======================================================================

    def register_artifact(self, artifact: ArtifactRecord) -> None:
        """Insert or update one artifact row (composite PK ``(run_id, name)``)."""
        with self._conn:
            self._conn.execute(
                _UPSERT_ARTIFACT_SQL,
                (
                    artifact.run_id,
                    artifact.name,
                    artifact.path,
                    artifact.content_type,
                    artifact.size_bytes,
                    artifact.checksum,
                    artifact.created_at,
                ),
            )

    def list_artifacts(self, run_id: str) -> List[ArtifactRecord]:
        """Return all artifacts for ``run_id`` ordered by ``name`` ASC."""
        cursor = self._conn.execute(_SELECT_ARTIFACTS_BY_RUN_SQL, (run_id,))
        return [self._row_to_artifact_record(row) for row in cursor.fetchall()]

    def get_artifact(self, run_id: str, name: str) -> Optional[ArtifactRecord]:
        """Return a single artifact by ``(run_id, name)`` or ``None`` if absent."""
        cursor = self._conn.execute(_SELECT_ARTIFACT_BY_PK_SQL, (run_id, name))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_artifact_record(row)

    # ======================================================================
    # Scorecards
    # ======================================================================

    def register_scorecard(self, summary: ScorecardSummary) -> None:
        """Insert or update one scorecard row (composite PK ``(run_id, kind)``)."""
        thresholds_json = json.dumps(summary.thresholds, separators=(",", ":"))
        details_json = json.dumps(summary.details, separators=(",", ":"))
        # Store `passed` as INTEGER (0/1) or NULL — SQLite has no native
        # boolean type. Convert back to bool on read.
        passed_int: Optional[int]
        if summary.passed is None:
            passed_int = None
        else:
            passed_int = 1 if summary.passed else 0

        with self._conn:
            self._conn.execute(
                _UPSERT_SCORECARD_SQL,
                (
                    summary.run_id,
                    summary.kind.value,
                    summary.overall_score,
                    passed_int,
                    thresholds_json,
                    details_json,
                ),
            )

    def get_scorecards(self, run_id: str) -> List[ScorecardSummary]:
        """Return all scorecards for ``run_id`` ordered by kind ASC."""
        cursor = self._conn.execute(_SELECT_SCORECARDS_BY_RUN_SQL, (run_id,))
        return [self._row_to_scorecard_summary(row) for row in cursor.fetchall()]

    # ======================================================================
    # Scenarios
    # ======================================================================

    def register_scenario(self, spec: ScenarioSpec) -> str:
        """Insert or update a scenario row. Returns ``spec.scenario_id``."""
        with self._conn:
            self._conn.execute(
                _UPSERT_SCENARIO_SQL,
                (
                    spec.scenario_id,
                    spec.name,
                    spec.version,
                    spec.engine,
                    json.dumps(spec.params, separators=(",", ":")),
                    json.dumps(spec.metadata, separators=(",", ":")),
                ),
            )
        return spec.scenario_id

    def list_scenarios(self) -> List[ScenarioSpec]:
        """Return all registered scenarios ordered by name ASC."""
        cursor = self._conn.execute(_SELECT_SCENARIOS_SQL)
        return [self._row_to_scenario_spec(row) for row in cursor.fetchall()]

    def get_scenario(self, scenario_id: str) -> Optional[ScenarioSpec]:
        """Return a single scenario by ``scenario_id`` or ``None`` if absent."""
        cursor = self._conn.execute(_SELECT_SCENARIO_BY_ID_SQL, (scenario_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_scenario_spec(row)

    # ======================================================================
    # Datasets
    # ======================================================================

    def register_dataset(self, spec: DatasetSpec) -> str:
        """Insert or update a dataset row. Returns ``spec.dataset_id``."""
        with self._conn:
            self._conn.execute(
                _UPSERT_DATASET_SQL,
                (
                    spec.dataset_id,
                    spec.name,
                    spec.version,
                    spec.source,
                    spec.schema_uri,
                    spec.n_rows,
                    spec.n_columns,
                    spec.checksum,
                    json.dumps(spec.metadata, separators=(",", ":")),
                ),
            )
        return spec.dataset_id

    def list_datasets(self) -> List[DatasetSpec]:
        """Return all registered datasets ordered by name ASC."""
        cursor = self._conn.execute(_SELECT_DATASETS_SQL)
        return [self._row_to_dataset_spec(row) for row in cursor.fetchall()]

    def get_dataset(self, dataset_id: str) -> Optional[DatasetSpec]:
        """Return a single dataset by ``dataset_id`` or ``None`` if absent."""
        cursor = self._conn.execute(_SELECT_DATASET_BY_ID_SQL, (dataset_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dataset_spec(row)

    # ======================================================================
    # Setup scanner v1 — Setup CRUD
    #
    # The setups table is created by ``migrations/0001_setups.sql``. These
    # methods are the application API for the personalized setup scanner;
    # they upsert by ``Setup.id``, list per-user, and cascade-delete via
    # the FK on ``feedback.setup_id``.
    # ======================================================================

    def create_setup(self, setup: Setup) -> str:
        """Insert or update a :class:`Setup`. Returns ``setup.id``.

        Idempotent on ``id`` — re-creating with the same ID replaces every
        column except ``created_at`` (which is preserved via SQLite's
        ON CONFLICT semantics — see the UPSERT statement; ``created_at``
        is intentionally absent from the SET clause).

        Auto-stamps ``created_at`` and ``updated_at`` when blank.
        Mutates the input dataclass in-place so callers see the stamped
        values. Empty ``user_id`` raises :class:`ValueError` — multi-tenant
        scoping is the whole point of the table.
        """
        if not setup.user_id:
            raise ValueError("Setup.user_id is required")
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not setup.created_at:
            setup.created_at = now_iso
        # Always bump updated_at on write — caller-supplied values are
        # respected (for tests / data imports) but we default to "now"
        # which is what 99% of callers want.
        setup.updated_at = setup.updated_at or now_iso

        # Region series is JSON-encoded text. Empty list serializes to
        # "[]" which is valid JSON and round-trips cleanly.
        series_json = json.dumps(list(setup.region_series), separators=(",", ":"))

        with self._conn:
            self._conn.execute(
                _UPSERT_SETUP_SQL,
                (
                    setup.id,
                    setup.user_id,
                    setup.name,
                    setup.instrument,
                    setup.timeframe,
                    setup.region_start_ts,
                    setup.region_end_ts,
                    series_json,
                    setup.created_at,
                    setup.updated_at,
                ),
            )
        return setup.id

    def get_setup(self, setup_id: str) -> Optional[Setup]:
        """Return the :class:`Setup` for ``setup_id`` or ``None`` if absent."""
        cursor = self._conn.execute(_SELECT_SETUP_BY_ID_SQL, (setup_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_setup(row)

    def list_setups(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Setup]:
        """Return setups owned by ``user_id``, newest-updated first.

        ``user_id`` is **required** — listing across users would leak
        between tenants. The index ``idx_setups_user_id`` covers the
        WHERE clause; the ORDER BY uses the table's ``updated_at`` column
        directly (no covering index, but the table is small).
        """
        if not user_id:
            raise ValueError("user_id is required for list_setups")
        cursor = self._conn.execute(
            _SELECT_SETUPS_BY_USER_SQL, (user_id, limit, offset)
        )
        return [self._row_to_setup(row) for row in cursor.fetchall()]

    def delete_setup(self, setup_id: str) -> bool:
        """Delete a setup and cascade to its feedback rows.

        Returns ``True`` if a row was removed, ``False`` otherwise. The
        ``ON DELETE CASCADE`` on ``feedback.setup_id`` fires at the DB
        layer (foreign keys are enabled via the connection PRAGMA).
        """
        with self._conn:
            cursor = self._conn.execute(_DELETE_SETUP_SQL, (setup_id,))
        return cursor.rowcount > 0

    # ======================================================================
    # Setup scanner v1 — Feedback CRUD
    #
    # Persisted from day 1 even when v1 doesn't compute on the rows yet.
    # See ``vision/personalized_setup_scanner.md`` (the goodrun feedback
    # moat) for why these rows MUST land at insert time, regardless of
    # whether the v1 filter logic uses them.
    # ======================================================================

    def record_feedback(self, feedback: Feedback) -> str:
        """Insert (or upsert by ``id``) a :class:`Feedback` row.

        Validates ``kind ∈ {"alert", "analog"}`` and
        ``thumb ∈ {"up", "down"}`` to catch typos before they corrupt
        the goodrun training set. Auto-stamps ``created_at`` if blank.
        """
        if feedback.kind not in ("alert", "analog"):
            raise ValueError(
                f"Feedback.kind must be 'alert' or 'analog', got {feedback.kind!r}"
            )
        if feedback.thumb not in ("up", "down"):
            raise ValueError(
                f"Feedback.thumb must be 'up' or 'down', got {feedback.thumb!r}"
            )
        if not feedback.user_id:
            raise ValueError("Feedback.user_id is required")
        if not feedback.setup_id:
            raise ValueError("Feedback.setup_id is required")
        if not feedback.created_at:
            feedback.created_at = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
        with self._conn:
            self._conn.execute(
                _INSERT_FEEDBACK_SQL,
                (
                    feedback.id,
                    feedback.user_id,
                    feedback.setup_id,
                    feedback.alert_id,
                    feedback.analog_id,
                    feedback.kind,
                    feedback.thumb,
                    feedback.free_text,
                    feedback.created_at,
                ),
            )
        return feedback.id

    def list_feedback(
        self,
        user_id: str,
        setup_id: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Feedback]:
        """Return feedback rows for ``user_id``, optionally filtered by setup.

        ``user_id`` is required (multi-tenant scope). When ``setup_id`` is
        provided, the result is limited to feedback on that setup —
        enabling the per-setup goodrun aggregation in
        :func:`the_similarity.core.scorer.compute_goodrun_score`.
        """
        if not user_id:
            raise ValueError("user_id is required for list_feedback")
        if setup_id is None:
            cursor = self._conn.execute(
                _SELECT_FEEDBACK_BY_USER_SQL, (user_id, limit, offset)
            )
        else:
            cursor = self._conn.execute(
                _SELECT_FEEDBACK_BY_USER_SETUP_SQL,
                (user_id, setup_id, limit, offset),
            )
        return [self._row_to_feedback(row) for row in cursor.fetchall()]

    # ======================================================================
    # Legacy RunArtifact API — kept byte-compatible with the pre-spine
    # registry so existing callers (CLI subcommands, tests, external
    # scripts) keep working. These wrappers adapt RunArtifact ↔ RunRecord.
    # ======================================================================

    def register(self, artifact: RunArtifact) -> str:
        """Legacy wrapper — registers a :class:`RunArtifact` as a RunRecord.

        Status defaults to ``SUCCEEDED`` and ``pillar`` to ``None``; callers
        needing richer fields must switch to :meth:`register_run`.
        """
        record = RunRecord(
            run_id=artifact.run_id,
            kind=artifact.kind,
            config=artifact.config,
            seed=artifact.seed,
            artifact_paths=artifact.artifact_paths,
            summary=artifact.summary,
            provenance=artifact.provenance,
            created_at=artifact.created_at,
            status=RunStatus.SUCCEEDED,
            pillar=None,
        )
        return self.register_run(record)

    def get(self, run_id: str) -> Optional[RunArtifact]:
        """Legacy wrapper — returns a :class:`RunArtifact` view of the row."""
        record = self.get_run(run_id)
        if record is None:
            return None
        return self._record_to_artifact(record)

    def list(
        self,
        kind: Optional[RunKind] = None,
        limit: int = 100,
    ) -> List[RunArtifact]:
        """Legacy wrapper — RunArtifact list, no pillar/status filters.

        New callers should prefer :meth:`list_runs` for pillar/status/offset
        support. This wrapper is pinned to the pre-spine call signature to
        keep older tests and the CLI untouched.
        """
        records = self.list_runs(kind=kind, limit=limit, offset=0)
        return [self._record_to_artifact(r) for r in records]

    def delete(self, run_id: str) -> bool:
        """Legacy wrapper — alias of :meth:`delete_run`."""
        return self.delete_run(run_id)

    def compare(self, run_id_a: str, run_id_b: str) -> Dict[str, Any]:
        """Compare the ``summary`` dicts of two runs.

        Semantics preserved from the pre-spine registry — returns
        ``{"a": summary_a, "b": summary_b, "diff": {...}}``. Fails loud
        via ``KeyError`` if either run_id is missing.
        """
        a = self.get(run_id_a)
        b = self.get(run_id_b)
        if a is None:
            raise KeyError(f"run_id not found: {run_id_a}")
        if b is None:
            raise KeyError(f"run_id not found: {run_id_b}")

        diff: Dict[str, Any] = {}
        # Sorted for deterministic output — the CLI pretty-prints this and
        # callers rely on stable ordering across runs.
        for key in sorted(set(a.summary.keys()) | set(b.summary.keys())):
            a_val = a.summary.get(key)
            b_val = b.summary.get(key)
            if a_val != b_val:
                diff[key] = (a_val, b_val)

        return {"a": a.summary, "b": b.summary, "diff": diff}

    # ======================================================================
    # Row unpackers — fixed column order matches the SELECT statements
    # above. Keeping them static avoids per-row Row-object overhead on the
    # hot list/get path.
    # ======================================================================

    @staticmethod
    def _row_to_run_record(row: Tuple[Any, ...]) -> RunRecord:
        (
            run_id,
            kind_str,
            config_json,
            seed,
            artifact_paths_json,
            summary_json,
            provenance_json,
            created_at,
            status_str,
            pillar,
        ) = row
        return RunRecord(
            run_id=run_id,
            kind=RunKind(kind_str),
            config=json.loads(config_json),
            seed=seed,
            artifact_paths=json.loads(artifact_paths_json),
            summary=json.loads(summary_json),
            provenance=json.loads(provenance_json),
            created_at=created_at,
            status=RunStatus(status_str) if status_str else RunStatus.SUCCEEDED,
            pillar=pillar,
        )

    @staticmethod
    def _record_to_artifact(record: RunRecord) -> RunArtifact:
        """Drop the spine-only fields (status/pillar) and return a RunArtifact."""
        return RunArtifact(
            run_id=record.run_id,
            kind=record.kind,
            config=record.config,
            seed=record.seed,
            artifact_paths=record.artifact_paths,
            summary=record.summary,
            provenance=record.provenance,
            created_at=record.created_at,
        )

    @staticmethod
    def _row_to_artifact_record(row: Tuple[Any, ...]) -> ArtifactRecord:
        run_id, name, path, content_type, size_bytes, checksum, created_at = row
        return ArtifactRecord(
            run_id=run_id,
            name=name,
            path=path,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum=checksum,
            created_at=created_at,
        )

    @staticmethod
    def _row_to_scorecard_summary(row: Tuple[Any, ...]) -> ScorecardSummary:
        run_id, kind_str, overall_score, passed_int, thresholds_json, details_json = row
        # Convert the INTEGER back to bool — None stays None.
        passed: Optional[bool]
        if passed_int is None:
            passed = None
        else:
            passed = bool(passed_int)
        return ScorecardSummary(
            run_id=run_id,
            kind=ScorecardKind(kind_str),
            overall_score=overall_score,
            passed=passed,
            thresholds=json.loads(thresholds_json) if thresholds_json else {},
            details=json.loads(details_json) if details_json else {},
        )

    @staticmethod
    def _row_to_scenario_spec(row: Tuple[Any, ...]) -> ScenarioSpec:
        scenario_id, name, version, engine, params_json, metadata_json = row
        return ScenarioSpec(
            scenario_id=scenario_id,
            name=name,
            version=version,
            engine=engine,
            params=json.loads(params_json) if params_json else {},
            metadata=json.loads(metadata_json) if metadata_json else {},
        )

    @staticmethod
    def _row_to_dataset_spec(row: Tuple[Any, ...]) -> DatasetSpec:
        (
            dataset_id,
            name,
            version,
            source,
            schema_uri,
            n_rows,
            n_columns,
            checksum,
            metadata_json,
        ) = row
        return DatasetSpec(
            dataset_id=dataset_id,
            name=name,
            version=version,
            source=source,
            schema_uri=schema_uri,
            n_rows=n_rows,
            n_columns=n_columns,
            checksum=checksum,
            metadata=json.loads(metadata_json) if metadata_json else {},
        )

    @staticmethod
    def _row_to_setup(row: Tuple[Any, ...]) -> Setup:
        """Hydrate a :class:`Setup` from a row matching ``_SELECT_SETUP_*_SQL``.

        ``region_series_json`` is JSON-decoded into a list of floats.
        Malformed JSON propagates as a ``json.JSONDecodeError`` — corrupt
        rows fail loud rather than silently returning an empty series.
        """
        (
            id_,
            user_id,
            name,
            instrument,
            timeframe,
            region_start_ts,
            region_end_ts,
            region_series_json,
            created_at,
            updated_at,
        ) = row
        return Setup(
            id=id_,
            user_id=user_id,
            name=name,
            instrument=instrument,
            timeframe=timeframe,
            region_start_ts=region_start_ts,
            region_end_ts=region_end_ts,
            region_series=json.loads(region_series_json) if region_series_json else [],
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _row_to_feedback(row: Tuple[Any, ...]) -> Feedback:
        """Hydrate a :class:`Feedback` from a row matching ``_SELECT_FEEDBACK_*_SQL``."""
        (
            id_,
            user_id,
            setup_id,
            alert_id,
            analog_id,
            kind,
            thumb,
            free_text,
            created_at,
        ) = row
        return Feedback(
            id=id_,
            user_id=user_id,
            setup_id=setup_id,
            alert_id=alert_id,
            analog_id=analog_id,
            kind=kind,
            thumb=thumb,
            free_text=free_text,
            created_at=created_at,
        )


__all__ = ["RunRegistry", "derive_run_id"]
