"""Event file I/O — load, save, and validate event datasets.

Supports two on-disk formats:

- **JSON** (default): A single object with ``"events"``, ``"name"``,
  ``"version"``, ``"provenance"`` keys. Matches the
  :meth:`EventSeries.to_dict` shape exactly. Used for benchmark
  fixtures and small curated datasets.
- **JSONL**: One JSON object per line, each matching the
  :meth:`Event.to_dict` shape. Used for streaming / append-only
  ingestion pipelines. When reading JSONL, the returned
  :class:`EventSeries` has ``name`` derived from the filename and
  empty ``provenance``.

Validation
----------
:func:`validate_events` performs advisory checks and returns a list of
human-readable warning strings. It does NOT raise — callers decide
whether warnings are fatal. Checks include:

- Missing required fields (``event_id``, ``timestamp``, ``event_type``,
  ``title``).
- Timestamps that fail ISO-8601 parsing.
- Future timestamps (> today + 1 day tolerance).
- Duplicate ``event_id`` values within the series.
- Empty ``events`` list.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

from the_similarity.events.contracts import Event, EventSeries


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def load_events(path: Union[str, Path]) -> EventSeries:
    """Load an :class:`EventSeries` from a JSON or JSONL file.

    Format detection is based on file extension:
    - ``.json`` -> full EventSeries JSON object.
    - ``.jsonl`` -> one Event dict per line.

    Parameters
    ----------
    path:
        Path to the events file. Must exist and be readable.

    Returns
    -------
    EventSeries
        Deserialized event series.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    json.JSONDecodeError
        If the file contains malformed JSON.
    KeyError
        If required fields are missing from the JSON structure.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Events file not found: {p}")

    text = p.read_text(encoding="utf-8")

    if p.suffix == ".jsonl":
        # JSONL: one Event dict per line; blank lines are skipped.
        events: List[Event] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            events.append(Event.from_dict(json.loads(stripped)))
        return EventSeries(
            events=events,
            name=p.stem,
            version="1.0.0",
            provenance={"source_file": str(p)},
        )

    # Default: full JSON object matching EventSeries.to_dict() shape.
    data: Dict[str, Any] = json.loads(text)
    return EventSeries.from_dict(data)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_events(series: EventSeries, path: Union[str, Path]) -> Path:
    """Write an :class:`EventSeries` to a JSON file (pretty-printed).

    Creates parent directories if they don't exist. The output matches
    the :meth:`EventSeries.to_dict` shape exactly.

    Parameters
    ----------
    series:
        The event series to serialize.
    path:
        Output file path. Parent directories are created if missing.

    Returns
    -------
    Path
        Absolute path of the written file.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(series.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return p.resolve()


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

# Required fields on every Event dict. These map 1:1 to the required
# positional args of the Event dataclass constructor.
_REQUIRED_FIELDS = ("event_id", "timestamp", "event_type", "title")


def validate_events(series: EventSeries) -> List[str]:
    """Run advisory validation checks on an :class:`EventSeries`.

    Returns a list of human-readable warning strings. An empty list
    means the series passed all checks. Warnings are informational —
    the caller decides whether to treat them as errors.

    Checks performed
    ----------------
    1. Empty events list.
    2. Per-event missing required fields.
    3. Per-event timestamp parse failures (ISO-8601).
    4. Per-event future timestamps (> today + 1 day).
    5. Duplicate event_id values across the series.
    """
    warnings: List[str] = []

    if not series.events:
        warnings.append("EventSeries contains no events.")
        return warnings

    seen_ids: Dict[str, int] = {}
    # One-day tolerance for "future" check — accounts for timezone
    # differences and events announced after market close.
    future_cutoff = datetime.now(timezone.utc) + timedelta(days=1)

    for idx, event in enumerate(series.events):
        prefix = f"Event[{idx}] (id={event.event_id!r})"

        # Check required fields by inspecting the actual attribute values.
        # Since Event is constructed via from_dict, missing required fields
        # would have already raised KeyError — but we also catch empty
        # strings as a softer warning.
        for field_name in _REQUIRED_FIELDS:
            val = getattr(event, field_name, None)
            if not val:
                warnings.append(f"{prefix}: missing or empty '{field_name}'.")

        # Timestamp parsing check.
        if event.timestamp:
            try:
                # Python 3.11+ fromisoformat handles timezone suffixes.
                parsed = datetime.fromisoformat(event.timestamp)
                # Make timezone-aware for comparison if naive.
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed > future_cutoff:
                    warnings.append(
                        f"{prefix}: timestamp '{event.timestamp}' is in the future."
                    )
            except ValueError:
                warnings.append(
                    f"{prefix}: timestamp '{event.timestamp}' is not valid ISO-8601."
                )

        # Duplicate ID tracking.
        if event.event_id in seen_ids:
            first_idx = seen_ids[event.event_id]
            warnings.append(
                f"{prefix}: duplicate event_id (first seen at index {first_idx})."
            )
        else:
            seen_ids[event.event_id] = idx

    return warnings


__all__ = [
    "load_events",
    "save_events",
    "validate_events",
]
