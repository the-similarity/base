"""Route-level tests for ``app.platform_routes`` (the /platform surface).

Every test runs against a fresh :class:`fastapi.testclient.TestClient`
backed by a tmp-path SQLite file. We override the ``get_registry``
dependency directly (rather than relying on the env var) so test state
is strictly scoped to the fixture and parallel test workers never
share a registry.

Coverage map
------------
- :func:`test_healthz` — liveness on an empty DB.
- :func:`test_list_runs_empty` — empty list (not 404) when no rows.
- :func:`test_post_then_get_run` — round-trip a run record.
- :func:`test_post_run_duplicate_409` — upsert guard at the router.
- :func:`test_get_run_404` — unknown run_id surfaces 404 w/ detail.
- :func:`test_list_runs_filters` — kind / pillar / status / pagination.
- :func:`test_artifacts_crud` — register + list + get + 404 paths.
- :func:`test_scorecards_crud` — register + list paths.
- :func:`test_scenarios_crud` — empty list, create, duplicate 409, 404.
- :func:`test_datasets_crud` — empty list, create, duplicate 409, 404.

Why TestClient over raw ASGI?
-----------------------------
TestClient spins up the full FastAPI app in-process and exercises
dependency injection, middleware, and response validation — the same
code path a deployed server hits. That mirrors CI's contract exactly:
if a test passes here, the deployed API behaves the same way.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform_routes import get_registry
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """TestClient with a tmp-path registry DB injected via dependency override.

    Yields a :class:`TestClient` whose ``get_registry`` dependency opens
    a fresh :class:`RunRegistry` per request against ``tmp_path/registry.db``.
    The override is removed on teardown so subsequent fixtures are not
    polluted. ``db_path`` is attached to the client so tests that want to
    bypass the HTTP layer (for out-of-band seeding) can open the same DB.
    """
    db_path = tmp_path / "registry.db"

    def _override() -> Iterator[RunRegistry]:
        registry = RunRegistry(db_path)
        # Mirror the production dependency — ensure companion tables exist.
        # (The production get_registry does this too; here we duplicate the
        # call so the override is self-contained.)
        from app.platform_routes import _ensure_ext_schema

        _ensure_ext_schema(registry._conn)  # noqa: SLF001
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
        # Clean up the override so parallel tests with different fixtures
        # never leak the tmp_path DB into each other.
        app.dependency_overrides.pop(get_registry, None)


def _sample_run_payload(
    *,
    run_id: str = "a" * 32,
    kind: str = "copies",
    pillar: str | None = None,
    status: str = "complete",
    created_at: str = "2026-04-15T10:00:00+00:00",
) -> dict:
    """Build a minimal valid POST /platform/runs body.

    Kept as a plain dict (not a Pydantic model) so tests can pass it to
    ``client.post(..., json=...)`` without a separate serialization step.
    """
    body: dict = {
        "run_id": run_id,
        "kind": kind,
        "config": {"note": "test"},
        "seed": 1,
        "artifact_paths": {"scorecard": "scorecard.json"},
        "summary": {"score": 0.9},
        "provenance": {"generator_name": "test"},
        "created_at": created_at,
        "status": status,
    }
    if pillar is not None:
        body["pillar"] = pillar
    return body


# ---------------------------------------------------------------------------
# /platform/healthz
# ---------------------------------------------------------------------------


def test_healthz_ok_on_empty_db(client: TestClient) -> None:
    """Fresh DB must answer 200 with status=ok — the registry is reachable."""
    resp = client.get("/platform/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /platform/runs — list + POST + GET
# ---------------------------------------------------------------------------


def test_list_runs_empty(client: TestClient) -> None:
    """An empty registry returns an empty list, not 404."""
    resp = client.get("/platform/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_then_get_run_round_trip(client: TestClient) -> None:
    """POST /platform/runs then GET /platform/runs/{id} returns the same record."""
    payload = _sample_run_payload(pillar="finance")

    post_resp = client.post("/platform/runs", json=payload)
    assert post_resp.status_code == 201, post_resp.text
    assert post_resp.json() == {"run_id": payload["run_id"]}

    get_resp = client.get(f"/platform/runs/{payload['run_id']}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    # Core fields match the payload verbatim.
    assert body["run_id"] == payload["run_id"]
    assert body["kind"] == payload["kind"]
    assert body["seed"] == payload["seed"]
    assert body["summary"] == payload["summary"]
    assert body["created_at"] == payload["created_at"]
    # Extension fields round-trip through provenance.
    assert body["pillar"] == "finance"
    assert body["status"] == "complete"
    assert body["provenance"]["pillar"] == "finance"
    assert body["provenance"]["status"] == "complete"


def test_post_run_duplicate_returns_409(client: TestClient) -> None:
    """Re-POST of the same run_id must surface as a 409 conflict."""
    payload = _sample_run_payload()
    assert client.post("/platform/runs", json=payload).status_code == 201
    dup = client.post("/platform/runs", json=payload)
    assert dup.status_code == 409
    assert payload["run_id"] in dup.json()["detail"]


def test_get_run_404_on_unknown_id(client: TestClient) -> None:
    """Unknown run_id yields 404 with the offending id in the detail body."""
    resp = client.get("/platform/runs/doesnotexist")
    assert resp.status_code == 404
    assert "doesnotexist" in resp.json()["detail"]


def test_list_runs_filters_kind_pillar_status_and_pagination(
    client: TestClient,
) -> None:
    """Filters compose; pagination slices the filtered result newest-first."""
    # Three runs across two kinds, two pillars, two statuses.
    runs = [
        _sample_run_payload(
            run_id="1" * 32,
            kind="copies",
            pillar="finance",
            status="complete",
            created_at="2026-04-15T10:00:00+00:00",
        ),
        _sample_run_payload(
            run_id="2" * 32,
            kind="copies",
            pillar="synthetic-data",
            status="failed",
            created_at="2026-04-15T11:00:00+00:00",
        ),
        _sample_run_payload(
            run_id="3" * 32,
            kind="worlds",
            pillar="finance",
            status="complete",
            created_at="2026-04-15T12:00:00+00:00",
        ),
    ]
    for r in runs:
        assert client.post("/platform/runs", json=r).status_code == 201

    # Unfiltered: newest-first (3, 2, 1).
    ids = [r["run_id"] for r in client.get("/platform/runs").json()]
    assert ids == ["3" * 32, "2" * 32, "1" * 32]

    # Filter by kind=copies — drops run 3.
    ids = [
        r["run_id"]
        for r in client.get("/platform/runs", params={"kind": "copies"}).json()
    ]
    assert ids == ["2" * 32, "1" * 32]

    # Filter by pillar=finance — drops run 2.
    ids = [
        r["run_id"]
        for r in client.get("/platform/runs", params={"pillar": "finance"}).json()
    ]
    assert ids == ["3" * 32, "1" * 32]

    # Filter by status=failed — only run 2.
    ids = [
        r["run_id"]
        for r in client.get("/platform/runs", params={"status": "failed"}).json()
    ]
    assert ids == ["2" * 32]

    # Composite filter: kind=copies + pillar=finance + status=complete — run 1.
    ids = [
        r["run_id"]
        for r in client.get(
            "/platform/runs",
            params={"kind": "copies", "pillar": "finance", "status": "complete"},
        ).json()
    ]
    assert ids == ["1" * 32]

    # Pagination: limit=1 then offset=1 walks the list.
    page0 = client.get("/platform/runs", params={"limit": 1, "offset": 0}).json()
    page1 = client.get("/platform/runs", params={"limit": 1, "offset": 1}).json()
    page2 = client.get("/platform/runs", params={"limit": 1, "offset": 2}).json()
    assert [p[0]["run_id"] for p in (page0, page1, page2)] == [
        "3" * 32,
        "2" * 32,
        "1" * 32,
    ]


def test_list_runs_limit_clamped_to_max(client: TestClient) -> None:
    """limit above 200 is rejected by FastAPI validation (422)."""
    resp = client.get("/platform/runs", params={"limit": 500})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /platform/runs/{id}/artifacts — CRUD
# ---------------------------------------------------------------------------


def test_artifacts_empty_list_on_known_run(client: TestClient) -> None:
    """A registered run with no artifact rows returns [] (not 404)."""
    run = _sample_run_payload()
    assert client.post("/platform/runs", json=run).status_code == 201
    resp = client.get(f"/platform/runs/{run['run_id']}/artifacts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_artifacts_404_on_unknown_run(client: TestClient) -> None:
    """Listing artifacts for a missing run is 404, not an empty list."""
    resp = client.get("/platform/runs/nope/artifacts")
    assert resp.status_code == 404


def test_artifacts_create_list_get(client: TestClient) -> None:
    """POST + list + GET round-trip for artifact rows."""
    run = _sample_run_payload()
    assert client.post("/platform/runs", json=run).status_code == 201

    artifact_body = {
        "run_id": run["run_id"],
        "name": "scorecard",
        "path": "scorecard.json",
        "content_type": "application/json",
        "size_bytes": 1234,
        "sha256": "deadbeef" * 8,
        "created_at": "2026-04-15T10:00:00+00:00",
    }
    resp = client.post(
        f"/platform/runs/{run['run_id']}/artifacts", json=artifact_body
    )
    assert resp.status_code == 201, resp.text
    assert resp.json() == artifact_body

    listing = client.get(f"/platform/runs/{run['run_id']}/artifacts").json()
    assert listing == [artifact_body]

    fetched = client.get(
        f"/platform/runs/{run['run_id']}/artifacts/scorecard"
    ).json()
    assert fetched == artifact_body


def test_artifact_get_404_on_unknown_name(client: TestClient) -> None:
    """Existing run but unknown artifact name → 404."""
    run = _sample_run_payload()
    client.post("/platform/runs", json=run)
    resp = client.get(f"/platform/runs/{run['run_id']}/artifacts/missing")
    assert resp.status_code == 404


def test_artifact_post_duplicate_409(client: TestClient) -> None:
    """Second POST of same (run_id, name) pair is 409."""
    run = _sample_run_payload()
    client.post("/platform/runs", json=run)
    artifact_body = {
        "run_id": run["run_id"],
        "name": "scorecard",
        "path": "scorecard.json",
        "created_at": "2026-04-15T10:00:00+00:00",
    }
    assert (
        client.post(
            f"/platform/runs/{run['run_id']}/artifacts", json=artifact_body
        ).status_code
        == 201
    )
    dup = client.post(
        f"/platform/runs/{run['run_id']}/artifacts", json=artifact_body
    )
    assert dup.status_code == 409


def test_artifact_post_url_body_run_id_mismatch_422(client: TestClient) -> None:
    """body.run_id must match URL run_id — mismatch is 422."""
    run = _sample_run_payload()
    client.post("/platform/runs", json=run)
    body = {
        "run_id": "different",
        "name": "scorecard",
        "path": "scorecard.json",
        "created_at": "2026-04-15T10:00:00+00:00",
    }
    resp = client.post(f"/platform/runs/{run['run_id']}/artifacts", json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /platform/runs/{id}/scorecards
# ---------------------------------------------------------------------------


def test_scorecards_create_and_list(client: TestClient) -> None:
    """Scorecards POST + list round-trip, including metrics dict."""
    run = _sample_run_payload()
    client.post("/platform/runs", json=run)
    scorecard = {
        "run_id": run["run_id"],
        "name": "fidelity",
        "passed": True,
        "overall_score": 0.87,
        "metrics": {"ks": 0.02, "acf_mae": 0.015},
        "created_at": "2026-04-15T10:00:00+00:00",
    }
    resp = client.post(
        f"/platform/runs/{run['run_id']}/scorecards", json=scorecard
    )
    assert resp.status_code == 201, resp.text

    listing = client.get(f"/platform/runs/{run['run_id']}/scorecards").json()
    assert len(listing) == 1
    assert listing[0]["name"] == "fidelity"
    assert listing[0]["passed"] is True
    assert listing[0]["overall_score"] == 0.87
    assert listing[0]["metrics"] == {"ks": 0.02, "acf_mae": 0.015}


def test_scorecards_list_404_on_unknown_run(client: TestClient) -> None:
    """Listing scorecards for a missing run is 404."""
    resp = client.get("/platform/runs/unknown/scorecards")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /platform/scenarios
# ---------------------------------------------------------------------------


def test_scenarios_empty_list(client: TestClient) -> None:
    """Fresh DB returns an empty scenarios list."""
    resp = client.get("/platform/scenarios")
    assert resp.status_code == 200
    assert resp.json() == []


def test_scenarios_crud(client: TestClient) -> None:
    """POST + list + GET + duplicate guard for scenarios."""
    body = {
        "scenario_id": "spy-baseline",
        "name": "SPY baseline 2020",
        "description": "SPY daily bars, baseline params.",
        "pillar": "finance",
        "parameters": {"seed_grid": [1, 2, 3], "lookback": 512},
        "created_at": "2026-04-15T10:00:00+00:00",
    }
    assert client.post("/platform/scenarios", json=body).status_code == 201
    # Duplicate POST → 409.
    assert client.post("/platform/scenarios", json=body).status_code == 409

    # Listing includes the new scenario.
    listing = client.get("/platform/scenarios").json()
    assert len(listing) == 1
    assert listing[0]["scenario_id"] == "spy-baseline"

    # GET by id returns the full record.
    fetched = client.get("/platform/scenarios/spy-baseline").json()
    assert fetched["parameters"] == {"seed_grid": [1, 2, 3], "lookback": 512}

    # Unknown id → 404.
    assert client.get("/platform/scenarios/unknown").status_code == 404


def test_scenarios_pillar_filter(client: TestClient) -> None:
    """List filter on pillar narrows results."""
    for i, pillar in enumerate(["finance", "synthetic-data", "finance"]):
        client.post(
            "/platform/scenarios",
            json={
                "scenario_id": f"s-{i}",
                "name": f"s-{i}",
                "pillar": pillar,
                "parameters": {},
                "created_at": f"2026-04-15T1{i}:00:00+00:00",
            },
        )
    ids = [
        s["scenario_id"]
        for s in client.get(
            "/platform/scenarios", params={"pillar": "finance"}
        ).json()
    ]
    # Newest-first: s-2 created at 12:00, s-0 at 10:00.
    assert ids == ["s-2", "s-0"]


# ---------------------------------------------------------------------------
# /platform/datasets
# ---------------------------------------------------------------------------


def test_datasets_empty_list(client: TestClient) -> None:
    """Fresh DB returns an empty datasets list."""
    resp = client.get("/platform/datasets")
    assert resp.status_code == 200
    assert resp.json() == []


def test_datasets_crud(client: TestClient) -> None:
    """POST + list + GET + duplicate guard for datasets."""
    body = {
        "dataset_id": "spy-daily",
        "name": "SPY daily bars",
        "description": "S&P 500 ETF daily close, 1993-2026.",
        "path": "the-similarity-data/data/equities/SPY/1d.parquet",
        # Alias 'schema' is the wire key; python attr is 'schema_'. Pydantic
        # accepts either because model_config sets populate_by_name=True.
        "schema": {"columns": ["open", "high", "low", "close", "volume"]},
        "version": "2026.04",
        "created_at": "2026-04-15T10:00:00+00:00",
    }
    assert client.post("/platform/datasets", json=body).status_code == 201
    # Duplicate POST → 409.
    assert client.post("/platform/datasets", json=body).status_code == 409

    # Listing includes the new dataset.
    listing = client.get("/platform/datasets").json()
    assert len(listing) == 1
    assert listing[0]["dataset_id"] == "spy-daily"
    # Response uses the 'schema' wire key (alias).
    assert listing[0]["schema"]["columns"] == [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    # GET by id returns the full record.
    fetched = client.get("/platform/datasets/spy-daily").json()
    assert fetched["version"] == "2026.04"

    # Unknown id → 404.
    assert client.get("/platform/datasets/unknown").status_code == 404


# ---------------------------------------------------------------------------
# Env-var path resolution — smoke test for settings.resolve_registry_db
# ---------------------------------------------------------------------------


def test_registry_env_override_uses_tmp_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting THE_SIMILARITY_REGISTRY_DB redirects the default dependency.

    We do NOT override ``get_registry`` here; the point is to prove the
    env-var path resolves lazily in :func:`app.settings.resolve_registry_db`
    so the default dependency honors late-binding env vars.
    """
    db_path = tmp_path / "env-registry.db"
    monkeypatch.setenv("THE_SIMILARITY_REGISTRY_DB", str(db_path))
    # Clear any lingering override from prior tests — fresh default path.
    app.dependency_overrides.pop(get_registry, None)
    try:
        with TestClient(app) as tc:
            resp = tc.get("/platform/healthz")
            assert resp.status_code == 200
            # The registry must have been created at the env-var path.
            assert db_path.exists()
    finally:
        # Restore clean state.
        app.dependency_overrides.pop(get_registry, None)
