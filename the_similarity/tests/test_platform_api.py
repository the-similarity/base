"""Tests for :mod:`the_similarity.platform.api`.

Every test operates on a fresh app built via :func:`create_app` with the
:func:`get_registry` dependency overridden to point at a tmp-path SQLite
file. This keeps the production default (``~/.the_similarity/registry.db``)
untouched and lets parallel test runs avoid sharing state.

The worlds endpoint is NOT exercised end-to-end — that requires ``node``
plus the fractal package and is outside the Python unit-test surface. We
do hit the endpoint with a bogus scenario path to confirm input validation
returns 400, which is enough to lock in the shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from the_similarity.platform.api import create_app, get_registry
from the_similarity.platform.artifacts import RunArtifact, RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_artifact(
    *,
    run_id: str,
    kind: RunKind = RunKind.COPIES,
    summary: dict | None = None,
    artifact_paths: dict | None = None,
    run_dir: Path | None = None,
) -> RunArtifact:
    """Build a RunArtifact with test-friendly defaults.

    When ``run_dir`` is given it is embedded in provenance under the
    ``run_dir`` key — the artifact-streaming endpoint keys off this anchor
    to resolve relative paths.
    """
    provenance = {"generator_name": "test", "version": "0.0.0"}
    if run_dir is not None:
        provenance["run_dir"] = str(run_dir)
    return RunArtifact(
        run_id=run_id,
        kind=kind,
        config={"seed": 1},
        seed=1,
        artifact_paths=artifact_paths
        if artifact_paths is not None
        else {"telemetry": "run.jsonl"},
        summary=summary if summary is not None else {"score": 0.9},
        provenance=provenance,
        created_at="2026-04-15T20:00:00+00:00",
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """FastAPI TestClient backed by a tmp-path registry DB.

    Rather than rely on env vars (which leak across tests), we override
    the ``get_registry`` dependency directly so each client gets its own
    isolated registry file. The override also closes the connection on
    teardown — the default dependency does this via FastAPI's `yield`
    pattern but overrides must opt in.
    """
    db_path = tmp_path / "registry.db"
    app = create_app()

    def _override() -> Iterator[RunRegistry]:
        registry = RunRegistry(db_path)
        try:
            yield registry
        finally:
            registry.close()

    app.dependency_overrides[get_registry] = _override
    with TestClient(app) as tc:
        # Expose the db_path on the client so tests that want to register
        # rows outside the HTTP flow can open their own RunRegistry.
        tc.db_path = db_path  # type: ignore[attr-defined]
        yield tc


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------


def test_healthz_returns_ok_and_zero_runs(client: TestClient) -> None:
    """Fresh DB reports status=ok and runs=0."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["runs"] == 0
    # The DB path should match the tmp path we injected — guards against a
    # future change that accidentally ignores the override.
    assert body["registry_db"] == str(client.db_path)  # type: ignore[attr-defined]


def test_healthz_runs_count_reflects_registry_rows(client: TestClient) -> None:
    """After registering rows out-of-band, healthz.runs mirrors the count."""
    with RunRegistry(client.db_path) as reg:  # type: ignore[attr-defined]
        reg.register(_make_artifact(run_id="a" * 32))
        reg.register(_make_artifact(run_id="b" * 32))
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["runs"] == 2


# ---------------------------------------------------------------------------
# /runs list + /runs/{id}
# ---------------------------------------------------------------------------


def test_list_runs_empty(client: TestClient) -> None:
    """No registered rows → empty list payload, not 404."""
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == {"runs": []}


def test_list_runs_newest_first_with_kind_filter(client: TestClient) -> None:
    """Kind filter narrows results; order is newest-first by created_at."""
    with RunRegistry(client.db_path) as reg:  # type: ignore[attr-defined]
        # Distinct created_at so ordering is deterministic. The registry
        # orders by created_at DESC — later strings sort higher lexicographically.
        older = _make_artifact(run_id="1" * 32, kind=RunKind.COPIES)
        older.created_at = "2026-04-15T10:00:00+00:00"
        newer = _make_artifact(run_id="2" * 32, kind=RunKind.COPIES)
        newer.created_at = "2026-04-15T20:00:00+00:00"
        worlds = _make_artifact(run_id="3" * 32, kind=RunKind.WORLDS)
        worlds.created_at = "2026-04-15T15:00:00+00:00"
        reg.register(older)
        reg.register(newer)
        reg.register(worlds)

    resp = client.get("/runs")
    assert resp.status_code == 200
    ids = [r["run_id"] for r in resp.json()["runs"]]
    assert ids == ["2" * 32, "3" * 32, "1" * 32]

    resp = client.get("/runs", params={"kind": "copies"})
    assert resp.status_code == 200
    ids = [r["run_id"] for r in resp.json()["runs"]]
    assert ids == ["2" * 32, "1" * 32]


def test_get_run_by_id_roundtrip(client: TestClient) -> None:
    """Registering out-of-band then fetching by id yields an identical payload."""
    artifact = _make_artifact(run_id="c" * 32)
    with RunRegistry(client.db_path) as reg:  # type: ignore[attr-defined]
        reg.register(artifact)

    resp = client.get(f"/runs/{artifact.run_id}")
    assert resp.status_code == 200
    body = resp.json()
    # The response must round-trip the dataclass via to_dict — comparing
    # on dicts avoids false negatives on field ordering.
    assert body == artifact.to_dict()


def test_get_run_404_when_missing(client: TestClient) -> None:
    """Unknown run_id returns 404 with a descriptive detail."""
    resp = client.get("/runs/does-not-exist")
    assert resp.status_code == 404
    assert "does-not-exist" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /runs/{id}/artifacts/{name}
# ---------------------------------------------------------------------------


def test_get_run_artifact_streams_file(client: TestClient, tmp_path: Path) -> None:
    """Streaming a registered artifact returns the exact file bytes."""
    run_dir = tmp_path / "runs" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "telemetry.jsonl").write_text("line1\nline2\n", encoding="utf-8")

    artifact = _make_artifact(
        run_id="d" * 32,
        artifact_paths={"telemetry": "telemetry.jsonl"},
        run_dir=run_dir,
    )
    with RunRegistry(client.db_path) as reg:  # type: ignore[attr-defined]
        reg.register(artifact)

    resp = client.get(f"/runs/{artifact.run_id}/artifacts/telemetry")
    assert resp.status_code == 200
    assert resp.text == "line1\nline2\n"


def test_get_run_artifact_404_on_unknown_name(
    client: TestClient, tmp_path: Path
) -> None:
    """A logical name not in artifact_paths yields 404."""
    run_dir = tmp_path / "runs" / "run2"
    run_dir.mkdir(parents=True)
    artifact = _make_artifact(
        run_id="e" * 32,
        artifact_paths={"telemetry": "telemetry.jsonl"},
        run_dir=run_dir,
    )
    with RunRegistry(client.db_path) as reg:  # type: ignore[attr-defined]
        reg.register(artifact)

    resp = client.get(f"/runs/{artifact.run_id}/artifacts/does-not-exist")
    assert resp.status_code == 404


def test_get_run_artifact_404_on_unknown_run(client: TestClient) -> None:
    """Unknown run_id in the artifact path produces 404, not 500."""
    resp = client.get("/runs/unknown/artifacts/telemetry")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /runs/copies
# ---------------------------------------------------------------------------


def test_create_copies_run_registers_and_returns_artifact(
    client: TestClient, tmp_path: Path
) -> None:
    """End-to-end copies pipeline against the committed demo CSV.

    We point ``out_dir`` at tmp_path so the pipeline does not pollute the
    repo's artifacts/ tree during tests. ``n=100`` keeps the run fast
    (<1s on a laptop) while still exercising fidelity/privacy/utility
    scorecards that require non-trivial sample sizes.
    """
    repo_root = Path(__file__).resolve().parents[2]
    demo_csv = repo_root / "the_similarity" / "synthetic" / "demos" / "sample.csv"
    assert demo_csv.exists(), "demo fixture missing; CI seed has moved"

    resp = client.post(
        "/runs/copies",
        json={
            "input_path": str(demo_csv),
            "n": 100,
            "seed": 7,
            "out_dir": str(tmp_path / "copies"),
            "generator": "block_bootstrap",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Basic artifact shape invariants.
    assert body["kind"] == "copies"
    assert body["seed"] == 7
    assert set(body["artifact_paths"]) >= {"real", "synth", "scorecard"}
    assert body["summary"], "summary should include headline numbers"
    assert body["provenance"], "provenance should be populated by the runner"

    # The run must be discoverable via /runs/{id}.
    resp2 = client.get(f"/runs/{body['run_id']}")
    assert resp2.status_code == 200
    assert resp2.json()["run_id"] == body["run_id"]


def test_create_copies_run_400_on_missing_input(client: TestClient) -> None:
    """A non-existent input_path returns 400, not 500."""
    resp = client.post(
        "/runs/copies",
        json={
            "input_path": "/definitely/not/a/real/file.csv",
            "n": 10,
            "seed": 1,
            "generator": "block_bootstrap",
        },
    )
    assert resp.status_code == 400
    assert "not exist" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /runs/worlds — input validation only (Node runner not unit-tested)
# ---------------------------------------------------------------------------


def test_create_worlds_run_400_on_missing_scenario(client: TestClient) -> None:
    """Missing scenario file → 400, never hits the Node subprocess.

    We intentionally do NOT test the successful path end-to-end: that
    requires Node plus the fractal package and belongs in a cross-language
    integration suite, not Python unit tests.
    """
    resp = client.post(
        "/runs/worlds",
        json={
            "scenario_path": "/no/such/scenario.json",
            "seed": 1,
            "steps": 10,
        },
    )
    assert resp.status_code == 400
    assert "scenario" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /compare
# ---------------------------------------------------------------------------


def test_compare_returns_diff_shape(client: TestClient) -> None:
    """Two registered runs → compare returns a,b,diff with correct keys."""
    a = _make_artifact(
        run_id="a" * 32,
        summary={"score": 0.8, "n": 100},
    )
    b = _make_artifact(
        run_id="b" * 32,
        summary={"score": 0.9, "extra": "field"},
    )
    with RunRegistry(client.db_path) as reg:  # type: ignore[attr-defined]
        reg.register(a)
        reg.register(b)

    resp = client.post(
        "/compare",
        json={"run_id_a": a.run_id, "run_id_b": b.run_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["a"] == {"score": 0.8, "n": 100}
    assert body["b"] == {"score": 0.9, "extra": "field"}
    # diff surfaces every differing or missing-on-one-side key.
    diff = body["diff"]
    assert diff["score"] == [0.8, 0.9]
    assert diff["n"] == [100, None]
    assert diff["extra"] == [None, "field"]


def test_compare_404_when_either_run_missing(client: TestClient) -> None:
    """Unknown run_id in compare request → 404."""
    a = _make_artifact(run_id="a" * 32)
    with RunRegistry(client.db_path) as reg:  # type: ignore[attr-defined]
        reg.register(a)

    resp = client.post("/compare", json={"run_id_a": a.run_id, "run_id_b": "missing"})
    assert resp.status_code == 404
