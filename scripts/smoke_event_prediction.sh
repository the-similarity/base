#!/usr/bin/env bash
# Smoke test for the world-event prediction pipeline.
#
# Runs:
#   1. The end-to-end demo (examples/event_prediction_demo.py)
#   2. The integration tests (test_event_prediction_e2e.py)
#
# Exit code 0 = all green, non-zero = something broke.
#
# Usage:
#   bash scripts/smoke_event_prediction.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "============================================================"
echo "Smoke: World Event Prediction Pipeline"
echo "============================================================"

echo ""
echo "--- Step 1: Running end-to-end demo ---"
python examples/event_prediction_demo.py
echo ""
echo "--- Step 1: PASSED ---"

echo ""
echo "--- Step 2: Running integration tests ---"
python -m pytest the_similarity/tests/test_event_prediction_e2e.py -v
echo ""
echo "--- Step 2: PASSED ---"

echo ""
echo "============================================================"
echo "Smoke: ALL PASSED"
echo "============================================================"
