# Platform Adapters

> 60-second onboarding. How finance / copies / worlds produce [[run_record]]s.

## What they are

A **platform adapter** is the per-pillar code that takes a pillar-specific run output and maps it into a [[run_record]] for the [[platform_registry]]. Each pillar runner produces native outputs (pandas dataframes, JSONL streams, CSV scorecards); the adapter packages those into the unified artifact shape.

## Current landed adapters (Batch 1)

| Pillar | RunKind | Adapter site | Output source |
|---|---|---|---|
| Copies | `COPIES` | `the_similarity/platform/api/routes.py::create_copies_run` | `the_similarity.synthetic.cli` pipeline |
| Worlds | `WORLDS` | `the_similarity/platform/api/routes.py::create_worlds_run` | Node subprocess → `runner.js` JSONL |
| Sweep  | `SWEEP`  | `the_similarity/platform/api/routes.py::create_sweep_run`  | Node subprocess → `run-example-sweep.js` |
| Eval (finance) | `EVAL` | manual today; adapter lives in test harness / backtester callers | `the_similarity.core.backtester` outputs |

## Adapter responsibilities (the contract)

Every adapter MUST:

1. **Run the pillar-native pipeline.** Produce whatever on-disk artifacts the pillar emits (parquet, JSONL, scorecard.json, etc.).
2. **Anchor `run_dir`.** Compute a canonical output directory (e.g. `<kind>-<seed>-<YYYYMMDD-HHMMSS>`) and record it in `provenance["run_dir"]` so the HTTP artifact streamer can resolve relative paths.
3. **Extract headline numbers** into `RunRecord.summary` — see [[scorecard_summary]] for canonical keys.
4. **Build provenance** with `generator_name`, `generator_version`, `seed`, `created_at`, plus pillar-specific knobs (scenario name for worlds, source_id for copies, symbol/date-range for finance).
5. **Call `write_artifact(run_dir, artifact)`** to materialize `artifact.json`.
6. **Call `registry.register(artifact)`** to index the record.

Step 6 is the invariant — an adapter that produces artifacts but does not register is invisible to the rest of the platform.

## Why separate adapters rather than one runner

- **Language split.** Copies + eval are Python, worlds is TypeScript (Node subprocess). No single runner can be in-process for both.
- **Pillar-specific provenance.** Finance needs `symbol/start/end`; worlds needs `scenario_name`; copies needs `source_id`. Forcing a union type would make every adapter uglier.
- **Independent evolution.** Each pillar can ship scorecard revisions without coordinating; the artifact shape stays stable (see [[run_record]] field contract).

## Invariants

- **No adapter mutates another pillar's artifacts.** One adapter, one run_dir, one `artifact.json`.
- **Adapters never update the summary after registration.** To enrich, produce a new `RunRecord` with a new `run_id` (or, for same-id re-registration via eval, document the re-registration in provenance).
- **Run dirs are immutable from the registry's perspective.** Moving a run dir invalidates the `provenance["run_dir"]` anchor and the artifact-streaming endpoint will 404.

## Related

- [[run_record]] — the output shape every adapter produces
- [[platform_registry]] — where adapters register
- [[platform_rest_api]] — the HTTP wrapping around adapters
- [[synthetic_contracts]] — the copies-side `Provenance` / `Scorecard` dataclasses adapters embed
- `the_similarity/platform/api/routes.py`
- `the_similarity/synthetic/cli.py`
- `the-similarity-fractal/src/sim/headless/runner.js`
