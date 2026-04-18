# Headless Telemetry JSONL Schema

**Telemetry version**: `2.0`

The headless runner (`src/sim/headless/runner.js`) emits one JSON object per line
(JSONL / newline-delimited JSON). Each line is independently parseable. The file
contains exactly three line types in a fixed order:

```
line 0        provenance   (exactly one)
lines 1..N    tick          (one per simulation step)
last line     summary       (exactly one)
```

---

## Line types

### 1. Provenance (line 0)

Metadata about the run. Written once before simulation begins.

| Field | Type | Description |
|---|---|---|
| `type` | `"provenance"` | Line discriminator |
| `telemetry_version` | `string` | Schema version, currently `"2.0"` |
| `seed` | `number` | PRNG seed used for this run |
| `generator_name` | `string` | Always `"the-similarity-fractal-headless"` |
| `version` | `string` | Generator code version (semver) |
| `scenario_name` | `string` | Human-readable scenario name |
| `scenario` | `object` | Full scenario JSON for exact replay |
| `params` | `object` | Resolved simulation parameters (after defaults) |
| `duration_steps` | `number` | Planned number of ticks |
| `created_at` | `string` | ISO 8601 timestamp |

**Params object fields**:

| Field | Type | Default | Description |
|---|---|---|---|
| `energy_decay` | `number` | `0.01` | Per-tick energy cost |
| `move_speed` | `number` | `1` | Max per-axis displacement per tick |
| `food_spawn_rate` | `number` | `0.05` | Probability of new food cell per tick |
| `food_energy` | `number` | `0.3` | Energy gained on food pickup |

### 2. Tick (lines 1..N)

Per-step metrics snapshot. One line per simulation tick.

| Field | Type | Description |
|---|---|---|
| `type` | `"tick"` | Line discriminator |
| `tick` | `number` | Zero-indexed step number |
| `metrics` | `object` | Metric values (see below) |
| `state` | `object?` | Optional per-agent state dump (only with `--include-state` or `--state-every`) |

**Metrics object fields**:

| Field | Type | Description |
|---|---|---|
| `alive` | `number` | Count of living agents |
| `dead` | `number` | Count of dead agents |
| `food_count` | `number` | Current food cells on the grid |
| `mean_energy` | `number` | Mean energy across living agents (0 if none alive) |
| `mean_age` | `number` | Mean age (ticks survived) across living agents |
| `cumulative_deaths` | `number` | Total deaths since tick 0 |
| `cumulative_food_eaten` | `number` | Total food pickups since tick 0 |
| `population_density` | `number` | `alive / world_size^2` — fraction of grid cells occupied |
| `food_per_agent` | `number` | `food_count / max(alive, 1)` — food availability per agent |
| `energy_variance` | `number` | Population variance of energy across living agents (0 if <2 alive) |

**Optional state object** (when `--include-state` or `--state-every N`):

| Field | Type | Description |
|---|---|---|
| `agents` | `array` | Array of `{id, x, y, energy, alive, age}` per agent |
| `food` | `array` | Array of `{x, y}` food positions |

### 3. Summary (last line)

Final snapshot and cumulative totals. Written once after the simulation loop.

| Field | Type | Description |
|---|---|---|
| `type` | `"summary"` | Line discriminator |
| `final_metrics` | `object` | Same schema as tick metrics, for the final world state |
| `totals` | `object` | Cumulative counters (see below) |
| `wall_time_ms` | `number` | Wall-clock time for the simulation in milliseconds |

**Totals object fields**:

| Field | Type | Description |
|---|---|---|
| `deaths` | `number` | Total agent deaths |
| `births` | `number` | Total agent births (currently always 0 in the MVP) |
| `food_eaten` | `number` | Total food pickups |

---

## Versioning

The `telemetry_version` field in the provenance line tracks backward-incompatible
schema changes. Consumers should check this field before parsing.

| Version | Changes |
|---|---|
| `2.0` | Added `population_density`, `food_per_agent`, `energy_variance` to tick metrics. Added `telemetry_version` to provenance. |
| `1.0` (implicit) | Original format: no `telemetry_version` field in provenance. |

---

## Example

```jsonl
{"type":"provenance","telemetry_version":"2.0","seed":42,"generator_name":"the-similarity-fractal-headless","version":"0.1.0","scenario_name":"small_village","scenario":{...},"params":{"energy_decay":0.01,"move_speed":1,"food_spawn_rate":0.05,"food_energy":0.3},"duration_steps":500,"created_at":"2026-04-15T12:00:00.000Z"}
{"type":"tick","tick":1,"metrics":{"alive":20,"dead":0,"food_count":1,"mean_energy":0.74,"mean_age":1,"cumulative_deaths":0,"cumulative_food_eaten":0,"population_density":0.00488,"food_per_agent":0.05,"energy_variance":0.008}}
...
{"type":"summary","final_metrics":{...},"totals":{"deaths":15,"births":0,"food_eaten":42},"wall_time_ms":123}
```

## Consuming JSONL

```bash
# Count ticks
grep -c '"type":"tick"' run.jsonl

# Extract alive time-series with jq
jq -r 'select(.type=="tick") | [.tick, .metrics.alive] | @csv' run.jsonl

# Parse in Node.js
import { parseTelemetry } from './telemetry-export.js';
const { provenance, ticks, summary } = parseTelemetry('run.jsonl');
```
