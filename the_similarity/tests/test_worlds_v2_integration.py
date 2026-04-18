"""Integration tests for Worlds v2 platform features.

Validates that the platform spine correctly handles worlds-specific
workflows introduced in Batch 4 (Worlds v2):

1. **World run registration with provenance + summary** — a mock JSONL
   telemetry file is "registered" via a ``RunArtifact`` with
   ``kind=WORLDS``, and the round-trip through the registry preserves
   kind, summary, and provenance fields.

2. **Scenario preset registration** — a ``ScenarioSpec`` representing a
   Worlds v2 preset (stress_test, abundance, etc.) is registered and
   retrievable via ``list_scenarios``.

3. **World-run filtering** — multiple run kinds coexist in the registry,
   and ``list_runs(kind="worlds")`` returns only worlds rows.

4. **Scorecard attachment** — a worlds run can carry an attached
   scorecard (regime coverage, controllability), mirroring the eval
   harness output shape.

These tests do NOT import Agent 1-4 modules (scenario DSL, eval harness,
telemetry export, worlds adapter) directly. They exercise the platform
spine that those modules build on, using try/except for any imports that
may only exist once the sibling agents' code lands.

Every test runs against a fresh ``tmp_path`` SQLite DB. No shared state.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from the_similarity.platform.artifacts import RunArtifact, RunKind, iso_now, new_run_id
from the_similarity.platform.contracts import ScenarioSpec, ScorecardSummary, ScorecardKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_worlds_artifact(
    *,
    run_id: str | None = None,
    seed: int = 42,
    scenario_name: str = "stress_test",
    steps: int = 100,
    summary: dict | None = None,
) -> RunArtifact:
    """Build a minimal worlds ``RunArtifact`` with realistic fields.

    The artifact mimics what the headless runner (Agent 4) or the
    ``register_world_run`` adapter would produce: JSONL telemetry path,
    provenance with generator identity, and a summary with headline
    metrics the UI can index without loading the bulk file.
    """
    rid = run_id or new_run_id()
    return RunArtifact(
        run_id=rid,
        kind=RunKind.WORLDS,
        config={
            "scenario": scenario_name,
            "steps": steps,
            "grid_size": 64,
            "n_agents": 20,
        },
        seed=seed,
        artifact_paths={
            "telemetry": "run.jsonl",
            "scorecard": "scorecard.json",
        },
        summary=summary or {
            "total_ticks": steps,
            "final_population": 18,
            "mean_energy": 0.73,
            "regime_coverage": 0.56,
        },
        provenance={
            "generator_name": "worlds-headless-runner",
            "version": "2.0.0",
            "seed": seed,
            "scenario_name": scenario_name,
            "created_at": iso_now(),
        },
        created_at=iso_now(),
    )


def _make_eval_artifact(*, run_id: str | None = None) -> RunArtifact:
    """Build a minimal eval ``RunArtifact`` for cross-kind isolation tests."""
    return RunArtifact(
        run_id=run_id or new_run_id(),
        kind=RunKind.EVAL,
        config={"symbol": "SPY", "method": "dtw"},
        seed=42,
        artifact_paths={"forecast": "forecast.parquet"},
        summary={"hit_rate": 0.62},
        provenance={"generator_name": "backtester"},
        created_at=iso_now(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWorldsV2RunRegistration:
    """Register a mock worlds run and verify round-trip through the registry."""

    def test_register_worlds_run_kind(self, tmp_path: Path) -> None:
        """A worlds run registered with kind=WORLDS survives get() unchanged."""
        db = tmp_path / "registry.db"
        reg = RunRegistry(str(db))
        try:
            art = _make_worlds_artifact(scenario_name="stress_test", steps=50)
            reg.register(art)

            got = reg.get(art.run_id)
            assert got is not None, "Registered worlds run not found"
            assert got.kind == RunKind.WORLDS, (
                f"Expected kind=WORLDS, got {got.kind}"
            )
            # Summary round-trips through JSON in SQLite — verify headline fields
            assert got.summary["total_ticks"] == 50
            assert got.summary["mean_energy"] == 0.73
            # Provenance carries scenario identity
            assert got.provenance["scenario_name"] == "stress_test"
            assert got.provenance["version"] == "2.0.0"
        finally:
            reg.close()

    def test_worlds_run_with_fake_jsonl(self, tmp_path: Path) -> None:
        """Simulate a JSONL telemetry file and verify artifact_paths reference."""
        # Write a fake JSONL telemetry file — the registry stores the path
        # reference, not the file contents. This mirrors the headless runner
        # workflow: runner writes JSONL, adapter registers the path.
        jsonl_path = tmp_path / "run.jsonl"
        rows = [
            {"tick": 0, "population": 20, "mean_energy": 1.0},
            {"tick": 1, "population": 19, "mean_energy": 0.95},
            {"tick": 2, "population": 18, "mean_energy": 0.88},
        ]
        with open(jsonl_path, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

        db = tmp_path / "registry.db"
        reg = RunRegistry(str(db))
        try:
            art = _make_worlds_artifact(steps=3)
            # Override artifact_paths to point at our temp file
            art.artifact_paths["telemetry"] = str(jsonl_path)
            reg.register(art)

            got = reg.get(art.run_id)
            assert got is not None
            assert got.artifact_paths["telemetry"] == str(jsonl_path)

            # Verify the file is valid JSONL
            with open(got.artifact_paths["telemetry"]) as f:
                loaded = [json.loads(line) for line in f]
            assert len(loaded) == 3
            assert loaded[-1]["population"] == 18
        finally:
            reg.close()


class TestWorldsV2ScenarioPresets:
    """Scenario presets register and list correctly."""

    def test_register_and_list_scenario(self, tmp_path: Path) -> None:
        """A registered scenario preset appears in list_scenarios()."""
        db = tmp_path / "registry.db"
        reg = RunRegistry(str(db))
        try:
            spec = ScenarioSpec(
                scenario_id="stress_test_v1",
                name="Stress Test",
                version="1.0.0",
                engine="small_village",
                params={
                    "initial_energy": 0.3,
                    "food_regen_rate": 0.01,
                    "n_agents": 40,
                    "grid_size": 64,
                },
                metadata={
                    "preset": "stress_test",
                    "description": "High population, low resources — tests survival dynamics",
                    "category": "adversarial",
                },
            )
            reg.register_scenario(spec)

            scenarios = reg.list_scenarios()
            assert len(scenarios) >= 1, "No scenarios returned after registration"

            # Find our scenario by ID
            found = [s for s in scenarios if s.scenario_id == "stress_test_v1"]
            assert len(found) == 1, f"Expected 1 match, got {len(found)}"
            assert found[0].name == "Stress Test"
            assert found[0].engine == "small_village"
            assert found[0].params["food_regen_rate"] == 0.01
            assert found[0].metadata["preset"] == "stress_test"
        finally:
            reg.close()


class TestWorldsV2KindFiltering:
    """list_runs(kind=...) correctly isolates worlds runs from other kinds."""

    def test_worlds_filter_excludes_eval(self, tmp_path: Path) -> None:
        """Registering both WORLDS and EVAL runs, filtering by kind returns only the requested kind."""
        db = tmp_path / "registry.db"
        reg = RunRegistry(str(db))
        try:
            # Register one worlds run and one eval run
            worlds_art = _make_worlds_artifact(scenario_name="abundance")
            eval_art = _make_eval_artifact()
            reg.register(worlds_art)
            reg.register(eval_art)

            # Filter by WORLDS — should return exactly 1
            worlds_runs = reg.list_runs(kind=RunKind.WORLDS)
            assert len(worlds_runs) == 1
            assert worlds_runs[0].run_id == worlds_art.run_id

            # Filter by EVAL — should return exactly 1
            eval_runs = reg.list_runs(kind=RunKind.EVAL)
            assert len(eval_runs) == 1
            assert eval_runs[0].run_id == eval_art.run_id

            # Unfiltered — both
            all_runs = reg.list_runs()
            assert len(all_runs) == 2
        finally:
            reg.close()


class TestWorldsV2Scorecard:
    """Worlds runs can carry attached scorecards (regime coverage, controllability)."""

    def test_attach_worlds_scorecard(self, tmp_path: Path) -> None:
        """A scorecard attached to a worlds run is retrievable."""
        db = tmp_path / "registry.db"
        reg = RunRegistry(str(db))
        try:
            # Register the worlds run first
            art = _make_worlds_artifact(scenario_name="sparse")
            reg.register(art)

            # Attach a scorecard — mirrors what the eval harness (Agent 2) would produce.
            # CONTROLLABILITY is the ScorecardKind for worlds-runner scenario
            # adherence (regime coverage + knob-to-observable correlation).
            scorecard = ScorecardSummary(
                run_id=art.run_id,
                kind=ScorecardKind.CONTROLLABILITY,
                overall_score=0.72,
                passed=True,
                thresholds={"regime_coverage": 0.5, "controllability_min_r": 0.3},
                details={
                    "regime_coverage": 0.56,
                    "controllability": {
                        "food_regen_rate": {"r": 0.81, "p_value": 0.002},
                        "initial_energy": {"r": 0.65, "p_value": 0.01},
                    },
                },
            )
            reg.register_scorecard(scorecard)

            # Retrieve and verify
            scorecards = reg.get_scorecards(art.run_id)
            assert len(scorecards) >= 1
            sc = scorecards[0]
            assert sc.kind == ScorecardKind.CONTROLLABILITY
            assert sc.overall_score == 0.72
            assert sc.passed is True
            assert sc.details["regime_coverage"] == 0.56
        finally:
            reg.close()


# ---------------------------------------------------------------------------
# Optional: Agent-dependent import tests
# ---------------------------------------------------------------------------
# These tests attempt to import modules that Agent 1-4 may or may not have
# shipped yet. They are wrapped in try/except so the test suite does not
# fail when running before sibling agents merge.


class TestWorldsV2AgentImports:
    """Smoke-test imports from sibling agent modules (graceful skip if missing)."""

    def test_worlds_adapter_importable(self) -> None:
        """Try importing the worlds adapter (Agent 4). Skip if not yet merged."""
        try:
            from the_similarity.platform.adapters.worlds import register_world_run  # noqa: F401
        except ImportError:
            pytest.skip(
                "worlds adapter not yet available — Agent 4 has not merged"
            )
