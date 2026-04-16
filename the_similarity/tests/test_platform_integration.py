"""End-to-end integration tests for the platform spine.

This suite exercises the Batch 1 spine across all pillars in a single
test process:

- synthetic **finance (eval)** runs
- synthetic **copies** runs
- synthetic **worlds** runs
- (bonus) **sweep** runs — the fourth :class:`RunKind`

The goal is to lock in the three cross-pillar invariants that downstream
surfaces (CLI, HTTP API, eventual UI, eval harness) depend on:

1. **Contract round-trip.** Every pillar's :class:`RunArtifact` survives
   ``register -> get`` and ``register -> list`` unchanged (modulo JSON
   round-trip ordering) regardless of which pillar produced it.

2. **Cross-pillar isolation.** ``list(kind=...)`` returns only rows of
   that kind. The filter is the primary tool UI consumers use to show
   "finance runs only" / "copies runs only"; silently leaking kinds
   would break every downstream view.

3. **Shared ordering.** Newest-first ordering is global, unaffected by
   kind. A worlds run registered after an eval run comes back first in
   both ``list()`` and ``list(kind=WORLDS)`` (where applicable).

These tests do NOT invoke the real pipelines (backtester, synthetic CLI,
Node worlds runner) — those have their own unit tests. We construct
:class:`RunArtifact` instances directly so the registry is the unit under
test, not the runners.

Every test runs against a fresh ``tmp_path`` SQLite DB. No shared state.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from the_similarity.platform.artifacts import RunArtifact, RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Pillar factories — one per pillar, each producing a realistic
# :class:`RunArtifact` for that pillar.
# ---------------------------------------------------------------------------


def _finance_artifact(
    *, run_id: str = "1" * 32, seed: int = 42, created_at: str = "2026-04-15T18:30:00+00:00"
) -> RunArtifact:
    """Build a synthetic **finance / eval** :class:`RunArtifact`.

    Finance runs land as ``RunKind.EVAL`` in Batch 1 (no dedicated finance
    kind); the pillar is encoded via ``provenance.generator_name`` +
    ``config.symbol``. Summary carries the metrics the UI / leaderboard
    indexes on: ``hit_rate``, ``crps``, ``mae``, ``calibration_error``.
    """
    return RunArtifact(
        run_id=run_id,
        kind=RunKind.EVAL,
        config={
            "symbol": "SPY",
            "start": "2020-01-01",
            "end": "2020-06-30",
            "method": "dtw",
        },
        seed=seed,
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
            "seed": seed,
            "symbol": "SPY",
            "start": "2020-01-01",
            "end": "2020-06-30",
            "created_at": created_at,
        },
        created_at=created_at,
    )


def _copies_artifact(
    *, run_id: str = "2" * 32, seed: int = 7, created_at: str = "2026-04-15T18:44:00+00:00"
) -> RunArtifact:
    """Build a synthetic **copies** :class:`RunArtifact`.

    Mirrors the shape ``the_similarity.platform.api.routes.create_copies_run``
    assembles after a ``synthetic.cli`` pipeline run — minus the actual
    parquet/scorecard files on disk. We only test the registry / contract
    surface here, so missing on-disk artifacts are fine.
    """
    return RunArtifact(
        run_id=run_id,
        kind=RunKind.COPIES,
        config={
            "input_path": "/repo/the_similarity/synthetic/demos/sample.csv",
            "n": 100,
            "seed": seed,
            "generator": "block_bootstrap",
        },
        seed=seed,
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
            "seed": seed,
            "created_at": created_at,
            "params": {"block_size": 32},
        },
        created_at=created_at,
    )


def _worlds_artifact(
    *, run_id: str = "3" * 32, seed: int = 1, created_at: str = "2026-04-15T19:00:00+00:00"
) -> RunArtifact:
    """Build a synthetic **worlds** :class:`RunArtifact`.

    Matches the shape the TS runner emits in its ``type=provenance`` JSONL
    record plus the :class:`RunArtifact` the API wrapper builds around it.
    ``summary`` carries the headline worlds numbers the UI highlights.
    """
    return RunArtifact(
        run_id=run_id,
        kind=RunKind.WORLDS,
        config={
            "scenario_path": "/repo/the-similarity-fractal/scenarios/small_village.json",
            "seed": seed,
            "steps": 500,
        },
        seed=seed,
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
            "seed": seed,
            "scenario_name": "small_village",
            "scenario": {"actors": 40, "cadence": "daily"},
            "params": {},
            "created_at": created_at,
        },
        created_at=created_at,
    )


def _sweep_artifact(
    *, run_id: str = "4" * 32, seed: int | None = None, created_at: str = "2026-04-15T19:30:00+00:00"
) -> RunArtifact:
    """Build a synthetic **sweep** :class:`RunArtifact`.

    Sweeps are the Eval-Layer primitive for worlds. ``seed`` is ``None``
    because a sweep spans a grid of seeds rather than pinning one. This
    exercises the registry's ``seed`` nullable column.
    """
    return RunArtifact(
        run_id=run_id,
        kind=RunKind.SWEEP,
        config={"sweep_script": "run-example-sweep.js"},
        seed=seed,
        artifact_paths={
            "scorecard": "scorecard.json",
            "telemetry": "telemetry.jsonl",
        },
        summary={
            "n_cells": 12,
            "n_rows": 48,
            "global_coverage": 0.81,
            "runtime_ms": 1_234,
            "passed": True,
        },
        provenance={
            "generator_name": "worlds_sweep",
            "generator_version": "0.3.0",
            "seed": None,
            "created_at": created_at,
        },
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def populated_registry(tmp_path: Path) -> RunRegistry:
    """A registry pre-seeded with one run per pillar.

    Timestamps are staggered in pillar order (finance < copies < worlds <
    sweep) so newest-first ordering is deterministic and visibly aligns
    with pillar identity when debugging.

    The fixture yields an OPEN registry — the test is responsible for
    closing it if it needs to open another connection. Most tests do not;
    they use the single connection the fixture hands them.
    """
    registry = RunRegistry(tmp_path / "registry.db")
    registry.register(_finance_artifact())
    registry.register(_copies_artifact())
    registry.register(_worlds_artifact())
    registry.register(_sweep_artifact())
    yield registry
    registry.close()


# ---------------------------------------------------------------------------
# 1. Contract round-trip — every pillar survives register/get unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [_finance_artifact, _copies_artifact, _worlds_artifact, _sweep_artifact],
    ids=["finance", "copies", "worlds", "sweep"],
)
def test_pillar_round_trip_through_registry(factory, tmp_path: Path) -> None:
    """Every pillar's artifact round-trips byte-for-byte through the DB.

    We compare via ``to_dict()`` rather than dataclass equality because
    the registry serializes each dict column through ``json.dumps/loads``;
    nested key ordering is not guaranteed to match the original Python
    dict. ``to_dict`` gives us a stable JSON-shaped comparison surface.
    """
    artifact = factory()
    with RunRegistry(tmp_path / "registry.db") as registry:
        registry.register(artifact)
        fetched = registry.get(artifact.run_id)

    assert fetched is not None, "registered artifact must be retrievable"
    assert fetched.to_dict() == artifact.to_dict()


# ---------------------------------------------------------------------------
# 2. Cross-pillar isolation — list(kind=X) returns only kind X.
# ---------------------------------------------------------------------------


def test_list_by_kind_isolates_pillars(populated_registry: RunRegistry) -> None:
    """``list(kind=K)`` returns exactly the runs registered with that kind.

    This is the primary cross-pillar isolation gate — UI consumers filter
    by kind to show "copies only" / "finance only" tabs. Silent leaks
    would break every downstream view.
    """
    copies = populated_registry.list(kind=RunKind.COPIES)
    worlds = populated_registry.list(kind=RunKind.WORLDS)
    evals = populated_registry.list(kind=RunKind.EVAL)
    sweeps = populated_registry.list(kind=RunKind.SWEEP)

    # Each kind returns exactly one row (the one we registered).
    assert [a.kind for a in copies] == [RunKind.COPIES]
    assert [a.kind for a in worlds] == [RunKind.WORLDS]
    assert [a.kind for a in evals] == [RunKind.EVAL]
    assert [a.kind for a in sweeps] == [RunKind.SWEEP]

    # The single-row finance/eval run must carry the canonical config keys.
    finance = evals[0]
    assert finance.config["symbol"] == "SPY"
    assert finance.provenance["generator_name"] == "backtester"


def test_list_without_kind_returns_all_pillars(
    populated_registry: RunRegistry,
) -> None:
    """``list()`` without a kind filter returns every pillar's run.

    Default limit is 100 — well above our 4 seed rows, so no pagination
    edge case to worry about here.
    """
    rows = populated_registry.list()
    kinds = {row.kind for row in rows}
    assert kinds == {RunKind.EVAL, RunKind.COPIES, RunKind.WORLDS, RunKind.SWEEP}
    assert len(rows) == 4


# ---------------------------------------------------------------------------
# 3. Shared ordering — newest-first is global, independent of kind.
# ---------------------------------------------------------------------------


def test_list_is_newest_first_across_pillars(
    populated_registry: RunRegistry,
) -> None:
    """Global list() is ordered by ``created_at DESC`` across every kind.

    Our fixture stages timestamps so the order is
    ``sweep > worlds > copies > finance`` — we assert that exact sequence.
    """
    rows = populated_registry.list()
    ordered = [row.kind for row in rows]
    assert ordered == [
        RunKind.SWEEP,   # 2026-04-15T19:30
        RunKind.WORLDS,  # 2026-04-15T19:00
        RunKind.COPIES,  # 2026-04-15T18:44
        RunKind.EVAL,    # 2026-04-15T18:30
    ]


# ---------------------------------------------------------------------------
# 4. Cross-pillar compare() — diff the summary dicts of two different kinds.
# ---------------------------------------------------------------------------


def test_compare_across_pillars_surfaces_full_key_union(
    populated_registry: RunRegistry,
) -> None:
    """``compare`` diffs summary dicts regardless of kind.

    Comparing a copies run (fidelity/privacy/utility) with a finance run
    (hit_rate/crps/mae) should surface every key in the union as a
    ``(a_value, b_value)`` tuple — never a silent match on absent keys.
    """
    # The finance run's run_id — hash-free; we built them in the factory.
    finance_id = "1" * 32
    copies_id = "2" * 32

    diff = populated_registry.compare(finance_id, copies_id)

    # Structural sanity first.
    assert set(diff.keys()) == {"a", "b", "diff"}
    # The summary for A (finance) carries hit_rate; B (copies) carries
    # fidelity_score. Both must appear in the diff (neither is shared).
    assert "hit_rate" in diff["diff"], "finance-only key must surface in diff"
    assert "fidelity_score" in diff["diff"], "copies-only key must surface in diff"
    # Missing-on-one-side values are filled with None per the compare() contract.
    assert diff["diff"]["hit_rate"] == (0.62, None)
    assert diff["diff"]["fidelity_score"] == (None, 0.87)


# ---------------------------------------------------------------------------
# 5. Upsert semantics survive across pillar re-registration.
# ---------------------------------------------------------------------------


def test_re_register_same_run_id_upserts_summary(tmp_path: Path) -> None:
    """The eval-harness use case: enrich an already-registered run.

    A finance run is registered by the backtester with a partial summary.
    The eval harness later re-registers the SAME run_id with enriched
    summary fields. The registry MUST upsert (replace) rather than
    insert-twice or raise — this is the documented contract.
    """
    partial = _finance_artifact()
    partial.summary = {"hit_rate": 0.62}  # partial — only the headline number

    with RunRegistry(tmp_path / "registry.db") as registry:
        registry.register(partial)
        # Re-register with enriched summary — SAME run_id, different summary.
        enriched = _finance_artifact()
        enriched.summary = {
            "hit_rate": 0.62,
            "crps": 0.18,
            "mae": 0.012,
            "calibration_error": 0.04,
        }
        registry.register(enriched)

        # Only one row — upsert, not double-insert.
        rows = registry.list()
        assert len(rows) == 1
        # Summary reflects the enriched payload, not the partial one.
        assert rows[0].summary == enriched.summary


# ---------------------------------------------------------------------------
# 6. Kind column integrity — every registered kind matches what we sent.
# ---------------------------------------------------------------------------


def test_registered_kinds_match_sent_kinds(populated_registry: RunRegistry) -> None:
    """No kind coercion, no silent remapping.

    Regression guard: if someone swaps the ``kind`` column for a string
    stored off the enum's ``.value``, the round-trip must still yield the
    correct :class:`RunKind` enum member.
    """
    expected: Dict[str, RunKind] = {
        "1" * 32: RunKind.EVAL,
        "2" * 32: RunKind.COPIES,
        "3" * 32: RunKind.WORLDS,
        "4" * 32: RunKind.SWEEP,
    }
    for run_id, kind in expected.items():
        fetched = populated_registry.get(run_id)
        assert fetched is not None, f"run_id {run_id} missing from registry"
        assert fetched.kind == kind


# ---------------------------------------------------------------------------
# 7. Deletion is per-run, not per-pillar.
# ---------------------------------------------------------------------------


def test_delete_one_pillar_leaves_others_untouched(
    populated_registry: RunRegistry,
) -> None:
    """Deleting a finance run does not affect copies/worlds/sweep rows."""
    finance_id = "1" * 32
    assert populated_registry.delete(finance_id) is True
    assert populated_registry.get(finance_id) is None

    # Other pillars are untouched.
    remaining_kinds = {row.kind for row in populated_registry.list()}
    assert remaining_kinds == {RunKind.COPIES, RunKind.WORLDS, RunKind.SWEEP}

    # Idempotent — deleting again returns False.
    assert populated_registry.delete(finance_id) is False
