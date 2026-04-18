#!/usr/bin/env node
/**
 * Eval harness CLI — run a policy against a baseline on a world scenario.
 *
 * Usage:
 *   node src/eval/run-eval.js \
 *     --scenario scenarios/small_village.json \
 *     --policy policies/greedy.js \
 *     --seeds 42,314 \
 *     --steps 200 \
 *     --out eval-results/
 *
 * Flags:
 *   --scenario <path>   (required) path to a scenario JSON file
 *   --policy <path>     path to a policy JS module (omit for baseline-only run)
 *   --baseline <path>   "default" (built-in random walk) or path to a policy module
 *   --seeds <list>      comma-separated seed list (default: 42)
 *   --steps <int>       number of ticks per run (default: from scenario or 200)
 *   --out <dir>         output directory for scorecard + summary (default: ./eval-results)
 *   --quiet             suppress progress logs
 *   -h, --help          show this help
 *
 * Output:
 *   <out>/eval_scorecard.json   — machine-readable evaluation results
 *   <out>/eval_summary.md       — human-readable markdown summary
 *
 * Exit codes:
 *   0  success
 *   1  argument or load error
 *
 * @module eval/run-eval
 */

import { runEvaluation } from './harness.js';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Parse CLI arguments. Hand-rolled to avoid external dependencies.
 */
function parseArgs(argv) {
  const out = {
    seeds: [42],
    steps: null,
    baseline: 'default',
    outDir: 'eval-results',
    quiet: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case '--scenario':  out.scenario = argv[++i]; break;
      case '--policy':    out.policy = argv[++i]; break;
      case '--baseline':  out.baseline = argv[++i]; break;
      case '--seeds':     out.seeds = argv[++i].split(',').map(Number); break;
      case '--steps':     out.steps = Number(argv[++i]); break;
      case '--out':       out.outDir = argv[++i]; break;
      case '--quiet':     out.quiet = true; break;
      case '-h':
      case '--help':      out.help = true; break;
      default:
        throw new Error(`Unknown flag: ${a}`);
    }
  }
  return out;
}

function printHelp() {
  process.stdout.write(
`Eval harness CLI — evaluate a policy against a baseline

  --scenario <path>   (required) scenario JSON
  --policy <path>     policy JS module to evaluate
  --baseline <path>   baseline policy or "default" for random walk
  --seeds <list>      comma-separated seed list (default: 42)
  --steps <int>       number of ticks (default: scenario value or 200)
  --out <dir>         output directory (default: eval-results/)
  --quiet             suppress progress logs

Exit codes: 0 ok, 1 error
`);
}

/**
 * Generate a human-readable markdown summary from the scorecard.
 *
 * @param {object} scorecard - Output from runEvaluation().
 * @returns {string} Markdown-formatted summary.
 */
function generateSummary(scorecard) {
  const lines = [];
  lines.push(`# Eval Summary`);
  lines.push('');
  lines.push(`**Scenario:** ${scorecard.scenario}`);
  lines.push(`**Policy:** ${scorecard.policy_name}`);
  lines.push(`**Baseline:** ${scorecard.baseline_name}`);
  lines.push(`**Seeds:** ${scorecard.seeds.join(', ')}`);
  lines.push(`**Steps:** ${scorecard.steps}`);
  lines.push(`**Verdict:** ${scorecard.verdict.toUpperCase()}`);
  lines.push('');

  // Aggregate deltas table.
  lines.push('## Aggregate Deltas (policy - baseline)');
  lines.push('');
  lines.push('| Metric | Delta |');
  lines.push('|--------|-------|');
  lines.push(`| Survival Rate | ${fmt(scorecard.metrics.survival_delta)} |`);
  lines.push(`| Mean Energy | ${fmt(scorecard.metrics.energy_delta)} |`);
  lines.push(`| Food Efficiency | ${fmt(scorecard.metrics.efficiency_delta)} |`);
  lines.push('');

  // Per-seed breakdown.
  lines.push('## Per-Seed Results');
  lines.push('');
  for (const s of scorecard.per_seed) {
    lines.push(`### Seed ${s.seed} — ${s.verdict}`);
    lines.push('');
    lines.push('| Metric | Policy | Baseline | Delta |');
    lines.push('|--------|--------|----------|-------|');
    lines.push(`| Survival Rate | ${fmt(s.policy.survival_rate)} | ${fmt(s.baseline.survival_rate)} | ${fmt(s.deltas.survival_delta)} |`);
    lines.push(`| Mean Energy | ${fmt(s.policy.mean_energy)} | ${fmt(s.baseline.mean_energy)} | ${fmt(s.deltas.energy_delta)} |`);
    lines.push(`| Food Efficiency | ${fmt(s.policy.food_efficiency)} | ${fmt(s.baseline.food_efficiency)} | ${fmt(s.deltas.efficiency_delta)} |`);
    lines.push('');
  }

  return lines.join('\n');
}

/** Format a number to 4 decimal places with sign. */
function fmt(n) {
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(4)}`;
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

  // Default steps: read from scenario if not specified via CLI.
  let steps = args.steps;
  if (!Number.isFinite(steps) || steps <= 0) {
    // Attempt to read from scenario file — fallback to 200.
    try {
      const { readFileSync } = await import('node:fs');
      const sc = JSON.parse(readFileSync(resolve(args.scenario), 'utf8'));
      steps = sc.steps ?? 200;
    } catch {
      steps = 200;
    }
  }

  const scorecard = await runEvaluation({
    scenario: args.scenario,
    seeds: args.seeds,
    steps,
    policy: args.policy ?? null,
    baseline: args.baseline,
    quiet: args.quiet,
  });

  // Write outputs.
  const outDir = resolve(args.outDir);
  mkdirSync(outDir, { recursive: true });

  const scorecardPath = resolve(outDir, 'eval_scorecard.json');
  writeFileSync(scorecardPath, JSON.stringify(scorecard, null, 2) + '\n');

  const summaryPath = resolve(outDir, 'eval_summary.md');
  writeFileSync(summaryPath, generateSummary(scorecard) + '\n');

  // Print result to stdout for piping.
  const log = args.quiet ? () => {} : (msg) => process.stderr.write(`${msg}\n`);
  log(`[eval] wrote ${scorecardPath}`);
  log(`[eval] wrote ${summaryPath}`);
  log(`[eval] verdict: ${scorecard.verdict}`);

  // Print scorecard to stdout so callers can pipe to jq etc.
  process.stdout.write(JSON.stringify(scorecard, null, 2) + '\n');
}

main().catch((err) => {
  process.stderr.write(`error: ${err.stack || err.message}\n`);
  process.exit(1);
});
