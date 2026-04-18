#!/usr/bin/env bash
# Smoke test for the 3D Data Space — runs the demo and the tests.
#
# Exit on first failure. This script is meant to be run from the repo root:
#   bash scripts/smoke_3d_state_space.sh
#
# It verifies:
#   1. The canonical demo script runs without error.
#   2. The integration tests pass.
#
# No external services required — everything runs locally with temp files.
set -euo pipefail

echo "=== 3D Data Space Smoke Test ==="
echo ""

# Resolve repo root (parent of scripts/).
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "[1/2] Running canonical demo..."
python examples/3d_state_space_demo.py
echo ""
echo "[1/2] Demo passed."
echo ""

echo "[2/2] Running integration tests..."
python -m pytest the_similarity/tests/test_3d_state_space.py -v
echo ""
echo "[2/2] Tests passed."
echo ""

echo "=== All smoke checks passed ==="
