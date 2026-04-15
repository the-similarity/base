# Synthetic worlds runner (headless)

Module: `the-similarity-fractal/src/sim/headless/` · Entrypoint: `npm run sim:headless` (runs `src/sim/headless/runner.js`) · Shipped: 2026-04-15 (PR #128).

Headless, seeded, renderer-free runner for the fractal-sim world. No THREE.js / DOM imports. Produces structured JSONL telemetry suitable for downstream analysis by [[synthetic worlds eval]].

## Invocation

```bash
cd the-similarity-fractal
npm run sim:headless -- \
  --scenario scenarios/small_village.json \
  --seed 42 --steps 500 --out <file.jsonl>
```

Optional: `--include-state` or `--state-every N` to emit per-tick agent/food positions.

## Telemetry JSONL schema

- **Line 0 — provenance** (field-compatible with `the_similarity.synthetic.contracts.Provenance`):
  ```json
  {"type":"provenance","seed":42,"generator_name":"the-similarity-fractal-headless",
   "version":"0.1.0","scenario_name":"small_village","scenario":{...},
   "params":{"energy_decay","move_speed","food_spawn_rate","food_energy"},
   "duration_steps":500,"created_at":"ISO8601"}
  ```
- **Lines 1..N — ticks**:
  ```json
  {"type":"tick","tick":N,"metrics":{"alive","dead","food_count","mean_energy",
   "mean_age","cumulative_deaths","cumulative_food_eaten"},"state":{...?}}
  ```
- **Last line — summary**:
  ```json
  {"type":"summary","final_metrics":{...},"totals":{"deaths","births","food_eaten"},"wall_time_ms":int}
  ```

## Knobs exposed (scenario.params)

- `energy_decay` — metabolism cost per tick. Raising it kills more agents.
- `move_speed` — distance per tick.
- `food_spawn_rate` — per-cell per-tick probability of food appearance.
- `food_energy` — energy restored per food eaten.

World knobs: `world.size`, `world.initial_population`. CLI overrides: `--seed`, `--steps`.

## Invariants

- Determinism is a contract — repeat runs at the same seed produce byte-identical JSONL (minus `created_at` / `wall_time_ms`).
- Runner must stay decoupled from the renderer. If the coupled sim imports DOM/THREE, headless runner must either stub or fail loudly rather than silently pull the renderer in.

## Example scenario

`the-similarity-fractal/scenarios/small_village.json` — tiny seeded world: 20 agents on a 64×64 torus with modest food spawn. Used as the default smoke scenario.

See [[synthetic worlds eval]] for the sweep runner and [[synthetic launch 2026-04-15]] for the broader launch context.
