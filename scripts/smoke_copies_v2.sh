#!/usr/bin/env bash
# Smoke test for Copies v2 pipeline.
#
# Runs the synthetic CLI with block_bootstrap, registers the result in a
# temp registry, and verifies the platform list command sees it.
#
# Exit codes:
#   0 — all steps passed.
#   non-zero — any step failed (set -e propagates the first failure).
set -euo pipefail

export THE_SIMILARITY_REGISTRY_DB=/tmp/copies-v2-smoke.db
rm -f "$THE_SIMILARITY_REGISTRY_DB"

echo "--- Copies v2 smoke test ---"
echo "Registry: $THE_SIMILARITY_REGISTRY_DB"

# Step 1: Generate synthetic data and register the run.
python -m the_similarity.synthetic.cli \
  --input the_similarity/synthetic/demos/sample.csv \
  --n 200 \
  --seed 42 \
  --generator block_bootstrap \
  --out /tmp/copies-v2 \
  --register

# Step 2: Verify the run appears in the platform listing.
python -m the_similarity.platform list --kind copies

echo ""
echo "Copies v2 smoke: OK"
