"""Migration files for the platform registry SQLite DB.

This is intentionally a *plain SQL* migration framework — no Alembic, no
SQLAlchemy. Each migration is a single ``NNNN_<slug>.sql`` file in this
directory. The runner (``the_similarity.platform.registry._apply_migrations``)
discovers files by sorted filename, applies them inside a single
transaction per file, and records the version in a ``schema_migrations``
table so re-applying is a no-op.

Constraints
-----------
- Filenames MUST match ``^[0-9]{4}_.+\\.sql$``. The four-digit prefix is
  the version number; the suffix is human-readable.
- Each file MUST be idempotent on its own when re-run on a partial DB
  (use ``IF NOT EXISTS`` aggressively). The runner additionally guards
  against re-application via the ``schema_migrations`` table — both
  layers exist because parallel agents on shared DBs occasionally beat
  the runner to a CREATE.
- Migrations MUST NOT drop or rename existing columns. SQLite's ALTER
  surface is limited and the spine schema is contract-locked. To
  evolve a column, add a new one and migrate data; deletes happen in
  a separate breaking-change release.
"""
