"""Test package for the-similarity-api.

Tests here exercise the HTTP-layer integration between the platform
spine (:mod:`the_similarity.platform`) and any API-layer wrappers that
the ``the-similarity-api/app`` package may add on top. The Batch 1
spine ships its FastAPI surface inside
:mod:`the_similarity.platform.api`; these tests target that surface
through ``fastapi.testclient.TestClient`` with a tmp-path SQLite DB so
the real ``~/.the_similarity/registry.db`` is never touched.
"""
