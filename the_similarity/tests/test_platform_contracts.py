"""Tests for the unified platform contracts module.

These tests lock in the *field contract* of every dataclass in
:mod:`the_similarity.platform.contracts` — any change that breaks them
is a breaking change for the registry, the HTTP API, the TypeScript
consumers, and every persisted row. If you find yourself editing one
of these tests, pause: the contracts are load-bearing for six pillars
at once.

Coverage
--------
1. Shape sanity — every dataclass round-trips cleanly through
   ``to_dict`` / ``from_dict`` and through a JSON encode/decode pass.
2. Enum coverage — ``RunKind`` continues to include every legacy value
   and the new pillar values; ``RunStatus`` / ``ScorecardKind`` expose
   their full membership.
3. JSON schema — ``platform_schema.json`` parses, declares Draft-07,
   and its ``$defs`` match the Python dataclasses.
4. Backward compat — a dict in the legacy ``RunArtifact`` shape loads
   cleanly into ``RunRecord`` with sensible defaults.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_similarity.platform import (
    ArtifactRecord,
    DatasetSpec,
    Provenance,
    RunArtifact,
    RunKind,
    RunRecord,
    RunStatus,
    ScenarioSpec,
    ScorecardKind,
    ScorecardSummary,
    iso_now,
    new_run_id,
)


# ---------------------------------------------------------------------------
# Fixtures — representative instances of every dataclass
# ---------------------------------------------------------------------------


def _sample_run_record() -> RunRecord:
    """Representative :class:`RunRecord` covering every field."""
    return RunRecord(
        run_id="a" * 32,
        kind=RunKind.FINANCE,
        config={"symbol": "SPY", "window": 60},
        seed=314,
        status=RunStatus.SUCCEEDED,
        summary={"hit_rate": 0.62, "crps": 0.031},
        created_at="2026-04-15T12:00:00+00:00",
        pillar="finance",
        artifact_paths={"scorecard": "scorecard.json"},
        provenance={
            "generator_name": "analogue_search",
            "generator_version": "0.2.0",
            "seed": 314,
            "created_at": "2026-04-15T12:00:00+00:00",
            "params": {"k": 25},
            "env": {"python": "3.12.4", "platform": "darwin-arm64"},
        },
    )


def _sample_artifact_record() -> ArtifactRecord:
    """Representative :class:`ArtifactRecord`."""
    return ArtifactRecord(
        run_id="a" * 32,
        name="scorecard",
        path="scorecard.json",
        content_type="application/json",
        created_at="2026-04-15T12:00:00+00:00",
        size_bytes=1234,
        checksum="deadbeef" * 8,
    )


def _sample_scorecard_summary() -> ScorecardSummary:
    """Representative :class:`ScorecardSummary`."""
    return ScorecardSummary(
        run_id="a" * 32,
        kind=ScorecardKind.FIDELITY,
        overall_score=0.87,
        passed=True,
        thresholds={"ks_max": 0.1, "acf_mae_max": 0.05},
        details={"ks": 0.08, "acf_mae": 0.03},
    )


def _sample_provenance() -> Provenance:
    """Representative :class:`Provenance` (extended shape)."""
    return Provenance(
        source_id="spy-2020-2024",
        generator_name="gaussian_copula",
        generator_version="0.1.0",
        seed=42,
        created_at="2026-04-15T12:00:00+00:00",
        params={"n_series": 3},
        env={
            "python": "3.12.4",
            "node": "20.11.0",
            "platform": "darwin-arm64",
            "git_sha": "b8c6714",
        },
    )


def _sample_scenario_spec() -> ScenarioSpec:
    """Representative :class:`ScenarioSpec`."""
    return ScenarioSpec(
        scenario_id="small_village_v1",
        name="Small Village",
        version="1.0.0",
        engine="small_village",
        params={"n_agents": 50, "rounds": 200},
        metadata={"authors": ["buba"], "tags": ["worlds", "mvp"]},
    )


def _sample_dataset_spec() -> DatasetSpec:
    """Representative :class:`DatasetSpec`."""
    return DatasetSpec(
        dataset_id="spy-2020-2024",
        name="SPY Daily Bars 2020-2024",
        version="v1.0",
        source="the-similarity-data/equity/spy.parquet",
        schema_uri="https://the-similarity.dev/schemas/bars.json",
        n_rows=1024,
        n_columns=6,
        checksum="cafebabe" * 8,
        metadata={"pillar": "finance", "license": "proprietary"},
    )


# ---------------------------------------------------------------------------
# Round-trip tests — to_dict / from_dict / JSON
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sample",
    [
        _sample_run_record(),
        _sample_artifact_record(),
        _sample_scorecard_summary(),
        _sample_provenance(),
        _sample_scenario_spec(),
        _sample_dataset_spec(),
    ],
    ids=[
        "RunRecord",
        "ArtifactRecord",
        "ScorecardSummary",
        "Provenance",
        "ScenarioSpec",
        "DatasetSpec",
    ],
)
def test_dataclass_round_trips_through_json(sample: object) -> None:
    """Every contract dataclass: dataclass -> dict -> JSON -> dict -> dataclass."""
    # The full loop exercises both to_dict and from_dict plus a JSON pass
    # to make sure all values are JSON-safe primitives.
    cls = type(sample)
    blob = json.dumps(sample.to_dict())  # type: ignore[attr-defined]
    reconstructed = cls.from_dict(json.loads(blob))  # type: ignore[attr-defined]
    assert reconstructed == sample


# ---------------------------------------------------------------------------
# RunRecord — enum & backward compat
# ---------------------------------------------------------------------------


def test_run_record_kind_serializes_to_string_value() -> None:
    """``kind`` must serialize to the lowercase string value, not the enum repr."""
    rec = _sample_run_record()
    d = rec.to_dict()
    assert d["kind"] == "finance"
    assert isinstance(d["kind"], str)
    assert d["status"] == "succeeded"
    assert isinstance(d["status"], str)


def test_run_record_from_dict_accepts_legacy_run_artifact_shape() -> None:
    """A dict in the legacy ``RunArtifact`` shape (no status/pillar) loads cleanly.

    This is the critical backward-compat guarantee: every ``artifact.json``
    ever written under the old shape must still be loadable as a
    :class:`RunRecord` without explosion. ``status`` defaults to
    ``SUCCEEDED`` (historical artifacts only landed after success) and
    ``pillar`` is inferred from ``kind``.
    """
    legacy_artifact = RunArtifact(
        run_id="b" * 32,
        kind=RunKind.COPIES,
        config={"generator": "gaussian_copula"},
        seed=42,
        artifact_paths={"synthetic_csv": "synthetic.csv"},
        summary={"fidelity_score": 0.87},
        provenance={
            "source_id": "spy-2020-2024",
            "generator_name": "gaussian_copula",
            "generator_version": "0.1.0",
            "seed": 42,
            "created_at": "2026-04-15T12:00:00+00:00",
            "params": {},
        },
        created_at="2026-04-15T12:00:00+00:00",
    )
    # RunArtifact's to_dict shape is exactly the legacy persisted shape.
    legacy_dict = legacy_artifact.to_dict()
    assert "status" not in legacy_dict
    assert "pillar" not in legacy_dict

    rec = RunRecord.from_dict(legacy_dict)
    # Defaults applied.
    assert rec.status is RunStatus.SUCCEEDED
    assert rec.pillar == "synthetic"  # mapping from COPIES
    # Legacy fields preserved verbatim.
    assert rec.artifact_paths == {"synthetic_csv": "synthetic.csv"}
    assert rec.provenance["generator_name"] == "gaussian_copula"
    # Core fields carried through unchanged.
    assert rec.run_id == "b" * 32
    assert rec.kind is RunKind.COPIES
    assert rec.seed == 42


def test_run_record_from_run_artifact_helper() -> None:
    """``RunRecord.from_run_artifact`` promotes a legacy artifact in one call."""
    legacy = RunArtifact(
        run_id="c" * 32,
        kind=RunKind.WORLDS,
        config={"scenario_name": "boom_bust"},
        seed=7,
        artifact_paths={"telemetry": "run.jsonl"},
        summary={"n_ticks": 2048},
        provenance={
            "generator_name": "the-similarity-fractal-headless",
            "version": "0.1.0",
            "seed": 7,
            "scenario_name": "boom_bust",
            "scenario": {"name": "boom_bust"},
            "params": {},
            "created_at": "2026-04-15T12:00:00+00:00",
        },
        created_at="2026-04-15T12:00:00+00:00",
    )
    rec = RunRecord.from_run_artifact(legacy)
    assert rec.run_id == "c" * 32
    assert rec.kind is RunKind.WORLDS
    assert rec.status is RunStatus.SUCCEEDED
    assert rec.pillar == "worlds"
    # Overrides must work.
    rec_failed = RunRecord.from_run_artifact(
        legacy, status=RunStatus.FAILED, pillar="custom"
    )
    assert rec_failed.status is RunStatus.FAILED
    assert rec_failed.pillar == "custom"


def test_run_record_from_dict_ignores_unknown_keys() -> None:
    """Forward compat: a newer writer may add fields we don't yet know."""
    d = _sample_run_record().to_dict()
    d["future_field"] = {"x": 1}
    rec = RunRecord.from_dict(d)
    # No explosion — the unknown key is simply dropped.
    assert rec.run_id == "a" * 32


def test_run_record_kind_round_trips_for_all_run_kinds() -> None:
    """Every :class:`RunKind` survives a RunRecord round-trip.

    Guards against divergence between the RunKind members and the
    ``from_dict`` / ``to_dict`` dispatch — a new member added to the
    enum without wiring here would surface as a ``ValueError``.
    """
    for kind in RunKind:
        rec = RunRecord(
            run_id=new_run_id(),
            kind=kind,
            config={},
            seed=None,
            status=RunStatus.SUCCEEDED,
            summary={},
            created_at=iso_now(),
            pillar="test",
        )
        d = rec.to_dict()
        assert d["kind"] == kind.value
        reconstructed = RunRecord.from_dict(json.loads(json.dumps(d)))
        assert reconstructed.kind is kind


def test_run_record_status_round_trips_for_all_statuses() -> None:
    """Every :class:`RunStatus` survives a RunRecord round-trip."""
    for status in RunStatus:
        rec = RunRecord(
            run_id=new_run_id(),
            kind=RunKind.FINANCE,
            config={},
            seed=None,
            status=status,
            summary={},
            created_at=iso_now(),
            pillar="finance",
        )
        d = rec.to_dict()
        assert d["status"] == status.value
        reconstructed = RunRecord.from_dict(json.loads(json.dumps(d)))
        assert reconstructed.status is status


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


def test_run_kind_covers_legacy_values() -> None:
    """Legacy RunKind values (copies/worlds/sweep/eval) MUST still exist.

    Removing any of them would invalidate every ``artifact.json`` already
    on disk — so this test guards the minimum set forever.
    """
    values = {k.value for k in RunKind}
    for legacy in ("copies", "worlds", "sweep", "eval"):
        assert legacy in values


def test_run_kind_includes_new_pillar_values() -> None:
    """New pillar kinds (finance/events/nl_ts) are live in the enum."""
    values = {k.value for k in RunKind}
    for pillar in ("finance", "events", "nl_ts"):
        assert pillar in values


def test_run_status_has_full_membership() -> None:
    """RunStatus covers the MVP linear state machine."""
    values = {s.value for s in RunStatus}
    assert values == {"pending", "running", "succeeded", "failed"}


def test_scorecard_kind_has_full_membership() -> None:
    """ScorecardKind covers every evaluation category the platform ships."""
    values = {k.value for k in ScorecardKind}
    assert values == {
        "fidelity",
        "privacy",
        "utility",
        "controllability",
        "calibration",
        "backtest",
    }


# ---------------------------------------------------------------------------
# Provenance — backward compat with the synthetic shape
# ---------------------------------------------------------------------------


def test_provenance_loads_legacy_synthetic_shape() -> None:
    """A dict matching :class:`the_similarity.synthetic.contracts.Provenance`
    (no ``env`` field) must still load into the platform :class:`Provenance`.
    """
    legacy = {
        "source_id": "spy-2020-2024",
        "generator_name": "gaussian_copula",
        "generator_version": "0.1.0",
        "seed": 42,
        "created_at": "2026-04-15T12:00:00+00:00",
        "params": {"n_series": 3},
    }
    prov = Provenance.from_dict(legacy)
    # env defaults to empty rather than raising.
    assert prov.env == {}
    assert prov.source_id == "spy-2020-2024"
    assert prov.seed == 42


def test_provenance_loads_worlds_runner_shape() -> None:
    """The worlds runner uses ``version`` rather than ``generator_version``.

    :meth:`Provenance.from_dict` accepts either for cross-pillar ingest
    — this test pins that contract so the TS worlds side stays readable.
    """
    worlds = {
        "generator_name": "the-similarity-fractal-headless",
        "version": "0.1.0",  # note: version, not generator_version
        "seed": 7,
        "created_at": "2026-04-15T12:00:00+00:00",
    }
    prov = Provenance.from_dict(worlds)
    assert prov.generator_version == "0.1.0"
    assert prov.source_id is None  # worlds has no source corpus


# ---------------------------------------------------------------------------
# JSON schema — platform_schema.json
# ---------------------------------------------------------------------------


SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "platform" / "platform_schema.json"
)


def test_platform_schema_is_valid_json() -> None:
    """``platform_schema.json`` must parse as JSON — it's shipped as-is to TS."""
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_platform_schema_declares_draft_07() -> None:
    """Draft-07 is what ``ajv`` consumes without flags."""
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert data["$schema"] == "http://json-schema.org/draft-07/schema#"


def test_platform_schema_defines_all_top_level_types() -> None:
    """Every dataclass + enum exposed from the module has a $defs entry."""
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    defs = set(data["$defs"].keys())
    expected = {
        "RunKind",
        "RunStatus",
        "ScorecardKind",
        "RunRecord",
        "ArtifactRecord",
        "ScorecardSummary",
        "Provenance",
        "ScenarioSpec",
        "DatasetSpec",
    }
    assert expected.issubset(defs)


def test_platform_schema_run_kind_matches_python_enum() -> None:
    """Schema ``RunKind`` enum MUST match the Python :class:`RunKind`.

    This is the tripwire that prevents Python-side additions from
    silently breaking TS validators.
    """
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_kinds = set(data["$defs"]["RunKind"]["enum"])
    python_kinds = {k.value for k in RunKind}
    assert schema_kinds == python_kinds


def test_platform_schema_run_status_matches_python_enum() -> None:
    """Schema ``RunStatus`` enum MUST match the Python :class:`RunStatus`."""
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_statuses = set(data["$defs"]["RunStatus"]["enum"])
    python_statuses = {s.value for s in RunStatus}
    assert schema_statuses == python_statuses


def test_platform_schema_scorecard_kind_matches_python_enum() -> None:
    """Schema ``ScorecardKind`` enum MUST match the Python :class:`ScorecardKind`."""
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_kinds = set(data["$defs"]["ScorecardKind"]["enum"])
    python_kinds = {k.value for k in ScorecardKind}
    assert schema_kinds == python_kinds


def test_platform_schema_required_fields_match_dataclasses() -> None:
    """Required fields in the schema align with the dataclass contracts.

    We don't require the schema to list ALL fields as required (optional
    fields with defaults are deliberately not required), but we do
    require the non-optional primary key + kind + type fields to be
    present so a validator rejects malformed rows.
    """
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    # RunRecord: everything but artifact_paths/provenance (which have
    # defaults in the dataclass) must be required.
    required = set(data["$defs"]["RunRecord"]["required"])
    assert {"run_id", "kind", "config", "seed", "status", "summary", "created_at", "pillar"}.issubset(
        required
    )
    # ArtifactRecord: run_id, name, path, content_type, created_at.
    required = set(data["$defs"]["ArtifactRecord"]["required"])
    assert {"run_id", "name", "path", "content_type", "created_at"}.issubset(required)
    # DatasetSpec: dataset_id, name, version, source.
    required = set(data["$defs"]["DatasetSpec"]["required"])
    assert {"dataset_id", "name", "version", "source"}.issubset(required)
    # ScenarioSpec: scenario_id, name, version, engine.
    required = set(data["$defs"]["ScenarioSpec"]["required"])
    assert {"scenario_id", "name", "version", "engine"}.issubset(required)


def _manual_shape_validate(instance: dict, schema_def: dict) -> None:
    """Minimal structural validator — fallback when jsonschema is absent.

    Validates:
    - Required keys are present.
    - Declared type for simple types ("string", "integer", "number",
      "boolean", "object") matches the value at that key.

    Not a full Draft-07 implementation — we only need enough to
    catch shape drift between the Python dataclasses and the schema.
    """
    for key in schema_def.get("required", []):
        assert key in instance, f"missing required field: {key}"
    # Best-effort type check on declared primitive types.
    for key, prop in schema_def.get("properties", {}).items():
        if key not in instance:
            continue
        value = instance[key]
        t = prop.get("type")
        if t == "string":
            assert isinstance(value, str), f"{key} must be str"
        elif t == "integer":
            assert isinstance(value, int) and not isinstance(value, bool), (
                f"{key} must be int"
            )
        elif t == "number":
            assert isinstance(value, (int, float)) and not isinstance(value, bool), (
                f"{key} must be number"
            )
        elif t == "boolean":
            assert isinstance(value, bool), f"{key} must be bool"
        elif t == "object":
            assert isinstance(value, dict), f"{key} must be dict"


def test_platform_schema_validates_sample_instances() -> None:
    """Example instances must validate against their schema $defs.

    Uses :mod:`jsonschema` if available (fuller validation), else falls
    back to a hand-rolled shape check that at least catches missing
    required fields and primitive-type mismatches.
    """
    data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    defs = data["$defs"]

    cases = {
        "RunRecord": _sample_run_record().to_dict(),
        "ArtifactRecord": _sample_artifact_record().to_dict(),
        "ScorecardSummary": _sample_scorecard_summary().to_dict(),
        "Provenance": _sample_provenance().to_dict(),
        "ScenarioSpec": _sample_scenario_spec().to_dict(),
        "DatasetSpec": _sample_dataset_spec().to_dict(),
    }

    try:
        # jsonschema is a transitive dep of many tools — use it if present
        # for a proper Draft-07 validation pass.
        import jsonschema  # type: ignore[import]

        for def_name, instance in cases.items():
            # Build a standalone schema pointing at the def we want to
            # validate against; jsonschema resolves $ref inside $defs.
            sub_schema = {
                "$schema": data["$schema"],
                "$defs": defs,
                "$ref": f"#/$defs/{def_name}",
            }
            jsonschema.validate(instance=instance, schema=sub_schema)
    except ImportError:
        # Fallback: minimal structural check using our hand-rolled
        # validator. Still catches missing-required-field regressions.
        for def_name, instance in cases.items():
            _manual_shape_validate(instance, defs[def_name])


# ---------------------------------------------------------------------------
# Cross-type FK sanity
# ---------------------------------------------------------------------------


def test_artifact_and_scorecard_point_at_same_run_id() -> None:
    """ArtifactRecord and ScorecardSummary share the same run_id convention.

    Not a schema check — just a sanity test that the FK pattern works
    end-to-end with real instances.
    """
    rec = _sample_run_record()
    art = ArtifactRecord(
        run_id=rec.run_id,
        name="scorecard",
        path="scorecard.json",
        content_type="application/json",
        created_at=rec.created_at,
    )
    sc = ScorecardSummary(
        run_id=rec.run_id,
        kind=ScorecardKind.BACKTEST,
        overall_score=0.7,
    )
    assert art.run_id == rec.run_id == sc.run_id
