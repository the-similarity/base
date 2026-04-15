"""Canonical autoresearch ledger schema and helpers.

The ledger (``progress/autoresearch/experiments.jsonl``) is the
*append-only* source of truth for every autoresearch run the project has
ever executed. Every lane writes one row per (run, variant/arm). The
schema MUST match ``research/autoresearch/ledger/experiment-ledger.schema.json``
plus the canonical extensions added here.

This module centralizes:

1. :class:`LedgerEntry` — a dataclass mirror of the schema so lanes get
   IDE autocomplete and type hints instead of raw ``dict`` passing.
2. :func:`append_entry` — the canonical append helper.
3. :func:`iter_entries`, :func:`entries_for_lane`, :func:`latest_run`,
   :func:`compare_runs` — query helpers a reviewer / discovery agent
   uses to answer "what did we try, what did we decide, and what
   changed since last time?".

Lifecycle and invariants
------------------------
* JSONL, one object per line, UTF-8.
* Append-only. If a ledger row was wrong, write a new row with
  ``notes`` carrying ``{"supersedes": "<old_run_id>", ...}`` — this
  keeps history auditable.
* ``run_id`` must be unique across rows written by a single lane. Cross-
  lane duplicates are legal (the tuple ``(lane_id, run_id)`` is the
  logical key) but strongly discouraged; prefer lane-prefixed IDs.
* ``status`` ∈ ``{"ok", "discarded", "crash", "aborted"}``. The status
  carries the *run's operational outcome*; ``decision`` carries the
  *scientific verdict*.
* ``decision`` ∈ ``{"keep", "discard", "retry", "abort", "baseline"}``.
  ``"baseline"`` is an extension used by sweeps where the row records a
  reference run with no delta to report.

Relation to per-lane ledgers
----------------------------
The legacy ``research/autoresearch/retrieval_bench/ledger.py`` keeps
existing behaviour but is now a thin wrapper over this module.
Per-lane builders should translate *lane-specific* fields into the
canonical ones and then call :func:`append_entry`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical relative path of the append-only ledger. Every lane writes
#: here unless a test overrides it with its own ``tmp_path``. We keep the
#: constant exported so tooling (dashboards, CLI auditors) has one place
#: to import the path from.
CANONICAL_LEDGER_PATH = Path("progress/autoresearch/experiments.jsonl")

#: Allowed values for the ``status`` field. Kept aligned with the JSON
#: schema; any lane that writes a value outside this set will not
#: round-trip through the schema validator.
ALLOWED_STATUSES: frozenset[str] = frozenset({"ok", "discarded", "crash", "aborted"})

#: Allowed values for the ``decision`` field. ``"baseline"`` is not in
#: the JSON schema enum (which predates the canonical layer); lanes
#: emitting ``"baseline"`` should be aware that schema-strict validators
#: may flag it until the schema is extended.
ALLOWED_DECISIONS: frozenset[str] = frozenset(
    {"keep", "discard", "retry", "abort", "baseline"}
)


# ---------------------------------------------------------------------------
# Dataclass mirror of the schema
# ---------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    """Canonical ledger entry mirroring the JSON schema.

    Every lane should build one of these per run (or one per variant in
    a sweep) and pass it to :func:`append_entry`. The dataclass is
    intentionally permissive on metric dicts — schemas downstream vary
    per lane — but rigid on the identifying fields.

    Invariants
    ----------
    * ``run_id`` uniquely identifies this row within the lane. Prefer
      ``"<lane_id>-<variant>-<ISO timestamp>"`` so ordering by
      ``run_id`` within a lane yields chronological order.
    * ``metrics_before`` is the baseline/prior metrics snapshot.
      ``metrics_after`` is the candidate/post snapshot. For a pure
      baseline row the two dicts are identical.
    * All numeric metric values should be JSON-serialisable (floats, not
      numpy scalars). Callers cast explicitly.
    """

    run_id: str
    timestamp: str
    benchmark_id: str
    lane_id: str
    status: str
    decision: str
    summary: str
    metrics_before: dict[str, Any]
    metrics_after: dict[str, Any]
    slices: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    branch: str | None = None
    commit_before: str | None = None
    commit_after: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict matching the ledger schema.

        ``None`` fields (``branch``, ``commit_before``, ``commit_after``)
        are omitted unless explicitly set. This keeps old readers that
        don't know about the optional fields happy.
        """
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "benchmark_id": self.benchmark_id,
            "lane_id": self.lane_id,
            "status": self.status,
            "decision": self.decision,
            "summary": self.summary,
            "slices": list(self.slices),
            "artifacts": list(self.artifacts),
            "metrics_before": dict(self.metrics_before),
            "metrics_after": dict(self.metrics_after),
            "regressions": list(self.regressions),
            "notes": self.notes,
        }
        if self.branch is not None:
            payload["branch"] = self.branch
        if self.commit_before is not None:
            payload["commit_before"] = self.commit_before
        if self.commit_after is not None:
            payload["commit_after"] = self.commit_after
        return payload

    def validate(self) -> None:
        """Raise ``ValueError`` if any field violates canonical invariants.

        Cheap structural check only — we do NOT reimplement the full
        JSON schema here. Callers that need strict schema compliance
        should round-trip through ``jsonschema`` against
        ``research/autoresearch/ledger/experiment-ledger.schema.json``.
        """
        if not self.run_id:
            raise ValueError("LedgerEntry.run_id must be non-empty")
        if not self.lane_id:
            raise ValueError("LedgerEntry.lane_id must be non-empty")
        if not self.benchmark_id:
            raise ValueError("LedgerEntry.benchmark_id must be non-empty")
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(
                f"LedgerEntry.status={self.status!r} not in {sorted(ALLOWED_STATUSES)}"
            )
        if self.decision not in ALLOWED_DECISIONS:
            raise ValueError(
                f"LedgerEntry.decision={self.decision!r} not in {sorted(ALLOWED_DECISIONS)}"
            )
        if not isinstance(self.metrics_before, dict):
            raise ValueError("LedgerEntry.metrics_before must be a dict")
        if not isinstance(self.metrics_after, dict):
            raise ValueError("LedgerEntry.metrics_after must be a dict")


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def utc_timestamp() -> str:
    """Return the current UTC timestamp in canonical ISO-8601 form.

    All ledger rows share one format — ``YYYY-MM-DDTHH:MM:SSZ`` — so
    lexicographic sort equals chronological sort without a timezone
    parser in the critical path.
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append_entry(
    entry: LedgerEntry | dict[str, Any],
    ledger_path: str | Path = CANONICAL_LEDGER_PATH,
) -> Path:
    """Append one entry as a JSONL line to the ledger.

    Creates the parent directory and file if absent. Always writes a
    trailing newline so future appends stay on their own line even if
    the file was opened with an editor that dropped one.

    ``entry`` accepts either a :class:`LedgerEntry` (preferred — it
    runs :meth:`LedgerEntry.validate` first) or a raw dict (for
    backward compat with the legacy per-lane builders that build
    dictionaries directly).
    """
    if isinstance(entry, LedgerEntry):
        entry.validate()
        payload = entry.to_dict()
    else:
        payload = dict(entry)

    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # ``sort_keys=True`` stabilises the byte-level output which helps
    # diff tools compare runs and prevents key-ordering noise on merges.
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


# ---------------------------------------------------------------------------
# Readers / queries
# ---------------------------------------------------------------------------


def iter_entries(
    ledger_path: str | Path = CANONICAL_LEDGER_PATH,
) -> Iterator[dict[str, Any]]:
    """Yield every entry in the ledger as a dict, in file order.

    Malformed lines are skipped silently — a lane that crashes halfway
    through writing a line should not cripple downstream tooling. Callers
    that need strict parsing should consume via ``json.loads`` directly.
    """
    path = Path(ledger_path)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def entries_for_lane(
    lane_id: str,
    ledger_path: str | Path = CANONICAL_LEDGER_PATH,
) -> list[dict[str, Any]]:
    """Return all entries for one ``lane_id`` in file order."""
    return [e for e in iter_entries(ledger_path) if e.get("lane_id") == lane_id]


def latest_run(
    lane_id: str,
    ledger_path: str | Path = CANONICAL_LEDGER_PATH,
) -> dict[str, Any] | None:
    """Return the most recent (by ``timestamp``) entry for a lane, or None."""
    rows = entries_for_lane(lane_id, ledger_path)
    if not rows:
        return None
    # Timestamp format is sort-safe (ISO-8601 UTC) so string max == latest.
    return max(rows, key=lambda e: str(e.get("timestamp", "")))


def compare_runs(
    run_id_a: str,
    run_id_b: str,
    ledger_path: str | Path = CANONICAL_LEDGER_PATH,
) -> dict[str, Any]:
    """Return a structured diff between two named runs.

    Missing runs raise ``LookupError``. Returned dict:

    .. code-block:: python

        {
            "run_a": <entry_a>,
            "run_b": <entry_b>,
            "metric_deltas": {metric_name: (value_a, value_b, delta)},
        }
    """
    a: dict[str, Any] | None = None
    b: dict[str, Any] | None = None
    for row in iter_entries(ledger_path):
        if row.get("run_id") == run_id_a:
            a = row
        if row.get("run_id") == run_id_b:
            b = row

    if a is None:
        raise LookupError(f"run_id not found: {run_id_a}")
    if b is None:
        raise LookupError(f"run_id not found: {run_id_b}")

    # Compare ``metrics_after`` since that's the post-change snapshot
    # both lanes publish. We union key sets to surface metrics that
    # disappeared or appeared between runs.
    metrics_a = a.get("metrics_after", {}) or {}
    metrics_b = b.get("metrics_after", {}) or {}
    metric_deltas: dict[str, tuple[Any, Any, float | None]] = {}
    for key in sorted(set(metrics_a) | set(metrics_b)):
        va = metrics_a.get(key)
        vb = metrics_b.get(key)
        try:
            delta: float | None = float(vb) - float(va)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            delta = None
        metric_deltas[key] = (va, vb, delta)

    return {"run_a": a, "run_b": b, "metric_deltas": metric_deltas}


def append_entries(
    entries: Iterable[LedgerEntry | dict[str, Any]],
    ledger_path: str | Path = CANONICAL_LEDGER_PATH,
) -> Path:
    """Batch-append helper — convenience wrapper around :func:`append_entry`.

    Entries are written in iteration order. The function does NOT open
    the file once for all entries because concurrent writers (two lanes
    running in parallel) could then interleave bytes mid-line. The
    per-entry append pattern is slower but safe on POSIX append semantics.
    """
    path = Path(ledger_path)
    for entry in entries:
        append_entry(entry, path)
    return path


__all__ = [
    "CANONICAL_LEDGER_PATH",
    "ALLOWED_STATUSES",
    "ALLOWED_DECISIONS",
    "LedgerEntry",
    "utc_timestamp",
    "append_entry",
    "append_entries",
    "iter_entries",
    "entries_for_lane",
    "latest_run",
    "compare_runs",
]
