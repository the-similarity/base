"""FastAPI application settings loaded from environment variables.

Responsibilities
----------------
- Centralize every environment-var-driven knob used by ``app/main.py`` and
  its routers so no module reads ``os.environ`` directly at request time.
- Expose a module-level :data:`settings` singleton for import-time reads
  (CORS origins, app version, etc.) and a helper :func:`resolve_registry_db`
  for request-time reads that must honor late-binding env vars (tests set
  ``THE_SIMILARITY_REGISTRY_DB`` via ``monkeypatch.setenv`` *after* this
  module has imported, so the path must be re-resolved per request, not
  snapshotted at import).

Invariants
----------
- Defaults are local-dev friendly. Production deploys override via env vars.
- :func:`resolve_registry_db` never raises on unset env: the default
  ``~/.the_similarity/registry.db`` is always returned when no override is
  present. Parent dir creation is the registry's responsibility, not ours.
"""

from __future__ import annotations

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Canonical env-var names — exported so tests and routers reference a single
# string literal rather than re-typing the key.
# ---------------------------------------------------------------------------

ENV_REGISTRY_DB = "THE_SIMILARITY_REGISTRY_DB"
"""Env var name for the platform registry SQLite path (see /platform/*)."""

# Default registry DB path — matches the platform API module
# (``the_similarity/platform/api/main.py``) so both surfaces share one
# registry file when neither process pins the env var.
DEFAULT_REGISTRY_DB_PATH = Path("~/.the_similarity/registry.db")


def split_csv(value: str) -> list[str]:
    """Split a comma-separated env var into a list, stripping whitespace."""
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_registry_db() -> Path:
    """Return the platform registry DB path per env-var precedence.

    Resolved at call time — NOT at import — so tests that set
    :data:`ENV_REGISTRY_DB` via ``monkeypatch.setenv`` after this module
    imports still see the override.

    Precedence
    ----------
    1. ``THE_SIMILARITY_REGISTRY_DB`` env var (absolute or user-relative).
    2. Fallback ``~/.the_similarity/registry.db``.

    Parent directory creation is deferred to the registry implementation
    itself — this helper is pure path resolution.
    """
    override = os.environ.get(ENV_REGISTRY_DB)
    if override:
        return Path(override).expanduser()
    return DEFAULT_REGISTRY_DB_PATH.expanduser()


class Settings:
    """Application settings populated from environment variables.

    Not using pydantic-settings here to keep the dependency footprint small.
    Every attribute has a sensible default for local development.
    """

    def __init__(self) -> None:
        # Service identification — used in /health and OpenAPI docs
        self.app_name = os.getenv("THE_SIMILARITY_API_NAME", "The Similarity API")
        self.app_version = os.getenv("THE_SIMILARITY_API_VERSION", "0.1.0")

        # Network binding — 127.0.0.1 is localhost-only by default for safety
        self.host = os.getenv("THE_SIMILARITY_API_HOST", "127.0.0.1")
        self.port = int(os.getenv("THE_SIMILARITY_API_PORT", "8000"))

        # CORS allowed origins — the Next.js frontend (3000-3004 worktrees)
        # and local fractal viewers (8080 / 8765) are allowed by default for local development.
        # In production, set this to the actual frontend domain(s).
        self.allowed_origins = split_csv(
            os.getenv(
                "THE_SIMILARITY_ALLOWED_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002,http://localhost:3003,http://127.0.0.1:3003,http://localhost:3004,http://127.0.0.1:3004,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001,http://localhost:8002,http://127.0.0.1:8002,http://localhost:8003,http://127.0.0.1:8003,http://localhost:8004,http://127.0.0.1:8004,http://localhost:8080,http://127.0.0.1:8080,http://localhost:8765,http://127.0.0.1:8765",
            )
        )

        # Platform registry DB — captured at import for display/logging only.
        # Routers MUST use :func:`resolve_registry_db` instead so test
        # overrides via ``monkeypatch.setenv`` are honored.
        self.registry_db_path = resolve_registry_db()


# Module-level singleton — imported by main.py and other modules.
# This is created once at import time and lives for the process lifetime.
settings = Settings()
