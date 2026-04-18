# Batch 7: NL-to-Time-Series v1 (2026-04-18)

Seventh pillar of the platform. Converts natural-language market narratives into synthetic price trajectories and registers them in the platform registry.

## What shipped

1. **Keyword parser** (`parse_narrative()`): rule-based extraction of direction, magnitude, duration, volatility, and catalyst keywords from free-form text. Scans hardcoded word lists.
2. **NarrativeSchema** dataclass: the intermediate representation between text and trajectory.
3. **Trajectory compiler** (`compile_trajectory()`): piecewise-linear drift + Gaussian noise, deterministic via `np.random.default_rng(seed)`.
4. **Registry integration** (`register_nl_ts_run()`): creates `RunRecord(kind=NL_TS)` with parsed schema as config and trajectory summary stats.
5. **E2E demo** (`examples/nl_to_timeseries_demo.py`): 3 inline narratives (crash, rally, sideways) through the full pipeline.
6. **Tests** (`the_similarity/tests/test_nl_ts_e2e.py`): 8 tests covering parse, compile, and full round-trip.
7. **Smoke test** (`scripts/smoke_nl_ts.sh`).
8. **Vision doc** (`vision/nl_to_timeseries.md`): what it does, v1 limitations, v2 roadmap.

## Key decisions

- **Keyword parser over LLM**: v1 is intentionally naive. The value is the end-to-end scaffold (schema, compiler, registry integration), not parsing quality. An LLM parser is v2 scope.
- **Demo-only, not a module**: the parser and compiler live in `examples/`, not `the_similarity/`. This is a prototype — when it matures, extract into `the_similarity/nl_ts/`.
- **Reuses existing platform contracts**: `RunKind.NL_TS` was already defined in `the_similarity/platform/artifacts.py`. No contract changes needed.

## Honest limitations

See `vision/nl_to_timeseries.md` for the full list. Key gaps:
- Keyword parser cannot understand context, negation, or novel phrasing.
- Trajectories are synthetic-only, not grounded in real historical data.
- No multi-phase or multi-asset narratives.
- No evaluation harness for plausibility scoring.

## See also

- [[narrative_schema]] — the intermediate representation
- [[trajectory_compiler]] — the synthesis algorithm
- [[batch1 platform spine 2026-04-17]] — platform registry that NL_TS runs register into
- [[batch6 world event prediction v1 2026-04-18]] — sibling pillar (events)
