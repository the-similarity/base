#!/usr/bin/env node
/**
 * Tests for telemetry export utilities.
 *
 * Runs as a standalone Node script (no test framework needed). Each test
 * function returns void on success or throws on failure. A final summary
 * reports pass/fail counts.
 *
 * Usage:
 *   node tests/test-telemetry.js
 *
 * Exit codes:
 *   0  all tests passed
 *   1  at least one test failed
 */

import { writeFileSync, readFileSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { parseTelemetry, toCSV, diffRuns } from '../src/sim/telemetry-export.js';

// ── Test helpers ────────────────────────────────────────────────────────────

const testDir = join(tmpdir(), `telemetry-test-${Date.now()}`);
mkdirSync(testDir, { recursive: true });

function assert(cond, msg) {
  if (!cond) throw new Error(`Assertion failed: ${msg}`);
}

function assertEq(a, b, msg) {
  if (a !== b) throw new Error(`${msg}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}

/**
 * Write a minimal JSONL fixture to disk.
 * @param {string} name - Filename (no dir).
 * @param {object[]} lines - Array of objects, one per JSONL line.
 * @returns {string} Full path.
 */
function writeFixture(name, lines) {
  const path = join(testDir, name);
  writeFileSync(path, lines.map(l => JSON.stringify(l)).join('\n') + '\n', 'utf8');
  return path;
}

// ── Fixtures ────────────────────────────────────────────────────────────────

const PROVENANCE = {
  type: 'provenance',
  telemetry_version: '2.0',
  seed: 42,
  generator_name: 'the-similarity-fractal-headless',
  version: '0.1.0',
  scenario_name: 'test',
  scenario: { name: 'test' },
  params: { energy_decay: 0.01, move_speed: 1, food_spawn_rate: 0.05, food_energy: 0.3 },
  duration_steps: 3,
  created_at: '2026-04-15T00:00:00.000Z',
};

const TICKS = [
  { type: 'tick', tick: 1, metrics: { alive: 20, dead: 0, food_count: 1, mean_energy: 0.74, mean_age: 1, cumulative_deaths: 0, cumulative_food_eaten: 0, population_density: 0.00488, food_per_agent: 0.05, energy_variance: 0.008 } },
  { type: 'tick', tick: 2, metrics: { alive: 19, dead: 1, food_count: 2, mean_energy: 0.71, mean_age: 2, cumulative_deaths: 1, cumulative_food_eaten: 1, population_density: 0.00464, food_per_agent: 0.105, energy_variance: 0.012 } },
  { type: 'tick', tick: 3, metrics: { alive: 18, dead: 2, food_count: 1, mean_energy: 0.68, mean_age: 3, cumulative_deaths: 2, cumulative_food_eaten: 2, population_density: 0.0044, food_per_agent: 0.0556, energy_variance: 0.015 } },
];

const SUMMARY = {
  type: 'summary',
  final_metrics: { alive: 18, dead: 2, food_count: 1, mean_energy: 0.68, mean_age: 3, cumulative_deaths: 2, cumulative_food_eaten: 2, population_density: 0.0044, food_per_agent: 0.0556, energy_variance: 0.015 },
  totals: { deaths: 2, births: 0, food_eaten: 2 },
  wall_time_ms: 50,
};

// A second run with different seed — diverges at tick 2
const PROVENANCE_B = { ...PROVENANCE, seed: 99 };
const TICKS_B = [
  { type: 'tick', tick: 1, metrics: { alive: 20, dead: 0, food_count: 0, mean_energy: 0.73, mean_age: 1, cumulative_deaths: 0, cumulative_food_eaten: 0, population_density: 0.00488, food_per_agent: 0.0, energy_variance: 0.009 } },
  { type: 'tick', tick: 2, metrics: { alive: 20, dead: 0, food_count: 1, mean_energy: 0.72, mean_age: 2, cumulative_deaths: 0, cumulative_food_eaten: 0, population_density: 0.00488, food_per_agent: 0.05, energy_variance: 0.011 } },
  { type: 'tick', tick: 3, metrics: { alive: 19, dead: 1, food_count: 2, mean_energy: 0.70, mean_age: 3, cumulative_deaths: 1, cumulative_food_eaten: 1, population_density: 0.00464, food_per_agent: 0.105, energy_variance: 0.013 } },
];
const SUMMARY_B = {
  type: 'summary',
  final_metrics: { alive: 19, dead: 1, food_count: 2, mean_energy: 0.70, mean_age: 3, cumulative_deaths: 1, cumulative_food_eaten: 1, population_density: 0.00464, food_per_agent: 0.105, energy_variance: 0.013 },
  totals: { deaths: 1, births: 0, food_eaten: 1 },
  wall_time_ms: 45,
};

// ── Tests ───────────────────────────────────────────────────────────────────

function test_parseTelemetry_reads_jsonl() {
  const path = writeFixture('run_a.jsonl', [PROVENANCE, ...TICKS, SUMMARY]);
  const result = parseTelemetry(path);

  assert(result.provenance !== null, 'provenance should not be null');
  assertEq(result.provenance.seed, 42, 'provenance.seed');
  assertEq(result.provenance.telemetry_version, '2.0', 'telemetry_version');
  assertEq(result.ticks.length, 3, 'tick count');
  assertEq(result.ticks[0].tick, 1, 'first tick number');
  assertEq(result.ticks[2].metrics.alive, 18, 'last tick alive');
  assert(result.summary !== null, 'summary should not be null');
  assertEq(result.summary.wall_time_ms, 50, 'wall_time_ms');
}

function test_parseTelemetry_handles_partial_file() {
  // Simulate a crash: no summary line, and a corrupt last line
  const path = writeFixture('partial.jsonl', [
    PROVENANCE,
    TICKS[0],
    // Corrupt line — should be skipped
  ]);
  // Append a corrupt line manually
  const content = readFileSync(path, 'utf8') + '{bad json\n';
  writeFileSync(path, content, 'utf8');

  const result = parseTelemetry(path);
  assert(result.provenance !== null, 'provenance should exist');
  assertEq(result.ticks.length, 1, 'should have 1 valid tick');
  assert(result.summary === null, 'summary should be null for partial file');
}

function test_toCSV_produces_valid_csv() {
  const csvPath = join(testDir, 'ticks.csv');
  const csv = toCSV(TICKS, csvPath);

  const lines = csv.trim().split('\n');
  assertEq(lines.length, 4, 'CSV should have 1 header + 3 data rows');

  // Header should contain tick and all metric keys
  const header = lines[0].split(',');
  assert(header.includes('tick'), 'header should have tick column');
  assert(header.includes('alive'), 'header should have alive column');
  assert(header.includes('population_density'), 'header should have population_density');
  assert(header.includes('energy_variance'), 'header should have energy_variance');

  // First data row — alive should be 20
  const firstRow = lines[1].split(',');
  const aliveIdx = header.indexOf('alive');
  assertEq(firstRow[aliveIdx], '20', 'first row alive should be 20');

  // Verify file was actually written
  const fromDisk = readFileSync(csvPath, 'utf8');
  assertEq(fromDisk, csv, 'CSV on disk should match returned string');
}

function test_diffRuns_detects_divergence() {
  const pathA = writeFixture('diff_a.jsonl', [PROVENANCE, ...TICKS, SUMMARY]);
  const pathB = writeFixture('diff_b.jsonl', [PROVENANCE_B, ...TICKS_B, SUMMARY_B]);

  const runA = parseTelemetry(pathA);
  const runB = parseTelemetry(pathB);
  const diff = diffRuns(runA, runB);

  // Seeds should be reported
  assertEq(diff.seeds.a, 42, 'seed A');
  assertEq(diff.seeds.b, 99, 'seed B');

  // Tick counts
  assertEq(diff.tick_counts.a, 3, 'tick count A');
  assertEq(diff.tick_counts.b, 3, 'tick count B');

  // Divergence should be at tick 2 (run A has alive=19, run B has alive=20)
  assertEq(diff.tick_divergence_point, 2, 'divergence at tick 2');
  assertEq(diff.divergence_details.a.alive, 19, 'run A alive at divergence');
  assertEq(diff.divergence_details.b.alive, 20, 'run B alive at divergence');

  // Summary deltas should exist
  assert(diff.metrics_delta !== null, 'metrics_delta should exist');
  // alive delta: B(19) - A(18) = 1
  assertEq(diff.metrics_delta.alive.abs_delta, 1, 'alive abs_delta');
  // total deaths: B(1) - A(2) = -1
  assertEq(diff.metrics_delta.total_deaths.abs_delta, -1, 'total_deaths abs_delta');
}

function test_diffRuns_identical_runs() {
  const pathA = writeFixture('same_a.jsonl', [PROVENANCE, ...TICKS, SUMMARY]);
  const pathB = writeFixture('same_b.jsonl', [PROVENANCE, ...TICKS, SUMMARY]);

  const runA = parseTelemetry(pathA);
  const runB = parseTelemetry(pathB);
  const diff = diffRuns(runA, runB);

  assert(diff.tick_divergence_point === null, 'identical runs should not diverge');
  assertEq(diff.metrics_delta.alive.abs_delta, 0, 'identical runs alive delta should be 0');
}

// ── Runner ──────────────────────────────────────────────────────────────────

const tests = [
  test_parseTelemetry_reads_jsonl,
  test_parseTelemetry_handles_partial_file,
  test_toCSV_produces_valid_csv,
  test_diffRuns_detects_divergence,
  test_diffRuns_identical_runs,
];

let passed = 0;
let failed = 0;

for (const t of tests) {
  try {
    t();
    passed++;
    process.stdout.write(`  PASS  ${t.name}\n`);
  } catch (e) {
    failed++;
    process.stderr.write(`  FAIL  ${t.name}: ${e.message}\n`);
  }
}

// Cleanup temp dir
try { rmSync(testDir, { recursive: true, force: true }); } catch { /* ignore */ }

process.stdout.write(`\n${passed} passed, ${failed} failed out of ${tests.length}\n`);
process.exit(failed > 0 ? 1 : 0);
