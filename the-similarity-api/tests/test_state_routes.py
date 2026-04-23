"""Route-level tests for ``app.state_routes`` (the /platform/state surface).

Every test runs against a fresh :class:`fastapi.testclient.TestClient`
backed by a tmp-path SQLite file. We override the ``get_registry``
dependency (same pattern as ``test_platform_routes.py``) so test state
is strictly scoped and parallel test workers never share a registry.

Coverage map
------------
- :func:`test_projection_empty_registry` — empty registry returns empty list.
- :func:`test_projection_with_runs` — populated registry returns dicts with x/y/z.
- :func:`test_nearest_empty_registry` — unknown run_id returns empty list.
- :func:`test_nearest_with_runs` — nearest neighbors for a known run.
- :func:`test_clusters_empty` — empty registry returns empty outer list.
- :func:`test_transitions_empty` — empty registry returns empty list.
- :func:`test_cross_domain_empty` — unknown source returns empty list.
- :func:`test_cross_domain_with_runs` — cross-domain with populated registry.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform_routes import get_registry
from the_similarity.platform.artifacts import RunArtifact, RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_run(
    kind: RunKind = RunKind.COPIES,
    summary: dict | None = None,
    seed: int | None = 42,
) -> RunArtifact:
    """Build a minimal RunArtifact with a unique run_id."""
    return RunArtifact(
        run_id=uuid.uuid4().hex,
        kind=kind,
        config={"generator_name": "test_gen"},
        seed=seed,
        artifact_paths={},
        summary=summary or {"fidelity_score": 0.85, "n_rows": 1000},
        provenance={},
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """TestClient with a tmp-path registry DB injected via dependency override.

    Mirrors the fixture in ``test_platform_routes.py`` — fresh DB per test,
    override removed on teardown.
    """
    db_path = tmp_path / "registry.db"

    def _override() -> Iterator[RunRegistry]:
        registry = RunRegistry(db_path)
        # The registry's __init__ creates all tables via idempotent DDL.
        try:
            yield registry
        finally:
            registry.close()

    app.dependency_overrides[get_registry] = _override
    try:
        with TestClient(app) as tc:
            tc.db_path = db_path  # type: ignore[attr-defined]
            yield tc
    finally:
        app.dependency_overrides.pop(get_registry, None)


@pytest.fixture
def seeded_client(client: TestClient) -> TestClient:
    """Client with 3 runs pre-registered (2 copies, 1 worlds).

    Provides ``run_ids`` attribute for test convenience.
    """
    runs = [
        _make_run(RunKind.COPIES, summary={"fidelity_score": 0.9, "n_rows": 500}),
        _make_run(RunKind.COPIES, summary={"fidelity_score": 0.7, "n_rows": 1500}),
        _make_run(RunKind.WORLDS, summary={"tick_count": 200, "n_agents": 10}),
    ]
    # Register runs directly via the registry to avoid going through POST.
    registry = RunRegistry(client.db_path)  # type: ignore[attr-defined]
    for run in runs:
        registry.register(run)
    registry.close()

    client.run_ids = [r.run_id for r in runs]  # type: ignore[attr-defined]
    return client


# ---------------------------------------------------------------------------
# Projection endpoint
# ---------------------------------------------------------------------------


def test_projection_empty_registry(client: TestClient) -> None:
    """Empty registry should return an empty list, not an error."""
    resp = client.get("/platform/state/projection")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_projection_with_runs(seeded_client: TestClient) -> None:
    """Populated registry should return dicts with x, y, z, run_id, kind, label."""
    resp = seeded_client.get("/platform/state/projection")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 3

    # Every entry must have the required keys.
    for entry in data:
        assert "run_id" in entry
        assert "kind" in entry
        assert "x" in entry
        assert "y" in entry
        assert "z" in entry
        assert "label" in entry
        # Coordinates must be numeric.
        assert isinstance(entry["x"], (int, float))
        assert isinstance(entry["y"], (int, float))
        assert isinstance(entry["z"], (int, float))


# ---------------------------------------------------------------------------
# Nearest endpoint
# ---------------------------------------------------------------------------


def test_nearest_empty_registry(client: TestClient) -> None:
    """Unknown run_id in an empty registry should return empty list."""
    resp = client.get("/platform/state/nearest/nonexistent")
    assert resp.status_code == 200
    assert resp.json() == []


def test_nearest_with_runs(seeded_client: TestClient) -> None:
    """Nearest for a known run should return results (possibly empty if
    StateIndex is not available — the fallback doesn't support nearest).
    """
    run_id = seeded_client.run_ids[0]  # type: ignore[attr-defined]
    resp = seeded_client.get(f"/platform/state/nearest/{run_id}?k=2")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Without StateIndex, this will be empty — that's the expected
    # graceful degradation behavior.


# ---------------------------------------------------------------------------
# Clusters endpoint
# ---------------------------------------------------------------------------


def test_clusters_empty(client: TestClient) -> None:
    """Empty registry should return an empty outer list."""
    resp = client.get("/platform/state/clusters")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_clusters_with_runs(seeded_client: TestClient) -> None:
    """Clusters endpoint should return a list (possibly empty without StateGraph)."""
    resp = seeded_client.get("/platform/state/clusters")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Transitions endpoint
# ---------------------------------------------------------------------------


def test_transitions_empty(client: TestClient) -> None:
    """Empty registry should return an empty list."""
    resp = client.get("/platform/state/transitions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_transitions_with_kind_filter(seeded_client: TestClient) -> None:
    """Transitions with kind filter should return a list."""
    resp = seeded_client.get("/platform/state/transitions?kind=finance")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Cross-domain endpoint
# ---------------------------------------------------------------------------


def test_cross_domain_empty(client: TestClient) -> None:
    """Unknown source in empty registry should return empty list."""
    resp = client.get(
        "/platform/state/cross-domain/nonexistent?target_kind=worlds&k=3"
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_cross_domain_with_runs(seeded_client: TestClient) -> None:
    """Cross-domain for a known run should return results (may be empty
    without StateGraph/StateIndex).
    """
    run_id = seeded_client.run_ids[0]  # type: ignore[attr-defined]
    resp = seeded_client.get(
        f"/platform/state/cross-domain/{run_id}?target_kind=worlds&k=2"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Query parameter validation
# ---------------------------------------------------------------------------


def test_nearest_k_bounds(client: TestClient) -> None:
    """k parameter should be validated: k < 1 should fail."""
    resp = client.get("/platform/state/nearest/any_id?k=0")
    assert resp.status_code == 422


def test_cross_domain_requires_target_kind(client: TestClient) -> None:
    """target_kind is a required query param — omitting it should fail."""
    resp = client.get("/platform/state/cross-domain/any_id")
    assert resp.status_code == 422
