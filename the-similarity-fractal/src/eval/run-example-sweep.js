/**
 * Example world-eval sweep — 2×3 knob grid, 3 seeds, short run.
 *
 * Produces a reference artifact at
 * `the-similarity-fractal/artifacts/sweep-example/sweep-example/` so that
 * reviewers (and CI) can see what a world-eval scorecard actually looks
 * like without having to run the sweep themselves.
 *
 * This script is intentionally small and dependency-free — it runs under
 * plain `node` with no build step. Invoked manually:
 *
 *     node src/eval/run-example-sweep.js
 *
 * It writes to `artifacts/sweep-example/` under the package root.
 */

import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  runSweep,
  summarizeRegimeCoverage,
  controllability,
  buildScorecard,
  writeScorecard,
  makeProvenance,
} from './index.js';

async function main() {
  // Base scenario — matches the headless world defaults, spelled out here so
  // the artifact is self-documenting (a reader can see exactly what was run).
  const baseScenario = {
    world: {
      size: 48,
      initial_population: 24,
    },
    params: {
      energy_decay: 0.01,
      move_speed: 1,
      food_spawn_rate: 0.05,
      food_energy: 0.3,
    },
  };

  // 2 × 3 grid = 6 cells, × 3 seeds = 18 runs. Short (120 ticks) so the
  // example completes in well under a second on typical hardware.
  const knobGrid = {
    food_spawn_rate: [0.02, 0.08],         // low vs. high food pressure
    energy_decay:    [0.005, 0.01, 0.02],  // slow, default, fast metabolism
  };
  const seeds = [1, 2, 3];
  const ticks = 120;

  const t0 = Date.now();
  const { cells, telemetry } = runSweep({ baseScenario, knobGrid, seeds, ticks });
  const runtimeMs = Date.now() - t0;

  const regimeCoverage = summarizeRegimeCoverage(telemetry, {
    initialPop: baseScenario.world.initial_population,
    knobNames: Object.keys(knobGrid),
  });

  // Use the lowest seed as the permutation-test seed so the p-values in the
  // artifact are stable across re-runs — documented explicitly on the
  // provenance record.
  const permSeed = Math.min(...seeds);
  const controllabilityReport = controllability(telemetry, {
    knobNames: Object.keys(knobGrid),
    nPerm: 500,
    seed: permSeed,
  });

  const provenance = makeProvenance({
    sourceId: 'worlds-headless-minimal',
    generatorName: 'worlds_headless',
    generatorVersion: '0.1.0',
    seed: permSeed,
    params: { baseScenario, knobGrid, seeds, ticks, runtime_ms: runtimeMs },
  });

  const scorecard = buildScorecard({
    scenario: baseScenario,
    knobGrid,
    seeds,
    ticks,
    regimeCoverage,
    controllability: controllabilityReport,
    provenance,
    sweepId: 'example',
  });

  const outDir = resolve(dirname(fileURLToPath(import.meta.url)), '../../artifacts/sweep-example');
  const wrote = await writeScorecard({
    outDir,
    scorecard,
    telemetry,
    cells,
  });

  // Single-line result summary — meant to be parseable by CI / orchestrator
  // log tailing without pulling in a JSON parser.
  console.log(JSON.stringify({
    ok: true,
    wrote,
    n_cells: cells.length,
    n_rows: telemetry.length,
    global_coverage: regimeCoverage.global.coverage,
    runtime_ms: runtimeMs,
  }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
