"""HTTP-layer integration tests for the platform spine.

These tests hit the actual FastAPI surface at
:mod:`the_similarity.platform.api` via :class:`fastapi.testclient.TestClient`
with the registry ``get_registry`` dependency overridden to point at a
tmp-path SQLite DB. They exercise the end-to-end path a real client
takes (JSON in, JSON out) for every pillar:

- **finance / eval** runs — registered out-of-band, queried over HTTP.
- **copies** runs — registered out-of-band, queried over HTTP.
- **worlds** runs — registered out-of-band, queried over HTTP.

The POST ``/runs/{copies,worlds,sweep}`` endpoints are NOT exercised
end-to-end here — they are covered by
``the_similarity/tests/test_platform_api.py``. This suite focuses on
**cross-pillar visibility over HTTP**: GET listings filtered by kind,
GET individual runs, POST /compare across pillars.

Every test uses its own ``TestClient`` backed by its own tmp-path
registry — no shared state, no production-DB pollution.
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
# Pillar factories — mirror the Python-side integration test factories so
# the two suites lock in the same example shapes.
# ---------------------------------------------------------------------------


def _finance_artifact(
    *, run_id: str = "e" * 32, created_at: str = "2026-04-15T18:30:00+00:00"
) -> RunArtifact:
    """Synthetic finance / eval artifact — canonical finance payload."""
    return RunArtifact(
        run_id=run_id,
        kind=RunKind.EVAL,
        config={
            "symbol": "SPY",
            "start": "2020-01-01",
            "end": "2020-06-30",
            "method": "dtw",
        },
        seed=42,
        artifact_paths={
            "forecast": "forecast.parquet",
            "metrics": "metrics.json",
            "report": "report.md",
        },
        summary={
            "hit_rate": 0.62,
            "crps": 0.18,
            "mae": 0.012,
            "calibration_error": 0.04,
        },
        provenance={
            "generator_name": "backtester",
            "generator_version": "0.2.1",
            "seed": 42,
            "symbol": "SPY",
            "start": "2020-01-01",
            "end": "2020-06-30",
            "created_at": created_at,
        },
        created_at=created_at,
    )


def _copies_artifact(
    *, run_id: str = "c" * 32, created_at: str = "2026-04-15T18:44:00+00:00"
) -> RunArtifact:
    """Synthetic copies artifact — canonical copies payload."""
    return RunArtifact(
        run_id=run_id,
        kind=RunKind.COPIES,
        config={
            "input_path": "/repo/the_similarity/synthetic/demos/sample.csv",
            "n": 100,
            "seed": 7,
            "generator": "block_bootstrap",
        },
        seed=7,
        artifact_paths={
            "real": "real.parquet",
            "synth": "synth.parquet",
            "scorecard": "scorecard.json",
            "provenance": "provenance.json",
            "report": "report.md",
        },
        summary={
            "passed": True,
            "fidelity_score": 0.87,
            "privacy_score": 0.91,
            "utility_transfer_gap": 0.04,
        },
        provenance={
            "source_id": "sample",
            "generator_name": "block_bootstrap",
            "generator_version": "0.1.0",
            "seed": 7,
            "created_at": created_at,
            "params": {"block_size": 32},
        },
        created_at=created_at,
    )


def _worlds_artifact(
    *, run_id: str = "w" * 32, created_at: str = "2026-04-15T19:00:00+00:00"
) -> RunArtifact:
    """Synthetic worlds artifact — canonical worlds payload."""
    return RunArtifact(
        run_id=run_id,
        kind=RunKind.WORLDS,
        config={
            "scenario_path": "/repo/the-similarity-fractal/scenarios/small_village.json",
            "seed": 1,
            "steps": 500,
        },
        seed=1,
        artifact_paths={"telemetry": "run.jsonl"},
        summary={
            "n_ticks": 500,
            "regime_coverage": 0.73,
            "controllability_p_value": 0.01,
            "runtime_ms": 4821,
        },
        provenance={
            "generator_name": "small_village",
            "version": "0.3.0",
            "seed": 1,
            "scenario_name": "small_village",
            "scenario": {"actors": 40, "cadence": "daily"},
            "params": {},
            "created_at": created_at,
        },
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Fixture: TestClient + tmp registry DB
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """FastAPI TestClient backed by a per-test SQLite DB.

    We override ``get_registry`` directly on the app rather than set the
    ``THE_SIMILARITY_REGISTRY_DB`` env var because env vars leak across
    tests; dependency overrides are scoped to the test's app instance.

    The override yields a registry per request and closes it on teardown —
    matching the production dependency's ``yield``/``close()`` contract.
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
        # Expose the tmp DB path on the client so tests that register
        # out-of-band can open their own connection.
        tc.db_path = db_path  # type: ignore[attr-defined]
        yield tc


# ---------------------------------------------------------------------------
# 1. Healthz + empty registry shape.
# ---------------------------------------------------------------------------


def test_healthz_reflects_fresh_registry(client: TestClient) -> None:
    """Fresh DB → ``status=ok`` and ``runs=0``.

    Smoke test that the app builds, the dependency override is honoured,
    and the registry round-trips a no-op SELECT.
    """
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["runs"] == 0
    # The DB path MUST match the tmp path — catches a future change that
    # silently reverts to the default registry path.
    assert body["registry_db"] == str(client.db_path)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 2. Cross-pillar listing over HTTP.
# ---------------------------------------------------------------------------


def _seed_all_pillars(client: TestClient) -> None:
    """Register one run per pillar out-of-band via the tmp DB.

    We bypass POST /runs/* because those endpoints invoke real runners
    (synthetic pipeline, node subprocess). This suite is about the HTTP
    read surface over a populated registry; runner coverage lives in
    the Python-side tests.
    """
    with RunRegistry(client.db_path) as registry:  # type: ignore[attr-defined]
        registry.register(_finance_artifact())
        registry.register(_copies_artifact())
        registry.register(_worlds_artifact())


def test_get_runs_lists_every_pillar(client: TestClient) -> None:
    """GET /runs returns all three pillars, newest-first."""
    _seed_all_pillars(client)
    resp = client.get("/runs")
    assert resp.status_code == 200
    body = resp.json()
    kinds = [row["kind"] for row in body["runs"]]
    # Our fixture stages timestamps: worlds (19:00) > copies (18:44) > eval (18:30)
    assert kinds == ["worlds", "copies", "eval"]


@pytest.mark.parametrize(
    "kind,expected_run_id",
    [
        ("copies", "c" * 32),
        ("worlds", "w" * 32),
        ("eval", "e" * 32),
    ],
)
def test_get_runs_filter_by_kind_isolates_pillars(
    client: TestClient, kind: str, expected_run_id: str
) -> None:
    """GET /runs?kind=X returns only runs of kind X.

    This is the HTTP-layer mirror of the Python-side isolation test —
    it catches regressions where the route drops the ``kind`` query
    parameter or the Pydantic model coerces it incorrectly.
    """
    _seed_all_pillars(client)
    resp = client.get("/runs", params={"kind": kind})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["runs"]) == 1
    assert body["runs"][0]["run_id"] == expected_run_id
    assert body["runs"][0]["kind"] == kind


def test_get_runs_with_invalid_kind_returns_422(client: TestClient) -> None:
    """Unknown kind strings fail fast at the FastAPI validation layer.

    Locks in the enum-validation behaviour so a typo in the UI's query
    string surfaces as a clear 422 rather than a silently-empty 200.
    """
    resp = client.get("/runs", params={"kind": "not-a-real-pillar"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. GET /runs/{run_id} — individual record round-trips over HTTP.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [_finance_artifact, _copies_artifact, _worlds_artifact],
    ids=["finance", "copies", "worlds"],
)
def test_get_run_by_id_round_trip(client: TestClient, factory) -> None:
    """GET /runs/{id} returns the exact artifact we registered.

    Round-trips through ``RunArtifact.to_dict`` on the way out — so any
    drift between the Pydantic wire model and the dataclass shape is
    caught here.
    """
    artifact = factory()
    with RunRegistry(client.db_path) as registry:  # type: ignore[attr-defined]
        registry.register(artifact)

    resp = client.get(f"/runs/{artifact.run_id}")
    assert resp.status_code == 200
    assert resp.json() == artifact.to_dict()


def test_get_run_unknown_id_returns_404(client: TestClient) -> None:
    """Unknown ids surface as 404 with a descriptive detail."""
    resp = client.get("/runs/deadbeef" * 4)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. Artifact streaming per pillar — hit /runs/{id}/artifacts/{name}.
# ---------------------------------------------------------------------------


def test_get_run_artifact_streams_file_per_pillar(
    client: TestClient, tmp_path: Path
) -> None:
    """Each pillar's artifact_paths entries resolve into streamable files.

    We write a minimal on-disk fixture for one artifact per pillar, embed
    the ``run_dir`` into provenance, and assert that the file bytes round
    trip through GET /runs/{id}/artifacts/{name}.
    """
    # -- copies pillar: write a dummy scorecard.json ----------------------
    copies_dir = tmp_path / "copies-run"
    copies_dir.mkdir()
    (copies_dir / "scorecard.json").write_text('{"fidelity":0.87}', encoding="utf-8")
    copies_artifact = _copies_artifact()
    copies_artifact.provenance["run_dir"] = str(copies_dir)

    # -- worlds pillar: write a dummy telemetry.jsonl ---------------------
    worlds_dir = tmp_path / "worlds-run"
    worlds_dir.mkdir()
    (worlds_dir / "run.jsonl").write_text(
        '{"type":"tick","t":0}\n{"type":"tick","t":1}\n', encoding="utf-8"
    )
    worlds_artifact = _worlds_artifact()
    worlds_artifact.provenance["run_dir"] = str(worlds_dir)

    # -- finance pillar: write a dummy report.md --------------------------
    finance_dir = tmp_path / "finance-run"
    finance_dir.mkdir()
    (finance_dir / "report.md").write_text("# Finance report\n", encoding="utf-8")
    finance_artifact = _finance_artifact()
    finance_artifact.provenance["run_dir"] = str(finance_dir)

    with RunRegistry(client.db_path) as registry:  # type: ignore[attr-defined]
        registry.register(copies_artifact)
        registry.register(worlds_artifact)
        registry.register(finance_artifact)

    # Copies → scorecard
    resp = client.get(f"/runs/{copies_artifact.run_id}/artifacts/scorecard")
    assert resp.status_code == 200
    assert resp.text == '{"fidelity":0.87}'

    # Worlds → telemetry
    resp = client.get(f"/runs/{worlds_artifact.run_id}/artifacts/telemetry")
    assert resp.status_code == 200
    assert resp.text.count("tick") == 2

    # Finance → report
    resp = client.get(f"/runs/{finance_artifact.run_id}/artifacts/report")
    assert resp.status_code == 200
    assert resp.text.startswith("# Finance report")


# ---------------------------------------------------------------------------
# 5. POST /compare across pillars.
# ---------------------------------------------------------------------------


def test_compare_across_pillars_surfaces_disjoint_keys(
    client: TestClient,
) -> None:
    """POST /compare diffs finance vs copies summaries correctly.

    Finance summary and copies summary share no keys; every key must
    surface in the diff with ``None`` filling the absent side (a
    2-element list over the wire because JSON has no tuple type).
    """
    finance = _finance_artifact()
    copies = _copies_artifact()
    with RunRegistry(client.db_path) as registry:  # type: ignore[attr-defined]
        registry.register(finance)
        registry.register(copies)

    resp = client.post(
        "/compare", json={"run_id_a": finance.run_id, "run_id_b": copies.run_id}
    )
    assert resp.status_code == 200
    body = resp.json()
    # Top-level shape — `a`, `b`, `diff`.
    assert set(body.keys()) == {"a", "b", "diff"}
    # Finance-only key appears in diff with [finance_value, None]
    assert body["diff"]["hit_rate"] == [0.62, None]
    # Copies-only key appears with [None, copies_value]
    assert body["diff"]["fidelity_score"] == [None, 0.87]


def test_compare_unknown_run_id_returns_404(client: TestClient) -> None:
    """Missing run_id in compare → 404 (the resource does not exist)."""
    finance = _finance_artifact()
    with RunRegistry(client.db_path) as registry:  # type: ignore[attr-defined]
        registry.register(finance)

    resp = client.post(
        "/compare",
        json={"run_id_a": finance.run_id, "run_id_b": "not-a-real-run-id"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Shape contract — wire shape matches the dataclass to_dict().
# ---------------------------------------------------------------------------


def test_run_wire_shape_matches_dataclass_contract(client: TestClient) -> None:
    """Every required field on :class:`RunArtifact` appears on the wire.

    Regression guard: if someone trims a field from the Pydantic model
    without trimming the dataclass (or vice versa), this test flags the
    drift before it bleeds into the UI.
    """
    _seed_all_pillars(client)
    resp = client.get("/runs")
    assert resp.status_code == 200

    required_keys = {
        "run_id",
        "kind",
        "config",
        "seed",
        "artifact_paths",
        "summary",
        "provenance",
        "created_at",
    }
    for row in resp.json()["runs"]:
        assert required_keys.issubset(row.keys()), (
            f"missing fields in {row.get('run_id')}: "
            f"{required_keys - set(row.keys())}"
        )
