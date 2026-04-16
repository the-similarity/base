"""SQLite-backed run registry — the platform's persistent memory.

Every run that lands a :class:`~the_similarity.platform.artifacts.RunArtifact`
also lands a row in this registry. The registry is the single index downstream
surfaces (CLI, eventual HTTP API, eval harness, UI) consult to answer:

- "What runs of kind X exist, newest first?"
- "Show me the full artifact for run_id Y."
- "How does run A's summary differ from run B's?"

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
- **Upsert on run_id** — re-registering the same run_id is a *replace*, not
  an error. Re-registration is a normal path: a runner may register early
  with partial summary, then the eval harness re-registers later with
  enriched summary fields.

Concurrency
-----------
Each :class:`RunRegistry` instance owns one ``sqlite3.Connection``. The
connection is *not* thread-safe — instantiate one per thread, or use the
context-manager form (``with RunRegistry(path) as r: ...``) to bound the
lifetime to a single block. WAL mode handles cross-process concurrency
safely.

Schema versioning
-----------------
There is no version column today. The schema is:

    CREATE TABLE runs (
        run_id              TEXT PRIMARY KEY,
        kind                TEXT NOT NULL,
        config_json         TEXT NOT NULL,
        seed                INTEGER,
        artifact_paths_json TEXT NOT NULL,
        summary_json        TEXT NOT NULL,
        provenance_json     TEXT NOT NULL,
        created_at          TEXT NOT NULL
    );
    CREATE INDEX idx_runs_kind_created ON runs (kind, created_at DESC);

If we ever need a migration, add a ``schema_version`` table and bump it.
For now the YAGNI approach wins.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from the_similarity.platform.artifacts import RunArtifact, RunKind


# ---------------------------------------------------------------------------
# DDL — kept inline so the schema lives next to the class that depends on it.
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    kind                TEXT NOT NULL,
    config_json         TEXT NOT NULL,
    seed                INTEGER,
    artifact_paths_json TEXT NOT NULL,
    summary_json        TEXT NOT NULL,
    provenance_json     TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
"""

# Composite index on (kind, created_at DESC) covers the dominant read path:
# `SELECT ... WHERE kind = ? ORDER BY created_at DESC LIMIT N` (the `list`
# method's hot path). DESC ordering in the index spec lets SQLite skip a
# sort step. We include kind=None queries by falling back to a plain
# ORDER BY on the unindexed `created_at` column — acceptable because the
# table is small (thousands of rows, not millions) for the foreseeable
# future.
_CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_runs_kind_created "
    "ON runs (kind, created_at DESC);"
)

_UPSERT_SQL = """
INSERT INTO runs (
    run_id, kind, config_json, seed,
    artifact_paths_json, summary_json, provenance_json, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(run_id) DO UPDATE SET
    kind                = excluded.kind,
    config_json         = excluded.config_json,
    seed                = excluded.seed,
    artifact_paths_json = excluded.artifact_paths_json,
    summary_json        = excluded.summary_json,
    provenance_json     = excluded.provenance_json,
    created_at          = excluded.created_at
;
"""

_SELECT_BY_ID_SQL = """
SELECT run_id, kind, config_json, seed,
       artifact_paths_json, summary_json, provenance_json, created_at
FROM runs
WHERE run_id = ?
;
"""

_SELECT_LIST_SQL = """
SELECT run_id, kind, config_json, seed,
       artifact_paths_json, summary_json, provenance_json, created_at
FROM runs
ORDER BY created_at DESC
LIMIT ?
;
"""

_SELECT_LIST_BY_KIND_SQL = """
SELECT run_id, kind, config_json, seed,
       artifact_paths_json, summary_json, provenance_json, created_at
FROM runs
WHERE kind = ?
ORDER BY created_at DESC
LIMIT ?
;
"""

_DELETE_SQL = "DELETE FROM runs WHERE run_id = ?;"


# ---------------------------------------------------------------------------
# RunRegistry
# ---------------------------------------------------------------------------


class RunRegistry:
    """SQLite-backed index of every :class:`RunArtifact` produced by the platform.

    Lifecycle
    ---------
    Construct with a path to the DB file (created if missing, with parent
    directories). The constructor opens a single :class:`sqlite3.Connection`,
    enables WAL journal mode, and ensures the schema and index exist. Close
    the connection by calling :meth:`close` or by using the instance as a
    context manager::

        with RunRegistry(db_path) as r:
            r.register(artifact)
            ...
        # connection auto-closed on exit

    Thread safety
    -------------
    The underlying ``sqlite3.Connection`` is not safe for concurrent use
    across threads (Python's sqlite3 module enforces this with
    ``check_same_thread=True`` by default). Use one registry instance per
    thread. Cross-*process* concurrency is fine — WAL mode lets readers and
    writers proceed without blocking.
    """

    def __init__(self, db_path: Union[str, Path]) -> None:
        # Keep the original path on the instance for debugging / repr only —
        # SQLite holds the open file descriptor internally once we connect.
        self.db_path: Path = Path(db_path).expanduser()
        # Create parent directories on first use. This makes the registry
        # usable straight from the CLI default (``~/.the_similarity/registry.db``)
        # without a separate `mkdir -p` step.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # We pass the path as a string because sqlite3 historically accepted
        # only str (PEP 519 PathLike support landed in 3.7 but third-party
        # forks may lag — stringifying is the safest portable form).
        self._conn: sqlite3.Connection = sqlite3.connect(str(self.db_path))
        # WAL journal mode is the headline concurrency setting: writers do
        # not block readers and vice versa. Set per-connection (it persists
        # in the DB file but we re-set defensively in case the file was
        # created by a different tool).
        self._conn.execute("PRAGMA journal_mode=WAL;")
        # Foreign keys default off in sqlite3; enable for forward-compat in
        # case we ever add a child table referencing run_id.
        self._conn.execute("PRAGMA foreign_keys=ON;")

        self._init_schema()

    # -- schema ------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create the ``runs`` table and ``idx_runs_kind_created`` if missing.

        Idempotent — uses ``IF NOT EXISTS`` so repeated construction against
        the same DB file is a no-op.
        """
        with self._conn:
            self._conn.execute(_CREATE_TABLE_SQL)
            self._conn.execute(_CREATE_INDEX_SQL)

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> "RunRegistry":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Close on context exit regardless of exception state — the
        # connection holds a file descriptor that should not leak.
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection.

        Safe to call multiple times; subsequent operations on this instance
        will raise ``sqlite3.ProgrammingError`` from the closed connection.
        """
        try:
            self._conn.close()
        except sqlite3.ProgrammingError:
            # Already closed — make close() idempotent.
            pass

    # -- write -------------------------------------------------------------

    def register(self, artifact: RunArtifact) -> str:
        """Insert or update a row for ``artifact.run_id``.

        Re-registering the same ``run_id`` is intentionally an *upsert* (not
        an error): runners may register a partial artifact early in the
        pipeline and the eval harness may re-register the same run_id later
        with enriched ``summary``. Callers that want hard uniqueness must
        check :meth:`get` first.

        Returns the ``run_id`` for chaining convenience (matches the CLI's
        contract of printing the id on success).
        """
        # Serialize JSON columns once. We use compact separators to keep DB
        # size down — humans inspect via the CLI's `show`, not by reading
        # the JSON column directly.
        config_json = json.dumps(artifact.config, separators=(",", ":"))
        paths_json = json.dumps(artifact.artifact_paths, separators=(",", ":"))
        summary_json = json.dumps(artifact.summary, separators=(",", ":"))
        provenance_json = json.dumps(artifact.provenance, separators=(",", ":"))

        with self._conn:
            self._conn.execute(
                _UPSERT_SQL,
                (
                    artifact.run_id,
                    artifact.kind.value,
                    config_json,
                    artifact.seed,
                    paths_json,
                    summary_json,
                    provenance_json,
                    artifact.created_at,
                ),
            )
        return artifact.run_id

    # -- read --------------------------------------------------------------

    def get(self, run_id: str) -> Optional[RunArtifact]:
        """Return the :class:`RunArtifact` for ``run_id``, or ``None`` if absent."""
        cursor = self._conn.execute(_SELECT_BY_ID_SQL, (run_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_artifact(row)

    def list(
        self,
        kind: Optional[RunKind] = None,
        limit: int = 100,
    ) -> List[RunArtifact]:
        """Return runs newest-first, optionally filtered by ``kind``.

        ``limit`` caps the number of rows returned (default 100). The
        :class:`RunRegistry` makes no attempt to paginate beyond that — for
        the foreseeable platform scale (thousands of runs) the limit + a
        kind filter is enough to keep the CLI responsive.
        """
        if kind is None:
            cursor = self._conn.execute(_SELECT_LIST_SQL, (limit,))
        else:
            cursor = self._conn.execute(_SELECT_LIST_BY_KIND_SQL, (kind.value, limit))
        return [self._row_to_artifact(row) for row in cursor.fetchall()]

    # -- delete ------------------------------------------------------------

    def delete(self, run_id: str) -> bool:
        """Delete the row for ``run_id``. Returns ``True`` if a row was removed.

        Idempotent: deleting a non-existent run_id returns ``False`` and
        does not raise. We rely on ``cursor.rowcount`` rather than a
        pre-flight ``SELECT`` to keep the operation atomic.
        """
        with self._conn:
            cursor = self._conn.execute(_DELETE_SQL, (run_id,))
        return cursor.rowcount > 0

    # -- compare -----------------------------------------------------------

    def compare(self, run_id_a: str, run_id_b: str) -> Dict[str, Any]:
        """Compare the ``summary`` dicts of two runs.

        Returns a dict with three keys::

            {
              "a":    <summary dict of run_id_a>,
              "b":    <summary dict of run_id_b>,
              "diff": {key: (a_value, b_value), ...}
            }

        ``diff`` covers the *union* of keys across both summaries; equal
        values are skipped, and a missing key on one side appears as
        ``None`` for that side. This is intentionally simple — it is the
        90%-case readout for "did the new run improve over the old one?".
        Callers needing structural diffs over ``config`` or ``provenance``
        should call :meth:`get` and compare directly.

        Raises ``KeyError`` if either run_id is missing — fail-loud so
        callers do not silently compare against an empty summary.
        """
        a = self.get(run_id_a)
        b = self.get(run_id_b)
        if a is None:
            raise KeyError(f"run_id not found: {run_id_a}")
        if b is None:
            raise KeyError(f"run_id not found: {run_id_b}")

        diff: Dict[str, Any] = {}
        # Iterate over the union of keys so a key present in only one side
        # still surfaces in the diff (with ``None`` filling the missing
        # side). Sort for deterministic output — important because the CLI
        # pretty-prints this dict and we want stable diffs across runs.
        for key in sorted(set(a.summary.keys()) | set(b.summary.keys())):
            a_val = a.summary.get(key)
            b_val = b.summary.get(key)
            if a_val != b_val:
                diff[key] = (a_val, b_val)

        return {"a": a.summary, "b": b.summary, "diff": diff}

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _row_to_artifact(row: tuple) -> RunArtifact:
        """Reconstruct a :class:`RunArtifact` from a raw sqlite3 row tuple.

        Column order is fixed by the ``SELECT`` statements above; if those
        change this method must change in lockstep. Keeping the unpacking
        positional (rather than using a row factory) avoids the per-row
        overhead of a Row object on the hot list/get path.
        """
        (
            run_id,
            kind_str,
            config_json,
            seed,
            artifact_paths_json,
            summary_json,
            provenance_json,
            created_at,
        ) = row
        # Round-trip via from_dict so any future enrichment (validation,
        # default coercion) lands in one place.
        return RunArtifact.from_dict(
            {
                "run_id": run_id,
                "kind": kind_str,
                "config": json.loads(config_json),
                "seed": seed,
                "artifact_paths": json.loads(artifact_paths_json),
                "summary": json.loads(summary_json),
                "provenance": json.loads(provenance_json),
                "created_at": created_at,
            }
        )
