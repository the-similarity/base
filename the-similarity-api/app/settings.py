"""
FastAPI application settings loaded from environment variables.

AI AGENT NOTES:
- All config is driven by env vars with sensible defaults for local dev.
- CORS origins default to localhost:3000 (Next.js) and localhost:8080 (fractal).
- To add a new config value, add it as an attribute in `Settings.__init__()`.
- The `settings` singleton at module scope is imported by `main.py` and other
  modules that need configuration values at import time.
"""

from __future__ import annotations

import os


def split_csv(value: str) -> list[str]:
    """Split a comma-separated env var into a list, stripping whitespace."""
    return [item.strip() for item in value.split(",") if item.strip()]


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

        # CORS allowed origins — the Next.js frontend (3000) and the fractal
        # terrain viewer (8080) are allowed by default for local development.
        # In production, set this to the actual frontend domain(s).
        self.allowed_origins = split_csv(
            os.getenv("THE_SIMILARITY_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080")
        )


# Module-level singleton — imported by main.py and other modules.
# This is created once at import time and lives for the process lifetime.
settings = Settings()
