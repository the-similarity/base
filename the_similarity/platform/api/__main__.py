"""Package entrypoint — ``python -m the_similarity.platform.api``.

Thin shim: parses argv, resolves host/port, and launches uvicorn against
the module-level ``app`` instance. All logic lives in :mod:`main` so this
file stays trivially forwardable; keeping it this terse avoids the
"python -m" path diverging from the app factory the tests exercise.
"""

from __future__ import annotations

from the_similarity.platform.api.main import main

if __name__ == "__main__":  # pragma: no cover - thin wrapper
    main()
