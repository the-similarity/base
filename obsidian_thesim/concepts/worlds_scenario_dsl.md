# Worlds Scenario DSL

**Module:** `the-similarity-fractal/src/sim/scenarios/` (JS) + `the_similarity/platform/contracts.py` (Python `ScenarioSpec`)
**Shipped:** Batch 4 (Worlds v2), April 2026

## What it is

A declarative schema for defining world simulation scenarios. Each scenario
specifies the engine type, initial conditions, and simulation parameters as a
JSON document validated against a schema.

## Presets

Three built-in presets ship with v2:

| Preset | Intent | Key overrides |
|--------|--------|--------------|
| `stress_test` | High population, scarce resources — tests survival | `initial_energy: 0.3`, `food_regen_rate: 0.01`, `n_agents: 40` |
| `abundance` | Rich environment, low population — tests growth | `initial_energy: 1.0`, `food_regen_rate: 0.2`, `n_agents: 10` |
| `sparse` | Large grid, few agents — tests spatial dynamics | `grid_size: 128`, `n_agents: 5`, `food_regen_rate: 0.05` |

## Override mechanism

1. Loader resolves a preset name to its base JSON document.
2. Caller supplies an `overrides` dict (flat key-value pairs).
3. Overrides are shallow-merged onto the preset defaults.
4. The merged document is validated against the scenario JSON schema.
5. Invalid overrides (unknown keys, wrong types) raise at load time.

This means a user can write `--preset stress_test --override n_agents=80`
to run the stress preset with double agents, without authoring a full
scenario file.

## Platform registration

Scenarios land in the registry as [[artifact_record|ScenarioSpec]] rows:

```python
ScenarioSpec(
    scenario_id="stress_test_v1",
    name="Stress Test",
    version="1.0.0",
    engine="small_village",
    params={...},
    metadata={"preset": "stress_test", "category": "adversarial"},
)
```

`registry.list_scenarios()` returns all registered specs. Runs reference
scenarios via `config.scenario` in their `RunArtifact`.

## Code paths

- Schema definition: `the-similarity-fractal/src/sim/scenarios/schema.json`
- Preset loader: `the-similarity-fractal/src/sim/scenarios/loader.js`
- Python contract: `the_similarity/platform/contracts.py` → `ScenarioSpec`
- Registry CRUD: `the_similarity/platform/registry.py` → `register_scenario()`, `list_scenarios()`
