#!/usr/bin/env bash
# =============================================================================
# scripts/ci_local.sh
# =============================================================================
#
# This is what CI runs. If this fails locally, your PR WILL fail.
# Agents MUST run this before `gh pr create`.
#
# Why: local `pytest` in a polluted dev env lies. It picks up packages that
# were installed in past sessions (e.g. `scikit-learn`, `fastapi`, `httpx`)
# but are NOT declared in pyproject.toml. That's how an entire batch of PRs
# can go green locally and fail CI simultaneously — which is exactly what
# happened the night this script was written.
#
# This script:
#   1. Creates a throwaway venv in a unique /tmp path.
#   2. Installs ONLY what pyproject.toml declares (+ pytest + ruff).
#   3. Runs `ruff check` and `pytest` — the same commands pr-gate runs.
#   4. Cleans up the venv on exit regardless of outcome.
#
# Exit code: 0 on success, non-zero on any failure (fail-fast).
# =============================================================================

set -euo pipefail

# ── Locate the repo root relative to this script ────────────────────────────
# Resolve symlinks so invocations like `bash scripts/ci_local.sh` or
# `./scripts/ci_local.sh` from anywhere in the tree behave identically.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ── Create the throwaway venv ───────────────────────────────────────────────
# Timestamp + pid keeps parallel runs from colliding on the same path.
VENV_ROOT="/tmp/ci-local-$(date +%s)-$$"
VENV="$VENV_ROOT/venv"

# Trap cleans up on ANY exit — success, failure, Ctrl-C. Critical because
# these venvs contain pinned copies of every dep and add up fast on disk.
cleanup() {
  local code=$?
  if [ -d "$VENV_ROOT" ]; then
    rm -rf "$VENV_ROOT"
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

echo "────────────────────────────────────────────────────────────────"
echo "  ci_local.sh — clean-room CI mirror"
echo "  repo:  $REPO_ROOT"
echo "  venv:  $VENV"
echo "────────────────────────────────────────────────────────────────"

# ── Pick a Python — prefer 3.12 to match pr-gate, fall back gracefully ──────
PY_BIN=""
for candidate in python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY_BIN="$candidate"
    break
  fi
done
if [ -z "$PY_BIN" ]; then
  echo "ERROR: no python3 on PATH" >&2
  exit 127
fi
echo "  python: $("$PY_BIN" --version) ($(command -v "$PY_BIN"))"

# ── Build the venv ──────────────────────────────────────────────────────────
"$PY_BIN" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

pip install --upgrade pip
# `pip install -e .` mirrors pr-gate exactly — no extras, no dev deps beyond
# the two testing tools we add below. If this fails with ModuleNotFoundError
# at test time, it means pyproject.toml is missing a dep.
pip install -e .
pip install pytest ruff

# ── Lint first — fail fast if code is even trying ───────────────────────────
echo
echo "── ruff check the_similarity/ ─────────────────────────────────"
ruff check the_similarity/

# ── Harness docs — keep agent operating context mechanically legible ────────
echo
echo "── agent harness check ────────────────────────────────────────"
python scripts/check_agent_harness.py

# ── Engine tests ────────────────────────────────────────────────────────────
echo
echo "── pytest the_similarity/tests/ ───────────────────────────────"
python -m pytest the_similarity/tests/ -v --tb=short

# ── Success banner ──────────────────────────────────────────────────────────
# Reaching this line means every check passed. Mirror the exact command
# pr-gate runs so operators can copy-paste to reproduce in CI.
cat <<'BANNER'

╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ✅  CI-LOCAL PASSED — PR is safe to open                       ║
║                                                                  ║
║   CI-equivalent:                                                 ║
║     pip install -e . && pip install pytest ruff                  ║
║     ruff check the_similarity/                                   ║
║     python scripts/check_agent_harness.py                        ║
║     python -m pytest the_similarity/tests/ -v --tb=short         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

BANNER
