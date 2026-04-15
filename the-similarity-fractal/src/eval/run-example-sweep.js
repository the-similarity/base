/**
 * Example world-eval sweep — 2×3 knob grid, 3 seeds, short run.
 *
 * Loads `scenarios/small_village.json` as the base scenario (matches the
 * team-lead spec), then sweeps `food_spawn_rate × energy_decay` × 3 seeds
 * using the headless runner CLI. Produces a reference artifact under
 * `the-similarity-fractal/artifacts/sweep-example/sweep-example/` so PR
 * reviewers can see what a world-eval scorecard actually looks like.
 *
 * Usage:
 *   node src/eval/run-example-sweep.js
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve, join } from 'node:path';

import {
  runSweep,
  summarizeRegimeCoverage,
  controllability,
  buildScorecard,
  writeScorecard,
  makeProvenance,
} from './index.js';

async function main() {
  const here = dirname(fileURLToPath(import.meta.url));
  const pkgRoot = resolve(here, '../..');
  const scenarioPath = join(pkgRoot, 'scenarios/small_village.json');
  const baseScenario = JSON.parse(readFileSync(scenarioPath, 'utf8'));

  // 2 × 3 grid × 3 seeds = 18 cells. Per team-lead guidance the chosen
  // knob pair is food_spawn_rate × energy_decay — the two knobs we expect
  // strongest controllability signal on (food availability vs metabolism).
  const knobGrid = {
    food_spawn_rate: [0.05, 0.15],         // sparse vs. abundant food
    energy_decay:    [0.005, 0.01, 0.02],  // slow, default, fast metabolism
  };
  const seeds = [1, 2, 3];
  const steps = 150;

  const sweepId = 'example';
  // Let the sweep use a tmpdir for per-cell JSONL + scenario files and
  // clean them up after reading — the committed artifact only needs the
  // aggregated telemetry.jsonl + scorecard.json.
  const t0 = Date.now();
  const { cells, telemetry } = runSweep({
    baseScenario, knobGrid, seeds, steps, keepWorkDir: false,
  });
  const runtimeMs = Date.now() - t0;

  const regimeCoverage = summarizeRegimeCoverage(telemetry, {
    initialPop: baseScenario.world.initial_population,
    knobNames: Object.keys(knobGrid),
  });

  // Fix the permutation-test seed so the committed scorecard's p-values are
  // stable across re-runs. This is documented on the provenance record.
  const permSeed = Math.min(...seeds);
  const controllabilityReport = controllability(telemetry, {
    knobNames: Object.keys(knobGrid),
    nPerm: 500,
    seed: permSeed,
  });

  const provenance = makeProvenance({
    sourceId: baseScenario.name ?? 'worlds-headless',
    generatorName: 'worlds_headless',
    generatorVersion: '0.1.0',
    seed: permSeed,
    params: { baseScenario, knobGrid, seeds, steps, runtime_ms: runtimeMs },
  });

  const scorecard = buildScorecard({
    scenario: baseScenario,
    knobGrid,
    seeds,
    ticks: steps,
    regimeCoverage,
    controllability: controllabilityReport,
    provenance,
    sweepId,
  });

  const outDir = join(pkgRoot, `artifacts/sweep-${sweepId}`);
  const wrote = await writeScorecard({ outDir, scorecard, telemetry, cells });

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
