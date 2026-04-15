"""Adapter package for the foundation-bench lane.

Every adapter implements ``ForecastAdapter`` from ``base.py``. Adapters
whose real weights are not reachable in the current environment MUST
emit a clearly-labelled synthetic fallback and set ``fallback_reason``
on the returned result so the runner can mark the ledger row as
``status: "partial_synthetic_fallback"``.
"""
