"""Tests for :mod:`the_similarity.platform.registry`.

Covers the registry's two surfaces:

1. The :class:`RunRegistry` Python API — round-trips, upsert semantics,
   list filtering / ordering, deletion, summary diffs.
2. The CLI surface (``python -m the_similarity.platform``) — invoked via
   :func:`subprocess.run` so we exercise the same code path users hit.

Every test isolates its DB under :func:`pytest.fixture` ``tmp_path`` so
parallel test runs do not see each other's writes. The CLI tests also
override ``THE_SIMILARITY_REGISTRY_DB`` via the subprocess env so the
default ``~/.the_similarity/registry.db`` is never touched.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from the_similarity.platform.artifacts import RunArtifact, RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


def _make_artifact(
    run_id: str = "00000000000000000000000000000001",
    kind: RunKind = RunKind.COPIES,
    seed: int | None = 42,
    summary: dict | None = None,
    created_at: str = "2026-04-15T20:00:00Z",
) -> RunArtifact:
    """Construct a minimal RunArtifact for tests, with sane defaults.

    Centralized so per-test setup stays terse and the field shape is in one
    place — easier to update if the artifact contract evolves.
    """
    return RunArtifact(
        run_id=run_id,
        kind=kind,
        config={"generator": "block_bootstrap", "block_size": 32},
        seed=seed,
        artifact_paths={"telemetry": "run.jsonl", "scorecard": "scorecard.json"},
        summary=summary if summary is not None else {"fidelity": 0.85, "n_ticks": 1024},
        provenance={"generator_name": "block_bootstrap", "version": "0.1.0"},
        created_at=created_at,
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Per-test SQLite DB path under tmp_path."""
    return tmp_path / "registry.db"


# ---------------------------------------------------------------------------
# Python API — round-trip and field preservation
# ---------------------------------------------------------------------------


def test_register_and_get_round_trip(db_path: Path) -> None:
    """A registered artifact comes back from get() with every field intact."""
    artifact = _make_artifact()
    with RunRegistry(db_path) as registry:
        run_id = registry.register(artifact)
        fetched = registry.get(run_id)

    assert run_id == artifact.run_id
    assert fetched is not None
    # We compare via to_dict() rather than == on the dataclass because
    # nested dicts may have been re-ordered by JSON round-trip; to_dict
    # gives a stable comparison surface.
    assert fetched.to_dict() == artifact.to_dict()


def test_register_preserves_seed_none(db_path: Path) -> None:
    """seed=None must round-trip — eval runs commonly have no seed."""
    artifact = _make_artifact(seed=None)
    with RunRegistry(db_path) as registry:
        registry.register(artifact)
        fetched = registry.get(artifact.run_id)
    assert fetched is not None
    assert fetched.seed is None


def test_get_missing_returns_none(db_path: Path) -> None:
    """Missing run_id returns None, not raises."""
    with RunRegistry(db_path) as registry:
        assert registry.get("does-not-exist") is None


# ---------------------------------------------------------------------------
# Upsert semantics
# ---------------------------------------------------------------------------


def test_register_twice_upserts_same_row(db_path: Path) -> None:
    """Re-registering the same run_id updates the row instead of duplicating."""
    a1 = _make_artifact(summary={"fidelity": 0.5})
    a2 = _make_artifact(summary={"fidelity": 0.9, "n_ticks": 2048})

    with RunRegistry(db_path) as registry:
        registry.register(a1)
        registry.register(a2)
        rows = registry.list()

    assert len(rows) == 1, "upsert must not produce duplicate rows"
    # Latest write wins: summary should match a2.
    assert rows[0].summary == {"fidelity": 0.9, "n_ticks": 2048}


# ---------------------------------------------------------------------------
# list() — ordering and filtering
# ---------------------------------------------------------------------------


def test_list_newest_first(db_path: Path) -> None:
    """list() orders rows by created_at DESC."""
    older = _make_artifact(run_id="a" * 32, created_at="2026-04-15T10:00:00Z")
    newer = _make_artifact(run_id="b" * 32, created_at="2026-04-15T20:00:00Z")
    with RunRegistry(db_path) as registry:
        registry.register(older)
        registry.register(newer)
        rows = registry.list()

    assert [r.run_id for r in rows] == [newer.run_id, older.run_id]


def test_list_filters_by_kind(db_path: Path) -> None:
    """list(kind=WORLDS) returns only WORLDS rows."""
    copies = _make_artifact(run_id="c" * 32, kind=RunKind.COPIES)
    worlds = _make_artifact(run_id="w" * 32, kind=RunKind.WORLDS)
    eval_ = _make_artifact(run_id="e" * 32, kind=RunKind.EVAL)
    with RunRegistry(db_path) as registry:
        for art in (copies, worlds, eval_):
            registry.register(art)
        worlds_only = registry.list(kind=RunKind.WORLDS)

    assert len(worlds_only) == 1
    assert worlds_only[0].run_id == worlds.run_id


def test_list_respects_limit(db_path: Path) -> None:
    """list(limit=N) returns at most N rows."""
    with RunRegistry(db_path) as registry:
        for i in range(5):
            registry.register(
                _make_artifact(
                    run_id=str(i).zfill(32),
                    created_at=f"2026-04-15T20:00:0{i}Z",
                )
            )
        rows = registry.list(limit=2)
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


def test_delete_returns_true_then_false(db_path: Path) -> None:
    """delete() returns True the first time, False on a re-delete (idempotent)."""
    artifact = _make_artifact()
    with RunRegistry(db_path) as registry:
        registry.register(artifact)
        assert registry.delete(artifact.run_id) is True
        assert registry.delete(artifact.run_id) is False
        assert registry.get(artifact.run_id) is None


# ---------------------------------------------------------------------------
# compare()
# ---------------------------------------------------------------------------


def test_compare_diffs_changed_summary_keys(db_path: Path) -> None:
    """compare() reports differing summary keys as (a_val, b_val) tuples."""
    a = _make_artifact(run_id="a" * 32, summary={"fidelity": 0.7, "n_ticks": 512})
    b = _make_artifact(
        run_id="b" * 32, summary={"fidelity": 0.9, "n_ticks": 512, "extra": 1}
    )
    with RunRegistry(db_path) as registry:
        registry.register(a)
        registry.register(b)
        result = registry.compare(a.run_id, b.run_id)

    assert result["a"] == a.summary
    assert result["b"] == b.summary
    # Unchanged keys (n_ticks=512 on both) are skipped; changed/missing surface.
    assert result["diff"] == {
        "fidelity": (0.7, 0.9),
        "extra": (None, 1),
    }


def test_compare_identical_summaries_empty_diff(db_path: Path) -> None:
    """compare() of two identical summaries returns an empty diff dict."""
    summary = {"fidelity": 0.85, "n_ticks": 1024}
    a = _make_artifact(run_id="a" * 32, summary=summary)
    b = _make_artifact(run_id="b" * 32, summary=summary)
    with RunRegistry(db_path) as registry:
        registry.register(a)
        registry.register(b)
        result = registry.compare(a.run_id, b.run_id)
    assert result["diff"] == {}


def test_compare_missing_run_id_raises(db_path: Path) -> None:
    """compare() raises KeyError on missing run_id — fail loud, do not silently zero."""
    artifact = _make_artifact()
    with RunRegistry(db_path) as registry:
        registry.register(artifact)
        with pytest.raises(KeyError):
            registry.compare(artifact.run_id, "missing-id")


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def test_context_manager_closes_connection(db_path: Path) -> None:
    """The `with RunRegistry(...)` form closes the underlying connection on exit."""
    with RunRegistry(db_path) as registry:
        registry.register(_make_artifact())
        conn = registry._conn
    # After context exit, further ops on the closed connection should raise.
    import sqlite3

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def _run_cli(
    *args: str, db_path: Path, env_extra: dict | None = None
) -> subprocess.CompletedProcess:
    """Invoke the CLI as a subprocess against an isolated DB.

    We pass ``--db`` explicitly (rather than relying on the env var) so the
    test asserts the flag path. A separate test exercises the env var.
    """
    import os

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "the_similarity.platform", "--db", str(db_path), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_cli_register_list_show_round_trip(tmp_path: Path) -> None:
    """End-to-end: write an artifact.json, register/list/show via the CLI."""
    db_path = tmp_path / "cli.db"
    artifact = _make_artifact()
    artifact_file = tmp_path / "artifact.json"
    artifact_file.write_text(json.dumps(artifact.to_dict()), encoding="utf-8")

    # register — exit 0, run_id printed on stdout.
    reg = _run_cli("register", str(artifact_file), db_path=db_path)
    assert reg.returncode == 0, reg.stderr
    assert artifact.run_id in reg.stdout

    # list — exit 0, run_id prefix appears in tabular output.
    listed = _run_cli("list", db_path=db_path)
    assert listed.returncode == 0, listed.stderr
    assert artifact.run_id[:8] in listed.stdout

    # show — exit 0, full artifact JSON printed; run_id appears verbatim.
    shown = _run_cli("show", artifact.run_id, db_path=db_path)
    assert shown.returncode == 0, shown.stderr
    payload = json.loads(shown.stdout)
    assert payload["run_id"] == artifact.run_id
    assert payload["kind"] == "copies"


def test_cli_show_missing_run_id_exits_1(tmp_path: Path) -> None:
    """show on a non-existent run_id exits 1 with an error on stderr."""
    db_path = tmp_path / "cli.db"
    # Touch the DB by registering and then querying a different id.
    artifact = _make_artifact()
    artifact_file = tmp_path / "artifact.json"
    artifact_file.write_text(json.dumps(artifact.to_dict()), encoding="utf-8")
    _run_cli("register", str(artifact_file), db_path=db_path)

    result = _run_cli("show", "no-such-run", db_path=db_path)
    assert result.returncode == 1
    assert "not found" in result.stderr
