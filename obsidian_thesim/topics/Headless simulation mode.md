# Headless simulation mode

The [[3D Society Simulation]] can run **without 3D rendering**. This is essential for the [[Self-similarity]] engine's pattern mining.

## Why headless matters

To find recurring patterns across simulation runs, you need many runs. A headless sim can:
- Generate dozens of runs overnight
- Export structured [[Telemetry and observability]] as JSON
- Feed historical windows into motif search, regime detection, precursor matching
- Test interventions against historical precursor states

## Architecture

All `src/sim/` and `src/world/` modules are **headless-safe** — they never touch the DOM or Three.js. Only `src/render/` imports Three.js. The `SimEngine` owns truth; the render layer is a projection.

This separation was a design requirement from the start: "The simulation must be able to run without 3D rendering so we can generate many runs for pattern mining."

## Source

- `the-similarity-fractal/src/sim/engine.js` — `SimEngine` runs independently of any renderer
