#!/usr/bin/env bash
# Smoke test for the NL-to-time-series demo.
#
# Runs the end-to-end demo and verifies it exits cleanly.
# Used by CI and local development to catch import errors or
# broken platform integration without running the full test suite.
#
# Usage:
#   bash scripts/smoke_nl_ts.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== NL-to-Time-Series Smoke Test ==="
echo "Repo root: $REPO_ROOT"

# Run the demo — it uses a temp registry so no side effects.
python "$REPO_ROOT/examples/nl_to_timeseries_demo.py"

echo ""
echo "=== Smoke test PASSED ==="
