"""Worlds pillar -> platform registry adapter.

Reads the on-disk artifacts produced by the headless worlds runner
(``the-similarity-fractal/src/sim/headless/runner.js``) — a JSONL
telemetry file containing a provenance header line and a summary
footer line — and registers them as platform
:class:`~the_similarity.platform.artifacts.RunArtifact` entries with
``kind=RunKind.WORLDS``.

Also provides scenario preset registration from JSON files on disk,
plus a bulk ``sync_all_presets`` that scans a directory of scenario
JSONs and registers each one idempotently.

JSONL telemetry contract (headless runner output)
-------------------------------------------------
The headless runner emits a JSONL file with exactly two meaningful lines:

1. **Line 0 — provenance**: ``{"type": "provenance", "generator_name":
   "...", "version": "...", "seed": 42, "scenario_name": "...",
   "scenario": {...}, "params": {...}, "created_at": "..."}``

2. **Last line — summary**: ``{"type": "summary", "ticks": N,
   "alive": M, "dead": D, "avg_energy": ..., "duration_ms": ...}``

Between them are per-tick telemetry lines (``"type": "tick"``) that this
adapter ignores — it only needs the envelope lines to build a registry
row. Ticking detail is preserved as an artifact reference (the JSONL
path is stored in ``artifact_paths["telemetry"]``).

Scenario JSON contract
----------------------
Scenario files live under ``the-similarity-fractal/scenarios/`` and
follow the shape defined by ``small_village.json``:

.. code-block:: json

    {
        "name": "small_village",
        "description": "...",
        "seed": 42,
        "steps": 500,
        "world": {"size": 64, "initial_population": 20},
        "params": {...}
    }

The adapter extracts ``name`` as both ``scenario_id`` and display name
(unless overridden), derives the ``engine`` from the filename stem, and
stores the full JSON body in ``ScenarioSpec.params``.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from the_similarity.platform.artifacts import (
    RunArtifact,
    RunKind,
    iso_now,
    new_run_id,
)
from the_similarity.platform.contracts import ScenarioSpec
from the_similarity.platform.registry import RunRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSONL readers
# ---------------------------------------------------------------------------


def _read_jsonl_envelope(
    telemetry_path: Path,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Extract the provenance (first) and summary (last) lines from a JSONL file.

    Returns ``(provenance_dict, summary_dict)``. If the file is empty or
    has fewer than two lines, returns empty dicts for the missing parts so
    callers get a thin-but-valid registry row rather than a crash.

    Lines that fail JSON parsing are silently skipped — a truncated
    telemetry file from a crashed run should still be registerable
    (the summary will be empty but the provenance survives).
    """
    provenance: Dict[str, Any] = {}
    summary: Dict[str, Any] = {}

    if not telemetry_path.exists():
        return provenance, summary

    lines: List[str] = []
    with open(telemetry_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            stripped = raw_line.strip()
            if stripped:
                lines.append(stripped)

    if not lines:
        return provenance, summary

    # First line: provenance header.
    try:
        first = json.loads(lines[0])
        if first.get("type") == "provenance":
            provenance = first
    except json.JSONDecodeError:
        logger.warning("Failed to parse provenance line as JSON: %s", lines[0][:200])

    # Last line: summary footer. If the file has only one line and that
    # line is the provenance, summary stays empty (crash before tick 0).
    if len(lines) >= 2:
        try:
            last = json.loads(lines[-1])
            if last.get("type") == "summary":
                summary = last
        except json.JSONDecodeError:
            logger.warning("Failed to parse summary line as JSON: %s", lines[-1][:200])

    return provenance, summary


def _build_summary(summary_line: Dict[str, Any]) -> Dict[str, Any]:
    """Extract headline numbers from the summary line for the registry.

    Projects a subset of the raw summary into the shape the UI grids
    over. ``pillar`` is stamped so listings filter correctly without
    joining to the ``kind`` column.
    """
    out: Dict[str, Any] = {"pillar": "worlds"}
    for key in ("ticks", "alive", "dead", "avg_energy", "duration_ms"):
        if key in summary_line:
            out[key] = summary_line[key]
    return out


# ---------------------------------------------------------------------------
# Public adapter — world runs
# ---------------------------------------------------------------------------


def register_world_run(
    telemetry_path: str | Path,
    scenario_name: str,
    seed: Optional[int] = None,
    registry: Optional[RunRegistry] = None,
    db_path: Optional[str] = None,
    run_id: Optional[str] = None,
) -> str:
    """Register a worlds simulation run from its JSONL telemetry file.

    Reads the provenance header and summary footer from ``telemetry_path``,
    builds a :class:`RunArtifact` with ``kind=RunKind.WORLDS``, and
    registers it in the platform registry.

    Parameters
    ----------
    telemetry_path:
        Path to the headless runner's JSONL output file. Must exist.
    scenario_name:
        Human-readable scenario name (e.g. ``"small_village"``). Stored
        in ``config["scenario_name"]`` and surfaced in listings.
    seed:
        Optional RNG seed. When ``None``, the adapter falls back to the
        seed recorded in the provenance header line (if any).
    registry:
        Optional pre-opened :class:`RunRegistry`. When omitted, one is
        opened against ``db_path`` (or the default) and closed on exit.
    db_path:
        Optional SQLite path override, used only when ``registry`` is
        ``None``.
    run_id:
        Optional explicit run_id. Defaults to a fresh UUID4 hex.

    Returns
    -------
    str
        The ``run_id`` written to the registry.

    Raises
    ------
    FileNotFoundError
        If ``telemetry_path`` does not exist on disk.
    """
    telem_path = Path(telemetry_path).expanduser().resolve()
    if not telem_path.exists():
        raise FileNotFoundError(f"telemetry file not found: {telem_path}")

    provenance_line, summary_line = _read_jsonl_envelope(telem_path)

    # Resolve seed: explicit arg > provenance header > None.
    resolved_seed = seed if seed is not None else provenance_line.get("seed")

    # Build the registry summary from the summary footer line.
    summary = _build_summary(summary_line)

    # Config captures the run inputs so the artifact is self-describing.
    config: Dict[str, Any] = {
        "scenario_name": scenario_name,
    }
    # Carry over scenario params from provenance if present.
    if "scenario" in provenance_line:
        config["scenario"] = provenance_line["scenario"]
    if "params" in provenance_line:
        config["params"] = provenance_line["params"]

    # Provenance: pass through the raw provenance line and augment with
    # the telemetry file path for traceability.
    provenance: Dict[str, Any] = dict(provenance_line)
    provenance["telemetry_path"] = str(telem_path)

    # Artifact paths: point to the telemetry file (relative name only
    # for portability — the full path lives in provenance).
    artifact_paths: Dict[str, str] = {
        "telemetry": telem_path.name,
    }

    artifact = RunArtifact(
        run_id=run_id or new_run_id(),
        kind=RunKind.WORLDS,
        config=config,
        seed=resolved_seed,
        artifact_paths=artifact_paths,
        summary=summary,
        provenance=provenance,
        created_at=iso_now(),
    )

    if registry is not None:
        return registry.register(artifact)

    # Self-managed registry path: open, register, close.
    resolved_db = _resolve_db(db_path)
    with RunRegistry(resolved_db) as r:
        return r.register(artifact)


# ---------------------------------------------------------------------------
# Public adapter — scenario presets
# ---------------------------------------------------------------------------


def register_scenario_preset(
    scenario_json_path: str | Path,
    registry: Optional[RunRegistry] = None,
    db_path: Optional[str] = None,
) -> str:
    """Register a scenario JSON file as a :class:`ScenarioSpec` in the registry.

    Reads the JSON file, derives ``scenario_id`` from the ``name`` field
    (or the filename stem if ``name`` is missing), and creates a
    :class:`ScenarioSpec` row.

    Parameters
    ----------
    scenario_json_path:
        Path to a scenario JSON file (e.g.
        ``the-similarity-fractal/scenarios/small_village.json``).
    registry:
        Optional pre-opened :class:`RunRegistry`.
    db_path:
        Optional SQLite path override, used only when ``registry`` is
        ``None``.

    Returns
    -------
    str
        The ``scenario_id`` written to the registry.

    Raises
    ------
    FileNotFoundError
        If ``scenario_json_path`` does not exist.
    """
    path = Path(scenario_json_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"scenario file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    # Derive identity fields from the JSON body, falling back to the
    # filename stem when the body lacks explicit values.
    name = raw.get("name") or path.stem
    scenario_id = name  # Use the name as the stable ID.
    # Engine defaults to the scenario name — the worlds runner uses it
    # to dispatch to the correct simulation module.
    engine = raw.get("engine") or name
    # Version: scenarios rarely carry an explicit version; default to
    # "v1" so the registry row is always populated.
    version = raw.get("version") or "v1"

    # The full JSON body goes into params so no information is lost.
    # ``world``, ``params``, ``steps``, ``seed`` keys are all preserved.
    params = {k: v for k, v in raw.items() if k not in ("name", "engine", "version")}

    metadata: Dict[str, Any] = {}
    if "description" in raw:
        metadata["description"] = raw["description"]
    metadata["source_file"] = str(path)

    spec = ScenarioSpec(
        scenario_id=scenario_id,
        name=name,
        version=version,
        engine=engine,
        params=params,
        metadata=metadata,
    )

    if registry is not None:
        return registry.register_scenario(spec)

    resolved_db = _resolve_db(db_path)
    with RunRegistry(resolved_db) as r:
        return r.register_scenario(spec)


def sync_all_presets(
    scenarios_dir: str | Path,
    registry: Optional[RunRegistry] = None,
    db_path: Optional[str] = None,
) -> List[str]:
    """Scan a directory of scenario JSONs and register each as a ScenarioSpec.

    Idempotent — the registry uses upsert semantics, so re-syncing the
    same directory is a no-op for unchanged scenarios and an update for
    modified ones. Only ``.json`` files in the top level of
    ``scenarios_dir`` are processed (no recursive descent).

    Parameters
    ----------
    scenarios_dir:
        Path to the directory containing scenario JSON files.
    registry:
        Optional pre-opened :class:`RunRegistry`.
    db_path:
        Optional SQLite path override.

    Returns
    -------
    List[str]
        The list of ``scenario_id`` values that were registered/updated.

    Raises
    ------
    FileNotFoundError
        If ``scenarios_dir`` does not exist or is not a directory.
    """
    dir_path = Path(scenarios_dir).expanduser().resolve()
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"scenarios directory not found: {dir_path}")

    # Collect all .json files in the directory (non-recursive).
    json_files = sorted(dir_path.glob("*.json"))

    if not json_files:
        return []

    # Open a single registry connection for the batch if none was provided.
    if registry is not None:
        return [
            register_scenario_preset(f, registry=registry) for f in json_files
        ]

    resolved_db = _resolve_db(db_path)
    with RunRegistry(resolved_db) as r:
        return [register_scenario_preset(f, registry=r) for f in json_files]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_db(db_path: Optional[str]) -> Path:
    """Resolve the registry DB path using the standard precedence rules.

    1. Explicit ``db_path`` argument.
    2. ``THE_SIMILARITY_REGISTRY_DB`` environment variable.
    3. Default ``~/.the_similarity/registry.db``.
    """
    if db_path is not None:
        return Path(db_path).expanduser()
    env_value = os.environ.get("THE_SIMILARITY_REGISTRY_DB")
    if env_value:
        return Path(env_value).expanduser()
    return Path("~/.the_similarity/registry.db").expanduser()


__all__ = [
    "register_world_run",
    "register_scenario_preset",
    "sync_all_presets",
]
