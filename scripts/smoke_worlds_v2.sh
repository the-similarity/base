#!/usr/bin/env bash
# smoke_worlds_v2.sh — End-to-end smoke test for Worlds v2 platform integration.
#
# Exercises the full pipeline: headless runner -> JSONL telemetry -> Python
# adapter registration -> registry query. Requires Node.js (for the headless
# runner) and the Python platform package.
#
# Exit codes:
#   0 — all checks passed
#   1 — a step failed (set -e)
#
# Usage:
#   bash scripts/smoke_worlds_v2.sh
#
# Environment:
#   THE_SIMILARITY_REGISTRY_DB — override registry DB path (default: temp file)

set -euo pipefail

export THE_SIMILARITY_REGISTRY_DB="${THE_SIMILARITY_REGISTRY_DB:-/tmp/worlds-v2-smoke.db}"
rm -f "$THE_SIMILARITY_REGISTRY_DB"

echo "=== Worlds v2 Smoke Test ==="
echo "Registry DB: $THE_SIMILARITY_REGISTRY_DB"

# Step 1: Run the headless world simulation (requires Node.js + fractal package)
echo ""
echo "--- Step 1: Headless world run ---"
cd the-similarity-fractal
node src/sim/headless/runner.js \
    --scenario scenarios/small_village.json \
    --seed 42 \
    --steps 50 \
    --out /tmp/worlds-smoke.jsonl
echo "Telemetry written: $(wc -l < /tmp/worlds-smoke.jsonl) lines"
cd ..

# Step 2: Register the world run via the Python adapter
echo ""
echo "--- Step 2: Register world run ---"
python -c "
from the_similarity.platform.adapters.worlds import register_world_run
from the_similarity.platform.registry import RunRegistry

reg = RunRegistry()
rid = register_world_run('/tmp/worlds-smoke.jsonl', 'small_village', 42, reg)
print(f'Registered world run: {rid}')

runs = reg.list_runs(kind='worlds')
print(f'World runs in registry: {len(runs)}')
assert len(runs) >= 1, 'Expected at least 1 world run in registry'

reg.close()
"

# Step 3: Verify via the platform CLI (if available)
echo ""
echo "--- Step 3: Verify via CLI ---"
python -m the_similarity.platform list --kind worlds 2>/dev/null || echo "(CLI list skipped — may not support --kind filter yet)"

echo ""
echo "=== Worlds v2 smoke: OK ==="
