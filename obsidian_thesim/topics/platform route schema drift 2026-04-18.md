# Platform route schema drift (2026-04-18)

## What broke

The `/platform/*` CRUD routes in `the-similarity-api/app/platform_routes.py` ship legacy field names that do not match the registry-truth schema in `the_similarity/platform/registry.py` + `the_similarity/platform/contracts.py`. The drift was invisible because `scripts/smoke_platform_spine.sh` only exercised run registration and API health — not the artifact / scorecard / scenario / dataset sub-resources.

## Registry truth vs current route

| Resource | Registry-truth field | Route ships (legacy) |
|----------|---------------------|---------------------|
| artifacts | `checksum` | `sha256` |
| scorecards | `kind` (ScorecardKind enum), `details` | `name`, `metrics_json` |
| scenarios | `version`, `engine`, `params`, `metadata` | `description`, `pillar`, `parameters`, `created_at` |
| datasets | `source`, `schema_uri`, `n_rows`, `n_columns`, `checksum`, `metadata` | `description`, `path`, `schema_json`, `created_at` |

Plus: the route's `_ensure_ext_schema` creates an `artifacts` table with `sha256`, but the registry's `_init_schema` creates it with `checksum` — whichever module opens the DB first wins, and the other fails with `sqlite3.OperationalError: no such column: <col>` on insert.

## Why it's the route layer, not the registry

`contracts.py` + `registry.py` are the canonical object model (see the field-contract freeze warning in the module docstring). The route was written before `contracts.py` stabilized, with an explicit note that the Pydantic models would be swapped for the dataclasses once Agent 1's spec landed. Agent 1's spec did land; the swap did not.

## Detection

- `scripts/smoke_platform_spine.sh` now POSTs registry-truth payloads to all four sub-resources and asserts round-trip via GET/list. Any future regression that flips a field name will turn the smoke red before it reaches production.

## Remediation

1. Route-layer Pydantic models in `platform_routes.py` import + mirror the dataclasses from `contracts.py`.
2. `_ensure_ext_schema` gets deleted — the registry creates every table, routes stop maintaining their own DDL.
3. CRUD handlers delegate to `RunRegistry.register_artifact` / `register_scorecard` / `register_scenario` / `register_dataset` instead of raw SQL.

## Missing endpoints (file follow-up)

- No DELETE endpoint for any sub-resource.
- No GET-by-(run_id, kind) for scorecards — only a list endpoint.

## Related

- `[[batch1 platform spine 2026-04-17]]` — original Batch 1 design.
- `the_similarity/platform/contracts.py` — frozen field contracts.
- `the_similarity/platform/registry.py` — DDL + upsert SQL.
- `the-similarity-api/app/platform_routes.py` — current broken router.
- `scripts/smoke_platform_spine.sh` — enforcement.
