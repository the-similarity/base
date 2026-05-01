"""Benchmark harness — reporting layer.

This package hosts the comparison + reporting layer for the cross-system
forecasting benchmark. The runner / loaders / system adapters live next to
this module and are owned by a parallel agent; the two pieces communicate
exclusively through the JSONL artifact at ``benchmarks/results/raw.jsonl``.

Public surface (reporting only):
    - ``benchmarks.chronos_published`` — verbatim, source-cited Chronos
      paper MASE numbers used as the neural-baseline reference row.
    - ``benchmarks.report``           — JSONL → Markdown comparison
      generator (CLI + library function).

Why a JSONL handoff?
    Decouples the (slow, GPU-flavoured) runner from the (fast, pure)
    report builder. Anyone can re-render the report by replaying the
    JSONL, and the report tests can fabricate synthetic JSONL without
    touching the runner at all.
"""
