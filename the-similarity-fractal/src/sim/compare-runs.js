#!/usr/bin/env node
/**
 * Cross-run telemetry comparison CLI.
 *
 * Usage:
 *   node src/sim/compare-runs.js --runs run1.jsonl,run2.jsonl --out comparison.json
 *
 * Compares exactly two headless runner JSONL outputs and writes a structured
 * diff report as JSON. The report includes:
 *   - Per-metric absolute and relative deltas at summary level
 *   - The first tick where alive/dead counts diverge between runs
 *   - Seed and tick-count metadata for both runs
 *
 * Exit codes:
 *   0  success
 *   1  argument or file-read error
 */

import { resolve } from 'node:path';
import { writeFileSync } from 'node:fs';
import { parseTelemetry, diffRuns } from './telemetry-export.js';

/**
 * Parse CLI arguments. Deliberately minimal — no external deps.
 */
function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '--runs':
        out.runs = argv[++i];
        break;
      case '--out':
        out.out = argv[++i];
        break;
      case '-h':
      case '--help':
        out.help = true;
        break;
      default:
        throw new Error(`Unknown flag: ${a}`);
    }
  }
  return out;
}

function printHelp() {
  process.stdout.write(
`Cross-run telemetry comparison

  --runs <a.jsonl,b.jsonl>  (required) comma-separated paths to two JSONL runs
  --out <path.json>         (required) output path for the comparison report

Exit codes: 0 ok, 1 arg/file error
`);
}

function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (e) {
    process.stderr.write(`error: ${e.message}\n`);
    printHelp();
    process.exit(1);
  }

  if (args.help) { printHelp(); process.exit(0); }

  if (!args.runs) {
    process.stderr.write('error: --runs is required\n');
    printHelp();
    process.exit(1);
  }
  if (!args.out) {
    process.stderr.write('error: --out is required\n');
    printHelp();
    process.exit(1);
  }

  const paths = args.runs.split(',').map(p => resolve(p.trim()));
  if (paths.length !== 2) {
    process.stderr.write('error: --runs must specify exactly two comma-separated JSONL paths\n');
    process.exit(1);
  }

  // Parse both runs. Errors here surface as file-not-found or JSON parse
  // failures, both of which are exit-code 1.
  let runA, runB;
  try {
    runA = parseTelemetry(paths[0]);
  } catch (e) {
    process.stderr.write(`error reading run A (${paths[0]}): ${e.message}\n`);
    process.exit(1);
  }
  try {
    runB = parseTelemetry(paths[1]);
  } catch (e) {
    process.stderr.write(`error reading run B (${paths[1]}): ${e.message}\n`);
    process.exit(1);
  }

  // Compute the diff report
  const report = diffRuns(runA, runB);

  // Add file paths for traceability
  report.files = { a: paths[0], b: paths[1] };

  const outPath = resolve(args.out);
  writeFileSync(outPath, JSON.stringify(report, null, 2) + '\n', 'utf8');

  process.stdout.write(`[compare] wrote ${outPath}\n`);
  if (report.tick_divergence_point !== null) {
    process.stdout.write(
      `[compare] runs diverge at tick ${report.tick_divergence_point}\n`
    );
  } else {
    process.stdout.write('[compare] runs have identical alive/dead trajectories\n');
  }
}

main();
