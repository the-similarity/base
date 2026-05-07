"""Tests for the personalized setup scanner v1 registry surfaces.

Covers three things:

1. The plain-SQL migration runner — discovers numbered files under
   ``the_similarity/platform/migrations/``, applies them inside a
   SAVEPOINT, and records the version in ``schema_migrations`` so
   re-applying is a no-op.
2. The :class:`Setup` CRUD API — multi-tenant scoping, upsert
   semantics, list-newest-first, cascade-delete on associated feedback.
3. The :class:`Feedback` CRUD API — kind/thumb validation, optional
   per-setup filter, cascade behavior with the parent setup.

Each test uses ``tmp_path`` so concurrent test runs cannot collide.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_similarity.platform.contracts import Feedback, Setup
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Per-test SQLite DB path under tmp_path."""
    return tmp_path / "registry.db"


def _make_setup(
    id_: str = "setup-1",
    user_id: str = "user-a",
    instrument: str = "BTCUSDT",
    timeframe: str = "1h",
    region_series: list[float] | None = None,
) -> Setup:
    return Setup(
        id=id_,
        user_id=user_id,
        name=f"{instrument} {timeframe} setup",
        instrument=instrument,
        timeframe=timeframe,
        region_start_ts="2026-04-01T00:00:00Z",
        region_end_ts="2026-04-02T00:00:00Z",
        region_series=region_series if region_series is not None else [1.0, 2.0, 3.0, 4.0],
    )


def _make_feedback(
    id_: str = "fb-1",
    user_id: str = "user-a",
    setup_id: str = "setup-1",
    kind: str = "analog",
    thumb: str = "up",
    analog_id: str | None = "analog-7",
    alert_id: str | None = None,
) -> Feedback:
    return Feedback(
        id=id_,
        user_id=user_id,
        setup_id=setup_id,
        kind=kind,
        thumb=thumb,
        alert_id=alert_id,
        analog_id=analog_id,
        free_text=None,
    )


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------


def test_migrations_create_setups_and_feedback_tables(db_path: Path) -> None:
    """Opening the registry on a fresh path must create both v1 tables."""
    with RunRegistry(db_path) as registry:
        # The conn is per-thread; reach in to inspect schema directly.
        tables = {
            row[0]
            for row in registry._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "setups" in tables
        assert "feedback" in tables
        assert "schema_migrations" in tables


def test_migrations_record_applied_versions(db_path: Path) -> None:
    """Each migration file lands a row in schema_migrations keyed by version."""
    with RunRegistry(db_path) as registry:
        rows = registry._conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    versions = [r[0] for r in rows]
    # Both v1 migrations should be applied.
    assert "0001" in versions
    assert "0002" in versions


def test_migrations_idempotent_on_reopen(db_path: Path) -> None:
    """Re-opening the registry must not re-apply already-recorded migrations."""
    # First open applies migrations.
    with RunRegistry(db_path) as registry:
        first_versions = sorted(
            row[0]
            for row in registry._conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        )
    # Second open must be a no-op — same set, no errors.
    with RunRegistry(db_path) as registry:
        second_versions = sorted(
            row[0]
            for row in registry._conn.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        )
    assert first_versions == second_versions


# ---------------------------------------------------------------------------
# Setup CRUD
# ---------------------------------------------------------------------------


def test_create_and_get_setup_round_trip(db_path: Path) -> None:
    """create_setup persists every field and get_setup recovers it intact."""
    setup = _make_setup(region_series=[10.0, 11.5, 12.25, 11.875])
    with RunRegistry(db_path) as registry:
        registry.create_setup(setup)
        fetched = registry.get_setup(setup.id)
    assert fetched is not None
    assert fetched.id == setup.id
    assert fetched.user_id == setup.user_id
    assert fetched.instrument == setup.instrument
    assert fetched.timeframe == setup.timeframe
    assert fetched.region_series == setup.region_series
    # created_at / updated_at must be auto-stamped (ISO-8601 UTC).
    assert fetched.created_at != ""
    assert fetched.updated_at != ""


def test_create_setup_requires_user_id(db_path: Path) -> None:
    """Empty user_id is a multi-tenant guardrail — must raise ValueError."""
    setup = _make_setup()
    setup.user_id = ""
    with RunRegistry(db_path) as registry:
        with pytest.raises(ValueError, match="user_id"):
            registry.create_setup(setup)


def test_create_setup_upserts_on_id(db_path: Path) -> None:
    """Re-creating with the same id replaces every column (upsert)."""
    setup = _make_setup(region_series=[1.0, 2.0, 3.0])
    with RunRegistry(db_path) as registry:
        registry.create_setup(setup)
        # Mutate a few fields and re-insert under the same id.
        setup.name = "renamed"
        setup.region_series = [9.0, 9.5, 10.0]
        registry.create_setup(setup)
        fetched = registry.get_setup(setup.id)
    assert fetched is not None
    assert fetched.name == "renamed"
    assert fetched.region_series == [9.0, 9.5, 10.0]


def test_get_setup_missing_returns_none(db_path: Path) -> None:
    """Lookup of an unknown id returns None — never raises."""
    with RunRegistry(db_path) as registry:
        assert registry.get_setup("does-not-exist") is None


def test_list_setups_filters_by_user_id(db_path: Path) -> None:
    """list_setups MUST scope to the given user — no cross-tenant leak."""
    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="s1", user_id="alice"))
        registry.create_setup(_make_setup(id_="s2", user_id="bob"))
        registry.create_setup(_make_setup(id_="s3", user_id="alice"))

        alice = registry.list_setups("alice")
        bob = registry.list_setups("bob")

    assert {s.id for s in alice} == {"s1", "s3"}
    assert {s.id for s in bob} == {"s2"}


def test_list_setups_empty_user_raises(db_path: Path) -> None:
    """Empty user_id must raise — defensive against multi-tenant leak."""
    with RunRegistry(db_path) as registry:
        with pytest.raises(ValueError, match="user_id"):
            registry.list_setups("")


def test_delete_setup_cascades_feedback(db_path: Path) -> None:
    """Deleting a setup must cascade-delete its feedback rows.

    The cascade is enforced by the FK on ``feedback.setup_id`` and the
    ``PRAGMA foreign_keys=ON`` set in :meth:`RunRegistry._configure_connection`.
    Without the PRAGMA SQLite would silently leave orphans.
    """
    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="setup-x", user_id="alice"))
        registry.record_feedback(
            _make_feedback(id_="fb-1", user_id="alice", setup_id="setup-x")
        )
        registry.record_feedback(
            _make_feedback(id_="fb-2", user_id="alice", setup_id="setup-x")
        )
        # Sanity: feedback present before delete.
        assert len(registry.list_feedback("alice", setup_id="setup-x")) == 2

        deleted = registry.delete_setup("setup-x")
        assert deleted is True
        # Cascade: feedback rows should be gone.
        assert registry.list_feedback("alice", setup_id="setup-x") == []


# ---------------------------------------------------------------------------
# Feedback CRUD
# ---------------------------------------------------------------------------


def test_record_feedback_round_trip(db_path: Path) -> None:
    """record_feedback persists every field and list_feedback round-trips."""
    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="setup-y", user_id="alice"))
        fb = _make_feedback(id_="fb-rt", user_id="alice", setup_id="setup-y")
        fb.free_text = "felt right"
        registry.record_feedback(fb)
        rows = registry.list_feedback("alice", setup_id="setup-y")
    assert len(rows) == 1
    assert rows[0].id == "fb-rt"
    assert rows[0].free_text == "felt right"
    assert rows[0].kind == "analog"
    assert rows[0].thumb == "up"
    assert rows[0].created_at != ""


def test_record_feedback_validates_kind(db_path: Path) -> None:
    """kind must be 'alert' or 'analog' — typos must fail loud."""
    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="s", user_id="alice"))
        bad = _make_feedback(setup_id="s", user_id="alice", kind="other")
        with pytest.raises(ValueError, match="kind"):
            registry.record_feedback(bad)


def test_record_feedback_validates_thumb(db_path: Path) -> None:
    """thumb must be 'up' or 'down' — typos must fail loud."""
    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="s", user_id="alice"))
        bad = _make_feedback(setup_id="s", user_id="alice", thumb="meh")
        with pytest.raises(ValueError, match="thumb"):
            registry.record_feedback(bad)


def test_list_feedback_per_setup_filter(db_path: Path) -> None:
    """list_feedback(setup_id=...) scopes to one setup; None aggregates all."""
    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="s1", user_id="alice"))
        registry.create_setup(_make_setup(id_="s2", user_id="alice"))
        registry.record_feedback(
            _make_feedback(id_="f1", user_id="alice", setup_id="s1")
        )
        registry.record_feedback(
            _make_feedback(id_="f2", user_id="alice", setup_id="s2")
        )
        registry.record_feedback(
            _make_feedback(id_="f3", user_id="alice", setup_id="s2")
        )

        all_user = registry.list_feedback("alice")
        s2_only = registry.list_feedback("alice", setup_id="s2")

    assert {f.id for f in all_user} == {"f1", "f2", "f3"}
    assert {f.id for f in s2_only} == {"f2", "f3"}


def test_list_feedback_filters_by_user_id(db_path: Path) -> None:
    """Feedback aggregation MUST scope to user — no cross-tenant leak."""
    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="s-a", user_id="alice"))
        registry.create_setup(_make_setup(id_="s-b", user_id="bob"))
        registry.record_feedback(
            _make_feedback(id_="f-a", user_id="alice", setup_id="s-a")
        )
        registry.record_feedback(
            _make_feedback(id_="f-b", user_id="bob", setup_id="s-b")
        )

        alice = registry.list_feedback("alice")
        bob = registry.list_feedback("bob")

    assert [f.id for f in alice] == ["f-a"]
    assert [f.id for f in bob] == ["f-b"]


# ---------------------------------------------------------------------------
# compute_goodrun_score helper (engine-side aggregator)
# ---------------------------------------------------------------------------


def test_compute_goodrun_score_aggregates_thumbs(db_path: Path) -> None:
    """The aggregator returns counts + net_score in [-1, 1]."""
    from the_similarity.core.scorer import compute_goodrun_score

    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="s1", user_id="alice"))
        for i in range(3):
            registry.record_feedback(
                _make_feedback(id_=f"up-{i}", user_id="alice", setup_id="s1", thumb="up")
            )
        registry.record_feedback(
            _make_feedback(id_="dn-1", user_id="alice", setup_id="s1", thumb="down")
        )

        score = compute_goodrun_score(registry, "alice", setup_id="s1")

    assert score["thumbs_up"] == 3
    assert score["thumbs_down"] == 1
    assert score["total"] == 4
    # net_score = (3 - 1) / 4 = 0.5
    assert score["net_score"] == pytest.approx(0.5)


def test_compute_goodrun_score_zero_total_is_zero_net(db_path: Path) -> None:
    """An empty feedback set returns a defined zero, not NaN or KeyError."""
    from the_similarity.core.scorer import compute_goodrun_score

    with RunRegistry(db_path) as registry:
        registry.create_setup(_make_setup(id_="s1", user_id="alice"))
        score = compute_goodrun_score(registry, "alice", setup_id="s1")
    assert score["total"] == 0
    assert score["net_score"] == 0.0
