"""Shared pytest fixtures for the-similarity-api tests.

The customer-facing API package lives at ``the-similarity-api/app/`` and
its tests import via ``app.*``. This conftest ensures the test process
can locate the ``app`` package by adding the repo's ``the-similarity-api``
directory to ``sys.path``. We also export a :func:`temp_registry_db`
fixture so every test gets an isolated SQLite file — parallel runs never
share state.

Why not rely on ``pyproject.toml``?
-----------------------------------
The repo's root ``pyproject.toml`` only ships the ``the_similarity``
engine package; the API lives outside its ``packages`` declaration and
is run with ``uvicorn app.main:app`` from the ``the-similarity-api``
directory. We reproduce that same working-directory assumption here so
``python -m pytest tests/`` works from any of:

1. the repo root (``python -m pytest the-similarity-api/tests/``)
2. the API directory (``cd the-similarity-api && python -m pytest tests/``)

without the caller having to manipulate ``PYTHONPATH`` by hand.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Path hygiene: the API app package ("app") lives in the parent of this
# tests/ directory. Prepend that parent so ``from app.main import app``
# resolves regardless of the caller's cwd.
_API_ROOT = Path(__file__).resolve().parent.parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# Walk two levels up from this file:
#   conftest.py → tests/ → the-similarity-api/ → <repo root>
# This lets tests import ``the_similarity.*`` from the in-tree package
# without requiring a pip-installed wheel.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
