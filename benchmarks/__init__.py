"""Forecasting benchmark harness for the_similarity engine.

This package provides a self-contained benchmark surface that compares the
analog-matching engine against simple but credible baselines (Seasonal
Naive, Matrix Profile) on standard public forecasting datasets (M4 Daily,
M4 Hourly, NN5 Daily, SPY daily close), plus a reporting layer that joins
our numbers with externally-published reference numbers (e.g. Chronos
paper) into a single Markdown comparison.

Design rules - DO NOT relax without explicit user sign-off:
- All systems run with their library DEFAULT configuration. The whole point
  of this harness is to give an honest baseline reading; per-system tuning
  here would let us cherry-pick a winner. Tuning belongs in a separate,
  clearly labelled experiment.
- Output is one JSONL line per (dataset, series_id, system, horizon) so the
  reporting layer can join our numbers with externally-published numbers
  without coupling us to their tooling.
- Resume support is non-negotiable: the runner walks a large Cartesian
  sweep that the user interrupts repeatedly while iterating.

Public surface:
    - ``benchmarks.core`` - Dataset / Forecast / Result / System dataclasses
      and Protocol definitions. The shared schema between runner and report.
    - ``benchmarks.chronos_published`` - verbatim, source-cited Chronos
      paper MASE numbers used as the neural-baseline reference row.
    - ``benchmarks.report`` - JSONL -> Markdown comparison generator
      (CLI + library function).

Why a JSONL handoff between runner and report?
    Decouples the (slow, library-heavy) runner from the (fast, pure) report
    builder. Anyone can re-render the report by replaying the JSONL, and
    the report tests can fabricate synthetic JSONL without touching the
    runner at all.
"""

from __future__ import annotations

from benchmarks.core import Dataset, Forecast, Result, System

__all__ = ["Dataset", "Forecast", "Result", "System"]
