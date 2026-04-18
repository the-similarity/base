# Eval Harness — External Model Evaluation

## What it does
Runs a world scenario with a pluggable policy module and compares performance against a baseline (default random walk or another policy). Produces a scorecard with survival rate, mean energy, and food efficiency deltas + a verdict.

## Key design decision: re-implemented tick loop
The headless world sim (`the-similarity-fractal/src/sim/headless/world.js`) has NO native policy hook — agents use a built-in random walk in `stepWorld()`. Rather than modifying `stepWorld` (which would break determinism guarantees for existing sweeps), the harness re-implements the tick loop in `stepWorldWithPolicy()`. This preserves all world mechanics (food spawn, energy decay, death) while injecting policy-controlled movement. RNG draws for food spawning are consumed identically so the food landscape is deterministic across runs.

## Policy contract
```js
export function decide(agentState, worldState) -> { action: "move", direction: {x, y} }
```
- `agentState`: `{ id, x, y, energy, alive, age }` — read-only snapshot
- `worldState`: `{ tick, size, food: [{x,y}], agents: [...] }` — read-only snapshot
- Direction is clamped to `move_speed` so policies cannot cheat

Fail-open: if `decide()` throws or returns null, the agent falls back to random walk for that tick.

## Files
- `the-similarity-fractal/src/eval/harness.js` — core harness, `runEvaluation(config)`
- `the-similarity-fractal/src/eval/run-eval.js` — CLI wrapper
- `the-similarity-fractal/policies/greedy.js` — example greedy policy
- `the-similarity-fractal/tests/test-eval-harness.js` — 5 tests

## Scoring
Three metrics computed over the final 20% of ticks:
- **survival_rate**: alive / initial_population
- **mean_energy**: average energy of alive agents
- **food_efficiency**: cumulative_food_eaten / steps

Verdict: "better" if all deltas >= 0 and at least one > 0; "worse" if all <= 0 and one < 0; "neutral" otherwise.

## Related
- [[regime-coverage]] — sweep-level regime analysis
- [[controllability]] — knob effect sizes
- [[scorecard]] — sweep artifact format
