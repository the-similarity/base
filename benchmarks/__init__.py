"""Forecasting benchmark harness for the_similarity engine.

This package provides a self-contained benchmark surface that compares the
analog-matching engine against simple but credible baselines (Seasonal
Naive, Matrix Profile) on standard public forecasting datasets (M4 Daily,
M4 Hourly, NN5 Daily, SPY daily close).

Design rules — DO NOT relax without explicit user sign-off:
- All systems run with their library DEFAULT configuration. The whole point
  of this harness is to give an honest baseline reading; per-system tuning
  here would let us cherry-pick a winner. Tuning belongs in a separate,
  clearly labelled experiment.
- Output is one JSONL line per (dataset, series_id, system, horizon) so a
  parallel report agent can join our numbers with externally-published
  numbers (e.g. Chronos paper) without coupling us to their tooling.
- Resume support is non-negotiable: the runner walks a large Cartesian
  sweep that the user interrupts repeatedly while iterating.
"""

from __future__ import annotations

from benchmarks.core import Dataset, Forecast, Result, System

__all__ = ["Dataset", "Forecast", "Result", "System"]
