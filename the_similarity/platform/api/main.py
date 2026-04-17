"""FastAPI application factory and uvicorn entrypoint for the Platform API.

Responsibilities
----------------
1. Build a fresh FastAPI ``app`` via :func:`create_app` with CORS configured
   and every route from :mod:`the_similarity.platform.api.routes` mounted.
2. Expose a module-level :data:`app` so
   ``uvicorn the_similarity.platform.api:app`` resolves without extra wiring.
3. Provide a dependency function :func:`get_registry` that every route
   injects via ``Depends(get_registry)``. Tests override this on a per-app
   basis using ``app.dependency_overrides[get_registry]``.
4. Ship a thin ``__main__`` so ``python -m the_similarity.platform.api``
   launches uvicorn with the right import target.

DB path resolution (matches the CLI surface for consistency)
------------------------------------------------------------
1. ``THE_SIMILARITY_REGISTRY_DB`` environment variable, if set.
2. Fallback ``~/.the_similarity/registry.db`` (parent dir auto-created by
   :class:`RunRegistry`).

Host / port resolution
----------------------
- ``--host`` / ``--port`` CLI flags take precedence.
- ``THE_SIMILARITY_API_HOST`` / ``THE_SIMILARITY_API_PORT`` env vars
  otherwise.
- Defaults ``0.0.0.0`` / ``8787`` — ``8787`` because 8080/8000 are already
  taken by the Next.js UI and the backend dev server on most developer
  laptops.

CORS
----
Enabled for all origins (``*``) in MVP so the local Next.js UI on
``localhost:3000`` (or any dev origin) can call the API without a proxy.
We will lock this down before deploying beyond dev.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Environment variable names — kept as module constants so tests and other
# modules reference one canonical string, not a hand-typed literal.
# ---------------------------------------------------------------------------

ENV_DB_PATH = "THE_SIMILARITY_REGISTRY_DB"
ENV_HOST = "THE_SIMILARITY_API_HOST"
ENV_PORT = "THE_SIMILARITY_API_PORT"

# Default DB path matches `python -m the_similarity.platform` so both
# surfaces share one registry file by default. Expanded lazily at request
# time so tests that set the env var before making a request see the
# override even if the API module was imported earlier.
DEFAULT_DB_PATH = Path("~/.the_similarity/registry.db")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8787


# ---------------------------------------------------------------------------
# Registry dependency
# ---------------------------------------------------------------------------


def _resolve_db_path() -> Path:
    """Return the DB path per the precedence rules in the module docstring.

    Resolved at call time — not at import — so env-var overrides set by
    tests after import still take effect.
    """
    env_value = os.environ.get(ENV_DB_PATH)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_DB_PATH.expanduser()


def get_registry() -> Iterator[RunRegistry]:
    """FastAPI dependency yielding a per-request :class:`RunRegistry`.

    A fresh connection is opened per request and closed on teardown so
    requests never share a ``sqlite3.Connection`` across threads (which
    ``sqlite3`` prohibits by default). The registry's WAL journal mode
    keeps concurrent requests from blocking each other at the DB level.

    Tests override this with ``app.dependency_overrides[get_registry]``
    pointing at a tmp-path registry so production defaults are never
    touched by the suite.
    """
    registry = RunRegistry(_resolve_db_path())
    try:
        yield registry
    finally:
        registry.close()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build a fresh FastAPI app with CORS + routes mounted.

    Called once at module import to produce :data:`app`, and separately by
    tests that want a clean instance without test-suite pollution of the
    ``dependency_overrides`` dict.
    """
    # Import here rather than at module top to avoid a circular import:
    # routes.py depends on get_registry defined above.
    from the_similarity.platform.api.routes import router

    application = FastAPI(
        title="The Similarity — Platform API",
        description=(
            "REST surface over the Ops Layer — run registry + synthetic / "
            "worlds / sweep runners. See /docs for the full OpenAPI schema."
        ),
        version="0.1.0",
    )

    # Dev-mode CORS: everything open. We revisit this before any deploy
    # outside localhost — see module docstring.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(router)
    return application


# Eagerly construct a module-level app so `uvicorn the_similarity.platform.api:app`
# resolves. Fresh instances for tests come from create_app() directly.
app = create_app()


# ---------------------------------------------------------------------------
# uvicorn entrypoint — `python -m the_similarity.platform.api`
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Argparse parser for the ``python -m`` entrypoint.

    Kept separate from :func:`main` so tests can introspect the parser
    without binding sockets.
    """
    parser = argparse.ArgumentParser(
        prog="python -m the_similarity.platform.api",
        description="Serve the Platform REST API via uvicorn.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help=(f"Host interface (default ${ENV_HOST} or {DEFAULT_HOST})."),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=(f"TCP port (default ${ENV_PORT} or {DEFAULT_PORT})."),
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable uvicorn auto-reload (dev only).",
    )
    return parser


def _resolve_host(cli_value: Optional[str]) -> str:
    """CLI flag > env var > default. Centralizing keeps precedence uniform."""
    if cli_value is not None:
        return cli_value
    return os.environ.get(ENV_HOST, DEFAULT_HOST)


def _resolve_port(cli_value: Optional[int]) -> int:
    """CLI flag > env var > default. ``int`` cast mirrors the argparse type."""
    if cli_value is not None:
        return cli_value
    env_value = os.environ.get(ENV_PORT)
    if env_value is not None:
        return int(env_value)
    return DEFAULT_PORT


def main(
    argv: Optional[list[str]] = None,
) -> None:  # pragma: no cover - serves a socket
    """Launch uvicorn against this module's ``app`` instance.

    Not covered by unit tests because it binds a socket; the smoke test is
    manual (see PR description) and the CI gate comes from route-level
    tests via ``TestClient``, which exercises the same app without a
    network hop.
    """
    import uvicorn

    parser = _build_parser()
    args = parser.parse_args(argv)
    host = _resolve_host(args.host)
    port = _resolve_port(args.port)
    # `import_string` form so uvicorn's reload worker can reimport the
    # module cleanly when --reload is enabled.
    uvicorn.run(
        "the_similarity.platform.api:app",
        host=host,
        port=port,
        reload=args.reload,
    )


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "ENV_DB_PATH",
    "ENV_HOST",
    "ENV_PORT",
    "app",
    "create_app",
    "get_registry",
    "main",
]
