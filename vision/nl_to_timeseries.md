# NL-to-Time-Series: Natural Language to Synthetic Trajectories

## What it does

The NL-to-time-series pipeline converts free-form natural-language descriptions of market scenarios into synthetic price trajectories and registers them in the platform registry. A user writes "a sharp crash over 30 days with volatile price action" and gets back a plausible trajectory that captures the described dynamics.

This is the seventh pillar of The Similarity platform, alongside finance retrieval, synthetic copies, worlds simulation, 3D data space, and world events.

## v1 Workflow

```
User narrative (text)
        │
        ▼
┌──────────────────┐
│  Keyword Parser   │  Scans for directional words, magnitude
│  (rule-based)     │  modifiers, duration, volatility cues
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ NarrativeSchema   │  direction, magnitude, duration_days,
│ (dataclass)       │  volatility, catalyst_keywords
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Trajectory        │  Piecewise-linear drift + Gaussian
│ Compiler          │  noise overlay → np.ndarray
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Platform Registry │  RunRecord(kind=NL_TS) with parsed
│ (SQLite)          │  schema as config, trajectory stats
└──────────────────┘
```

## What's honest (v1 limitations)

1. **Keyword parser, not an LLM.** The parser scans for hardcoded word lists ("crash", "rally", "sideways") and returns the first match. It cannot understand nuance, context, or novel phrasing. "The market experienced a period of declining confidence" would parse as sideways (no keyword hit), not down.

2. **Simple trajectory compiler.** Trajectories are piecewise-linear with additive Gaussian noise. There is no volatility clustering, no mean-reversion, no regime switching, no fat tails. The trajectories look like a random walk with drift, not real market data.

3. **Simple correlation retrieval.** v1 does not retrieve similar historical periods from the engine's database. The trajectories are purely synthetic — generated from the parsed schema, not grounded in real data.

4. **No multi-asset support.** Each narrative produces a single univariate trajectory. Cross-asset narratives ("equities crash while bonds rally") are not handled.

5. **No temporal structure.** The compiler cannot handle multi-phase narratives like "crash for 2 weeks then recovery over 3 months". Duration is a single value.

## What's next (v2 roadmap)

### LLM parsing
Replace the keyword parser with an LLM call (Claude or GPT) that outputs structured JSON matching the NarrativeSchema. This handles nuance, novel phrasing, and multi-phase narratives.

### Learned priors (retrieval-grounded compilation)
Instead of synthetic-only trajectories, retrieve the top-K historical analogues from the engine that match the parsed schema (direction, magnitude, regime), then compile the trajectory as a weighted blend of historical paths. This grounds narratives in real market dynamics.

### Multi-phase narratives
Extend NarrativeSchema to support a sequence of phases, each with its own direction/magnitude/duration. The compiler chains phases with smooth transitions.

### Multi-asset narratives
Support cross-asset narratives by parsing entity references ("equities", "bonds", "oil") and generating correlated multi-variate trajectories using the copula generator.

### Evaluation harness
A benchmark of narrative-trajectory pairs with human-rated "plausibility" scores, enabling systematic comparison of parser + compiler variants.

## Code references

- Demo: `examples/nl_to_timeseries_demo.py`
- Tests: `the_similarity/tests/test_nl_ts_e2e.py`
- Platform contracts: `the_similarity/platform/contracts.py` (RunKind.NL_TS)
- Platform registry: `the_similarity/platform/registry.py`
- Smoke test: `scripts/smoke_nl_ts.sh`
