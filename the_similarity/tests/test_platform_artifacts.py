"""Tests for the unified run artifact model.

These tests lock in the *field contract* of :class:`RunArtifact` — any change
that breaks them is a breaking change for the registry, the HTTP API, the
TypeScript worlds side, and every downstream consumer. If you find yourself
editing one of these tests, pause: the registry agent and the TS worlds side
are keyed on this exact shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_similarity.platform import (
    RunArtifact,
    RunKind,
    new_run_id,
    read_artifact,
    write_artifact,
)
from the_similarity.platform.artifacts import (
    ARTIFACT_FILENAME,
    iso_now,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _sample_copies_artifact() -> RunArtifact:
    """A representative COPIES artifact covering every field.

    We use a fixed `created_at` and `run_id` so equality comparisons in
    round-trip tests don't depend on wall-clock time or randomness.
    """
    return RunArtifact(
        run_id="a" * 32,
        kind=RunKind.COPIES,
        config={"generator": "gaussian_copula", "n_samples": 512},
        seed=42,
        artifact_paths={
            "synthetic_csv": "synthetic.csv",
            "scorecard": "scorecard.json",
        },
        summary={"fidelity_score": 0.87, "passed": True},
        provenance={
            "source_id": "spy-2020-2024",
            "generator_name": "gaussian_copula",
            "generator_version": "0.1.0",
            "seed": 42,
            "created_at": "2026-04-15T12:00:00+00:00",
            "params": {"n_series": 3},
        },
        created_at="2026-04-15T12:00:00+00:00",
    )


def _sample_worlds_artifact() -> RunArtifact:
    """A WORLDS artifact shaped to match the TS runner's provenance line.

    The TS runner (`the-similarity-fractal/src/sim/headless/telemetry.js`)
    emits provenance with `generator_name`, `version`, `seed`,
    `scenario_name`, `scenario`, `params`, `created_at`. The unified
    artifact accepts that shape verbatim in the ``provenance`` dict.
    """
    return RunArtifact(
        run_id="b" * 32,
        kind=RunKind.WORLDS,
        config={"scenario_name": "boom_bust", "duration_steps": 2048},
        seed=7,
        artifact_paths={"telemetry": "run.jsonl"},
        summary={"n_ticks": 2048, "wall_time_ms": 1234},
        provenance={
            "generator_name": "the-similarity-fractal-headless",
            "version": "0.1.0",
            "seed": 7,
            "scenario_name": "boom_bust",
            "scenario": {"name": "boom_bust", "regime": "bull"},
            "params": {"volatility": 0.2},
            "created_at": "2026-04-15T12:00:00+00:00",
        },
        created_at="2026-04-15T12:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


def test_to_dict_from_dict_round_trip_copies() -> None:
    """COPIES artifact -> dict -> JSON string -> dict -> artifact is equal."""
    original = _sample_copies_artifact()
    # The full loop exercises: dataclass -> dict, dict -> json string,
    # json string -> dict, dict -> dataclass. Any serialization hole in
    # the chain will produce a non-equal result at the end.
    blob = json.dumps(original.to_dict())
    reconstructed = RunArtifact.from_dict(json.loads(blob))
    assert reconstructed == original


def test_to_dict_from_dict_round_trip_worlds() -> None:
    """WORLDS artifact (nested provenance) round-trips cleanly."""
    original = _sample_worlds_artifact()
    blob = json.dumps(original.to_dict())
    reconstructed = RunArtifact.from_dict(json.loads(blob))
    assert reconstructed == original


def test_enum_serializes_to_string_value() -> None:
    """`kind` field must serialize to the lowercase string value.

    The TS worlds side and ad-hoc jq queries read this field as a raw
    string — if it ever leaks the Python repr (``RunKind.COPIES``) we
    break every non-Python consumer.
    """
    art = _sample_copies_artifact()
    d = art.to_dict()
    assert d["kind"] == "copies"
    assert isinstance(d["kind"], str)


def test_enum_deserializes_from_string() -> None:
    """`from_dict` must accept the raw string form of `kind`."""
    art = _sample_copies_artifact()
    d = art.to_dict()
    # Simulate a writer that emits plain JSON (not via to_dict) — kind
    # is a bare string, not an enum instance.
    assert isinstance(d["kind"], str)
    reconstructed = RunArtifact.from_dict(d)
    assert reconstructed.kind is RunKind.COPIES


def test_optional_seed_none_round_trip() -> None:
    """`seed = None` must survive round-trip for eval-style runs.

    Evaluation runs over an existing corpus don't have a single seed —
    the artifact carries ``seed=None`` and consumers must tolerate it.
    """
    art = RunArtifact(
        run_id=new_run_id(),
        kind=RunKind.EVAL,
        config={"runs": ["abc123", "def456"]},
        seed=None,
        artifact_paths={"scorecard": "scorecard.json"},
        summary={"mean_fidelity": 0.81},
        provenance={"evaluator": "default", "created_at": iso_now()},
        created_at=iso_now(),
    )
    d = art.to_dict()
    assert d["seed"] is None
    reconstructed = RunArtifact.from_dict(json.loads(json.dumps(d)))
    assert reconstructed.seed is None
    assert reconstructed == art


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------


def test_write_read_symmetry(tmp_path: Path) -> None:
    """write_artifact then read_artifact yields an equal RunArtifact."""
    art = _sample_copies_artifact()
    run_dir = tmp_path / "run_abc"
    written = write_artifact(run_dir, art)

    # write_artifact must create the directory and place artifact.json.
    assert written == run_dir / ARTIFACT_FILENAME
    assert written.exists()

    # The inverse returns an equal object.
    loaded = read_artifact(written)
    assert loaded == art


def test_read_artifact_accepts_directory(tmp_path: Path) -> None:
    """read_artifact may be pointed at the run dir, not just the file.

    Callers often hold the run directory handle (from the runner) and
    it's friction to make them append `/artifact.json`. The helper
    detects and appends for them.
    """
    art = _sample_worlds_artifact()
    run_dir = tmp_path / "run_xyz"
    write_artifact(run_dir, art)

    loaded = read_artifact(run_dir)  # directory, not file
    assert loaded == art


def test_write_artifact_is_pretty_printed(tmp_path: Path) -> None:
    """`artifact.json` must be human-readable (2-space indent, trailing newline).

    We diff these files in git and grep them at the terminal — a single
    unindented blob would be hostile to both.
    """
    art = _sample_copies_artifact()
    path = write_artifact(tmp_path / "run", art)
    text = path.read_text(encoding="utf-8")
    # 2-space indent shows up as "  \"" after the opening brace.
    assert '\n  "run_id":' in text
    # Trailing newline for POSIX-friendly file.
    assert text.endswith("\n")


def test_write_artifact_creates_missing_run_dir(tmp_path: Path) -> None:
    """write_artifact must create parent directories if they don't exist."""
    art = _sample_copies_artifact()
    deep_run_dir = tmp_path / "runs" / "2026" / "04" / "run_a"
    assert not deep_run_dir.exists()
    write_artifact(deep_run_dir, art)
    assert (deep_run_dir / ARTIFACT_FILENAME).exists()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_new_run_id_is_uuid4_hex() -> None:
    """`new_run_id` returns 32 hex chars (no dashes)."""
    rid = new_run_id()
    assert len(rid) == 32
    # All lowercase hex — we use it in file paths and URLs.
    int(rid, 16)  # raises if not hex


def test_new_run_id_is_unique() -> None:
    """Two calls must not collide (UUID4, so collision probability ~0)."""
    assert new_run_id() != new_run_id()


def test_from_dict_ignores_unknown_keys() -> None:
    """Forward compatibility: a newer writer may add fields.

    An older reader must not explode on fields it doesn't know about.
    This test is the contract between versions — do not weaken it.
    """
    d = _sample_copies_artifact().to_dict()
    d["future_field"] = {"something": "new"}
    art = RunArtifact.from_dict(d)
    assert art.run_id == "a" * 32


# ---------------------------------------------------------------------------
# JSON schema
# ---------------------------------------------------------------------------


SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "platform" / "artifacts_schema.json"
)


def test_schema_file_is_valid_json() -> None:
    """`artifacts_schema.json` must parse as JSON.

    It's shipped as-is to the TypeScript worlds side, which will refuse
    to start if the schema is malformed.
    """
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_schema_declares_draft_07() -> None:
    """We target JSON Schema Draft-07 — `ajv` defaults consume it without flags."""
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert data["$schema"] == "http://json-schema.org/draft-07/schema#"


def test_schema_is_object_type_with_required_fields() -> None:
    """Every frozen field must appear in the schema's `required` array.

    If a field is added to `RunArtifact`, it must also be added here —
    or explicitly declared optional. We test for exact required-set match
    against the dataclass's non-optional fields.
    """
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert data["type"] == "object"
    assert set(data["required"]) == {
        "run_id",
        "kind",
        "config",
        "seed",
        "artifact_paths",
        "summary",
        "provenance",
        "created_at",
    }


def test_schema_enumerates_all_run_kinds() -> None:
    """`kind` enum in the schema must match `RunKind` exactly.

    Mismatch means a run produced by the Python side may be rejected by
    the TS validator (or vice versa). This is the tripwire.
    """
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_kinds = set(data["properties"]["kind"]["enum"])
    python_kinds = {k.value for k in RunKind}
    assert schema_kinds == python_kinds


@pytest.mark.parametrize(
    "kind",
    list(RunKind),
)
def test_every_run_kind_round_trips(kind: RunKind) -> None:
    """Smoke test — every RunKind serializes and deserializes to itself."""
    art = RunArtifact(
        run_id=new_run_id(),
        kind=kind,
        config={},
        seed=None,
        artifact_paths={},
        summary={},
        provenance={},
        created_at=iso_now(),
    )
    d = art.to_dict()
    assert d["kind"] == kind.value
    reconstructed = RunArtifact.from_dict(json.loads(json.dumps(d)))
    assert reconstructed.kind is kind
