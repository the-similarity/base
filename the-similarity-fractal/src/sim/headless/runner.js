#!/usr/bin/env node
/**
 * Headless synthetic-worlds runner — CLI entrypoint.
 *
 * Usage:
 *   node src/sim/headless/runner.js --scenario scenarios/small_village.json \
 *                                   --seed 42 --steps 500 --out runs/foo.jsonl
 *
 *   # via package script:
 *   npm run sim:headless -- --scenario scenarios/small_village.json --out runs/foo.jsonl
 *
 * Flags:
 *   --scenario <path>    (required) path to a scenario JSON file
 *   --seed <int>         override scenario.seed (default: scenario.seed or 42)
 *   --steps <int>        override scenario.steps (number of ticks to run)
 *   --duration <int>     alias for --steps
 *   --out <path>         JSONL output path (default: runs/<scenario>-<seed>.jsonl)
 *   --include-state      emit per-agent state on every tick (larger output)
 *   --state-every <n>    emit per-agent state every n ticks (default: never)
 *   --quiet              suppress stdout progress logs
 *
 * This runner is a pure Node script — no bundler, no transpiler, no external
 * deps. It imports the minimal headless world module (no THREE.js, no DOM).
 *
 * Exit codes:
 *   0  success
 *   1  argument error / scenario load error
 *   2  runtime error mid-simulation
 */

import { createWorld, stepWorld, summarizeWorld } from './world.js';
import { loadScenario } from './scenario.js';
import { TelemetryWriter } from './telemetry.js';
import { basename, dirname, resolve as resolvePath } from 'node:path';
import { registerWorldRun } from '../../platform/registry-client.js';

/**
 * Parse a minimal GNU-style flag set. Deliberately hand-rolled to avoid
 * pulling in commander/yargs for a ~6-flag CLI. Unknown flags throw so typos
 * do not silently become no-ops.
 */
function parseArgs(argv) {
  const out = {
    includeState: false,
    stateEvery: 0,
    quiet: false,
    register: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '--scenario':   out.scenario = argv[++i]; break;
      case '--seed':       out.seed = Number(argv[++i]); break;
      case '--steps':
      case '--duration':   out.steps = Number(argv[++i]); break;
      case '--out':        out.out = argv[++i]; break;
      case '--include-state': out.includeState = true; break;
      case '--state-every':   out.stateEvery = Number(argv[++i]); break;
      case '--quiet':      out.quiet = true; break;
      // --register is best-effort: POST to the platform registry after the
      // simulation finishes. A missing or unreachable API server is logged
      // to stderr and ignored; the runner still exits 0.
      case '--register':   out.register = true; break;
      case '--api-url':    out.apiUrl = argv[++i]; break;
      case '-h':
      case '--help':       out.help = true; break;
      default:
        throw new Error(`Unknown flag: ${a}`);
    }
  }
  return out;
}

function printHelp() {
  // Keep help text in sync with the top-of-file docstring — single source of
  // truth for flag names and defaults.
  process.stdout.write(
`Headless synthetic-worlds runner

  --scenario <path>   (required) scenario JSON
  --seed <int>        override scenario seed
  --steps <int>       number of ticks (alias: --duration)
  --out <path>        JSONL output path
  --include-state     dump per-agent state every tick
  --state-every <n>   dump per-agent state every n ticks
  --register          POST the finished run to the platform registry
                      (best-effort; warns on failure, exit 0)
  --api-url <url>     platform API base URL (default: $THE_SIMILARITY_API_URL
                      or http://localhost:8787)
  --quiet             no stdout progress

Exit codes: 0 ok, 1 arg error, 2 runtime error
`);
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (e) {
    process.stderr.write(`error: ${e.message}\n`);
    printHelp();
    process.exit(1);
  }

  if (args.help) { printHelp(); process.exit(0); }

  if (!args.scenario) {
    process.stderr.write('error: --scenario is required\n');
    printHelp();
    process.exit(1);
  }

  // Load + merge CLI overrides. CLI always wins over scenario file values so
  // sweeps can pin seed/steps from the shell without editing JSON.
  let scenario;
  try {
    scenario = loadScenario(args.scenario);
  } catch (e) {
    process.stderr.write(`error: ${e.message}\n`);
    process.exit(1);
  }

  const seed = Number.isFinite(args.seed) ? args.seed : (scenario.seed ?? 42);
  const steps = Number.isFinite(args.steps)
    ? args.steps
    : (scenario.steps ?? 500);

  // Default output path mirrors the input scenario name so batch runs are
  // easy to correlate with their source config.
  const outPath = args.out
    ?? `runs/${basename(args.scenario, '.json')}-seed${seed}.jsonl`;

  const log = args.quiet ? () => {} : (msg) => process.stdout.write(`${msg}\n`);

  log(`[worlds] scenario=${scenario.name} seed=${seed} steps=${steps} out=${outPath}`);

  const world = createWorld(scenario, seed);
  const writer = new TelemetryWriter(outPath);

  writer.writeProvenance({
    seed,
    scenario,
    params: world.params,
    durationSteps: steps,
  });

  const startMs = Date.now();
  try {
    for (let t = 0; t < steps; t++) {
      stepWorld(world);
      const metrics = summarizeWorld(world);

      // State emission policy: either every tick (--include-state), every N
      // ticks (--state-every N), or never. Keeps default output compact.
      let state;
      if (args.includeState
          || (args.stateEvery > 0 && world.tick % args.stateEvery === 0)) {
        state = {
          agents: world.agents.map((a) => ({
            id: a.id, x: a.x, y: a.y,
            energy: a.energy, alive: a.alive, age: a.age,
          })),
          food: world.food.slice(),
        };
      }

      writer.writeTick(world.tick, metrics, state);

      // Light progress log every ~10% so a user running interactively sees
      // something, but the output is bounded in CI/batch mode.
      if (!args.quiet && steps >= 10 && t % Math.max(1, Math.floor(steps / 10)) === 0) {
        log(`[worlds] tick=${world.tick}/${steps} alive=${metrics.alive} food=${metrics.food_count}`);
      }
    }

    const wallMs = Date.now() - startMs;
    writer.writeSummary(summarizeWorld(world), world.totals, wallMs);
    log(`[worlds] done in ${wallMs}ms — ${writer.lineCount} lines -> ${outPath}`);
  } catch (e) {
    process.stderr.write(`runtime error at tick=${world.tick}: ${e.stack || e.message}\n`);
    await writer.close();
    process.exit(2);
  } finally {
    // Must close before reading back for registration — the writer flushes
    // asynchronously and partial reads would miss the final summary line.
    await writer.close();
  }

  // Post-run registration. Guarded by --register so default behavior is
  // byte-identical to the pre-adapter runner. Any failure here is logged
  // and swallowed: the simulation already succeeded and the JSONL file
  // is the primary artifact — a missing registry row is an ops
  // inconvenience, not a data-loss event.
  if (args.register) {
    try {
      const absOut = resolvePath(outPath);
      const runId = await registerWorldRun({
        runDir: dirname(absOut),
        jsonlPath: absOut,
        scenario: args.scenario,
        seed,
        steps,
        apiUrl: args.apiUrl,
        log: (msg) => process.stderr.write(`${msg}\n`),
      });
      if (runId) {
        log(`[worlds] registered run_id=${runId}`);
      } else {
        log('[worlds] registration skipped (see stderr for reason)');
      }
    } catch (err) {
      // Defensive: registerWorldRun already traps errors internally. If
      // a new failure mode slips through we STILL want the process to
      // exit 0 — the simulation output is intact on disk.
      process.stderr.write(`[worlds] registration error (ignored): ${err.message}\n`);
    }
  }
}

main();
