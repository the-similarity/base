# Worlds Telemetry Export

**Module:** `the-similarity-fractal/src/sim/` (JS runner) + comparison CLI
**Shipped:** Batch 4 (Worlds v2), April 2026

## JSONL format

The headless runner writes one JSON line per simulation tick:

```jsonl
{"tick":0,"population":20,"mean_energy":1.0,"food_count":150,"births":0,"deaths":0}
{"tick":1,"population":19,"mean_energy":0.95,"food_count":148,"births":0,"deaths":1}
```

Fields are global aggregates — there is no per-agent or spatial data in v2.
The format is intentionally flat so `jq`, `pandas.read_json(lines=True)`,
and `csvkit` can all consume it without a custom parser.

## CSV export

The telemetry CLI converts JSONL to CSV:

```bash
node src/sim/headless/export.js --in run.jsonl --out run.csv --format csv
```

Optional enrichment adds derived columns:
- `rolling_mean_energy_10` — 10-tick rolling mean of `mean_energy`
- `regime` — discrete regime label (one of 9 bins on population health x energy)
- `energy_gradient` — first difference of `mean_energy`

Enrichment is opt-in (`--enrich`) to keep the default export lean.

## Cross-run diff

The comparison CLI diffs two JSONL telemetry files:

```bash
node src/sim/headless/compare.js --a run_a.jsonl --b run_b.jsonl --out diff.json
```

Output is a structured JSON report with per-metric divergence:
- **mean absolute difference** per column across all ticks
- **terminal divergence** — difference at the last tick
- **regime overlap** — Jaccard similarity of visited regime sets

This enables "policy A vs policy B on the same scenario/seed" comparisons
without loading both files into a notebook.

## Platform integration

After export, the Python worlds adapter registers the run:

```python
from the_similarity.platform.adapters.worlds import register_world_run
rid = register_world_run("run.jsonl", "small_village", seed=42, registry=reg)
```

The adapter reads JSONL metadata (tick count, final-tick values) to populate
`RunArtifact.summary` without loading the full file into memory.

## Related

- [[worlds_scenario_dsl]] — scenarios that produce the telemetry
- [[worlds_eval_harness]] — harness that consumes telemetry for scoring
- `the-similarity-fractal/src/sim/headless/runner.js` — JSONL writer
