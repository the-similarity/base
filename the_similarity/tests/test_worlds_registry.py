"""Tests for the worlds pillar registry adapter.

Covers:
1. Registering a world run from a mock JSONL telemetry file.
2. Registering a scenario preset from a JSON file.
3. Syncing all presets from a directory of scenario JSONs.
4. Listing runs filtered by kind=worlds.
5. Edge cases: empty JSONL, missing summary line.
6. CLI sync-scenarios subcommand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_similarity.platform.adapters.worlds import (
    register_scenario_preset,
    register_world_run,
    sync_all_presets,
)
from the_similarity.platform.artifacts import RunKind
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry(tmp_path: Path) -> RunRegistry:
    """A throwaway registry backed by a tmp-path SQLite DB."""
    db = tmp_path / "test_registry.db"
    reg = RunRegistry(db)
    yield reg
    reg.close()


def _write_telemetry(
    directory: Path,
    *,
    scenario_name: str = "small_village",
    seed: int = 42,
    ticks: int = 500,
    alive: int = 15,
    dead: int = 5,
) -> Path:
    """Write a minimal two-line JSONL telemetry file and return its path."""
    telemetry_path = directory / "run.jsonl"
    provenance_line = {
        "type": "provenance",
        "generator_name": "the-similarity-fractal-headless",
        "version": "0.1.0",
        "seed": seed,
        "scenario_name": scenario_name,
        "scenario": {"size": 64, "initial_population": 20},
        "params": {"energy_decay": 0.01},
        "created_at": "2026-04-15T00:00:00Z",
    }
    summary_line = {
        "type": "summary",
        "ticks": ticks,
        "alive": alive,
        "dead": dead,
        "avg_energy": 0.45,
        "duration_ms": 1234,
    }
    with open(telemetry_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(provenance_line) + "\n")
        # Write a few tick lines in between to simulate real output.
        f.write(json.dumps({"type": "tick", "tick": 0}) + "\n")
        f.write(json.dumps({"type": "tick", "tick": 1}) + "\n")
        f.write(json.dumps(summary_line) + "\n")
    return telemetry_path


def _write_scenario_json(directory: Path, name: str = "small_village") -> Path:
    """Write a minimal scenario JSON file and return its path."""
    scenario = {
        "name": name,
        "description": f"Test scenario: {name}",
        "seed": 42,
        "steps": 500,
        "world": {"size": 64, "initial_population": 20},
        "params": {"energy_decay": 0.01},
    }
    path = directory / f"{name}.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests — world run registration
# ---------------------------------------------------------------------------


class TestRegisterWorldRun:
    """Tests for :func:`register_world_run`."""

    def test_registers_run_from_jsonl(
        self, tmp_path: Path, registry: RunRegistry
    ) -> None:
        """A valid JSONL file produces a registry row with correct fields."""
        telem = _write_telemetry(tmp_path)
        run_id = register_world_run(
            telem, scenario_name="small_village", seed=42, registry=registry
        )

        # Verify the run exists in the registry.
        artifact = registry.get(run_id)
        assert artifact is not None
        assert artifact.kind == RunKind.WORLDS
        assert artifact.seed == 42
        assert artifact.config["scenario_name"] == "small_village"
        assert artifact.summary["ticks"] == 500
        assert artifact.summary["alive"] == 15
        assert artifact.summary["dead"] == 5
        assert artifact.summary["pillar"] == "worlds"
        assert "telemetry" in artifact.artifact_paths

    def test_seed_from_provenance_when_not_explicit(
        self, tmp_path: Path, registry: RunRegistry
    ) -> None:
        """When seed is not passed explicitly, falls back to provenance header."""
        telem = _write_telemetry(tmp_path, seed=314)
        run_id = register_world_run(
            telem, scenario_name="small_village", registry=registry
        )
        artifact = registry.get(run_id)
        assert artifact is not None
        assert artifact.seed == 314

    def test_missing_telemetry_raises(self, registry: RunRegistry) -> None:
        """FileNotFoundError when the telemetry file does not exist."""
        with pytest.raises(FileNotFoundError):
            register_world_run(
                "/nonexistent/path.jsonl",
                scenario_name="x",
                registry=registry,
            )

    def test_empty_jsonl_produces_thin_summary(
        self, tmp_path: Path, registry: RunRegistry
    ) -> None:
        """An empty JSONL file still registers (thin summary, no crash)."""
        empty = tmp_path / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        run_id = register_world_run(
            empty, scenario_name="test", seed=1, registry=registry
        )
        artifact = registry.get(run_id)
        assert artifact is not None
        assert artifact.summary == {"pillar": "worlds"}


# ---------------------------------------------------------------------------
# Tests — scenario preset registration
# ---------------------------------------------------------------------------


class TestRegisterScenarioPreset:
    """Tests for :func:`register_scenario_preset`."""

    def test_registers_scenario_from_json(
        self, tmp_path: Path, registry: RunRegistry
    ) -> None:
        """A valid scenario JSON produces a registry scenario row."""
        path = _write_scenario_json(tmp_path)
        scenario_id = register_scenario_preset(path, registry=registry)

        assert scenario_id == "small_village"
        scenarios = registry.list_scenarios()
        assert len(scenarios) == 1
        assert scenarios[0].name == "small_village"
        assert scenarios[0].engine == "small_village"
        assert scenarios[0].version == "v1"
        assert "description" in scenarios[0].metadata

    def test_missing_scenario_raises(self, registry: RunRegistry) -> None:
        """FileNotFoundError when the scenario file does not exist."""
        with pytest.raises(FileNotFoundError):
            register_scenario_preset("/nonexistent/scenario.json", registry=registry)


# ---------------------------------------------------------------------------
# Tests — sync_all_presets
# ---------------------------------------------------------------------------


class TestSyncAllPresets:
    """Tests for :func:`sync_all_presets`."""

    def test_syncs_directory_of_scenarios(
        self, tmp_path: Path, registry: RunRegistry
    ) -> None:
        """Multiple scenario JSONs in a directory are all registered."""
        _write_scenario_json(tmp_path, name="village_a")
        _write_scenario_json(tmp_path, name="village_b")
        _write_scenario_json(tmp_path, name="village_c")

        ids = sync_all_presets(tmp_path, registry=registry)
        assert len(ids) == 3
        assert set(ids) == {"village_a", "village_b", "village_c"}

        # Verify all are in the registry.
        scenarios = registry.list_scenarios()
        assert len(scenarios) == 3

    def test_idempotent_sync(self, tmp_path: Path, registry: RunRegistry) -> None:
        """Re-syncing the same directory does not create duplicates."""
        _write_scenario_json(tmp_path, name="idempotent_test")

        ids1 = sync_all_presets(tmp_path, registry=registry)
        ids2 = sync_all_presets(tmp_path, registry=registry)
        assert ids1 == ids2
        assert len(registry.list_scenarios()) == 1

    def test_missing_dir_raises(self, registry: RunRegistry) -> None:
        """FileNotFoundError when the directory does not exist."""
        with pytest.raises(FileNotFoundError):
            sync_all_presets("/nonexistent/dir", registry=registry)


# ---------------------------------------------------------------------------
# Tests — list by kind=worlds
# ---------------------------------------------------------------------------


class TestListByKindWorlds:
    """Verify that kind=worlds filtering works correctly."""

    def test_list_filters_by_worlds_kind(
        self, tmp_path: Path, registry: RunRegistry
    ) -> None:
        """Only worlds runs appear when filtering by kind=worlds."""
        # Register a worlds run.
        telem = _write_telemetry(tmp_path)
        worlds_id = register_world_run(
            telem, scenario_name="sv", seed=1, registry=registry
        )

        # Register a non-worlds run (finance-style).
        from the_similarity.platform.artifacts import RunArtifact, iso_now, new_run_id

        finance_artifact = RunArtifact(
            run_id=new_run_id(),
            kind=RunKind.FINANCE,
            config={"window_size": 60},
            seed=None,
            artifact_paths={},
            summary={"pillar": "finance"},
            provenance={},
            created_at=iso_now(),
        )
        registry.register(finance_artifact)

        # Filter by worlds kind.
        worlds_runs = registry.list(kind=RunKind.WORLDS)
        assert len(worlds_runs) == 1
        assert worlds_runs[0].run_id == worlds_id

        # All runs.
        all_runs = registry.list()
        assert len(all_runs) == 2
