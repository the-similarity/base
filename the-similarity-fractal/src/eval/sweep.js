/**
 * Scenario sweep runner — grid over scenario knobs × seed list.
 *
 * Given a base scenario, a knob grid ({knob: [values...]}) and a list of
 * seeds, invokes the headless world (renderer-free) for every cell of the
 * Cartesian product and collects per-tick telemetry as JSONL-shaped rows.
 *
 * Lifecycle / Invariants:
 * - Pure function of (baseScenario, knobGrid, seeds, ticks) — the same
 *   inputs MUST produce the same telemetry rows. All randomness routes
 *   through the seed via the headless world's PRNG.
 * - `runCell` is the atomic unit: one (knobs, seed) → one array of tick
 *   records. It does not perform IO so it is safe to call from tests.
 * - `runSweep` materializes every cell in memory. For the MVP grids are
 *   small (≤ a few hundred cells × ≤ a few hundred ticks). When this grows
 *   we should stream cells to disk as they complete.
 * - Telemetry row schema matches `summarizeWorld()` in
 *   `src/sim/headless/world.js` plus a `tick` counter and the cell
 *   identifiers (knobs + seed). Downstream regime-coverage /
 *   controllability modules rely on this contract.
 *
 * @module eval/sweep
 */

import { createWorld, stepWorld, summarizeWorld } from '../sim/headless/world.js';

/**
 * Generate every cell of a knob grid. Deterministic key order.
 * Exported for tests and for `runSweep`'s consumers that want to preview
 * how many cells will run before committing to execution.
 */
export function enumerateGrid(knobGrid) {
  const keys = Object.keys(knobGrid).sort(); // sorted for deterministic output
  if (keys.length === 0) return [{}];

  // Iterative Cartesian product — avoids recursion depth issues on large
  // grids (not a concern today, but cheap to be safe).
  let cells = [{}];
  for (const k of keys) {
    const values = knobGrid[k];
    if (!Array.isArray(values) || values.length === 0) {
      throw new TypeError(`knobGrid['${k}'] must be a non-empty array`);
    }
    const next = [];
    for (const prefix of cells) {
      for (const v of values) {
        next.push({ ...prefix, [k]: v });
      }
    }
    cells = next;
  }
  return cells;
}

/**
 * Overlay a knob-value map on a base scenario. Knobs are merged into
 * `scenario.params` — this matches the knobs defined in `world.js` (they all
 * live under `params`). Non-param knobs (e.g. `world.size`) can be supplied
 * via dotted keys like `"world.size"`.
 */
export function applyKnobs(baseScenario, knobs) {
  // Deep-ish clone: we care about the two sub-trees `world` and `params`.
  const out = {
    world: { ...(baseScenario.world ?? {}) },
    params: { ...(baseScenario.params ?? {}) },
  };
  for (const [k, v] of Object.entries(knobs)) {
    if (k.startsWith('world.')) {
      out.world[k.slice('world.'.length)] = v;
    } else {
      // Default path: knob lives in params. This matches the MVP scenario
      // schema — if a future scenario grows more sub-trees we can add more
      // dotted prefixes without breaking callers.
      out.params[k] = v;
    }
  }
  return out;
}

/**
 * Execute a single sweep cell. Returns an array of telemetry rows, one per
 * tick. Does NOT write to disk — caller decides how to persist.
 */
export function runCell({ baseScenario, knobs, seed, ticks }) {
  if (!Number.isInteger(ticks) || ticks <= 0) {
    throw new RangeError(`runCell: ticks must be a positive integer, got ${ticks}`);
  }
  const scenario = applyKnobs(baseScenario, knobs);
  const world = createWorld(scenario, seed);

  const rows = new Array(ticks);
  for (let t = 0; t < ticks; t++) {
    stepWorld(world);
    const s = summarizeWorld(world);
    // Flatten cell identity + tick + metrics. A flat row shape keeps JSONL
    // trivial to parse and lets downstream regime/controllability modules
    // treat rows uniformly regardless of which cell emitted them.
    rows[t] = {
      tick: world.tick,
      seed,
      ...knobs,
      ...s,
    };
  }
  return rows;
}

/**
 * Run the full sweep: cartesian product of knob grid × seed list. Returns
 * { cells, telemetry } where `telemetry` is a flat array of all rows across
 * every cell — callers can filter by (seed, knobs) to isolate a single cell.
 */
export function runSweep({ baseScenario, knobGrid, seeds, ticks }) {
  if (!Array.isArray(seeds) || seeds.length === 0) {
    throw new TypeError('runSweep: seeds must be a non-empty array of integers');
  }
  const cells = enumerateGrid(knobGrid);
  const telemetry = [];
  const cellRecords = [];

  for (const knobs of cells) {
    for (const seed of seeds) {
      const rows = runCell({ baseScenario, knobs, seed, ticks });
      // Reference the cell's last row so downstream consumers can quickly
      // inspect terminal state without rescanning the JSONL.
      cellRecords.push({ knobs, seed, n_rows: rows.length });
      for (const r of rows) telemetry.push(r);
    }
  }

  return { cells: cellRecords, telemetry };
}
