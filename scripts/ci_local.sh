#!/usr/bin/env bash
# =============================================================================
# scripts/ci_local.sh
# =============================================================================
#
# Fast (~30s) install-graph + lint check.
#
# What this catches:
#   The "polluted dev env" bug — a package installed in your local venv
#   from a past session that isn't declared in pyproject.toml. Tests pass
#   locally, then fail in CI's clean-room install because the import
#   resolves to nothing. This script reproduces that clean-room install
#   in a throwaway venv so you find the gap before pushing.
#
# What this does NOT catch:
#   Test failures. We deliberately don't run pytest here — pr-gate runs
#   the full suite on every PR with proper path filtering, so paying
#   8+ minutes locally to duplicate that is a pure velocity tax. Push,
#   let pr-gate verify, fix forward if anything breaks.
#
# When to run:
#   - When you've touched pyproject.toml, imports, or anything install-shaped.
#   - Otherwise, optional. CI is the test gate now.
#
# Exit code: 0 on success, non-zero on any failure.
# =============================================================================

set -euo pipefail

# ── Locate the repo root relative to this script ────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ── Create the throwaway venv ───────────────────────────────────────────────
# Timestamp + pid keeps parallel runs from colliding on the same path.
VENV_ROOT="/tmp/ci-local-$(date +%s)-$$"
VENV="$VENV_ROOT/venv"

cleanup() {
  local code=$?
  if [ -d "$VENV_ROOT" ]; then
    rm -rf "$VENV_ROOT"
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

echo "── ci_local.sh — fast install-graph + lint check ──"
echo "   repo:  $REPO_ROOT"
echo "   venv:  $VENV"

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
echo "   python: $("$PY_BIN" --version)"

# ── Build the venv ──────────────────────────────────────────────────────────
"$PY_BIN" -m venv "$VENV" --without-pip
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# `ensurepip` is faster than `pip install --upgrade pip` over the network on
# every run. Quiet flags shave seconds off the run.
"$PY_BIN" -m ensurepip --upgrade --default-pip >/dev/null
pip install --quiet --upgrade pip

# This is the actual signal: does pyproject.toml resolve to a working
# install graph? If a transitive dep is missing, this errors. If imports
# at install time fail, this errors. Everything past this is gravy.
pip install --quiet -e .

# Ruff is cheap (~1 sec) and catches the silly stuff before pr-gate does.
pip install --quiet ruff
echo
echo "── ruff check the_similarity/ ──"
ruff check the_similarity/

cat <<'BANNER'

╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ✅  install graph clean, lint clean — push when ready          ║
║                                                                  ║
║   Note: pytest is NOT run here. pr-gate runs the full suite      ║
║   on every PR. Run `pytest` manually if you've changed test-     ║
║   reachable code and want a local check first.                   ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

BANNER
