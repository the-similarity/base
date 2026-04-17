"""Synthetic-copies pillar -> platform registry adapter.

Reads the on-disk artifacts produced by
``the_similarity.synthetic.cli`` (``scorecard.json``, ``provenance.json``,
``real.parquet``, ``synth.parquet``, ``report.md``) and registers them as a
single :class:`~the_similarity.platform.artifacts.RunArtifact` with
``kind=RunKind.COPIES``.

Why a separate adapter?
-----------------------
The synthetic CLI predates the platform registry and already writes a
self-contained run directory. Rather than reach into the CLI's writers to
also emit an ``artifact.json``, the adapter runs *after* the CLI finishes,
reading what's on disk. This keeps the CLI free of an optional dependency
on the registry while still letting the platform index every copies run.

The adapter is idempotent over ``run_id``: re-running it against the same
directory with the same run_id upserts the registry row but does not
modify the on-disk artifacts.

File contract
-------------
- ``<run_dir>/scorecard.json`` — required. Carries passed / fidelity /
  privacy / utility metrics.
- ``<run_dir>/provenance.json`` — required. Flat JSON dict matching the
  :class:`the_similarity.synthetic.contracts.Provenance` dataclass shape.
- ``<run_dir>/real.parquet`` — optional. Listed in ``artifact_paths`` if
  present; absent files are skipped so older runs still register.
- ``<run_dir>/synth.parquet`` — optional. Same treatment as real.parquet.
- ``<run_dir>/report.md`` — optional. Human-readable summary.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from the_similarity.platform.artifacts import (
    RunArtifact,
    RunKind,
    iso_now,
    new_run_id,
    write_artifact,
)
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def _read_json_if_present(path: Path) -> Dict[str, Any]:
    """Parse a JSON file into a dict, returning {} if the file is missing.

    We deliberately swallow JSONDecodeError in favor of logging to stderr —
    a malformed scorecard should not prevent the run from being indexed
    (the parquet files may still be usable for manual audit).
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _summary_from_scorecard(scorecard: Dict[str, Any]) -> Dict[str, Any]:
    """Extract headline numbers from scorecard.json for the registry summary.

    Missing scorecard sections collapse silently — a run with only fidelity
    still produces a useful summary. We project the same three headline
    metrics the API route exposes (``create_copies_run`` in routes.py) so
    listings are symmetric regardless of which path registered the run.
    """
    summary: Dict[str, Any] = {"pillar": "copies"}
    if "passed" in scorecard:
        summary["passed"] = scorecard["passed"]
    fidelity = scorecard.get("fidelity") or {}
    privacy = scorecard.get("privacy") or {}
    utility = scorecard.get("utility") or {}
    if "overall_score" in fidelity:
        summary["fidelity_score"] = fidelity["overall_score"]
    if "overall_score" in privacy:
        summary["privacy_score"] = privacy["overall_score"]
    if "transfer_gap" in utility:
        summary["utility_transfer_gap"] = utility["transfer_gap"]
    return summary


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------


def register_copies_run(
    run_dir: Path | str,
    source_id: Optional[str] = None,
    n: Optional[int] = None,
    seed: Optional[int] = None,
    generator: Optional[str] = None,
    registry: Optional[RunRegistry] = None,
    db_path: Optional[str] = None,
    run_id: Optional[str] = None,
    write_artifact_json: bool = True,
) -> str:
    """Register a synthetic-copies run directory with the platform registry.

    Parameters
    ----------
    run_dir:
        Path to a run directory produced by ``python -m
        the_similarity.synthetic.cli`` (contains ``scorecard.json``,
        ``provenance.json``, etc.). May be relative or absolute.
    source_id / n / seed / generator:
        Optional overrides for the run's identity fields. When omitted we
        fall back to the values recorded in ``provenance.json``, which is
        the source of truth. Explicit arguments win so callers wrapping
        the CLI programmatically don't have to re-parse provenance.
    registry:
        Optional pre-opened :class:`RunRegistry`. When omitted we open one
        against ``db_path`` (or the default) and close it on exit.
    db_path:
        Optional SQLite path override used only when ``registry`` is None.
    run_id:
        Optional explicit run_id. Defaults to a fresh UUID4 hex. Passing
        an existing id triggers upsert.
    write_artifact_json:
        When True (default), also emit ``<run_dir>/artifact.json`` so the
        run directory is self-contained. Set False to leave the run dir
        untouched (e.g. read-only snapshots).

    Returns
    -------
    str
        The ``run_id`` written to the registry.

    Raises
    ------
    FileNotFoundError
        If ``run_dir`` does not exist. Missing scorecard.json /
        provenance.json are tolerated (returned as empty dicts) — that
        produces a thin summary but still indexes the run.
    """
    run_path = Path(run_dir).expanduser().resolve()
    if not run_path.exists():
        raise FileNotFoundError(f"run_dir does not exist: {run_path}")
    if not run_path.is_dir():
        raise FileNotFoundError(f"run_dir is not a directory: {run_path}")

    scorecard = _read_json_if_present(run_path / "scorecard.json")
    provenance_on_disk = _read_json_if_present(run_path / "provenance.json")

    # Identity: explicit args > provenance.json > reasonable defaults.
    # This lets a caller tag e.g. a synthetic run with a custom source_id
    # without needing to rewrite provenance.json.
    resolved_seed = seed if seed is not None else provenance_on_disk.get("seed")
    resolved_generator = generator or provenance_on_disk.get("generator_name")
    resolved_source = source_id or provenance_on_disk.get("source_id")

    # artifact_paths: only list files that actually exist. This keeps the
    # registry row honest — a consumer that follows a path will always
    # find a file there. Paths are relative to run_dir, matching the
    # contract in artifacts.py.
    artifact_paths: Dict[str, str] = {}
    for logical, filename in (
        ("real", "real.parquet"),
        ("synth", "synth.parquet"),
        ("scorecard", "scorecard.json"),
        ("provenance", "provenance.json"),
        ("report", "report.md"),
    ):
        if (run_path / filename).exists():
            artifact_paths[logical] = filename

    summary = _summary_from_scorecard(scorecard)
    # Mirror the row count / shape into summary when scorecard carries it
    # so listings show a useful size cue without loading parquet.
    ds = scorecard.get("dataset") or {}
    if "shape" in ds:
        summary["shape"] = ds["shape"]
    if n is not None:
        summary["n"] = n

    # provenance: copy what was on disk and augment with run_dir so the
    # FileResponse endpoint in routes.py (and any future file-streaming
    # surface) can resolve relative paths back to absolute ones.
    provenance: Dict[str, Any] = dict(provenance_on_disk)
    provenance["run_dir"] = str(run_path)
    if resolved_generator and "generator_name" not in provenance:
        provenance["generator_name"] = resolved_generator
    if resolved_source and "source_id" not in provenance:
        provenance["source_id"] = resolved_source

    config_payload: Dict[str, Any] = {
        "input_path": provenance_on_disk.get("source_id"),
        "generator": resolved_generator,
    }
    if n is not None:
        config_payload["n"] = n
    if resolved_seed is not None:
        config_payload["seed"] = resolved_seed

    artifact = RunArtifact(
        run_id=run_id or new_run_id(),
        kind=RunKind.COPIES,
        config=config_payload,
        seed=resolved_seed,
        artifact_paths=artifact_paths,
        summary=summary,
        provenance=provenance,
        created_at=iso_now(),
    )

    if write_artifact_json:
        # Emit the canonical artifact.json so the run_dir matches what the
        # API route produces. Safe to overwrite — artifact.json is derived
        # from the other files in the directory.
        try:
            write_artifact(run_path, artifact)
        except OSError:
            # Read-only filesystem / permissions: ignore so registration
            # itself still succeeds. The registry row is the primary output.
            pass

    if registry is not None:
        return registry.register(artifact)

    resolved_db: Path
    if db_path is not None:
        resolved_db = Path(db_path).expanduser()
    else:
        env_value = os.environ.get("THE_SIMILARITY_REGISTRY_DB")
        resolved_db = (
            Path(env_value).expanduser()
            if env_value
            else Path("~/.the_similarity/registry.db").expanduser()
        )

    with RunRegistry(resolved_db) as r:
        return r.register(artifact)


__all__ = ["register_copies_run"]
