# Synthetic Worlds v2

**Status:** Batch 4, shipping April 2026
**Scope:** Scenario presets, eval harness, telemetry export, platform integration

---

## What Worlds v2 adds

Worlds v1 shipped a single headless runner that produces JSONL telemetry and
registers runs in the platform registry. v2 extends this with four capabilities:

1. **Scenario DSL with presets** — A declarative schema for scenario definitions
   (`stress_test`, `abundance`, `sparse`) plus a loader that resolves presets,
   applies overrides, and validates against a JSON schema. Scenarios are
   registered in the platform registry as `ScenarioSpec` rows, making them
   discoverable and reusable across runs and sweeps.

2. **Eval harness for external policies** — A pluggable evaluation framework
   where external agent policies (Python callables or JS functions) drive
   agent decisions in the simulation. The harness runs the policy against a
   scenario, collects per-tick telemetry, and produces a scorecard
   (`ScorecardKind.CONTROLLABILITY`) with regime coverage and controllability
   metrics. Ships with a greedy policy example.

3. **Telemetry export** — Structured export of per-tick JSONL telemetry to CSV,
   plus enriched metrics (derived columns like rolling averages, regime labels).
   A comparison CLI diffs two runs side-by-side, producing a delta report with
   per-metric divergence scores.

4. **Platform integration** — A Python worlds adapter that bridges the JS
   headless runner output to the platform registry. Scenario sync ensures
   `ScenarioSpec` rows stay in sync with the `scenarios/` directory. FastAPI
   endpoints expose worlds runs, scenarios, and scorecards to the UI.

## The workflow

```
define scenario     run headless        export telemetry
  (DSL preset)  -->  (Node runner)  -->  (JSONL -> CSV)
       |                  |                    |
       v                  v                    v
  register in       register run         evaluate policy
  registry          with provenance      (eval harness)
       |                  |                    |
       v                  v                    v
  list/compare      query registry       compare runs
  scenarios         by kind=WORLDS       (telemetry diff)
```

1. **Define scenario** — Pick a preset (`stress_test`, `abundance`, `sparse`) or
   write a custom scenario JSON. The DSL validates against a schema and provides
   sensible defaults. Register the scenario in the platform registry.

2. **Run headless** — Execute the scenario via the Node.js headless runner with a
   seed for reproducibility. Output: JSONL telemetry file + provenance metadata.

3. **Export telemetry** — Convert JSONL to CSV for analysis. Optionally enrich
   with derived metrics (rolling means, regime labels, energy gradients).

4. **Evaluate policy** — Plug an external policy into the eval harness. The
   harness runs the policy against the scenario, collects telemetry, and
   produces a scorecard with regime coverage and controllability scores.

5. **Register** — The Python worlds adapter registers the run in the platform
   registry with `kind=WORLDS`, provenance, and summary metrics. The run is
   now queryable via CLI, API, and UI alongside finance and copies runs.

6. **Compare** — The comparison CLI diffs two world runs (e.g. greedy vs random
   policy on the same scenario/seed), producing a structured delta report.

## What's honest

- **One engine, one biome.** The only world type is `small_village` — a 2D torus
  grid with simple energy/food/population dynamics. There are no multi-biome
  worlds, no 3D environments, no complex agent behaviors beyond the energy model.

- **Eval harness is MVP-level.** The harness supports external policies but the
  evaluation surface is limited: regime coverage (fraction of 9 discrete regimes
  visited) and controllability (Pearson r between knobs and observables). There
  is no causal analysis, no counterfactual evaluation, no multi-objective scoring.

- **Telemetry format is flat.** Each JSONL row is a per-tick snapshot of global
  metrics. There is no per-agent telemetry, no spatial data, no event streams.
  The format is sufficient for aggregate analysis but not for agent-level
  debugging or replay.

- **Scenario presets are hand-authored.** The three presets (`stress_test`,
  `abundance`, `sparse`) were designed by intuition, not by systematic
  exploration of the parameter space. They may not cover all interesting
  dynamical regimes.

## What's next

- **More world types.** Queue/M/M/1 models, boom-bust economic cycles, and
  eventually multi-biome environments with inter-region dynamics.

- **Real agent policies.** RL-trained policies, LLM-driven agents, and hybrid
  approaches that combine learned and rule-based behavior. The eval harness
  is designed to accept any callable; the bottleneck is building interesting
  policies, not the harness itself.

- **Rendered visualization.** The fractal terrain engine (`terrain_generator.py`)
  already supports 3D rendering. The next step is wiring headless simulation
  state to the renderer so users can watch a world unfold in real time and
  replay from telemetry.

- **Cross-pillar evaluation.** Compare worlds-generated synthetic trajectories
  against real market data using the finance pillar's fidelity scorecards.
  This closes the loop: generate a synthetic world, extract a time series,
  evaluate it against reality.

- **Scenario discovery.** Automated exploration of the parameter space to find
  scenarios that maximize regime coverage or expose policy failure modes.
  This turns the hand-authored presets into a search problem.
