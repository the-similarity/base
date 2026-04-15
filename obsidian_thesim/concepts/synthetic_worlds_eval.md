# Synthetic worlds eval

Module: `the-similarity-fractal/src/eval/` · Entrypoint: `node src/eval/run-example-sweep.js` · Shipped: 2026-04-15 (PR #133).

Scenario sweep runner + scorecard for the [[synthetic worlds runner]]. Answers two questions per run:

1. **Regime coverage** — does sweeping the knob grid actually visit a diverse set of world regimes, or does everything collapse into the same state?
2. **Controllability** — does varying each knob actually move the expected metric? If not, the knob is decorative.

## Pipeline

- `sweep.js` — enumerates the grid (dict of knob → list of values) × seed list, invokes the headless runner per cell, collects JSONL telemetry.
- `regime-coverage.js` — bins telemetry into 9 regimes (population × energy: {collapsed, thin, healthy} × {starving, lean, fed}), reports coverage % global and per-config.
- `controllability.js` — for each (knob, metric) pair, computes Pearson r and permutation-test p-value across the sweep.
- `scorecard.js` — writes a `kind: "worlds"` artifact that mirrors the Python `Scorecard` shape for cross-lane consistency.

## Artifact shape

```json
{
  "kind": "worlds",
  "sweep_id": "example",
  "scenario": {...},
  "knob_grid": {...},
  "seeds": [...],
  "ticks": 150,
  "regime_coverage": {
    "regime_labels": [...9 regimes...],
    "global": {"regimes_visited": [...], "coverage": 0.67, "counts": {...}},
    "per_config": [...]
  },
  "controllability": {
    "food_spawn_rate": {"alive": {"effect_size", "p_value", "n"}, ...},
    "energy_decay": {...}
  },
  "provenance": {...}
}
```

Saved under `the-similarity-fractal/artifacts/sweep-<id>/sweep-<id>/`.

## Example-grid results (committed)

`run-example-sweep.js` runs `food_spawn_rate × energy_decay` (2×3) × 3 seeds × 150 steps in ~1.3s. Validated signals matching physical intuition:

- `energy_decay → alive` — r = -0.75, p = 0.002
- `energy_decay → cumulative_deaths` — r = +0.75, p = 0.002
- `food_spawn_rate → food_count` — r = +0.87, p = 0.002

Global regime coverage: 6/9.

## Why it matters

A world runner can emit telemetry that "looks real" without the knobs actually controlling anything. Controllability + coverage together are the minimum credible check that the world is a usable stress-testing substrate rather than a decorated random walk. The permutation p-value matters — effect size alone can be noise on a small grid.

See [[synthetic worlds runner]] for the runner consumed by this scorecard, and [[synthetic launch 2026-04-15]] for context.
