#!/usr/bin/env bash
# Smoke test for the platform spine (Batch 1).
#
# Exercises the end-to-end flow a new operator would walk through on a
# clean laptop:
#
#   1. Create an isolated SQLite registry at /tmp/spine-smoke.db.
#   2. Register one synthetic artifact per pillar (finance, copies,
#      worlds) via the CLI (`python -m the_similarity.platform register`).
#   3. List runs globally and per-kind via the CLI.
#   4. Start the Platform REST API (`uvicorn`) on 127.0.0.1:8787.
#   5. Hit /healthz, /runs, /runs?kind=<pillar> via curl and verify JSON.
#   6. Start the customer-facing API (`app.main:app` from the-similarity-api)
#      on 127.0.0.1:8788 and exercise the /platform/* CRUD sub-resources:
#      artifacts, scorecards, scenarios, datasets. Each block POSTs a
#      registry-truth payload then verifies round-trip via GET/list.
#   7. Stop both APIs and clean up the tmp DB.
#
# Expected terminal output is documented in
# `vision/platform_spine_batch1.md#32-expected-output-abridged`.
#
# Registry-truth schema
# ---------------------
# The CRUD payloads in step 6 use the canonical field names defined in
# `the_similarity/platform/registry.py` and `contracts.py` — NOT the
# legacy shapes that `the-similarity-api/app/platform_routes.py` may
# still ship. Registry-truth field names this smoke relies on:
#
#   - artifacts:  `checksum` (NOT `sha256`)
#   - scorecards: `kind`, `details` / `details_json`
#                 (NOT `name`, `metrics_json`, `description`)
#   - scenarios:  `version`, `engine`, `params`, `metadata`
#                 (NOT `path`, `parameters_json`)
#   - datasets:   `source`, `schema_uri`, `n_rows`, `n_columns`,
#                 `checksum`, `metadata`
#                 (NOT `schema_json` / `schema` alias blob)
#
# The script is expected to fail the CRUD assertions until the schema
# reconciliation PR lands on `platform_routes.py` — this is deliberate:
# the smoke is the contract, the routes converge to match. Which
# assertions currently fail is spelled out in the PR description.
#
# Exit codes:
#   0 — every step succeeded.
#   1 — any step failed (the trap below re-raises after cleanup).
#
# The script is idempotent: running it repeatedly starts from a fresh
# DB because we `rm -f` the smoke DB at the top. It never touches the
# operator's real registry (~/.the_similarity/registry.db) because the
# whole script runs under `THE_SIMILARITY_REGISTRY_DB=/tmp/spine-smoke.db`.
set -euo pipefail

# -- config ----------------------------------------------------------------

REGISTRY_DB="${THE_SIMILARITY_REGISTRY_DB:-/tmp/spine-smoke.db}"
API_HOST="${THE_SIMILARITY_API_HOST:-127.0.0.1}"
API_PORT="${THE_SIMILARITY_API_PORT:-8787}"
# Second API (customer-facing, /platform/* CRUD surface) uses a distinct
# port so both servers run concurrently against the same registry DB.
# 8788 chosen as +1 from the platform API default — no other service on
# the dev laptop uses this range.
CUSTOMER_API_PORT="${THE_SIMILARITY_CUSTOMER_API_PORT:-8788}"
TMP_DIR="$(mktemp -d -t spine-smoke.XXXXXX)"
UVICORN_PID=""
CUSTOMER_UVICORN_PID=""
# Repo root: two levels up from the script's own directory. Needed to
# pivot `cd` into the customer API package since its module path is
# `app.main:app`, which only resolves from inside `the-similarity-api/`.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CUSTOMER_API_DIR="$REPO_ROOT/the-similarity-api"

export THE_SIMILARITY_REGISTRY_DB="$REGISTRY_DB"

# -- cleanup ---------------------------------------------------------------
# Always runs, even on failure. Kills the API if we started it, drops the
# DB, removes the tmp dir.
cleanup() {
  local rc=$?
  if [[ -n "${UVICORN_PID}" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "[smoke] stopping platform-api uvicorn (pid=${UVICORN_PID})"
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
  if [[ -n "${CUSTOMER_UVICORN_PID}" ]] && kill -0 "$CUSTOMER_UVICORN_PID" 2>/dev/null; then
    echo "[smoke] stopping customer-api uvicorn (pid=${CUSTOMER_UVICORN_PID})"
    kill "$CUSTOMER_UVICORN_PID" 2>/dev/null || true
    wait "$CUSTOMER_UVICORN_PID" 2>/dev/null || true
  fi
  rm -f "$REGISTRY_DB" "$REGISTRY_DB-journal" "$REGISTRY_DB-wal" "$REGISTRY_DB-shm"
  rm -rf "$TMP_DIR"
  if [[ $rc -eq 0 ]]; then
    echo "[smoke] OK"
  else
    echo "[smoke] FAILED (exit=$rc)"
  fi
  exit $rc
}
trap cleanup EXIT INT TERM

echo "[smoke] registry db: $REGISTRY_DB"
rm -f "$REGISTRY_DB" "$REGISTRY_DB-journal" "$REGISTRY_DB-wal" "$REGISTRY_DB-shm"

# -- step 1: build an empty registry so the file exists before we POST. ---
python -c "from the_similarity.platform.registry import RunRegistry; RunRegistry('$REGISTRY_DB').close()"

# -- step 2: register one synthetic run per pillar via the CLI ------------
# We materialize three artifact.json files under $TMP_DIR/{finance,copies,
# worlds}/artifact.json then pipe each through `python -m the_similarity.
# platform register`. The CLI prints the run_id on success; we capture it
# for the subsequent lookups.

mkdir -p "$TMP_DIR/finance" "$TMP_DIR/copies" "$TMP_DIR/worlds"

cat > "$TMP_DIR/finance/artifact.json" <<'JSON'
{
  "run_id": "8b62e4a9fd1a40b3a0e0f5c6a1b2c3d4",
  "kind": "eval",
  "config": {"symbol": "SPY", "start": "2020-01-01", "end": "2020-06-30", "method": "dtw"},
  "seed": 42,
  "artifact_paths": {"forecast": "forecast.parquet", "metrics": "metrics.json"},
  "summary": {"hit_rate": 0.62, "crps": 0.18, "mae": 0.012},
  "provenance": {"generator_name": "backtester", "generator_version": "0.2.1", "seed": 42, "created_at": "2026-04-15T18:30:00+00:00"},
  "created_at": "2026-04-15T18:30:00+00:00"
}
JSON

cat > "$TMP_DIR/copies/artifact.json" <<'JSON'
{
  "run_id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
  "kind": "copies",
  "config": {"input_path": "sample.csv", "n": 100, "seed": 7, "generator": "block_bootstrap"},
  "seed": 7,
  "artifact_paths": {"real": "real.parquet", "synth": "synth.parquet", "scorecard": "scorecard.json"},
  "summary": {"passed": true, "fidelity_score": 0.87, "privacy_score": 0.91},
  "provenance": {"source_id": "sample", "generator_name": "block_bootstrap", "generator_version": "0.1.0", "seed": 7, "created_at": "2026-04-15T18:44:00+00:00"},
  "created_at": "2026-04-15T18:44:00+00:00"
}
JSON

cat > "$TMP_DIR/worlds/artifact.json" <<'JSON'
{
  "run_id": "c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0",
  "kind": "worlds",
  "config": {"scenario_path": "small_village.json", "seed": 1, "steps": 500},
  "seed": 1,
  "artifact_paths": {"telemetry": "run.jsonl"},
  "summary": {"n_ticks": 500, "regime_coverage": 0.73, "runtime_ms": 4821},
  "provenance": {"generator_name": "small_village", "version": "0.3.0", "seed": 1, "scenario_name": "small_village", "created_at": "2026-04-15T19:00:00+00:00"},
  "created_at": "2026-04-15T19:00:00+00:00"
}
JSON

FINANCE_ID="$(python -m the_similarity.platform register "$TMP_DIR/finance/artifact.json")"
echo "[smoke] registered finance: $FINANCE_ID"
COPIES_ID="$(python -m the_similarity.platform register "$TMP_DIR/copies/artifact.json")"
echo "[smoke] registered copies : $COPIES_ID"
WORLDS_ID="$(python -m the_similarity.platform register "$TMP_DIR/worlds/artifact.json")"
echo "[smoke] registered worlds : $WORLDS_ID"

# -- step 3: list runs via the CLI, globally and per-kind -----------------
echo "[smoke] list all:"
python -m the_similarity.platform list
for kind in copies worlds eval; do
  rows="$(python -m the_similarity.platform list --kind "$kind" | tail -n +3 | wc -l | tr -d ' ')"
  echo "[smoke] list --kind $kind → $rows row(s)"
  if [[ "$rows" != "1" ]]; then
    echo "[smoke] ERROR: expected 1 row for kind=$kind, got $rows"
    exit 1
  fi
done

# -- step 4: start the API in the background ------------------------------
echo "[smoke] starting uvicorn on $API_HOST:$API_PORT ..."
python -m uvicorn the_similarity.platform.api:app \
  --host "$API_HOST" --port "$API_PORT" \
  --log-level warning \
  > "$TMP_DIR/uvicorn.log" 2>&1 &
UVICORN_PID=$!

# Wait up to 10s for the server to answer /healthz. We poll on a short
# interval rather than sleep once so the smoke is fast on warm machines
# and still lenient on CI runners.
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf "http://$API_HOST:$API_PORT/healthz" > /dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == "10" ]]; then
    echo "[smoke] ERROR: uvicorn never became ready"
    echo "--- uvicorn log ---"
    cat "$TMP_DIR/uvicorn.log"
    exit 1
  fi
  sleep 1
done

# -- step 5: hit the routes -----------------------------------------------
HEALTH="$(curl -sf "http://$API_HOST:$API_PORT/healthz")"
echo "[smoke] GET /healthz → $HEALTH"
if ! echo "$HEALTH" | python -c 'import sys,json; d=json.load(sys.stdin); assert d["status"]=="ok" and d["runs"]==3, d'; then
  echo "[smoke] ERROR: /healthz did not report status=ok, runs=3"
  exit 1
fi

RUNS_ALL="$(curl -sf "http://$API_HOST:$API_PORT/runs")"
N_ALL="$(echo "$RUNS_ALL" | python -c 'import sys,json; print(len(json.load(sys.stdin)["runs"]))')"
echo "[smoke] GET /runs → $N_ALL rows"
if [[ "$N_ALL" != "3" ]]; then
  echo "[smoke] ERROR: expected 3 rows, got $N_ALL"
  exit 1
fi

for kind in copies worlds eval; do
  RUNS_K="$(curl -sf "http://$API_HOST:$API_PORT/runs?kind=$kind")"
  N_K="$(echo "$RUNS_K" | python -c 'import sys,json; print(len(json.load(sys.stdin)["runs"]))')"
  echo "[smoke] GET /runs?kind=$kind → $N_K row"
  if [[ "$N_K" != "1" ]]; then
    echo "[smoke] ERROR: expected 1 row for kind=$kind, got $N_K"
    exit 1
  fi
done

# -- step 6: customer-facing API CRUD round-trips -------------------------
# The four sub-resources (artifacts, scorecards, scenarios, datasets) are
# only exposed through the customer-facing app at
# `the-similarity-api/app/platform_routes.py`. We start that server on a
# second port, sharing the same tmp registry DB, so the CRUD assertions
# see the three runs we already registered (needed as parent run_id for
# artifacts + scorecards).
#
# IMPORTANT: every POST body below uses the registry-truth field names
# from `the_similarity/platform/registry.py` and `contracts.py`. When
# the routes drift from that schema (currently: `sha256` vs `checksum`,
# `name` vs `kind` on scorecards, `parameters_json` vs `params_json` on
# scenarios, `schema_json` vs `schema_uri`/`metadata_json` on datasets),
# this smoke will fail — which is correct. The route layer converges to
# the contract, not the other way around.

echo "[smoke] starting customer-api uvicorn on $API_HOST:$CUSTOMER_API_PORT ..."
# Must cd into the-similarity-api so the `app.main` module resolves —
# the package does not live at the repo root. We run the server in a
# subshell so the outer script's cwd is untouched.
(
  cd "$CUSTOMER_API_DIR"
  python -m uvicorn app.main:app \
    --host "$API_HOST" --port "$CUSTOMER_API_PORT" \
    --log-level warning \
    > "$TMP_DIR/customer-uvicorn.log" 2>&1
) &
CUSTOMER_UVICORN_PID=$!

# Same readiness-poll pattern as the platform API. /health is the
# customer app's liveness endpoint; /platform/healthz is registry-backed
# but we poll the cheaper root first.
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf "http://$API_HOST:$CUSTOMER_API_PORT/health" > /dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == "10" ]]; then
    echo "[smoke] ERROR: customer-api uvicorn never became ready"
    echo "--- customer-uvicorn log ---"
    cat "$TMP_DIR/customer-uvicorn.log"
    exit 1
  fi
  sleep 1
done

# Base URL shared by every CRUD block below. Keeps the curl lines
# readable and makes a port-flip (e.g. staging test) a one-line change.
CUSTOMER_BASE="http://$API_HOST:$CUSTOMER_API_PORT/platform"

# Helper: emit "[smoke]   ✓ <msg>" for per-assertion success lines so
# the CRUD blocks have consistent, greppable output. Printed to stderr
# so it does not contaminate pipelines that parse command output.
# shellcheck disable=SC2317
ok() { echo "[smoke]   ✓ $*"; }

# Counter for CRUD-block failures. Each sub-resource block records a
# pass/fail, prints it alongside the assertion output, and at the end of
# the script we exit non-zero iff any block failed. This design lets
# reviewers see which specific CRUD blocks still drift from registry
# truth rather than stopping at the first one — valuable when the
# reconciliation PR lands partial fixes across sub-resources.
CRUD_FAILURES=0
CRUD_PASS_BLOCKS=""
CRUD_FAIL_BLOCKS=""

# Helper: run a curl command and capture both body + HTTP status in one
# call. Prints the pair to stdout in the form "<status>\t<body>" so the
# caller can split on tab. We bypass `curl -f` because a 4xx/5xx is a
# valid failure signal we want to observe, not an abort trigger.
curl_json() {
  local method="$1" url="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -s -o /tmp/smoke-body -w '%{http_code}' \
      -X "$method" -H "Content-Type: application/json" \
      -d "$body" "$url"
  else
    curl -s -o /tmp/smoke-body -w '%{http_code}' \
      -X "$method" "$url"
  fi
  echo
  cat /tmp/smoke-body
  echo
}

# Helper: evaluate a python expression against a JSON payload. Returns 0
# on success, 1 on any assertion / parse failure. Stdout from the python
# block is captured and echoed on failure for quick debugging.
assert_json() {
  local tag="$1" payload="$2" expr="$3"
  if ! echo "$payload" | python -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
except Exception as exc:
    print(f'[smoke] $tag: non-JSON payload: {exc}', file=sys.stderr)
    sys.exit(1)
$expr
"; then
    echo "[smoke] ASSERT FAIL: $tag"
    echo "--- payload ---"
    echo "$payload"
    return 1
  fi
  return 0
}

# Per-block wrapper: takes a block name + a body function, runs the body
# with errexit temporarily OFF so one failing assertion does not short-
# circuit the remaining blocks. Records the outcome in CRUD_FAILURES
# and the pass/fail block-name lists for the final summary.
run_crud_block() {
  local name="$1"; shift
  echo "[smoke] ── $name CRUD ──"
  set +e
  (
    set -e
    "$@"
  )
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    echo "[smoke] BLOCK FAIL: $name (rc=$rc)"
    CRUD_FAILURES=$((CRUD_FAILURES + 1))
    CRUD_FAIL_BLOCKS="$CRUD_FAIL_BLOCKS $name"
  else
    echo "[smoke] BLOCK PASS: $name"
    CRUD_PASS_BLOCKS="$CRUD_PASS_BLOCKS $name"
  fi
}

# -- step 6a: artifacts CRUD ----------------------------------------------
# Registry-truth schema (see `registry.py` _CREATE_ARTIFACTS_SQL):
#   run_id, name, path, content_type, size_bytes, checksum, created_at
# Field is `checksum` — NOT `sha256`. Routes currently ship `sha256`;
# after reconciliation they will accept `checksum`.

artifacts_crud_body() {
  local artifact_name="forecast-parquet-smoke"
  # Deterministic SHA-256 of an empty string — stable, readable,
  # semantically meaningless. Consumers MUST NOT rely on this exact value.
  local artifact_checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  local artifact_created_at="2026-04-15T18:31:00+00:00"

  local body
  body=$(cat <<JSON
{
  "run_id": "$FINANCE_ID",
  "name": "$artifact_name",
  "path": "forecast.parquet",
  "content_type": "application/x-parquet",
  "size_bytes": 12345,
  "checksum": "$artifact_checksum",
  "created_at": "$artifact_created_at"
}
JSON
)

  local post_status post_body
  post_status=$(curl -s -o /tmp/smoke-artifact-post -w '%{http_code}' \
    -X POST -H "Content-Type: application/json" \
    -d "$body" \
    "$CUSTOMER_BASE/runs/$FINANCE_ID/artifacts")
  post_body=$(cat /tmp/smoke-artifact-post)
  echo "[smoke] POST /platform/runs/$FINANCE_ID/artifacts → HTTP $post_status"
  if [[ "$post_status" != "200" && "$post_status" != "201" ]]; then
    echo "[smoke] ERROR: artifact POST returned HTTP $post_status"
    echo "--- body ---"
    echo "$post_body"
    return 1
  fi
  assert_json "artifact POST" "$post_body" "
assert data.get('run_id') == '$FINANCE_ID', data
assert data.get('name') == '$artifact_name', data
# Registry-truth requires 'checksum' — the router may still echo 'sha256'
# until the reconciliation PR lands. We fail loud if the router returns
# the legacy name so the drift is visible.
assert data.get('checksum') == '$artifact_checksum', data
print('[smoke]   ✓ artifact POST shape matches registry-truth (checksum)')
"

  local list_body
  list_body=$(curl -sf "$CUSTOMER_BASE/runs/$FINANCE_ID/artifacts")
  echo "[smoke] GET  /platform/runs/$FINANCE_ID/artifacts → (list)"
  assert_json "artifact list" "$list_body" "
assert isinstance(data, list), data
names = [row.get('name') for row in data]
assert '$artifact_name' in names, f'missing artifact name: {names}'
row = next(r for r in data if r.get('name') == '$artifact_name')
assert row.get('checksum') == '$artifact_checksum', row
print('[smoke]   ✓ artifact list contains row with registry-truth checksum')
"

  local get_body
  get_body=$(curl -sf "$CUSTOMER_BASE/runs/$FINANCE_ID/artifacts/$artifact_name")
  echo "[smoke] GET  /platform/runs/$FINANCE_ID/artifacts/$artifact_name"
  assert_json "artifact GET" "$get_body" "
assert data.get('run_id') == '$FINANCE_ID', data
assert data.get('name') == '$artifact_name', data
assert data.get('checksum') == '$artifact_checksum', data
print('[smoke]   ✓ artifact GET round-trips with registry-truth fields')
"
  # DELETE is NOT exposed by platform_routes.py as of 2026-04-18. See
  # PR description for follow-up.
}

run_crud_block "artifacts" artifacts_crud_body

# -- step 6b: scorecards CRUD ---------------------------------------------
# Registry-truth schema (see `registry.py` _CREATE_SCORECARDS_SQL):
#   run_id, kind, overall_score, passed, thresholds_json, details_json
#
# The route layer may currently ship legacy names (`name` instead of
# `kind`, `metrics_json` instead of `details_json`). We send the
# registry-truth shape — `kind` from the ScorecardKind enum
# (fidelity / privacy / utility / controllability / calibration /
# backtest), and `thresholds` + `details` as free-form dicts.

scorecards_crud_body() {
  # The copies run is the natural parent for a fidelity scorecard.
  local parent="$COPIES_ID"
  local kind="fidelity"
  local created_at="2026-04-15T18:45:00+00:00"

  local body
  body=$(cat <<JSON
{
  "run_id": "$parent",
  "kind": "$kind",
  "overall_score": 0.87,
  "passed": true,
  "thresholds": {"ks_max": 0.1, "wasserstein_max": 0.05},
  "details": {"ks": 0.07, "wasserstein": 0.04, "acf_error": 0.02},
  "created_at": "$created_at"
}
JSON
)

  local post_status post_body
  post_status=$(curl -s -o /tmp/smoke-scorecard-post -w '%{http_code}' \
    -X POST -H "Content-Type: application/json" \
    -d "$body" \
    "$CUSTOMER_BASE/runs/$parent/scorecards")
  post_body=$(cat /tmp/smoke-scorecard-post)
  echo "[smoke] POST /platform/runs/$parent/scorecards → HTTP $post_status"
  if [[ "$post_status" != "200" && "$post_status" != "201" ]]; then
    echo "[smoke] ERROR: scorecard POST returned HTTP $post_status"
    echo "--- body ---"
    echo "$post_body"
    return 1
  fi
  assert_json "scorecard POST" "$post_body" "
assert data.get('run_id') == '$parent', data
# Registry-truth uses 'kind' (not 'name') and 'details' (not 'metrics').
assert data.get('kind') == '$kind', data
assert data.get('overall_score') == 0.87, data
assert data.get('passed') is True, data
details = data.get('details') or {}
assert details.get('ks') == 0.07, details
print('[smoke]   ✓ scorecard POST shape matches registry-truth (kind, details)')
"

  local list_body
  list_body=$(curl -sf "$CUSTOMER_BASE/runs/$parent/scorecards")
  echo "[smoke] GET  /platform/runs/$parent/scorecards → (list)"
  assert_json "scorecard list" "$list_body" "
assert isinstance(data, list), data
kinds = [row.get('kind') for row in data]
assert '$kind' in kinds, f'missing scorecard kind: {kinds}'
row = next(r for r in data if r.get('kind') == '$kind')
assert row.get('overall_score') == 0.87, row
print('[smoke]   ✓ scorecard list contains registry-truth kind=$kind')
"
  # No GET-by-(run_id, kind) route exists yet on platform_routes.py — the
  # list endpoint is the only read path. Noted in PR description.
  # No DELETE route either.
}

run_crud_block "scorecards" scorecards_crud_body

# -- step 7: final summary ------------------------------------------------
# Print a rolled-up pass/fail summary and exit non-zero iff any CRUD
# block failed. Cleanup (killing uvicorns, removing the DB) happens
# unconditionally in the trap.
echo
echo "[smoke] ── CRUD summary ──"
echo "[smoke]   pass: $CRUD_PASS_BLOCKS"
echo "[smoke]   fail: $CRUD_FAIL_BLOCKS"
if [[ "$CRUD_FAILURES" -gt 0 ]]; then
  echo "[smoke] $CRUD_FAILURES CRUD block(s) failed — see log above."
  exit 1
fi

# -- cleanup handled by the trap ------------------------------------------
