"""JSON persistence for prediction market question sets.

Provides two functions:
- :func:`load_questions` — read a :class:`QuestionSet` from a JSON file.
- :func:`save_questions` — write a :class:`QuestionSet` to a JSON file.

File format
-----------
The JSON file is a single object matching :meth:`QuestionSet.to_dict`:
``{"questions": [...], "name": "...", "version": "..."}``.  Files are
written with ``indent=2`` for human readability and diffability; read
tolerates any valid JSON (compact or pretty).

Path handling
-------------
Both functions accept ``str`` or ``pathlib.Path``. Parent directories are
created automatically on write (``mkdir -p`` semantics) to avoid forcing
callers to pre-create directory trees.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from the_similarity.events.markets import QuestionSet


def load_questions(path: Union[str, Path]) -> QuestionSet:
    """Load a :class:`QuestionSet` from a JSON file.

    Parameters
    ----------
    path:
        Path to the JSON file. Raises ``FileNotFoundError`` if missing,
        ``json.JSONDecodeError`` if malformed.

    Returns
    -------
    QuestionSet
        Fully hydrated question set with all nested dataclasses.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return QuestionSet.from_dict(data)


def save_questions(qs: QuestionSet, path: Union[str, Path]) -> None:
    """Write a :class:`QuestionSet` to a JSON file.

    Parameters
    ----------
    qs:
        The question set to serialize.
    path:
        Destination path. Parent directories are created if missing.

    Notes
    -----
    The file is written atomically: serialize to string first, then
    write in a single call. This avoids leaving a partial file on disk
    if the process is interrupted mid-write (the OS typically buffers
    small writes and flushes on close).
    """
    p = Path(path)
    # Create parent directories so callers don't need to mkdir first.
    p.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(qs.to_dict(), indent=2, ensure_ascii=False)
    with p.open("w", encoding="utf-8") as f:
        f.write(content)
        # Trailing newline for POSIX compliance (many tools expect it).
        f.write("\n")


__all__ = ["load_questions", "save_questions"]
