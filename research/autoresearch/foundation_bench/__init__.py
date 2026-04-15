"""foundation-bench-v1: foundation-model baseline lane.

This package benchmarks five baseline forecasters (TimesFM, Chronos,
Moirai, MOMENT, and one wavelet-aware classical model) against the
current 9-method engine and the Tier 1 retrieval stack on the slices
defined by ``slices.yaml``.

Lane invariants
---------------
* Walk-forward: no adapter is ever given data past ``query_start``.
* Fair protocol: every adapter sees the same ``(history, forward_bars,
  percentiles, seed)`` triple; adapter-local preprocessing that the
  engine does not also get is forbidden.
* Engine read-only: the runner constructs fresh ``Config`` objects but
  never mutates any file under ``the_similarity/``.

See ``research/autoresearch/foundation_bench/README.md`` for the spec.
"""
