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
#   6. Stop the API and clean up the tmp DB.
#
# Expected terminal output is documented in
# `vision/platform_spine_batch1.md#32-expected-output-abridged`.
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
TMP_DIR="$(mktemp -d -t spine-smoke.XXXXXX)"
UVICORN_PID=""

export THE_SIMILARITY_REGISTRY_DB="$REGISTRY_DB"

# -- cleanup ---------------------------------------------------------------
# Always runs, even on failure. Kills the API if we started it, drops the
# DB, removes the tmp dir.
cleanup() {
  local rc=$?
  if [[ -n "${UVICORN_PID}" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "[smoke] stopping uvicorn (pid=${UVICORN_PID})"
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
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

# -- step 6: cleanup handled by the trap ----------------------------------
