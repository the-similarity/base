"""Shared autoresearch infrastructure (``research/autoresearch/core``).

This package is the canonical home for the autoresearch standardization
layer used by every lane (retrieval-bench, projector-v2, Phase 2
foundation bench, future synthetic-data lane, JEPA lane). It centralizes:

1. :mod:`ledger`           — canonical append-only JSONL schema and query helpers
2. :mod:`metrics_delta`    — baseline/candidate delta computation with
                             paired-bootstrap significance annotation
3. :mod:`gates`            — declarative keep/discard gate evaluation
4. :mod:`report`           — canonical Markdown report renderer
5. :mod:`rejection_log`    — append-only record of killed directions with
                             revisit conditions

Lanes import these modules directly instead of duplicating the ledger /
report / gate logic per lane. The per-lane code stays responsible for
producing the lane-specific raw metrics; this package standardizes the
*contract* so downstream tooling (dashboards, discovery agents,
decision auditors) can treat every lane uniformly.

Invariants:
    * The ledger is append-only. No helper in this package rewrites
      existing rows; a wrong row must be corrected by appending a
      superseding row (carrying ``supersedes`` in ``notes``).
    * The report renderer is a pure function of its inputs so snapshot
      tests stay deterministic.
    * The rejection log is separately persisted so "already-killed"
      ideas are mechanically discoverable by a future agent via
      :func:`rejection_log.is_rejected`.
"""

from __future__ import annotations
