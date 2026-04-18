# Platform routes vs registry schema drift (fixed 2026-04-18)

The customer-facing `/platform/*` router at
`the-similarity-api/app/platform_routes.py` had drifted from the
registry-truth schema defined in `the_similarity/platform/registry.py`
and `the_similarity/platform/contracts.py`. Every CRUD handler that
touched `artifacts`, `scorecards`, `scenarios`, or `datasets` used
column names that did not exist on the canonical tables — the registry
created the tables first (with the right shape), and the router's
`CREATE TABLE IF NOT EXISTS` with the wrong columns was a no-op, so
subsequent INSERTs failed with `OperationalError: table X has no
column named Y`.

What broke
----------

| Resource    | Registry column (truth) | Router was using (drifted) |
|-------------|-------------------------|----------------------------|
| artifacts   | `checksum`              | `sha256`                   |
| scorecards  | `kind`, `details_json`, `thresholds_json` | `name`, `metrics_json`, `created_at` |
| scenarios   | `version`, `engine`, `params_json`, `metadata_json` | `description`, `pillar`, `parameters_json`, `created_at` |
| datasets    | `source`, `schema_uri`, `n_rows`, `n_columns`, `checksum`, `metadata_json` | `description`, `path`, `schema_json`, `created_at` |

10 tests in `the-similarity-api/tests/test_platform_routes.py` failed
on `OperationalError` whenever a handler ran SQL against the registry's
(correct) tables with drifted column names. The registry was opened
first via `get_registry()`, so its DDL won the race every time.

Fix (registry-is-truth)
-----------------------

Decision: **registry is the source of truth; routes and tests must
follow.** We did NOT touch `registry.py`, `contracts.py`, or the JSON
schemas.

Implementation:

1. **Delete companion-table DDL** in `platform_routes.py`
   (`_EXT_SCHEMA_SQL`). The registry already creates all four tables
   with the canonical shape on first connect. `_ensure_ext_schema` is
   now a no-op kept only for test-fixture import compatibility.
2. **Rename Pydantic fields to registry-truth**. `ArtifactRecordModel.sha256`
   -> `checksum`. `ScorecardSummaryModel.name` -> `kind` (ScorecardKind),
   `.metrics` -> `.details`, add `.thresholds`, drop `.created_at`.
   `ScenarioSpecModel`: swap to `version` / `engine` / `params` /
   `metadata`; display hints (pillar, description) live in `metadata`
   now. `DatasetSpecModel`: swap to `source` / `schema_uri` / `n_rows`
   / `n_columns` / `checksum` / `metadata`; drop the `schema`/`columns`
   alias shim entirely.
3. **Delegate CRUD to the registry.** Every handler now calls
   `registry.register_artifact(...)`, `.list_artifacts(...)`,
   `.register_scorecard(...)`, `.get_scorecards(...)`, etc. Raw SQL is
   gone. Pre-flight scans enforce the 409-on-duplicate router
   contract because the registry's methods are upserts.
4. **Remove the `pillar` list filter on scenarios** (no column) —
   replaced with an `engine` filter (registry-native). Scenario and
   dataset lists are ordered by `name ASC` (registry default; no
   `created_at` column).
5. **Update frontend TS types** in `the-similarity-app/lib/platform-api.ts`
   to match the renamed wire fields. No callers consume the old names
   (confirmed via grep).

Why this drift happened
-----------------------

The router module comments (line 50 of the old `platform_routes.py`
docstring) show the intent: "Agent 2 is extending `registry.py` with
matching `register_*`/`list_*`/`get_*` methods. Until those land the
router maintains companion SQLite tables." Agent 2 shipped the
registry extensions in [[batch1 platform spine 2026-04-17]], but the
router's companion-table migration was never performed — so the two
sides drifted from that merge onward.

Take-away for future agents
---------------------------

When the registry grows a new table, every API surface that writes
to it MUST delegate via the registry's public methods. Parallel raw
SQL against the same SQLite file will drift silently because SQLite's
`CREATE TABLE IF NOT EXISTS` is a no-op when the table already
exists — the column list of the **winning** DDL call is what the
file actually has, and subsequent statements against the loser's
columns will fail with `OperationalError`.

Cross-links
-----------
- [[Platform routes on the customer-facing API]] — current wire contract.
- [[Platform thesis]] — eval-lock-in strategy; registry is the lock.
- [[batch1 platform spine 2026-04-17]] — the platform spine that shipped
  the registry-truth schema.
- `the_similarity/platform/registry.py` — canonical schema (DDL).
- `the_similarity/platform/contracts.py` — canonical dataclass shapes.
- `the-similarity-api/app/platform_routes.py` — router (now thin).
