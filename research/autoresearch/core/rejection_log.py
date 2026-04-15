"""Rejection log — mechanical memory of killed directions.

Motivation
----------
Autoresearch generates ideas faster than humans can remember. An agent
six months from now will naturally re-propose a direction that was
already tested and discarded — unless there is a machine-readable log
it can consult before running the sweep.

This module owns that log. It lives at
``progress/autoresearch/rejections.jsonl`` (one JSON object per line)
and is append-only, just like the experiment ledger.

Required fields per entry
-------------------------
* ``direction_id``: short snake_case identifier, unique per direction
  (e.g. ``"tier2_as_default"``, ``"regime_aware_widening"``). Used by
  :func:`is_rejected` for mechanical lookup.
* ``lane_id``: which lane killed it.
* ``summary``: one paragraph — what was tried, what happened, why it
  was killed.
* ``killed_at``: ISO-8601 UTC timestamp.
* ``evidence_refs``: list of ``run_id`` strings from the ledger that
  document the kill. A future agent can cross-ref these to the ledger
  to read the raw metrics.
* ``revisit_conditions``: list of short declarative statements
  describing under what circumstances the direction is worth
  re-testing. Examples:
     * "On a shift-rich slice (≥3 regime changes in window)"
     * "With multipliers fit from residual study rather than constants"
     * "After Tier 2 runtime drops below 5x baseline"
  These statements are what make the log actionable — an agent
  surveying the log can mechanically decide "has the world changed
  enough to re-test?".

Why not reuse the ledger?
-------------------------
The ledger is per-run and granular. The rejection log is coarser —
one entry per *direction*, not per run. A direction may span multiple
lanes and multiple runs. Keeping them separate means a discovery
agent can do a cheap "is this already a known dead end?" check
without scanning the full run history.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


#: Canonical rejection log path relative to repo root.
CANONICAL_REJECTION_PATH = Path("progress/autoresearch/rejections.jsonl")


@dataclass
class RejectionEntry:
    """One killed direction with revisit conditions.

    See the module docstring for field semantics.

    ``extra`` is a free-form dict for lane-specific metadata that
    does not belong in the standardised fields (e.g. dataset snapshot
    hashes, variant parameters). Downstream tooling must not rely on
    it without a schema check.
    """

    direction_id: str
    lane_id: str
    summary: str
    killed_at: str
    evidence_refs: list[str]
    revisit_conditions: list[str]
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        payload: dict[str, Any] = {
            "direction_id": self.direction_id,
            "lane_id": self.lane_id,
            "summary": self.summary,
            "killed_at": self.killed_at,
            "evidence_refs": list(self.evidence_refs),
            "revisit_conditions": list(self.revisit_conditions),
        }
        if self.extra:
            payload["extra"] = dict(self.extra)
        return payload

    def validate(self) -> None:
        """Raise ``ValueError`` if any canonical invariant is broken.

        The structural checks are deliberately strict on list-valued
        fields: a str slipping in where a list is expected would silently
        pass JSON round-trip but break :func:`is_rejected` and any
        agent iterating ``revisit_conditions``.
        """
        if not self.direction_id or not isinstance(self.direction_id, str):
            raise ValueError("RejectionEntry.direction_id must be a non-empty str")
        if not self.lane_id:
            raise ValueError("RejectionEntry.lane_id must be non-empty")
        if not isinstance(self.evidence_refs, list):
            raise ValueError("RejectionEntry.evidence_refs must be a list of run_id strings")
        if not isinstance(self.revisit_conditions, list):
            raise ValueError(
                "RejectionEntry.revisit_conditions must be a list of short "
                "declarative statements (strings)"
            )
        for s in self.revisit_conditions:
            if not isinstance(s, str):
                raise ValueError("revisit_conditions entries must be strings")
        if not self.killed_at:
            raise ValueError("RejectionEntry.killed_at must be a non-empty ISO timestamp")


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def append_rejection(
    entry: RejectionEntry | dict[str, Any],
    log_path: str | Path = CANONICAL_REJECTION_PATH,
) -> Path:
    """Append a rejection entry to the log.

    Accepts either a :class:`RejectionEntry` (validated first) or a
    raw dict (trust-the-caller path, still written as JSONL).
    """
    if isinstance(entry, RejectionEntry):
        entry.validate()
        payload = entry.to_dict()
    else:
        payload = dict(entry)

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


# ---------------------------------------------------------------------------
# Readers / queries
# ---------------------------------------------------------------------------


def iter_rejections(
    log_path: str | Path = CANONICAL_REJECTION_PATH,
) -> Iterator[dict[str, Any]]:
    """Yield every rejection entry as a dict in file order.

    Silently skips malformed lines — same trade-off as
    :func:`research.autoresearch.core.ledger.iter_entries`.
    """
    path = Path(log_path)
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


def is_rejected(
    direction_id: str,
    log_path: str | Path = CANONICAL_REJECTION_PATH,
) -> bool:
    """Fast lookup — return True if ``direction_id`` has any kill record."""
    for row in iter_rejections(log_path):
        if row.get("direction_id") == direction_id:
            return True
    return False


def get_rejection(
    direction_id: str,
    log_path: str | Path = CANONICAL_REJECTION_PATH,
) -> dict[str, Any] | None:
    """Return the most recent rejection entry for ``direction_id`` or None.

    Multiple entries for the same ``direction_id`` are allowed — e.g. if
    a direction was killed, revisited, and killed again with new
    evidence. The most recent (by file order) wins.
    """
    latest: dict[str, Any] | None = None
    for row in iter_rejections(log_path):
        if row.get("direction_id") == direction_id:
            latest = row
    return latest


def revisit_ready(
    direction_id: str,
    current_state: dict[str, Any],
    log_path: str | Path = CANONICAL_REJECTION_PATH,
) -> tuple[bool, list[str]]:
    """Mechanical "should we re-test this direction?" helper.

    ``current_state`` is a free-form dict a caller builds describing
    the current world. The function returns ``(ready, unmet)`` where
    ``ready`` is True iff **all** revisit conditions can be matched
    against ``current_state`` via substring keyword matching.

    This is intentionally simple — it is a heuristic, not a logic
    solver. The value is that agents can short-circuit "already killed
    and nothing has changed" cases without reading prose.

    Callers wanting sophisticated matching should iterate the entry's
    ``revisit_conditions`` themselves.
    """
    entry = get_rejection(direction_id, log_path)
    if entry is None:
        return True, []  # never rejected -> ready to try
    conditions = entry.get("revisit_conditions", [])
    unmet: list[str] = []
    state_blob = " ".join(str(v) for v in current_state.values()).lower()
    for cond in conditions:
        # Heuristic: at least one non-trivial word in the condition
        # must appear (case-insensitive) in the state blob.
        words = [
            w
            for w in cond.lower().replace(",", " ").split()
            if len(w) >= 4 and w.isalpha()
        ]
        if not any(w in state_blob for w in words):
            unmet.append(cond)
    return (len(unmet) == 0), unmet


__all__ = [
    "CANONICAL_REJECTION_PATH",
    "RejectionEntry",
    "append_rejection",
    "iter_rejections",
    "is_rejected",
    "get_rejection",
    "revisit_ready",
]
