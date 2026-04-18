/**
 * External model / agent evaluation harness.
 *
 * Runs a scenario with an external policy (a JS module exporting a `decide`
 * function) and compares its performance against a baseline (either the
 * built-in random-walk behavior or another policy module).
 *
 * ## Pluggability caveat
 *
 * The headless world simulation (`src/sim/headless/world.js`) does NOT have a
 * native policy hook — agents move via a built-in random walk inside
 * `stepWorld()`. This harness achieves pluggability by re-implementing the
 * tick loop at a lower level: it calls `createWorld()` for initialization,
 * then runs its own step function that replaces the random-walk movement
 * with the policy's `decide()` output while preserving all other world
 * mechanics (food spawn, energy decay, death). The RNG is advanced
 * identically for non-movement draws so food spawning remains deterministic
 * across policy vs. baseline runs given the same seed.
 *
 * ## Policy contract
 *
 * A policy module must export a `decide(agentState, worldState)` function:
 *
 *   agentState: { id, x, y, energy, alive, age }
 *   worldState: { tick, size, food: [{x,y}...], agents: [{id,x,y,energy,alive,age}...] }
 *   returns:    { action: "move", direction: {x, y} }
 *              — x, y are integer deltas clamped to [-move_speed, move_speed]
 *
 * If `decide` throws or returns null/undefined, the agent falls back to the
 * built-in random walk for that tick (fail-open for robustness).
 *
 * ## Baseline modes
 *
 * - `"default"` (or omitted): uses the built-in random walk (no policy module).
 * - A file path string: loads that module as a policy for the baseline run.
 *
 * ## Scoring
 *
 * The harness computes three metrics over the final 20% of ticks:
 *   - survival_rate:   fraction of initial population still alive
 *   - mean_energy:     average energy of alive agents
 *   - food_efficiency: cumulative_food_eaten / steps (food consumed per tick)
 *
 * The delta is policy - baseline; verdict is "better" if all deltas >= 0 and
 * at least one is strictly positive, "worse" if all <= 0 and at least one is
 * strictly negative, "neutral" otherwise.
 *
 * @module eval/harness
 */

import { createWorld, summarizeWorld } from '../sim/headless/world.js';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pathToFileURL } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Load a scenario JSON file from disk.
 * @param {string} scenarioPath - Absolute or relative path to the scenario JSON.
 * @returns {object} Parsed scenario object.
 */
function loadScenario(scenarioPath) {
  const abs = resolve(scenarioPath);
  return JSON.parse(readFileSync(abs, 'utf8'));
}

/**
 * Dynamically import a policy module. The module must export a `decide` function.
 * Uses file:// URLs so absolute paths work on all platforms.
 *
 * @param {string} policyPath - Path to the JS module.
 * @returns {Promise<{decide: Function, name: string}>}
 */
async function loadPolicy(policyPath) {
  const abs = resolve(policyPath);
  const url = pathToFileURL(abs).href;
  const mod = await import(url);
  if (typeof mod.decide !== 'function') {
    throw new Error(
      `Policy module ${policyPath} must export a decide(agentState, worldState) function`
    );
  }
  // Policy name defaults to the module's `name` export or the filename.
  const name = mod.name ?? policyPath.split('/').pop().replace(/\.js$/, '');
  return { decide: mod.decide, name };
}

/**
 * Step the world by one tick with an optional policy controlling agent movement.
 *
 * Mirrors `stepWorld()` from world.js exactly, except agent movement is
 * delegated to `policy.decide()` when a policy is provided. The RNG is
 * advanced for food spawning regardless, so the food landscape is identical
 * between policy and baseline runs (same seed = same food).
 *
 * When no policy is provided (policy === null), this function reproduces the
 * built-in random walk behavior exactly.
 *
 * @param {object} world - Mutable world state from createWorld().
 * @param {object|null} policy - Policy object with a decide() method, or null for default behavior.
 */
function stepWorldWithPolicy(world, policy) {
  const { rng, size, params, agents, food } = world;

  // 1. Food spawn — identical to world.js. Must consume the same RNG draws
  //    regardless of policy so food placement is deterministic per seed.
  if (rng.next() < params.food_spawn_rate) {
    food.push({
      x: Math.floor(rng.next() * size),
      y: Math.floor(rng.next() * size),
    });
  }

  // 2. Agent updates — movement comes from policy or random walk.
  for (const a of agents) {
    if (!a.alive) continue;

    let dx, dy;

    if (policy) {
      // Build read-only snapshots for the policy so it cannot mutate world state.
      const agentState = { id: a.id, x: a.x, y: a.y, energy: a.energy, alive: a.alive, age: a.age };
      const worldState = {
        tick: world.tick,
        size,
        food: food.map(f => ({ x: f.x, y: f.y })),
        agents: agents.map(ag => ({
          id: ag.id, x: ag.x, y: ag.y, energy: ag.energy, alive: ag.alive, age: ag.age,
        })),
      };

      try {
        const decision = policy.decide(agentState, worldState);
        if (decision && decision.direction) {
          // Clamp to move_speed so a policy cannot cheat by moving faster.
          const ms = params.move_speed;
          dx = Math.round(Math.max(-ms, Math.min(ms, decision.direction.x)));
          dy = Math.round(Math.max(-ms, Math.min(ms, decision.direction.y)));
        } else {
          // Fallback: random walk (consume RNG draws for determinism).
          dx = Math.round((rng.next() * 2 - 1) * params.move_speed);
          dy = Math.round((rng.next() * 2 - 1) * params.move_speed);
        }
      } catch {
        // Fail-open: if the policy throws, fall back to random walk.
        dx = Math.round((rng.next() * 2 - 1) * params.move_speed);
        dy = Math.round((rng.next() * 2 - 1) * params.move_speed);
      }
    } else {
      // No policy: built-in random walk, identical to world.js.
      dx = Math.round((rng.next() * 2 - 1) * params.move_speed);
      dy = Math.round((rng.next() * 2 - 1) * params.move_speed);
    }

    // Toroidal wrap.
    a.x = ((a.x + dx) % size + size) % size;
    a.y = ((a.y + dy) % size + size) % size;

    // Food pickup — same logic as world.js.
    for (let i = food.length - 1; i >= 0; i--) {
      if (food[i].x === a.x && food[i].y === a.y) {
        a.energy = Math.min(1, a.energy + params.food_energy);
        food.splice(i, 1);
        world.totals.food_eaten += 1;
        break;
      }
    }

    // Energy decay.
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
 * Run a single simulation with an optional policy, collecting per-tick metrics.
 *
 * @param {object} opts
 * @param {object} opts.scenario - Parsed scenario JSON.
 * @param {number} opts.seed - RNG seed.
 * @param {number} opts.steps - Number of ticks to simulate.
 * @param {object|null} opts.policy - Policy object or null for baseline.
 * @returns {{ ticks: object[], summary: object }}
 */
function runSimulation({ scenario, seed, steps, policy }) {
  const world = createWorld(scenario, seed);
  const ticks = [];

  for (let t = 0; t < steps; t++) {
    stepWorldWithPolicy(world, policy);
    const metrics = summarizeWorld(world);
    ticks.push({ tick: world.tick, ...metrics, totals: { ...world.totals } });
  }

  const finalMetrics = summarizeWorld(world);
  return {
    ticks,
    summary: {
      final_metrics: finalMetrics,
      totals: { ...world.totals },
    },
  };
}

/**
 * Compute aggregate metrics over the final `tailFrac` of ticks.
 * Returns { survival_rate, mean_energy, food_efficiency }.
 *
 * @param {object[]} ticks - Array of per-tick metric objects.
 * @param {number} initialPop - Starting population count.
 * @param {number} steps - Total number of steps run.
 * @param {number} [tailFrac=0.2] - Fraction of ticks at the end to average over.
 */
function computeAggregateMetrics(ticks, initialPop, steps, tailFrac = 0.2) {
  const tailN = Math.max(1, Math.ceil(ticks.length * tailFrac));
  const tail = ticks.slice(-tailN);

  let survivalSum = 0;
  let energySum = 0;
  for (const t of tail) {
    survivalSum += initialPop > 0 ? t.alive / initialPop : 0;
    energySum += t.mean_energy;
  }

  // Food efficiency: total food eaten by end of run, normalized by steps.
  const lastTick = ticks[ticks.length - 1];
  const totalFoodEaten = lastTick?.totals?.food_eaten ?? lastTick?.cumulative_food_eaten ?? 0;

  return {
    survival_rate: survivalSum / tail.length,
    mean_energy: energySum / tail.length,
    food_efficiency: steps > 0 ? totalFoodEaten / steps : 0,
  };
}

/**
 * Determine verdict from metric deltas.
 * "better" if all deltas >= 0 and at least one > 0.
 * "worse" if all deltas <= 0 and at least one < 0.
 * "neutral" otherwise (mixed signals).
 *
 * @param {object} deltas - { survival_delta, energy_delta, efficiency_delta }
 * @returns {"better"|"worse"|"neutral"}
 */
function computeVerdict(deltas) {
  const vals = [deltas.survival_delta, deltas.energy_delta, deltas.efficiency_delta];
  const allNonNeg = vals.every(v => v >= 0);
  const allNonPos = vals.every(v => v <= 0);
  const anyPos = vals.some(v => v > 0);
  const anyNeg = vals.some(v => v < 0);

  if (allNonNeg && anyPos) return 'better';
  if (allNonPos && anyNeg) return 'worse';
  return 'neutral';
}

/**
 * Run the full evaluation: scenario × seeds with policy vs. baseline.
 *
 * @param {object} config
 * @param {string} config.scenario - Path to scenario JSON file.
 * @param {number[]} config.seeds - List of seeds to test.
 * @param {number} config.steps - Number of ticks per run.
 * @param {string} [config.policy] - Path to policy JS module (optional).
 * @param {string} [config.baseline="default"] - "default" for random walk, or
 *   path to a policy module.
 * @param {boolean} [config.quiet=false] - Suppress progress logging.
 *
 * @returns {Promise<object>} Eval scorecard with policy_name, baseline_name,
 *   seeds, per_seed results, aggregate metrics, deltas, and verdict.
 */
export async function runEvaluation(config) {
  const {
    scenario: scenarioPath,
    seeds,
    steps,
    policy: policyPath = null,
    baseline: baselineSpec = 'default',
    quiet = false,
  } = config;

  if (!scenarioPath) throw new Error('runEvaluation: scenario path is required');
  if (!Array.isArray(seeds) || seeds.length === 0) {
    throw new TypeError('runEvaluation: seeds must be a non-empty array');
  }
  if (!Number.isInteger(steps) || steps <= 0) {
    throw new RangeError('runEvaluation: steps must be a positive integer');
  }

  const log = quiet ? () => {} : (msg) => process.stderr.write(`[harness] ${msg}\n`);
  const scenario = loadScenario(scenarioPath);
  const initialPop = scenario.world?.initial_population ?? 20;

  // Load policy if provided.
  let policyObj = null;
  let policyName = 'default';
  if (policyPath) {
    policyObj = await loadPolicy(policyPath);
    policyName = policyObj.name;
    log(`loaded policy: ${policyName} from ${policyPath}`);
  }

  // Load baseline policy (or use null for built-in random walk).
  let baselineObj = null;
  let baselineName = 'default';
  if (baselineSpec !== 'default') {
    baselineObj = await loadPolicy(baselineSpec);
    baselineName = baselineObj.name;
    log(`loaded baseline: ${baselineName} from ${baselineSpec}`);
  }

  const perSeed = [];

  for (const seed of seeds) {
    log(`seed=${seed}: running policy="${policyName}" ...`);
    const policyResult = runSimulation({
      scenario, seed, steps,
      policy: policyObj,
    });
    const policyMetrics = computeAggregateMetrics(policyResult.ticks, initialPop, steps);

    log(`seed=${seed}: running baseline="${baselineName}" ...`);
    const baselineResult = runSimulation({
      scenario, seed, steps,
      policy: baselineObj,
    });
    const baselineMetrics = computeAggregateMetrics(baselineResult.ticks, initialPop, steps);

    const deltas = {
      survival_delta: policyMetrics.survival_rate - baselineMetrics.survival_rate,
      energy_delta: policyMetrics.mean_energy - baselineMetrics.mean_energy,
      efficiency_delta: policyMetrics.food_efficiency - baselineMetrics.food_efficiency,
    };

    perSeed.push({
      seed,
      policy: policyMetrics,
      baseline: baselineMetrics,
      deltas,
      verdict: computeVerdict(deltas),
    });
  }

  // Aggregate across seeds: average the deltas.
  const avgDeltas = {
    survival_delta: 0,
    energy_delta: 0,
    efficiency_delta: 0,
  };
  for (const s of perSeed) {
    avgDeltas.survival_delta += s.deltas.survival_delta;
    avgDeltas.energy_delta += s.deltas.energy_delta;
    avgDeltas.efficiency_delta += s.deltas.efficiency_delta;
  }
  const n = perSeed.length;
  avgDeltas.survival_delta /= n;
  avgDeltas.energy_delta /= n;
  avgDeltas.efficiency_delta /= n;

  const overallVerdict = computeVerdict(avgDeltas);

  return {
    policy_name: policyName,
    baseline_name: baselineName,
    scenario: scenario.name ?? scenarioPath,
    seeds,
    steps,
    per_seed: perSeed,
    metrics: avgDeltas,
    verdict: overallVerdict,
  };
}
