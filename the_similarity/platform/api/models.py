"""Pydantic v2 request/response models for the Platform REST API.

These models mirror — do not rewrite — the dataclasses in
:mod:`the_similarity.platform.artifacts`. The contract is that
``RunArtifactModel`` round-trips losslessly through ``RunArtifact.to_dict()``
in both directions:

    RunArtifact -> to_dict() -> RunArtifactModel.model_validate(...)
    RunArtifactModel.model_dump() -> RunArtifact.from_dict(...)

Field names, types, and optionality must stay aligned with
``artifacts.py`` and ``artifacts_schema.json``. Adding a field here without
adding it there (or vice versa) is a contract break.

Why Pydantic rather than reusing the dataclass
----------------------------------------------
FastAPI synthesizes OpenAPI schema from Pydantic models only — dataclasses
surface as opaque `dict` in the generated docs. We keep the dataclass as the
internal source of truth (used by the registry, synthetic CLI, worlds
runner) and Pydantic models as the *wire* shape. Callers that need to move
between the two use :meth:`RunArtifactModel.from_artifact` and
:meth:`RunArtifactModel.to_artifact`.

Request models deliberately leave runner-specific fields (``out_dir``,
``out_path``) optional so the API can choose sensible defaults when the
client does not care, while still allowing clients that orchestrate disk
layout to pin paths.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from the_similarity.platform.artifacts import RunArtifact, RunKind


# ---------------------------------------------------------------------------
# Core artifact wire shape
# ---------------------------------------------------------------------------


class RunArtifactModel(BaseModel):
    """Wire-level mirror of :class:`RunArtifact`.

    One-to-one with the dataclass fields. The ``kind`` field is typed as
    :class:`RunKind` so FastAPI's OpenAPI schema advertises the closed set
    of legal values; values round-trip as the lowercase string form because
    ``RunKind`` inherits from ``str``.
    """

    # Allow the enum in the model; Pydantic will serialize to its string
    # value by default because RunKind is a str-backed enum.
    model_config = ConfigDict(use_enum_values=True)

    run_id: str = Field(..., description="UUID4 hex (no dashes). Primary key in the registry.")
    kind: RunKind = Field(..., description="Run kind — one of copies, worlds, sweep, eval.")
    config: Dict[str, Any] = Field(
        ..., description="Run inputs (generator name + params, scenario, etc.)."
    )
    seed: Optional[int] = Field(
        None, description="RNG seed. None when a seed is not meaningful for this kind."
    )
    artifact_paths: Dict[str, str] = Field(
        ...,
        description="Logical artifact name -> relative path inside the run dir.",
    )
    summary: Dict[str, Any] = Field(
        ..., description="Headline numbers safe to index without loading bulk artifacts."
    )
    provenance: Dict[str, Any] = Field(
        ..., description="Reproducibility record (generator, version, seed, scenario...)."
    )
    created_at: str = Field(
        ..., description="ISO-8601 UTC timestamp, seconds precision."
    )

    # -- adapters ----------------------------------------------------------

    @classmethod
    def from_artifact(cls, artifact: RunArtifact) -> "RunArtifactModel":
        """Build a Pydantic model from a :class:`RunArtifact` dataclass.

        Uses ``to_dict()`` so the contract lives in exactly one place
        (the artifacts module); if that serializer grows a new field, it
        flows through here automatically.
        """
        return cls.model_validate(artifact.to_dict())

    def to_artifact(self) -> RunArtifact:
        """Invert :meth:`from_artifact` — build the dataclass from this model."""
        return RunArtifact.from_dict(self.model_dump())


# ---------------------------------------------------------------------------
# Health / listing
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Payload for ``GET /healthz`` — smoke test for orchestrators/monitors."""

    status: str = Field(..., description="Always 'ok' when the API is live.")
    registry_db: str = Field(
        ..., description="Absolute path of the SQLite DB backing the registry."
    )
    runs: int = Field(..., description="Total number of runs in the registry.")


class RunListResponse(BaseModel):
    """Wrapper for ``GET /runs`` — an ordered newest-first list of artifacts."""

    runs: List[RunArtifactModel] = Field(
        default_factory=list, description="Newest-first slice of registered runs."
    )


# ---------------------------------------------------------------------------
# Run-creation requests
# ---------------------------------------------------------------------------


class CreateCopiesRunRequest(BaseModel):
    """Body for ``POST /runs/copies`` — synthetic copies generation."""

    input_path: str = Field(
        ...,
        description="Absolute or repo-relative path to source data (.csv or .parquet).",
    )
    n: int = Field(..., ge=1, description="Number of synthetic rows to generate.")
    seed: int = Field(0, description="RNG seed. Default 0 for reproducibility.")
    out_dir: Optional[str] = Field(
        None,
        description=(
            "Optional output root. If omitted, API places runs under the "
            "default artifacts/copies-runs/ directory."
        ),
    )
    generator: str = Field(
        "block_bootstrap",
        description="Generator name — one of the synthetic CLI's choices.",
    )


class CreateWorldsRunRequest(BaseModel):
    """Body for ``POST /runs/worlds`` — headless worlds simulation."""

    scenario_path: str = Field(
        ..., description="Path to a scenario JSON (passed to the Node runner)."
    )
    seed: int = Field(42, description="RNG seed. Overrides scenario.seed.")
    steps: int = Field(
        500, ge=1, description="Number of ticks to simulate. Overrides scenario.steps."
    )
    out_path: Optional[str] = Field(
        None,
        description=(
            "Optional output .jsonl path. If omitted, API defaults under "
            "artifacts/worlds-runs/."
        ),
    )


class CreateSweepRequest(BaseModel):
    """Body for ``POST /runs/sweep`` — parameter sweep across the worlds runner.

    MVP wraps the example sweep script; ``sweep_script`` is accepted for
    forward-compatibility so the UI can point at custom sweep scripts once
    we generalize the runner. Unused in MVP.
    """

    sweep_script: Optional[str] = Field(
        None,
        description=(
            "Optional path to an alternative sweep .js script. "
            "MVP always runs run-example-sweep.js regardless."
        ),
    )


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    """Body for ``POST /compare`` — diff two registered runs by run_id."""

    run_id_a: str = Field(..., description="First run_id.")
    run_id_b: str = Field(..., description="Second run_id.")


class CompareResponse(BaseModel):
    """Return shape of ``registry.compare()`` with tuples flattened to lists.

    ``diff`` values are emitted as 2-element lists ``[a_value, b_value]``
    because JSON has no tuple type. Missing-on-one-side keys appear as
    ``None`` for the absent side — same semantics as :meth:`RunRegistry.compare`.
    """

    a: Dict[str, Any] = Field(..., description="summary dict of run_id_a.")
    b: Dict[str, Any] = Field(..., description="summary dict of run_id_b.")
    diff: Dict[str, Tuple[Any, Any]] = Field(
        default_factory=dict,
        description="Keys differing between the two summaries; value = [a, b].",
    )


__all__ = [
    "CompareRequest",
    "CompareResponse",
    "CreateCopiesRunRequest",
    "CreateSweepRequest",
    "CreateWorldsRunRequest",
    "HealthResponse",
    "RunArtifactModel",
    "RunListResponse",
]
