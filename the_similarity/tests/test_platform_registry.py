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
from the_similarity.platform.contracts import (
    ArtifactRecord,
    DatasetSpec,
    RunRecord,
    RunStatus,
    ScenarioSpec,
    ScorecardKind,
    ScorecardSummary,
)
from the_similarity.platform.registry import RunRegistry, derive_run_id


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


# ===========================================================================
# Spine extension — RunRecord / ArtifactRecord / ScorecardSummary /
# ScenarioSpec / DatasetSpec surfaces.
# ===========================================================================


def _make_run_record(
    run_id: str = "00000000000000000000000000000001",
    kind: RunKind = RunKind.FINANCE,
    pillar: str | None = "finance",
    status: RunStatus = RunStatus.SUCCEEDED,
    seed: int | None = 7,
    created_at: str = "2026-04-15T20:00:00Z",
    summary: dict | None = None,
) -> RunRecord:
    """Minimal RunRecord factory for spine tests.

    Separate from ``_make_artifact`` because the legacy tests exercise
    RunArtifact semantics; the spine tests need pillar/status fields.
    """
    return RunRecord(
        run_id=run_id,
        kind=kind,
        config={"dataset_id": "spy.2020", "seed": seed},
        seed=seed,
        artifact_paths={"telemetry": "run.jsonl"},
        summary=summary if summary is not None else {"fidelity": 0.9},
        provenance={"generator_name": "finance-runner", "version": "0.2.0"},
        created_at=created_at,
        status=status,
        pillar=pillar,
    )


# ---------------------------------------------------------------------------
# register_run / get_run / list_runs
# ---------------------------------------------------------------------------


def test_register_run_round_trip(db_path: Path) -> None:
    """RunRecord round-trip preserves every new field including status/pillar."""
    record = _make_run_record()
    with RunRegistry(db_path) as registry:
        run_id = registry.register_run(record)
        fetched = registry.get_run(run_id)

    assert run_id == record.run_id
    assert fetched is not None
    assert fetched.to_dict() == record.to_dict()
    assert fetched.status is RunStatus.SUCCEEDED
    assert fetched.pillar == "finance"


def test_register_run_upsert(db_path: Path) -> None:
    """Re-registering the same run_id replaces every column including status."""
    r1 = _make_run_record(status=RunStatus.RUNNING, summary={"fidelity": 0.1})
    r2 = _make_run_record(status=RunStatus.SUCCEEDED, summary={"fidelity": 0.95})
    with RunRegistry(db_path) as registry:
        registry.register_run(r1)
        registry.register_run(r2)
        rows = registry.list_runs()

    assert len(rows) == 1
    assert rows[0].status is RunStatus.SUCCEEDED
    assert rows[0].summary == {"fidelity": 0.95}


def test_list_runs_filters_by_pillar(db_path: Path) -> None:
    """list_runs(pillar='finance') returns only finance-pillar rows."""
    fin = _make_run_record(run_id="f" * 32, pillar="finance")
    evt = _make_run_record(run_id="e" * 32, pillar="events", kind=RunKind.EVENTS)
    nlts = _make_run_record(run_id="n" * 32, pillar="nl_ts", kind=RunKind.NL_TS)
    with RunRegistry(db_path) as registry:
        for rec in (fin, evt, nlts):
            registry.register_run(rec)
        finance_only = registry.list_runs(pillar="finance")

    assert [r.run_id for r in finance_only] == [fin.run_id]


def test_list_runs_filters_by_status(db_path: Path) -> None:
    """list_runs(status=FAILED) filters on the status column."""
    ok = _make_run_record(run_id="a" * 32, status=RunStatus.SUCCEEDED)
    bad = _make_run_record(run_id="b" * 32, status=RunStatus.FAILED)
    with RunRegistry(db_path) as registry:
        registry.register_run(ok)
        registry.register_run(bad)
        failed = registry.list_runs(status=RunStatus.FAILED)

    assert len(failed) == 1
    assert failed[0].run_id == bad.run_id


def test_list_runs_filters_combine(db_path: Path) -> None:
    """Multiple filters AND together (kind + pillar + status)."""
    a = _make_run_record(
        run_id="a" * 32,
        kind=RunKind.FINANCE,
        pillar="finance",
        status=RunStatus.SUCCEEDED,
    )
    b = _make_run_record(
        run_id="b" * 32,
        kind=RunKind.FINANCE,
        pillar="finance",
        status=RunStatus.FAILED,
    )
    c = _make_run_record(
        run_id="c" * 32,
        kind=RunKind.EVENTS,
        pillar="events",
        status=RunStatus.SUCCEEDED,
    )
    with RunRegistry(db_path) as registry:
        for r in (a, b, c):
            registry.register_run(r)
        matches = registry.list_runs(
            kind=RunKind.FINANCE,
            pillar="finance",
            status=RunStatus.SUCCEEDED,
        )
    assert [r.run_id for r in matches] == [a.run_id]


def test_list_runs_limit_and_offset(db_path: Path) -> None:
    """list_runs respects limit and offset for pagination."""
    with RunRegistry(db_path) as registry:
        for i in range(5):
            registry.register_run(
                _make_run_record(
                    run_id=str(i).zfill(32),
                    created_at=f"2026-04-15T20:00:0{i}Z",
                )
            )
        page1 = registry.list_runs(limit=2, offset=0)
        page2 = registry.list_runs(limit=2, offset=2)
    # Newest-first ordering is by created_at DESC, so the first page holds
    # entries 4,3 and the second page holds 2,1.
    assert [r.run_id for r in page1] == ["4".zfill(32), "3".zfill(32)]
    assert [r.run_id for r in page2] == ["2".zfill(32), "1".zfill(32)]


# ---------------------------------------------------------------------------
# register_artifact / list_artifacts
# ---------------------------------------------------------------------------


def test_register_artifact_round_trip(db_path: Path) -> None:
    """Artifact rows round-trip with all optional fields preserved."""
    record = _make_run_record()
    artifact = ArtifactRecord(
        run_id=record.run_id,
        name="telemetry",
        path="run.jsonl",
        content_type="application/x-ndjson",
        size_bytes=2048,
        checksum="blake2b:deadbeef",
        created_at="2026-04-15T20:01:00Z",
    )
    with RunRegistry(db_path) as registry:
        registry.register_run(record)
        registry.register_artifact(artifact)
        rows = registry.list_artifacts(record.run_id)

    assert len(rows) == 1
    assert rows[0].to_dict() == artifact.to_dict()


def test_register_artifact_upsert_same_name(db_path: Path) -> None:
    """Same (run_id, name) updates in place — no duplicate rows."""
    record = _make_run_record()
    a1 = ArtifactRecord(
        run_id=record.run_id, name="scorecard", path="old.json",
        content_type="application/json", created_at="2026-04-15T20:00:00Z",
        size_bytes=10,
    )
    a2 = ArtifactRecord(
        run_id=record.run_id, name="scorecard", path="new.json",
        content_type="application/json", created_at="2026-04-15T20:01:00Z",
        size_bytes=42,
    )
    with RunRegistry(db_path) as registry:
        registry.register_run(record)
        registry.register_artifact(a1)
        registry.register_artifact(a2)
        rows = registry.list_artifacts(record.run_id)
    assert len(rows) == 1
    assert rows[0].path == "new.json"
    assert rows[0].size_bytes == 42


# ---------------------------------------------------------------------------
# register_scorecard / get_scorecards
# ---------------------------------------------------------------------------


def test_register_scorecard_round_trip(db_path: Path) -> None:
    """Scorecard summary round-trips with passed/bool + thresholds/details."""
    record = _make_run_record()
    card = ScorecardSummary(
        run_id=record.run_id,
        kind=ScorecardKind.FIDELITY,
        overall_score=0.87,
        passed=True,
        thresholds={"min_score": 0.8},
        details={"n_features": 12},
    )
    with RunRegistry(db_path) as registry:
        registry.register_run(record)
        registry.register_scorecard(card)
        fetched = registry.get_scorecards(record.run_id)
    assert len(fetched) == 1
    assert fetched[0].to_dict() == card.to_dict()
    assert fetched[0].passed is True


def test_multiple_scorecards_per_run(db_path: Path) -> None:
    """(run_id, kind) composite PK allows many scorecards per run."""
    record = _make_run_record()
    fid = ScorecardSummary(
        record.run_id, ScorecardKind.FIDELITY, overall_score=0.9, passed=True
    )
    stat = ScorecardSummary(
        record.run_id, ScorecardKind.PRIVACY, overall_score=0.7, passed=False
    )
    with RunRegistry(db_path) as registry:
        registry.register_run(record)
        registry.register_scorecard(fid)
        registry.register_scorecard(stat)
        rows = registry.get_scorecards(record.run_id)
    assert {r.kind for r in rows} == {ScorecardKind.FIDELITY, ScorecardKind.PRIVACY}


def test_scorecard_passed_none_preserved(db_path: Path) -> None:
    """A scorecard with ``passed=None`` must round-trip as None, not False."""
    record = _make_run_record()
    card = ScorecardSummary(record.run_id, ScorecardKind.UTILITY, passed=None)
    with RunRegistry(db_path) as registry:
        registry.register_run(record)
        registry.register_scorecard(card)
        fetched = registry.get_scorecards(record.run_id)
    assert fetched[0].passed is None


# ---------------------------------------------------------------------------
# register_scenario / list_scenarios
# ---------------------------------------------------------------------------


def test_register_scenario_round_trip(db_path: Path) -> None:
    spec = ScenarioSpec(
        scenario_id="scn-001",
        name="flash-crash",
        version="1.0",
        engine="worlds",
        params={"duration": 300},
        metadata={"author": "buba"},
    )
    with RunRegistry(db_path) as registry:
        scenario_id = registry.register_scenario(spec)
        rows = registry.list_scenarios()
    assert scenario_id == "scn-001"
    assert len(rows) == 1
    assert rows[0].to_dict() == spec.to_dict()


# ---------------------------------------------------------------------------
# register_dataset / list_datasets
# ---------------------------------------------------------------------------


def test_register_dataset_round_trip(db_path: Path) -> None:
    spec = DatasetSpec(
        dataset_id="spy.2020",
        name="SPY daily 2020",
        version="1.0",
        source="yfinance",
        schema_uri="s3://contracts/bar.json",
        n_rows=253,
        n_columns=6,
        checksum="blake2b:cafef00d",
        metadata={"asof": "2020-12-31"},
    )
    with RunRegistry(db_path) as registry:
        dataset_id = registry.register_dataset(spec)
        rows = registry.list_datasets()
    assert dataset_id == "spy.2020"
    assert len(rows) == 1
    assert rows[0].to_dict() == spec.to_dict()


# ---------------------------------------------------------------------------
# delete_run cascade
# ---------------------------------------------------------------------------


def test_delete_run_cascades_to_artifacts_and_scorecards(db_path: Path) -> None:
    """Deleting a run removes its artifacts AND scorecards."""
    record = _make_run_record()
    artifact = ArtifactRecord(
        run_id=record.run_id, name="telemetry", path="run.jsonl",
        content_type="application/x-ndjson", created_at="2026-04-15T20:00:00Z",
    )
    card = ScorecardSummary(
        record.run_id, ScorecardKind.FIDELITY, overall_score=0.9, passed=True
    )

    with RunRegistry(db_path) as registry:
        registry.register_run(record)
        registry.register_artifact(artifact)
        registry.register_scorecard(card)

        # Sanity: everything present.
        assert registry.list_artifacts(record.run_id)
        assert registry.get_scorecards(record.run_id)

        removed = registry.delete_run(record.run_id)

        assert removed is True
        assert registry.get_run(record.run_id) is None
        assert registry.list_artifacts(record.run_id) == []
        assert registry.get_scorecards(record.run_id) == []


def test_delete_run_missing_returns_false(db_path: Path) -> None:
    """Delete on a non-existent run_id returns False, no error."""
    with RunRegistry(db_path) as registry:
        assert registry.delete_run("no-such-run") is False


# ---------------------------------------------------------------------------
# Legacy RunArtifact API still works on the new schema
# ---------------------------------------------------------------------------


def test_legacy_register_reads_back_as_run_record_with_defaults(db_path: Path) -> None:
    """RunArtifact registered via legacy API reads back with default status/pillar."""
    artifact = _make_artifact()
    with RunRegistry(db_path) as registry:
        registry.register(artifact)
        record = registry.get_run(artifact.run_id)
    assert record is not None
    assert record.status is RunStatus.SUCCEEDED
    assert record.pillar is None


# ---------------------------------------------------------------------------
# derive_run_id — deterministic across runs
# ---------------------------------------------------------------------------


def test_derive_run_id_deterministic() -> None:
    """Same (kind, config, seed) → same run_id across invocations."""
    a = derive_run_id(RunKind.FINANCE, {"dataset": "spy", "horizon": 30}, seed=42)
    b = derive_run_id(RunKind.FINANCE, {"dataset": "spy", "horizon": 30}, seed=42)
    assert a == b
    assert len(a) == 32  # hex form


def test_derive_run_id_keyorder_invariant() -> None:
    """Config dict key order does not affect the derived id."""
    a = derive_run_id(RunKind.FINANCE, {"a": 1, "b": 2}, seed=0)
    b = derive_run_id(RunKind.FINANCE, {"b": 2, "a": 1}, seed=0)
    assert a == b


def test_derive_run_id_differs_on_any_input_change() -> None:
    """Changing kind OR config OR seed yields a different id."""
    base = derive_run_id(RunKind.FINANCE, {"x": 1}, seed=0)
    assert base != derive_run_id(RunKind.EVENTS, {"x": 1}, seed=0)
    assert base != derive_run_id(RunKind.FINANCE, {"x": 2}, seed=0)
    assert base != derive_run_id(RunKind.FINANCE, {"x": 1}, seed=1)


# ---------------------------------------------------------------------------
# v0 → v1 migration — a DB created with the pre-spine schema still opens.
# ---------------------------------------------------------------------------


def test_migration_from_v0_schema(tmp_path: Path) -> None:
    """Open a DB created with the pre-spine `runs` schema; verify migration adds columns and sibling tables without losing data."""
    db_path = tmp_path / "legacy.db"

    # Build a v0 DB by running the pre-spine DDL directly. This is the
    # exact schema that shipped in commit 8ce86f5 — one runs table, no
    # status/pillar/sibling tables.
    import sqlite3 as _sqlite3

    v0_ddl = """
    CREATE TABLE runs (
        run_id              TEXT PRIMARY KEY,
        kind                TEXT NOT NULL,
        config_json         TEXT NOT NULL,
        seed                INTEGER,
        artifact_paths_json TEXT NOT NULL,
        summary_json        TEXT NOT NULL,
        provenance_json     TEXT NOT NULL,
        created_at          TEXT NOT NULL
    );
    CREATE INDEX idx_runs_kind_created ON runs (kind, created_at DESC);
    """
    conn = _sqlite3.connect(str(db_path))
    try:
        conn.executescript(v0_ddl)
        # Insert a legacy row so we can assert it survives the migration.
        conn.execute(
            "INSERT INTO runs (run_id, kind, config_json, seed, "
            "artifact_paths_json, summary_json, provenance_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-0001",
                "copies",
                json.dumps({"generator": "block_bootstrap"}),
                42,
                json.dumps({"telemetry": "run.jsonl"}),
                json.dumps({"fidelity": 0.8}),
                json.dumps({"generator_name": "block_bootstrap"}),
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Opening the DB under the new registry MUST migrate it in place.
    with RunRegistry(db_path) as registry:
        # Legacy row still readable.
        legacy = registry.get_run("legacy-0001")
        assert legacy is not None
        assert legacy.status is RunStatus.SUCCEEDED  # default applied
        assert legacy.pillar is None

        # Sibling tables are usable — register then read.
        registry.register_artifact(
            ArtifactRecord(
                run_id="legacy-0001", name="telemetry", path="run.jsonl",
                content_type="application/x-ndjson", created_at="2026-04-15T20:00:00Z",
            )
        )
        assert len(registry.list_artifacts("legacy-0001")) == 1

        registry.register_scorecard(
            ScorecardSummary(
                run_id="legacy-0001",
                kind=ScorecardKind.FIDELITY,
                overall_score=0.8,
                passed=True,
            )
        )
        assert len(registry.get_scorecards("legacy-0001")) == 1

    # A second open is still idempotent (migration does not re-apply
    # ALTERs that already succeeded).
    with RunRegistry(db_path) as registry:
        assert registry.get_run("legacy-0001") is not None


def test_migration_is_idempotent_on_v1_db(tmp_path: Path) -> None:
    """Opening a v1 DB a second time is a no-op (ALTER swallows duplicate-column)."""
    db_path = tmp_path / "v1.db"
    # First open creates schema.
    RunRegistry(db_path).close()
    # Second open — must not raise.
    RunRegistry(db_path).close()


# ---------------------------------------------------------------------------
# Schema introspection sanity
# ---------------------------------------------------------------------------


def test_schema_has_all_new_tables_and_indexes(db_path: Path) -> None:
    """Every table + named index from the spine schema is present after init."""
    with RunRegistry(db_path) as registry:
        cur = registry._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        tables = {row[0] for row in cur.fetchall()}
        cur = registry._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name;"
        )
        indexes = {row[0] for row in cur.fetchall()}

    assert {"runs", "artifacts", "scorecards", "scenarios", "datasets"}.issubset(tables)
    assert {
        "idx_runs_kind_created",
        "idx_runs_pillar",
        "idx_runs_status",
        "idx_artifacts_run_id",
        "idx_scorecards_kind",
    }.issubset(indexes)
