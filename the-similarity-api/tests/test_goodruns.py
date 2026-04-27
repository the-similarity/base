"""Route-level tests for ``app.goodruns`` (the /goodruns surface).

The module uses a module-level resolver (``resolve_goodruns_db``) rather
than a FastAPI dependency, so we redirect storage via the
``THE_SIMILARITY_GOODRUNS_DB`` env var — set per-test through
``monkeypatch.setenv`` so parallel test workers never share a DB file.

Coverage map
------------
- :func:`test_create_then_get_roundtrip` — POST + GET by id returns the
  same payload verbatim, including the engine math-name lens fields.
- :func:`test_list_newest_first` — GET lists respect saved_at ordering.
- :func:`test_list_filters_by_dataset` — ``dataset`` query param narrows
  the result set.
- :func:`test_create_duplicate_id_409` — id uniqueness is enforced at
  the router layer.
- :func:`test_get_missing_404` / :func:`test_delete_missing_404` —
  not-found paths return HTTP 404 with a JSON detail body.
- :func:`test_delete_removes_row` — DELETE followed by GET yields 404.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.goodruns import ENV_GOODRUNS_DB
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient pointed at an isolated tmp-path goodruns DB.

    The module reads ``THE_SIMILARITY_GOODRUNS_DB`` per request (not at
    import), so ``monkeypatch.setenv`` before yielding the client is
    enough to scope all storage to this tmp path.
    """
    db_path = tmp_path / "goodruns.db"
    monkeypatch.setenv(ENV_GOODRUNS_DB, str(db_path))
    with TestClient(app) as tc:
        yield tc


def _sample_payload(goodrun_id: str = "goodrun-1", dataset: str = "stocks/spy/1d") -> dict:
    """Build a fully-populated POST body with engine math-name lens keys.

    Values are arbitrary but shape-correct so the API validates the
    contract end-to-end.
    """
    return {
        "id": goodrun_id,
        "dataset": dataset,
        "horizon": 60,
        "query": {
            "start_idx": 4500,
            "end_idx": 4550,
            "start_date": "2023-01-10",
            "end_date": "2023-03-20",
            "values": [100.0, 101.2, 102.5, 103.1],
        },
        "match_id": "API-1234",
        "match": {
            "start_idx": 1200,
            "end_idx": 1250,
            "start_date": "2008-09-15",
            "end_date": "2008-11-21",
            "values": [80.0, 79.5, 78.2, 77.9],
        },
        "match_after_values": [77.5, 76.8, 77.1, 77.9, 78.3],
        "lens_breakdown": {
            "dtw": 0.82,
            "pearsonWarped": 0.71,
            "bempedelisR2": 0.64,
            "bempedelisSmoothness": 0.59,
            "koopman": 0.55,
            "waveletSpectrum": 0.68,
            "emd": 0.62,
            "tda": 0.45,
            "transferEntropy": 0.33,
        },
        "composite": 0.67,
        "note": "COVID-like regime vs 2008",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_then_get_roundtrip(client: TestClient) -> None:
    """POST + GET-by-id returns the same record including math-name lenses."""
    payload = _sample_payload()
    post_res = client.post("/goodruns", json=payload)
    assert post_res.status_code == 201, post_res.text
    body = post_res.json()
    assert body["id"] == payload["id"]
    # saved_at is server-assigned — just assert it's populated and ISO-ish.
    assert "T" in body["saved_at"]

    get_res = client.get(f"/goodruns/{payload['id']}")
    assert get_res.status_code == 200
    got = get_res.json()
    # Lens keys must be the engine math names — NOT lens1..9 or legacy
    # shape/dynamics/scaling aliases. This is the whole point of the
    # feature per the spec, so assert explicitly rather than relying on
    # a shallow equality.
    assert set(got["lens_breakdown"].keys()) == {
        "dtw",
        "pearsonWarped",
        "bempedelisR2",
        "bempedelisSmoothness",
        "koopman",
        "waveletSpectrum",
        "emd",
        "tda",
        "transferEntropy",
    }
    assert got["lens_breakdown"]["dtw"] == pytest.approx(0.82)
    assert got["query"]["values"] == payload["query"]["values"]
    assert got["match_after_values"] == payload["match_after_values"]


def test_list_newest_first(client: TestClient) -> None:
    """GET / returns goodruns ordered by saved_at DESC."""
    first = _sample_payload(goodrun_id="grun-A")
    second = _sample_payload(goodrun_id="grun-B")
    assert client.post("/goodruns", json=first).status_code == 201
    # Sleep long enough that the ISO-seconds timestamps differ.
    # Two records saved in the same second would sort indeterminately.
    time.sleep(1.1)
    assert client.post("/goodruns", json=second).status_code == 201

    res = client.get("/goodruns")
    assert res.status_code == 200
    rows = res.json()
    assert [r["id"] for r in rows] == ["grun-B", "grun-A"]


def test_list_filters_by_dataset(client: TestClient) -> None:
    """``?dataset=`` narrows the list to matching rows only."""
    spy = _sample_payload(goodrun_id="g-spy", dataset="stocks/spy/1d")
    btc = _sample_payload(goodrun_id="g-btc", dataset="crypto/btc/1d")
    assert client.post("/goodruns", json=spy).status_code == 201
    assert client.post("/goodruns", json=btc).status_code == 201

    res = client.get("/goodruns", params={"dataset": "stocks/spy/1d"})
    assert res.status_code == 200
    rows = res.json()
    assert [r["id"] for r in rows] == ["g-spy"]


def test_create_duplicate_id_409(client: TestClient) -> None:
    """Re-POSTing the same id returns 409 rather than silently upserting."""
    payload = _sample_payload()
    assert client.post("/goodruns", json=payload).status_code == 201
    dup = client.post("/goodruns", json=payload)
    assert dup.status_code == 409
    assert "already exists" in dup.json()["detail"]


def test_get_missing_404(client: TestClient) -> None:
    """GET on an unknown id returns 404 with a JSON detail body."""
    res = client.get("/goodruns/does-not-exist")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


def test_delete_removes_row(client: TestClient) -> None:
    """DELETE followed by GET shows the row is gone (404)."""
    payload = _sample_payload()
    assert client.post("/goodruns", json=payload).status_code == 201

    del_res = client.delete(f"/goodruns/{payload['id']}")
    assert del_res.status_code == 204

    get_res = client.get(f"/goodruns/{payload['id']}")
    assert get_res.status_code == 404


def test_delete_missing_404(client: TestClient) -> None:
    """DELETE on an unknown id returns 404, not 204."""
    res = client.delete("/goodruns/never-existed")
    assert res.status_code == 404
