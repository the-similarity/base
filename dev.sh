#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/the-similarity-app"
API_DIR="$ROOT_DIR/the-similarity-api"

usage() {
  cat <<'EOF'
Usage:
  ./dev.sh            Start the frontend dev server
  ./dev.sh frontend   Start the frontend dev server
  ./dev.sh backend    Start the backend API server
  ./dev.sh full       Start backend and frontend together
  ./dev.sh setup      Install frontend deps and Python package deps
  ./dev.sh test       Run Python tests and frontend lint

Notes:
  - The backend API is served by FastAPI from ./the-similarity-api/app/main.py.
  - The frontend can target the API with NEXT_PUBLIC_THE_SIMILARITY_API_URL.
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

setup_frontend() {
  require_cmd npm

  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "Installing frontend dependencies..."
    (
      cd "$FRONTEND_DIR"
      npm install
    )
  fi
}

setup_python() {
  if command -v poetry >/dev/null 2>&1; then
    echo "Installing Python dependencies with poetry..."
    (
      cd "$ROOT_DIR"
      poetry install
    )
  elif command -v pip >/dev/null 2>&1; then
    echo "Poetry not found. Installing package in editable mode with pip..."
    (
      cd "$ROOT_DIR"
      pip install -e .
    )
  else
    echo "Skipping Python dependency installation: no poetry or pip found."
  fi
}

run_setup() {
  setup_frontend
  setup_python
}

run_tests() {
  setup_frontend

  if command -v pytest >/dev/null 2>&1; then
    (
      cd "$ROOT_DIR"
      pytest
    )
  elif command -v poetry >/dev/null 2>&1; then
    (
      cd "$ROOT_DIR"
      poetry run pytest
    )
  else
    echo "Skipping pytest: neither pytest nor poetry is available."
  fi

  (
    cd "$FRONTEND_DIR"
    npm run lint
  )
}

run_frontend() {
  setup_frontend

  echo "Starting The Similarity frontend at http://localhost:3000"

  (
    cd "$FRONTEND_DIR"
    npm run dev
  )
}

run_backend() {
  echo "Starting The Similarity API at http://127.0.0.1:8000"

  (
    cd "$API_DIR"
    THE_SIMILARITY_DATA_ROOT="${THE_SIMILARITY_DATA_ROOT:-$(git worktree list --porcelain | grep '^worktree ' | head -1 | sed 's/^worktree //')}/the-similarity-data" PYTHONPATH="$ROOT_DIR" python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  )
}

run_full() {
  setup_frontend

  echo "Starting The Similarity API and frontend together"

  (
    cd "$API_DIR"
    THE_SIMILARITY_DATA_ROOT="${THE_SIMILARITY_DATA_ROOT:-$(git worktree list --porcelain | grep '^worktree ' | head -1 | sed 's/^worktree //')}/the-similarity-data" PYTHONPATH="$ROOT_DIR" python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  ) &
  BACKEND_PID=$!

  cleanup() {
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  }

  trap cleanup EXIT INT TERM

  (
    cd "$FRONTEND_DIR"
    NEXT_PUBLIC_THE_SIMILARITY_API_URL="http://127.0.0.1:8000" npm run dev
  )
}

case "${1:-full}" in
  dev)
    run_frontend
    ;;
  frontend)
    run_frontend
    ;;
  backend)
    run_backend
    ;;
  full)
    run_full
    ;;
  setup)
    run_setup
    ;;
  test)
    run_tests
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
