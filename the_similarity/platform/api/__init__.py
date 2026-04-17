"""Platform REST API — FastAPI surface over the Ops Layer.

This subpackage exposes every :class:`~the_similarity.platform.artifacts.RunArtifact`
producer (synthetic copies, headless worlds, parameter sweeps) and every
registry operation (list/get/stream/compare) behind a single HTTP interface.
It is the third priority of the platform thesis — below the artifact contract
(``artifacts.py``) and the registry (``registry.py``) — and it assumes both
are stable and present.

Lifecycle
---------
The FastAPI ``app`` is built once at import time via :func:`create_app` and
cached on the module. Callers who need a fresh app (tests, alternative
registry injection) should import :func:`create_app` directly and construct
their own instance; ``app`` is the convenience handle for
``uvicorn the_similarity.platform.api:app``.

Registry dependency
-------------------
Every route that needs the :class:`~the_similarity.platform.registry.RunRegistry`
receives it via FastAPI's ``Depends`` mechanism. The default provider
resolves the DB path from the ``THE_SIMILARITY_REGISTRY_DB`` env var, falling
back to ``~/.the_similarity/registry.db``. Tests override the dependency by
calling ``app.dependency_overrides[get_registry] = lambda: RunRegistry(tmp_db)``
so production and test code share one resolver.

Immutability
------------
``app`` is meant to be a singleton per-process. Do not mutate it after
import; configure behavior via environment variables or dependency overrides.

Exports
-------
- :data:`app`         — the FastAPI application instance (uvicorn target).
- :func:`create_app`  — factory for fresh app instances (tests, embed).
- :func:`get_registry` — dependency function; used in ``Depends`` wiring.
"""

from __future__ import annotations

from the_similarity.platform.api.main import app, create_app, get_registry

__all__ = ["app", "create_app", "get_registry"]
