# auth row-level scoping audit — 2026-05-07

Pre-launch audit of `the_similarity/core/auth.py` and adjacent route code
for the personalized setup scanner v1 launch. Goal: confirm that row-level
filtering exists on every read/write that touches user-owned data so user A
cannot see or mutate user B's records.

## Reads — all properly scoped

| Method | Query | Scoping mechanism |
|---|---|---|
| `authenticate(email, pw)` | `SELECT FROM users WHERE email = ? AND enabled = 1` | Email is the credential being verified — correct |
| `get_user(user_id)` | `SELECT FROM users WHERE id = ?` | Caller passes the authenticated `user_id` from JWT/api-key |
| `verify_api_key(raw_key)` | `SELECT FROM api_keys ak JOIN users u WHERE ak.key_hash = ?` | Key hash is the credential |
| `list_api_keys(user_id)` | `SELECT FROM api_keys WHERE user_id = ?` | Filtered by `user_id` |
| `refresh_tokens` SELECT | `SELECT FROM refresh_tokens WHERE token_hash = ? AND revoked = 0` | Token hash is the credential |

## Writes — one defense-in-depth gap (fixed)

`revoke_api_key(key_id)` was `UPDATE api_keys SET enabled = 0 WHERE id = ?` —
no `user_id` filter at the DB layer. The route handler at
`the-similarity-api/app/auth_routes.py` did check ownership before calling,
but the DB query itself accepted any `key_id`. **Not currently exploitable**
(only one call site, and it does the check), but a single point of failure:
any future programmatic call site, internal admin tool, or refactor that
forgets the route-layer check would let user A revoke user B's keys.

**Fix shipped in this PR:**
- `revoke_api_key(user_id, key_id)` now requires both args and uses
  `WHERE id = ? AND user_id = ?`. Cross-tenant attempts return `False`
  → 404, which also avoids leaking the existence of another tenant's
  `key_id` (a 403 would).
- Route handler simplified: trusts the DB-layer return value and drops
  the separate `list_api_keys` round-trip.
- New test `test_revoke_api_key_cross_tenant_blocked` locks in the
  guarantee — user B cannot revoke user A's key, and vice-versa.

## Other writes — OK as-is

- `update_user_tier(user_id, tier)` — admin-only, not exposed via routes.
- `create_user`, `create_api_key`, `issue_tokens` — INSERTs against the
  user being created/operated-on; no cross-tenant risk.
- `refresh_tokens` UPDATE (`SET revoked = 1 WHERE token_hash = ?`) —
  filtered by the token hash itself, which is a credential.

## Out of scope for this audit

- `the_similarity/platform/registry.py` — does not yet have multi-tenant
  `user_id` FKs. Adding them is Worktree A's lane in the v1 plan
  (`Multi-tenant setups schema (user_id FK on every relevant table,
  migrations)`). When that lands, the same audit lens should be re-run
  against the registry's CRUD methods.
- Marketplace-tier authorization (v3+) — owner-vs-subscriber checks for
  shared setups. Not relevant to v1 retail.

## Lesson for future code

Any DB write that touches a per-user row should filter by `user_id` in
the WHERE clause even if the route layer also checks. Two cheap
defenses are stronger than one expensive one — and the layered approach
survives refactors that the route-layer-only approach does not.

Code path: `the_similarity/core/auth.py:504`
