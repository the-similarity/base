/**
 * Minimal headless world state + tick loop for synthetic-world generation.
 *
 * This module is intentionally renderer-free: it imports only the deterministic
 * PRNG and standard JS. It is NOT coupled to the full SimEngine / THREE.js
 * renderer path — agents here are a light-weight representation sufficient for
 * producing reproducible JSONL telemetry that downstream World Eval can consume.
 *
 * Invariants:
 * - Given the same seed + params + duration the per-tick metrics are identical
 *   on every machine. All stochastic decisions route through a single PRNG
 *   instance owned by the world.
 * - State is mutated in place each tick; there is no hidden shared state with
 *   the render-mode SimEngine. Two World instances can run concurrently in the
 *   same process without cross-contamination.
 * - Tick counter is monotonically increasing; `tick` equals the zero-indexed
 *   step just completed when a tick record is emitted.
 *
 * Knobs (scenario.params):
 * - energy_decay     (default 0.01)  : per-tick energy cost for living.
 * - move_speed       (default 1)     : max steps in x/y per tick.
 * - food_spawn_rate  (default 0.05)  : probability a new food cell spawns/tick.
 * - food_energy      (default 0.3)   : energy gained on food pickup.
 *
 * Knobs (scenario.world):
 * - size                 (default 64): grid is size × size; agents/food wrap.
 * - initial_population   (default 20): number of agents spawned at t=0.
 *
 * Optional 3D mode (terrain-walking agents):
 * - createWorld accepts an optional `heightmap` parameter shaped
 *   `{ width, height, data }` where `data` is a flat row-major float array
 *   of length width*height. When provided, every alive agent's `z` field is
 *   set to `heightmap.data[y * width + x]` after each move so trajectories
 *   are 3D and bend with the terrain. When `heightmap` is omitted, agents
 *   stay 2D (no `z` field) — backwards-compatible with all existing JSONL
 *   outputs and consumers.
 */

import { PRNG } from '../rng.js';

/**
 * Look up a row-major heightmap value at integer (x, y), with toroidal
 * wrapping that matches the world's torus topology. Returns 0 when the
 * heightmap is missing or malformed — fail-soft so a corrupt fixture
 * does not crash the simulation; downstream telemetry simply records
 * z=0 and the trajectory is detectable as "lookup failed".
 */
export function sampleHeight(heightmap, x, y) {
  if (!heightmap || !heightmap.data) return 0;
  const w = heightmap.width;
  const h = heightmap.height;
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return 0;
  // Wrap negative / oversized indices the same way the world wraps agent
  // positions. Without this, a movement step that lands exactly on `size`
  // (post-modulo) plus a heightmap of a different size would index OOB.
  const xi = ((Math.floor(x) % w) + w) % w;
  const yi = ((Math.floor(y) % h) + h) % h;
  const idx = yi * w + xi;
  const v = heightmap.data[idx];
  return Number.isFinite(v) ? v : 0;
}

/**
 * Build an initial world from a scenario config + seed.
 * Pure factory — all randomness goes through the provided PRNG.
 *
 * @param {object} scenario - Scenario config (see module docstring).
 * @param {number} seed - PRNG seed.
 * @param {object} [options] - Optional extras.
 * @param {object} [options.heightmap] - Optional 2D height grid:
 *     `{ width: number, height: number, data: number[] }`. When supplied,
 *     agents are lifted to 3D — each alive agent gets a `z` field equal
 *     to `data[y * width + x]` after every step. The heightmap is stored
 *     by reference on the world; mutating it externally during a run is
 *     unsupported and produces undefined behavior.
 */
export function createWorld(scenario, seed, options = {}) {
  const rng = new PRNG(seed);
  const worldCfg = scenario.world ?? {};
  const params = scenario.params ?? {};
  const heightmap = options.heightmap ?? null;

  // Fill in defaults once here so downstream code can read params without
  // constantly null-coalescing. Mutating this object is NOT allowed after
  // createWorld returns — we freeze it to surface accidental writes.
  const resolvedParams = Object.freeze({
    energy_decay:   params.energy_decay   ?? 0.01,
    move_speed:     params.move_speed     ?? 1,
    food_spawn_rate: params.food_spawn_rate ?? 0.05,
    food_energy:    params.food_energy    ?? 0.3,
  });

  const size = worldCfg.size ?? 64;
  const initialPop = worldCfg.initial_population ?? 20;

  // Agents: light representation — id, position, energy, alive. Keep numeric
  // fields as plain numbers (not objects) so JSON serialization is compact
  // when full-state dumps are requested. The optional `z` field is only
  // populated when a heightmap is provided; in 2D mode it stays undefined
  // and is omitted from JSON serialization (backwards compatible).
  const agents = [];
  for (let i = 0; i < initialPop; i++) {
    const x = Math.floor(rng.next() * size);
    const y = Math.floor(rng.next() * size);
    const a = {
      id: i,
      x,
      y,
      // Start with energy in [0.5, 1.0] so a few agents die early and we see
      // non-trivial population dynamics in the telemetry.
      energy: 0.5 + rng.next() * 0.5,
      alive: true,
      age: 0,
    };
    if (heightmap) {
      // Lift to 3D. We sample at the spawn position so the very first
      // emitted track record carries a sensible z value (not undefined).
      a.z = sampleHeight(heightmap, x, y);
    }
    agents.push(a);
  }

  // Food cells: sparse list of {x,y}. We keep this as an array instead of a
  // 2D grid because populations and food counts here are small (< ~10³) and
  // array iteration is simpler to reason about. At higher densities a grid
  // would be cheaper, but this MVP targets readability + JSON-friendliness.
  const food = [];

  return {
    tick: 0,
    size,
    agents,
    food,
    params: resolvedParams,
    rng,
    // Cumulative counters — useful for World Eval calibration checks.
    totals: { deaths: 0, births: 0, food_eaten: 0 },
    // Optional heightmap for 3D mode. Stored by reference; consumers that
    // need to inspect z values per tick should call `sampleHeight(world.heightmap, x, y)`
    // rather than re-reading scenario config.
    heightmap,
  };
}

/**
 * Advance the world by exactly one tick. Deterministic given the world's PRNG.
 *
 * Order of operations (deliberate — change only with a migration):
 *   1. Spawn food probabilistically (environmental clock).
 *   2. For each alive agent: move, seek nearby food, decay energy, die if <= 0.
 *   3. Update tick counter.
 */
export function stepWorld(world) {
  const { rng, size, params, agents, food, heightmap } = world;

  // 1. Food spawn — one independent Bernoulli trial per tick, not per cell,
  //    to keep food density bounded and predictable regardless of grid size.
  if (rng.next() < params.food_spawn_rate) {
    food.push({
      x: Math.floor(rng.next() * size),
      y: Math.floor(rng.next() * size),
    });
  }

  // 2. Agent updates.
  for (const a of agents) {
    if (!a.alive) continue;

    // Random walk — move_speed is a hard cap on per-axis displacement per tick.
    // We sample integer deltas in [-move_speed, move_speed] to stay on the grid.
    const dx = Math.round((rng.next() * 2 - 1) * params.move_speed);
    const dy = Math.round((rng.next() * 2 - 1) * params.move_speed);
    // Toroidal wrap — world is a torus so agents cannot get stuck on a border.
    // This also avoids the need for collision-with-boundary logic in the MVP.
    a.x = ((a.x + dx) % size + size) % size;
    a.y = ((a.y + dy) % size + size) % size;

    // 3D lift — when a heightmap is loaded, snap z to the local terrain
    // height after each move. This produces trajectories that bend with
    // slope (non-trivial torsion) which is the whole point of the 3D
    // self-similarity experiment. When no heightmap is loaded, `z` stays
    // undefined and the agent record serializes 2D-style.
    if (heightmap) {
      a.z = sampleHeight(heightmap, a.x, a.y);
    }

    // Food pickup — linear scan is O(F) per agent; acceptable while F stays
    // small. If food ever grows unbounded we should switch to a spatial hash.
    for (let i = food.length - 1; i >= 0; i--) {
      if (food[i].x === a.x && food[i].y === a.y) {
        a.energy = Math.min(1, a.energy + params.food_energy);
        food.splice(i, 1);
        world.totals.food_eaten += 1;
        break; // one food per tick per agent — keeps throughput bounded
      }
    }

    // Energy decay — constant per-tick cost models basal metabolism.
    a.energy -= params.energy_decay;
    a.age += 1;

    if (a.energy <= 0) {
      a.alive = false;
      a.energy = 0;
      world.totals.deaths += 1;
    }
  }

  world.tick += 1;
}

/**
 * Compute summary metrics for the current world state.
 * Returned object is JSON-safe and has stable keys across ticks so downstream
 * JSONL consumers can rely on a fixed schema.
 *
 * Derived metrics (added for regime-coverage binning):
 * - population_density: alive / world_size^2 — fraction of cells occupied.
 * - food_per_agent: food_count / max(alive, 1) — resource availability per
 *   living agent. Clamped to avoid division by zero when all agents are dead.
 * - energy_variance: Var(energy) across living agents — measures heterogeneity
 *   in agent health. High variance signals divergent subpopulations. Zero when
 *   0 or 1 agents alive (variance undefined for n<2, reported as 0).
 */
export function summarizeWorld(world) {
  let alive = 0;
  let energySum = 0;
  let ageSum = 0;
  // Collect energies for variance calculation in a single pass by storing
  // them, then computing the second moment. Two-pass is fine at n < 10^4.
  const energies = [];
  for (const a of world.agents) {
    if (!a.alive) continue;
    alive += 1;
    energySum += a.energy;
    ageSum += a.age;
    energies.push(a.energy);
  }

  const meanEnergy = alive > 0 ? energySum / alive : 0;

  // Variance: E[(X - mu)^2]. Zero for 0 or 1 living agents.
  let energyVariance = 0;
  if (alive >= 2) {
    let sqDiffSum = 0;
    for (const e of energies) {
      sqDiffSum += (e - meanEnergy) ** 2;
    }
    energyVariance = sqDiffSum / alive;
  }

  return {
    alive,
    dead: world.agents.length - alive,
    food_count: world.food.length,
    mean_energy: meanEnergy,
    mean_age: alive > 0 ? ageSum / alive : 0,
    cumulative_deaths: world.totals.deaths,
    cumulative_food_eaten: world.totals.food_eaten,
    // Derived metrics for regime-coverage binning
    population_density: alive / (world.size * world.size),
    food_per_agent: world.food.length / Math.max(alive, 1),
    energy_variance: energyVariance,
  };
}
