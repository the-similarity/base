# Worlds Eval Harness

**Module:** `the-similarity-fractal/src/eval/` (JS) + Python scorecard integration
**Shipped:** Batch 4 (Worlds v2), April 2026

## What it does

Pluggable evaluation framework for external agent policies in the worlds
simulation. A "policy" is any callable that receives the current world state
and returns an action for each agent. The harness:

1. Loads a [[worlds_scenario_dsl|scenario]] (preset or custom).
2. Injects the external policy into the simulation loop.
3. Runs the scenario for N steps, collecting per-tick telemetry.
4. Produces a scorecard (`ScorecardKind.CONTROLLABILITY`).

## How external policies plug in

```
policy(state) -> actions
```

- **Python policies** — a callable `(state_dict) -> list[action_dict]`.
  The harness serializes world state to JSON, calls the policy, and
  deserializes the actions back.
- **JS policies** — a function `(state) => actions[]` passed directly
  to the simulation loop. No serialization overhead.

The greedy policy example (`src/eval/policies/greedy.js`) moves each agent
toward the nearest food source. It serves as a baseline and a template
for custom policies.

## Scorecard shape

The harness produces a `ScorecardSummary` with:

```json
{
  "kind": "controllability",
  "overall_score": 0.72,
  "passed": true,
  "thresholds": {
    "regime_coverage": 0.5,
    "controllability_min_r": 0.3
  },
  "details": {
    "regime_coverage": 0.56,
    "controllability": {
      "food_regen_rate": {"r": 0.81, "p_value": 0.002},
      "initial_energy": {"r": 0.65, "p_value": 0.01}
    }
  }
}
```

- **regime_coverage** — fraction of 9 discrete regimes (3x3 grid on
  population health x mean energy) visited during the run.
- **controllability** — per-knob Pearson r between the knob value and
  the terminal-window mean of the target metric, plus a permutation
  p-value. High r + low p = the knob actually moves the observable.

## Limitations (honest)

- MVP surface: only regime coverage and controllability. No causal
  analysis, no counterfactual evaluation, no multi-objective scoring.
- Python policies incur JSON serialization overhead per tick.
- The greedy policy is trivial — it exists to prove the harness works,
  not to demonstrate interesting agent behavior.

## Related

- [[worlds_scenario_dsl]] — scenario definitions consumed by the harness
- [[worlds_telemetry_export]] — telemetry produced by the harness
- `the_similarity/platform/contracts.py` → `ScorecardKind.CONTROLLABILITY`
- `the-similarity-fractal/src/eval/` — sweep, regime-coverage, controllability modules
