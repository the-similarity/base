/**
 * Scenario sweep runner — grid over scenario knobs × seed list.
 *
 * Invokes the headless worlds runner (`src/sim/headless/runner.js`) once per
 * (knobs, seed) cell. Each invocation writes a JSONL file with one
 * `provenance` line, N `tick` lines, and one `summary` line (schema defined
 * by the runner team in `src/sim/headless/telemetry.js`). This module reads
 * those files back in, flattens each tick into a single row, and returns a
 * structure downstream regime-coverage / controllability modules can
 * consume uniformly.
 *
 * Invocation contract (matches team-lead spec):
 *   npm run sim:headless -- --scenario <path> --seed S --steps N --out <file.jsonl>
 *
 * We use `node <runner.js>` directly instead of `npm run` to avoid npm's
 * wrapper overhead on each cell (sweeps with ~18 cells otherwise spend
 * more time in npm shimming than in the simulation itself).
 *
 * Invariants:
 * - Sweeps are pure functions of (baseScenario, knobGrid, seeds, steps).
 *   Re-running the same sweep produces identical telemetry rows (tick,
 *   metrics) bit-for-bit. The runner's provenance `created_at` timestamp
 *   is the only per-invocation mutable field and is stripped from
 *   regime/controllability inputs.
 * - Cells are executed sequentially. Determinism > throughput for the MVP;
 *   parallel invocation would require tagging temp paths with a cell id to
 *   avoid collisions, which we can add when grids get big enough to care.
 * - Temp scenarios and per-cell JSONL files are written under
 *   `<workDir>/sweep-<sweepId>/cell-<i>/` so concurrent sweeps don't clash
 *   and the artifact directory is self-contained (easy to archive / attach
 *   to a PR).
 *
 * Flattened row schema (produced by `flattenTicks`):
 *   { tick, seed, <knobs...>, alive, dead, food_count, mean_energy,
 *     mean_age, cumulative_deaths, cumulative_food_eaten }
 * — matches `summarizeWorld()` keys + cell identity so regime-coverage and
 * controllability modules don't need to know about the runner's JSONL shape.
 *
 * @module eval/sweep
 */

import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));
/** Absolute path to the headless runner entrypoint. */
const RUNNER_PATH = resolve(__dirname, '../sim/headless/runner.js');

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
 * Overlay a knob-value map onto a base scenario. Knobs under `params` go
 * into `scenario.params`; knobs prefixed `world.` go into `scenario.world`.
 * These are the two sub-trees the runner's scenario schema exposes today —
 * see `scenarios/small_village.json` for the canonical example.
 */
export function applyKnobs(baseScenario, knobs) {
  const out = {
    ...baseScenario,
    world: { ...(baseScenario.world ?? {}) },
    params: { ...(baseScenario.params ?? {}) },
  };
  for (const [k, v] of Object.entries(knobs)) {
    if (k.startsWith('world.')) {
      out.world[k.slice('world.'.length)] = v;
    } else {
      // Default path: knob lives in params. If a knob name accidentally
      // collides with a top-level scenario key, params wins — matches how a
      // user would reason about "tune a scenario knob."
      out.params[k] = v;
    }
  }
  return out;
}

/**
 * Parse a runner JSONL file into {provenance, ticks[], summary}.
 * Throws on malformed input — we never want a silent partial read to mask
 * a crashed runner.
 */
export function parseRunnerJsonl(path) {
  const text = readFileSync(path, 'utf8');
  const lines = text.split('\n').filter((l) => l.length > 0);
  let provenance = null;
  const ticks = [];
  let summary = null;
  for (const line of lines) {
    const rec = JSON.parse(line);
    if (rec.type === 'provenance') provenance = rec;
    else if (rec.type === 'tick') ticks.push(rec);
    else if (rec.type === 'summary') summary = rec;
    else throw new Error(`Unknown JSONL record type: ${rec.type}`);
  }
  if (!provenance) throw new Error(`No provenance line in ${path}`);
  return { provenance, ticks, summary };
}

/**
 * Flatten runner tick records into the row schema used by regime-coverage
 * and controllability. `knobs` and `seed` are injected so a row is
 * self-identifying once it joins the sweep-wide telemetry array.
 */
export function flattenTicks(ticks, { knobs, seed }) {
  const rows = new Array(ticks.length);
  for (let i = 0; i < ticks.length; i++) {
    const t = ticks[i];
    rows[i] = { tick: t.tick, seed, ...knobs, ...t.metrics };
  }
  return rows;
}

/**
 * Invoke the headless runner for a single (scenario, seed) pair. Writes a
 * scenario JSON + JSONL output under `workDir` and returns the JSONL path.
 * Exported for tests that want to inspect what the sweep is about to do.
 */
export function invokeRunner({
  scenario,
  seed,
  steps,
  workDir,
  runnerPath = RUNNER_PATH,
}) {
  mkdirSync(workDir, { recursive: true });
  const scenarioPath = join(workDir, 'scenario.json');
  const outPath = join(workDir, 'telemetry.jsonl');
  writeFileSync(scenarioPath, JSON.stringify(scenario, null, 2));

  // spawnSync + --quiet keeps stderr clean and avoids progress-log noise
  // from leaking into the sweep's own stdout. Using `node` directly (not
  // `npm run`) shaves ~200ms per cell.
  const res = spawnSync(process.execPath, [
    runnerPath,
    '--scenario', scenarioPath,
    '--seed', String(seed),
    '--steps', String(steps),
    '--out', outPath,
    '--quiet',
  ], { encoding: 'utf8' });

  if (res.status !== 0) {
    // Surface runner stderr verbatim — the runner's error messages already
    // include tick number and scenario context, which is exactly what a
    // sweep user needs to debug.
    throw new Error(
      `runner failed (exit ${res.status}) for seed=${seed}: ${res.stderr || res.stdout}`,
    );
  }
  return outPath;
}

/**
 * Execute a single sweep cell. Returns {rows, provenance, summary, jsonlPath}.
 * Does NOT delete the JSONL file — the caller decides whether to archive
 * it into the sweep artifact or clean up.
 */
export function runCell({ baseScenario, knobs, seed, steps, workDir }) {
  if (!Number.isInteger(steps) || steps <= 0) {
    throw new RangeError(`runCell: steps must be a positive integer, got ${steps}`);
  }
  const scenario = applyKnobs(baseScenario, knobs);
  const jsonlPath = invokeRunner({ scenario, seed, steps, workDir });
  const { provenance, ticks, summary } = parseRunnerJsonl(jsonlPath);
  const rows = flattenTicks(ticks, { knobs, seed });
  return { rows, provenance, summary, jsonlPath };
}

/**
 * Run the full sweep: cartesian product of knob grid × seed list.
 *
 * @param {object} opts
 * @param {object} opts.baseScenario - Base scenario object (same shape as
 *   `scenarios/small_village.json`).
 * @param {object} opts.knobGrid - `{knob: [values...]}` to vary.
 * @param {number[]} opts.seeds - Seed list (non-empty).
 * @param {number} opts.steps - Tick count per cell.
 * @param {string} [opts.workDir] - Directory for per-cell scenario + JSONL
 *   files. Defaults to a unique subdir of `os.tmpdir()`.
 * @param {boolean} [opts.keepWorkDir=true] - If false, the workDir is
 *   deleted after reading. Set true when you want to archive JSONL files
 *   alongside the scorecard artifact.
 *
 * @returns {{cells, telemetry, cellArtifacts}}
 *   cells: [{ knobs, seed, n_rows, final_metrics, totals }]
 *   telemetry: flat [{tick, seed, ...knobs, ...metrics}]
 *   cellArtifacts: [{ knobs, seed, jsonlPath, provenance }]
 */
export function runSweep({
  baseScenario,
  knobGrid,
  seeds,
  steps,
  workDir,
  keepWorkDir = true,
}) {
  if (!Array.isArray(seeds) || seeds.length === 0) {
    throw new TypeError('runSweep: seeds must be a non-empty array of integers');
  }
  const cells = enumerateGrid(knobGrid);
  const sweepDir = workDir ?? join(tmpdir(), `world-eval-sweep-${process.pid}-${Date.now()}`);
  mkdirSync(sweepDir, { recursive: true });

  const telemetry = [];
  const cellRecords = [];
  const cellArtifacts = [];

  let cellIdx = 0;
  for (const knobs of cells) {
    for (const seed of seeds) {
      const cellWorkDir = join(sweepDir, `cell-${String(cellIdx).padStart(4, '0')}`);
      const { rows, provenance, summary, jsonlPath } = runCell({
        baseScenario, knobs, seed, steps, workDir: cellWorkDir,
      });
      cellRecords.push({
        knobs,
        seed,
        n_rows: rows.length,
        final_metrics: summary?.final_metrics ?? null,
        totals: summary?.totals ?? null,
      });
      cellArtifacts.push({ knobs, seed, jsonlPath, provenance });
      for (const r of rows) telemetry.push(r);
      cellIdx += 1;
    }
  }

  if (!keepWorkDir) {
    // Best-effort cleanup — a failed rm shouldn't fail the sweep since the
    // telemetry is already in memory and the artifact has been produced.
    try { rmSync(sweepDir, { recursive: true, force: true }); } catch { /* ignore */ }
  }

  return { cells: cellRecords, telemetry, cellArtifacts, workDir: sweepDir };
}
