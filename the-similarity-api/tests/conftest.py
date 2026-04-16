"""Pytest configuration for the ``the-similarity-api`` test package.

We add the repo root to :data:`sys.path` so ``from the_similarity.platform
...`` resolves when pytest is invoked from inside ``the-similarity-api/``.
This mirrors the ergonomic we use in the top-level project: tests do not
depend on an installed wheel; they import the in-tree package directly.

Why a conftest.py rather than a ``pyproject.toml`` / ``setup.cfg``:
``the-similarity-api`` does not currently ship its own package — it is
a thin FastAPI harness folder. Introducing packaging here would force
downstream CI to install a wheel, which is overkill for a test-only
gate. The sys.path hack is opt-in (tests only), idempotent, and
immediately visible to a reader.
"""
from __future__ import annotations

import sys
from pathlib import Path


# Walk two levels up from this file:
#   conftest.py → tests/ → the-similarity-api/ → <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[2]
# Insert at index 0 so this takes precedence over any pip-installed
# version of the package on the test machine (important in CI runners
# that may have a cached wheel).
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
