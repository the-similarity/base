"""Thin adapters that wire existing pillar outputs into the platform registry.

Each adapter reads the on-disk (or in-memory) artifacts that a pillar already
produces, builds a :class:`~the_similarity.platform.artifacts.RunArtifact` that
conforms to the unified contract, and registers it in the shared
:class:`~the_similarity.platform.registry.RunRegistry`.

Adapters are deliberately **one-way** — they read pillar outputs and write
registry rows, never the other direction. The adapter layer is therefore safe
to call from inside a pillar's own pipeline as a best-effort post-run step:
registration failure should never abort the underlying run.

Modules
-------
- :mod:`the_similarity.platform.adapters.finance` — wraps
  :func:`the_similarity.api.backtest` outputs (hit_rate / calibration / CRPS).
- :mod:`the_similarity.platform.adapters.copies` — wraps the synthetic CLI's
  per-run directory (scorecard.json, provenance.json, parquet files, report.md).

The worlds adapter is the TypeScript-side counterpart; see
``the-similarity-fractal/src/platform/registry-client.js``. We keep the Python
adapters here and the JS adapter in the fractal package so each side depends
only on its native language's stdlib.
"""
from __future__ import annotations

from the_similarity.platform.adapters.finance import register_backtest_run
from the_similarity.platform.adapters.copies import register_copies_run

__all__ = [
    "register_backtest_run",
    "register_copies_run",
]
