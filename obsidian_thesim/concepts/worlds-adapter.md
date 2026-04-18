# Worlds Registry Adapter

The worlds adapter (`the_similarity/platform/adapters/worlds.py`) bridges the headless worlds runner output to the platform registry.

## What it does

Three functions:

1. **`register_world_run(telemetry_path, scenario_name, seed, registry)`** — reads a JSONL telemetry file (provenance header + summary footer), builds a `RunArtifact` with `kind=WORLDS`, registers it.

2. **`register_scenario_preset(scenario_json_path, registry)`** — reads a scenario JSON file, creates a `ScenarioSpec`, registers it.

3. **`sync_all_presets(scenarios_dir, registry)`** — scans a directory of scenario JSONs, registers each idempotently.

## JSONL contract

The headless runner (`the-similarity-fractal/src/sim/headless/runner.js`) emits:
- Line 0: `{"type": "provenance", "generator_name": "...", "seed": 42, ...}`
- Lines 1..N-1: `{"type": "tick", "tick": N, ...}` (ignored by adapter)
- Line N: `{"type": "summary", "ticks": N, "alive": M, "dead": D, ...}`

## CLI

```bash
python -m the_similarity.platform sync-scenarios --dir the-similarity-fractal/scenarios/
python -m the_similarity.platform list --kind worlds
```

## API endpoints

- `GET /platform/scenarios/{id}/runs` — list world runs for a scenario
- `POST /platform/worlds/run` — trigger a world run (PLACEHOLDER)

## Related

- [[platform-contracts]] — `ScenarioSpec`, `RunKind.WORLDS`
- [[copies-adapter]] — analogous adapter for the synthetic copies pillar
- Code: `the_similarity/platform/adapters/worlds.py`
- Tests: `the_similarity/tests/test_worlds_registry.py`
