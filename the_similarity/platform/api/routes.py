"""Route handlers for the Platform REST API.

All endpoints are synchronous per design decision in the task brief —
every runner we wrap (synthetic copies <1s, worlds ~2ms, sweep ~1.2s) fits
in a single HTTP request window for MVP. Background jobs come later when
something actually blocks.

Endpoint map
------------
- ``GET  /healthz``                           — smoke test + registry sanity.
- ``GET  /runs``                              — list newest-first, optional kind filter.
- ``GET  /runs/{run_id}``                     — full artifact by id.
- ``GET  /runs/{run_id}/artifacts/{name}``    — stream a named artifact file.
- ``POST /runs/copies``                       — synthetic copies generation.
- ``POST /runs/worlds``                       — headless worlds simulation.
- ``POST /runs/sweep``                        — example worlds-eval sweep.
- ``POST /compare``                           — diff two runs by run_id.

Invariant
---------
Every ``POST /runs/*`` that produces artifacts MUST register a
:class:`RunArtifact` with the :class:`RunRegistry` before returning. The
registry is the source of truth for downstream consumers (UI, harness);
returning without a registry write means the run is effectively invisible.

Failure modes
-------------
- 200 on GET success, 201 on POST that creates a new run.
- 404 when a run_id or logical artifact name is missing.
- 400 on malformed / logically-invalid input (missing file, bad generator).
- 500 on runner subprocess / pipeline failure — the detail message carries
  the runner's stderr so debugging does not require tailing logs.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from the_similarity.platform.api.main import get_registry
from the_similarity.platform.api.models import (
    CompareRequest,
    CompareResponse,
    CreateCopiesRunRequest,
    CreateSweepRequest,
    CreateWorldsRunRequest,
    HealthResponse,
    RunArtifactModel,
    RunListResponse,
)
from the_similarity.platform.artifacts import (
    RunArtifact,
    RunKind,
    iso_now,
    new_run_id,
    write_artifact,
)
from the_similarity.platform.registry import RunRegistry


router = APIRouter()


# ---------------------------------------------------------------------------
# Default artifact roots
# ---------------------------------------------------------------------------

# Repo root is three levels up from this file: api/ -> platform/ -> the_similarity/
# -> <repo>. Computed once so downstream helpers don't re-derive per request.
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Default output root for POST /runs/copies when the client does not pin
# ``out_dir``. Lives under ``artifacts/`` so the existing top-level gitignore
# rule applies and we do not accidentally commit synthetic outputs.
_DEFAULT_COPIES_OUT = _REPO_ROOT / "artifacts" / "copies-runs"

# Default output root for POST /runs/worlds.
_DEFAULT_WORLDS_OUT = _REPO_ROOT / "artifacts" / "worlds-runs"

# Path to the fractal package — the Node runner lives here.
_FRACTAL_ROOT = _REPO_ROOT / "the-similarity-fractal"
_WORLDS_RUNNER_JS = _FRACTAL_ROOT / "src" / "sim" / "headless" / "runner.js"
_SWEEP_SCRIPT_JS = _FRACTAL_ROOT / "src" / "eval" / "run-example-sweep.js"


# ---------------------------------------------------------------------------
# GET /healthz
# ---------------------------------------------------------------------------


@router.get("/healthz", response_model=HealthResponse, tags=["health"])
def healthz(registry: RunRegistry = Depends(get_registry)) -> HealthResponse:
    """Liveness + basic registry sanity.

    Returns 200 always — if the registry cannot be opened at all the
    dependency itself would have raised before entering this function,
    and FastAPI would emit 500. That is the intended signal: a broken
    registry is not "live".
    """
    # `.list(limit=...)` round-trips through SQLite, so this also verifies
    # the SQLite connection is usable (not just that the file exists).
    runs = registry.list(limit=10_000)
    return HealthResponse(
        status="ok",
        registry_db=str(registry.db_path),
        runs=len(runs),
    )


# ---------------------------------------------------------------------------
# GET /runs
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=RunListResponse, tags=["runs"])
def list_runs(
    kind: Optional[RunKind] = Query(None, description="Filter by run kind."),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of rows (default 100, max 1000).",
    ),
    registry: RunRegistry = Depends(get_registry),
) -> RunListResponse:
    """Newest-first listing of runs.

    Wraps :meth:`RunRegistry.list`. The ``kind`` filter is validated by
    FastAPI against the :class:`RunKind` enum so invalid values surface as
    422 before reaching this handler.
    """
    artifacts = registry.list(kind=kind, limit=limit)
    return RunListResponse(runs=[RunArtifactModel.from_artifact(a) for a in artifacts])


# ---------------------------------------------------------------------------
# GET /runs/{run_id}
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}",
    response_model=RunArtifactModel,
    tags=["runs"],
    responses={404: {"description": "run_id not found."}},
)
def get_run(
    run_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> RunArtifactModel:
    """Return a single artifact by run_id, or 404 if unknown."""
    artifact = registry.get(run_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"run_id not found: {run_id}",
        )
    return RunArtifactModel.from_artifact(artifact)


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/artifacts/{name}
# ---------------------------------------------------------------------------


def _resolve_artifact_file(artifact: RunArtifact, name: str) -> Path:
    """Map a logical artifact name to an absolute file path.

    ``artifact.artifact_paths[name]`` is relative to the run dir. We resolve
    the run dir by checking a few canonical anchors on the artifact:

    - ``provenance["run_dir"]`` — the runner's recorded absolute path, when
      present. This is the most reliable anchor because it was written at
      run time, not reconstructed post-hoc.
    - ``artifact.artifact_paths["run_dir"]`` — rare, but allowed for runs
      that key their own dir.

    Falls back to treating the logical path as absolute if it resolves on
    disk; otherwise raises FileNotFoundError so the caller emits 404.

    The returned path is validated to stay inside the resolved run dir to
    prevent path-traversal via a malicious ``artifact_paths`` entry.
    """
    relative = artifact.artifact_paths.get(name)
    if relative is None:
        raise FileNotFoundError(
            f"no artifact named {name!r} on run {artifact.run_id!r}"
        )

    candidate = Path(relative)
    if candidate.is_absolute() and candidate.exists():
        # Rare: runners that store absolute paths. Accept when the file
        # resolves; still return it since there is no run_dir to enclose.
        return candidate

    run_dir_hint = artifact.provenance.get("run_dir") or artifact.artifact_paths.get(
        "run_dir"
    )
    if run_dir_hint is None:
        # Without a run_dir anchor we cannot reliably resolve a relative
        # path; surface a clear error so the caller returns 404.
        raise FileNotFoundError(
            f"run {artifact.run_id!r} has no run_dir anchor; cannot resolve {name!r}"
        )

    run_dir = Path(run_dir_hint).resolve()
    resolved = (run_dir / candidate).resolve()

    # Path-traversal guard: the resolved path must stay inside run_dir.
    # ``Path.is_relative_to`` is Python 3.9+ and we target modern Python.
    if not resolved.is_relative_to(run_dir):
        raise FileNotFoundError(
            f"artifact path {relative!r} escapes run dir — refusing."
        )
    if not resolved.exists():
        raise FileNotFoundError(f"artifact file missing on disk: {resolved}")
    return resolved


@router.get(
    "/runs/{run_id}/artifacts/{name}",
    tags=["runs"],
    responses={404: {"description": "run_id or artifact name missing."}},
)
def get_run_artifact(
    run_id: str,
    name: str,
    registry: RunRegistry = Depends(get_registry),
) -> FileResponse:
    """Stream an artifact file from disk.

    The logical ``name`` must exist in ``artifact.artifact_paths`` — we do
    not expose arbitrary files on disk. A missing name or missing file both
    surface as 404 because either way the client's request cannot be
    fulfilled, and distinguishing them would leak registry internals.
    """
    artifact = registry.get(run_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"run_id not found: {run_id}",
        )
    try:
        path = _resolve_artifact_file(artifact, name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return FileResponse(path, filename=path.name)


# ---------------------------------------------------------------------------
# POST /runs/copies
# ---------------------------------------------------------------------------


def _new_run_dir(base: Path, kind: str, seed: int) -> Path:
    """Canonical per-run output dir under ``base``.

    Naming mirrors the synthetic CLI's ``run_dir_name`` convention:
    ``<kind>-<seed>-<YYYYMMDD-HHMMSS>``. The timestamp is UTC so
    directories sort chronologically regardless of the server's tz.
    """
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return base / f"{kind}-{seed}-{ts}"


def _run_copies_pipeline(req: CreateCopiesRunRequest) -> Path:
    """Execute the synthetic copies pipeline and return the run_dir.

    Imports the synthetic CLI module lazily to keep the API module import
    cheap — the copies pipeline pulls in pandas/numpy, which would slow
    ``uvicorn --reload`` cycles for every route edit otherwise.

    The run dir is computed here (not inside the CLI) so we have a direct
    handle to the outputs — the CLI itself does not return the path. We
    then invoke the CLI's public helpers to do the actual work.
    """
    from the_similarity.synthetic.cli import (
        build_generator,
        load_source,
        run_scorecards,
        write_parquets,
        write_provenance,
        write_report,
        write_scorecard,
    )
    from the_similarity.synthetic.contracts import (
        Provenance,
        Scorecard,
        SyntheticDataset,
        iso_now as synth_iso_now,
    )

    input_path = Path(req.input_path).expanduser()
    if not input_path.exists():
        # 400 — the client referenced a file we cannot read.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"input_path does not exist: {input_path}",
        )

    out_root = Path(req.out_dir).expanduser() if req.out_dir else _DEFAULT_COPIES_OUT
    out_root.mkdir(parents=True, exist_ok=True)

    run_dir = _new_run_dir(out_root, req.generator, req.seed)
    run_dir.mkdir(parents=True, exist_ok=False)

    # -- pipeline (mirrors synthetic.cli.run but we own the run_dir) ------
    df = load_source(input_path)
    source_id = input_path.stem

    real = SyntheticDataset(
        data=df,
        columns=list(df.columns),
        provenance=Provenance(
            source_id=source_id,
            generator_name="real",
            generator_version="0",
            seed=0,
            created_at=synth_iso_now(),
        ),
    )

    generator = build_generator(req.generator)
    generator.fit(real)
    synth = generator.sample(req.n, seed=req.seed)

    # Backfill provenance if the generator omitted it — the CLI applies the
    # same shim so the report renderer can always assume it is present.
    if synth.provenance is None:
        synth = SyntheticDataset(
            data=synth.data,
            index=synth.index,
            columns=synth.columns,
            provenance=Provenance(
                source_id=source_id,
                generator_name=getattr(generator, "name", req.generator),
                generator_version=getattr(generator, "version", "0"),
                seed=req.seed,
                created_at=synth_iso_now(),
            ),
        )

    fidelity, privacy, utility = run_scorecards(real, synth)
    scorecard = Scorecard(
        dataset=synth, fidelity=fidelity, privacy=privacy, utility=utility
    )

    write_parquets(run_dir, real, synth)
    write_scorecard(run_dir, scorecard)
    write_provenance(run_dir, synth.provenance)
    write_report(run_dir, scorecard, synth.provenance)
    return run_dir


def _copies_summary(run_dir: Path) -> Dict[str, Any]:
    """Extract headline numbers from scorecard.json for the artifact summary.

    Returns a best-effort dict: missing sections fall through silently so a
    partial scorecard (any of fidelity/privacy/utility optional) still
    produces a non-empty summary.
    """
    scorecard_path = run_dir / "scorecard.json"
    if not scorecard_path.exists():
        return {}
    payload = json.loads(scorecard_path.read_text(encoding="utf-8"))
    summary: Dict[str, Any] = {"passed": payload.get("passed")}
    fidelity = payload.get("fidelity") or {}
    privacy = payload.get("privacy") or {}
    utility = payload.get("utility") or {}
    if "overall_score" in fidelity:
        summary["fidelity_score"] = fidelity["overall_score"]
    if "overall_score" in privacy:
        summary["privacy_score"] = privacy["overall_score"]
    if "transfer_gap" in utility:
        summary["utility_transfer_gap"] = utility["transfer_gap"]
    return summary


@router.post(
    "/runs/copies",
    response_model=RunArtifactModel,
    status_code=status.HTTP_201_CREATED,
    tags=["runs"],
)
def create_copies_run(
    req: CreateCopiesRunRequest,
    registry: RunRegistry = Depends(get_registry),
) -> RunArtifactModel:
    """Run the synthetic copies pipeline and register the resulting artifact.

    Pipeline on success:

    1. Load source CSV/parquet from ``req.input_path``.
    2. Fit + sample via ``req.generator``.
    3. Score fidelity / privacy / utility (optional, tolerated if missing).
    4. Write real/synth parquet, scorecard.json, provenance.json, report.md.
    5. Build + register a :class:`RunArtifact`.

    Errors:

    - 400 when the input path does not exist or the generator name is bad.
    - 500 wrapping any other runner exception — detail surfaces the message.
    """
    try:
        run_dir = _run_copies_pipeline(req)
    except HTTPException:
        # Let FastAPI-shaped errors (400 from missing input) propagate.
        raise
    except ValueError as exc:
        # Unknown generator / unsupported file suffix.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:  # pragma: no cover - guard for unexpected failures
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"copies pipeline failed: {exc}",
        ) from exc

    # Build the unified RunArtifact. ``provenance`` embeds the synthetic
    # Provenance shape plus the run_dir anchor used by the artifacts
    # streaming endpoint.
    provenance_path = run_dir / "provenance.json"
    provenance = (
        json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance_path.exists()
        else {}
    )
    provenance["run_dir"] = str(run_dir)

    artifact = RunArtifact(
        run_id=new_run_id(),
        kind=RunKind.COPIES,
        config={
            "input_path": str(Path(req.input_path).expanduser()),
            "n": req.n,
            "seed": req.seed,
            "generator": req.generator,
        },
        seed=req.seed,
        artifact_paths={
            "real": "real.parquet",
            "synth": "synth.parquet",
            "scorecard": "scorecard.json",
            "provenance": "provenance.json",
            "report": "report.md",
        },
        summary=_copies_summary(run_dir),
        provenance=provenance,
        created_at=iso_now(),
    )
    write_artifact(run_dir, artifact)
    registry.register(artifact)
    return RunArtifactModel.from_artifact(artifact)


# ---------------------------------------------------------------------------
# POST /runs/worlds
# ---------------------------------------------------------------------------


def _parse_worlds_jsonl(path: Path) -> Dict[str, Any]:
    """Parse a worlds-runner JSONL file into provenance + summary dicts.

    The runner emits exactly one ``type=provenance`` record at the top and
    one ``type=summary`` record at the bottom, with ``type=tick`` records
    in between. We scan the file once and keep the first and last that
    match — the tick volume can be large so we avoid materializing
    intermediate records.
    """
    provenance: Dict[str, Any] = {}
    summary: Dict[str, Any] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines rather than fail the whole parse —
                # a truncated log is still informative.
                continue
            rtype = record.get("type")
            if rtype == "provenance" and not provenance:
                provenance = record
            elif rtype == "summary":
                summary = record
    return {"provenance": provenance, "summary": summary}


@router.post(
    "/runs/worlds",
    response_model=RunArtifactModel,
    status_code=status.HTTP_201_CREATED,
    tags=["runs"],
)
def create_worlds_run(
    req: CreateWorldsRunRequest,
    registry: RunRegistry = Depends(get_registry),
) -> RunArtifactModel:
    """Invoke the Node headless worlds runner as a subprocess.

    The worlds engine is TypeScript-first by design (see vision docs), so
    the API always crosses the language boundary via ``node
    the-similarity-fractal/src/sim/headless/runner.js``. We capture its
    stdout/stderr so runtime errors surface in the 500 detail rather than
    disappearing into the server's log buffer.
    """
    scenario_path = Path(req.scenario_path).expanduser()
    if not scenario_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"scenario_path does not exist: {scenario_path}",
        )

    if not _WORLDS_RUNNER_JS.exists():
        # Misconfigured install — fail loud so the operator fixes layout
        # rather than silently skipping the runner.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"worlds runner not found at {_WORLDS_RUNNER_JS}",
        )

    out_path = (
        Path(req.out_path).expanduser()
        if req.out_path
        else _new_run_dir(_DEFAULT_WORLDS_OUT, "worlds", req.seed) / "run.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_dir = out_path.parent

    cmd = [
        "node",
        str(_WORLDS_RUNNER_JS),
        "--scenario",
        str(scenario_path),
        "--seed",
        str(req.seed),
        "--steps",
        str(req.steps),
        "--out",
        str(out_path),
        "--quiet",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_FRACTAL_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        # ``node`` itself is missing — distinct from runner.js missing so
        # operators get a precise error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"node executable not found on PATH: {exc}",
        ) from exc

    if proc.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"worlds runner exit={proc.returncode}: {proc.stderr.strip()}",
        )

    parsed = _parse_worlds_jsonl(out_path)
    provenance = dict(parsed.get("provenance") or {})
    provenance["run_dir"] = str(run_dir)

    artifact = RunArtifact(
        run_id=new_run_id(),
        kind=RunKind.WORLDS,
        config={
            "scenario_path": str(scenario_path),
            "seed": req.seed,
            "steps": req.steps,
        },
        seed=req.seed,
        artifact_paths={"telemetry": out_path.name},
        summary=dict(parsed.get("summary") or {}),
        provenance=provenance,
        created_at=iso_now(),
    )
    write_artifact(run_dir, artifact)
    registry.register(artifact)
    return RunArtifactModel.from_artifact(artifact)


# ---------------------------------------------------------------------------
# POST /runs/sweep
# ---------------------------------------------------------------------------


@router.post(
    "/runs/sweep",
    response_model=RunArtifactModel,
    status_code=status.HTTP_201_CREATED,
    tags=["runs"],
)
def create_sweep_run(
    req: CreateSweepRequest,
    registry: RunRegistry = Depends(get_registry),
) -> RunArtifactModel:
    """Run the example parameter sweep and register its scorecard.

    MVP hard-wires ``run-example-sweep.js`` (ignoring ``req.sweep_script``)
    so we have one path to test. Forward-compatible: the request schema
    already accepts an alternative script so the UI can learn to pass one
    once we generalize the runner.
    """
    script_path = _SWEEP_SCRIPT_JS
    if not script_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"sweep script not found at {script_path}",
        )

    try:
        proc = subprocess.run(
            ["node", str(script_path)],
            cwd=str(_FRACTAL_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"node executable not found on PATH: {exc}",
        ) from exc

    if proc.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"sweep script exit={proc.returncode}: {proc.stderr.strip()}",
        )

    # The script prints one JSON line on success — capture it for the
    # summary preview. run-example-sweep.js emits to
    # ``artifacts/sweep-example/sweep-example/``.
    try:
        header = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        header = {}

    run_dir = _FRACTAL_ROOT / "artifacts" / "sweep-example" / "sweep-example"
    scorecard_path = run_dir / "scorecard.json"
    scorecard_payload: Dict[str, Any] = {}
    if scorecard_path.exists():
        try:
            scorecard_payload = json.loads(scorecard_path.read_text(encoding="utf-8"))
        except ValueError:
            scorecard_payload = {}

    # Summary pulls the headline numbers the UI cares about: global regime
    # coverage + any scorecard-wide pass flag. Falls back to the script's
    # stdout blob if scorecard.json is absent.
    summary: Dict[str, Any] = {}
    if header:
        summary.update(
            {
                "n_cells": header.get("n_cells"),
                "n_rows": header.get("n_rows"),
                "global_coverage": header.get("global_coverage"),
                "runtime_ms": header.get("runtime_ms"),
            }
        )
    if "passed" in scorecard_payload:
        summary["passed"] = scorecard_payload["passed"]

    provenance = scorecard_payload.get("provenance") or {}
    # ``provenance`` may itself be a dataclass dump; stringify to dict for
    # safety and anchor the run_dir for the artifact-streaming endpoint.
    if not isinstance(provenance, dict):
        provenance = {}
    provenance["run_dir"] = str(run_dir)

    artifact = RunArtifact(
        run_id=new_run_id(),
        kind=RunKind.SWEEP,
        config={"sweep_script": str(script_path)},
        seed=provenance.get("seed"),
        artifact_paths={
            "scorecard": "scorecard.json",
            "telemetry": "telemetry.jsonl",
        },
        summary=summary,
        provenance=provenance,
        created_at=iso_now(),
    )
    write_artifact(run_dir, artifact)
    registry.register(artifact)
    return RunArtifactModel.from_artifact(artifact)


# ---------------------------------------------------------------------------
# POST /compare
# ---------------------------------------------------------------------------


@router.post("/compare", response_model=CompareResponse, tags=["runs"])
def compare_runs(
    req: CompareRequest,
    registry: RunRegistry = Depends(get_registry),
) -> CompareResponse:
    """Diff the ``summary`` dicts of two runs.

    Thin wrapper over :meth:`RunRegistry.compare`. Missing run_ids surface
    as 404 (not 400) because the problem is a reference to a resource that
    does not exist, not malformed input.
    """
    try:
        result = registry.compare(req.run_id_a, req.run_id_b)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.args[0])
        ) from exc
    return CompareResponse(a=result["a"], b=result["b"], diff=result["diff"])


__all__ = ["router"]
