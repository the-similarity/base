#!/usr/bin/env node
/**
 * Tests for the eval harness — validates scorecard shape, policy loading,
 * baseline-only runs, and greedy policy behavior.
 *
 * Run:
 *   node tests/test-eval-harness.js
 *
 * Uses a lightweight assert-based test runner (no external deps). Each test
 * function is named `test_*` and throws on failure. The runner prints pass/fail
 * per test and exits with code 1 if any test fails.
 *
 * @module tests/test-eval-harness
 */

import { strict as assert } from 'node:assert';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runEvaluation } from '../src/eval/harness.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCENARIO_PATH = resolve(__dirname, '../scenarios/small_village.json');
const GREEDY_POLICY_PATH = resolve(__dirname, '../policies/greedy.js');

/** Required top-level fields on the scorecard. */
const REQUIRED_FIELDS = [
  'policy_name', 'baseline_name', 'scenario', 'seeds', 'steps',
  'per_seed', 'metrics', 'verdict',
];

/** Required metric delta fields. */
const REQUIRED_METRIC_FIELDS = [
  'survival_delta', 'energy_delta', 'efficiency_delta',
];

// ---------------------------------------------------------------------------
// Test 1: Baseline-only run (no external policy) produces valid scorecard
// ---------------------------------------------------------------------------
async function test_baseline_only_scorecard_shape() {
  const scorecard = await runEvaluation({
    scenario: SCENARIO_PATH,
    seeds: [42],
    steps: 50,
    quiet: true,
  });

  // All required fields present.
  for (const f of REQUIRED_FIELDS) {
    assert.ok(f in scorecard, `Missing field: ${f}`);
  }

  // Metric deltas present.
  for (const f of REQUIRED_METRIC_FIELDS) {
    assert.ok(f in scorecard.metrics, `Missing metric: ${f}`);
    assert.ok(typeof scorecard.metrics[f] === 'number', `metric ${f} should be a number`);
  }

  // Verdict is one of the valid values.
  assert.ok(
    ['better', 'worse', 'neutral'].includes(scorecard.verdict),
    `Invalid verdict: ${scorecard.verdict}`,
  );

  // When no policy is provided, both sides are "default" — deltas should be zero.
  assert.equal(scorecard.policy_name, 'default');
  assert.equal(scorecard.baseline_name, 'default');
  assert.equal(scorecard.metrics.survival_delta, 0, 'same policy vs same baseline should have 0 survival delta');
  assert.equal(scorecard.metrics.energy_delta, 0, 'same policy vs same baseline should have 0 energy delta');
  assert.equal(scorecard.metrics.efficiency_delta, 0, 'same policy vs same baseline should have 0 efficiency delta');
  assert.equal(scorecard.verdict, 'neutral');
}

// ---------------------------------------------------------------------------
// Test 2: Greedy policy loads and runs without error
// ---------------------------------------------------------------------------
async function test_greedy_policy_loads_and_runs() {
  const scorecard = await runEvaluation({
    scenario: SCENARIO_PATH,
    seeds: [42],
    steps: 50,
    policy: GREEDY_POLICY_PATH,
    quiet: true,
  });

  assert.equal(scorecard.policy_name, 'greedy');
  assert.equal(scorecard.baseline_name, 'default');
  assert.equal(scorecard.seeds.length, 1);
  assert.equal(scorecard.seeds[0], 42);
  assert.equal(scorecard.steps, 50);
}

// ---------------------------------------------------------------------------
// Test 3: Per-seed results have expected structure
// ---------------------------------------------------------------------------
async function test_per_seed_structure() {
  const scorecard = await runEvaluation({
    scenario: SCENARIO_PATH,
    seeds: [42, 314],
    steps: 30,
    policy: GREEDY_POLICY_PATH,
    quiet: true,
  });

  assert.equal(scorecard.per_seed.length, 2, 'should have 2 per_seed entries');

  for (const entry of scorecard.per_seed) {
    assert.ok('seed' in entry, 'per_seed entry missing seed');
    assert.ok('policy' in entry, 'per_seed entry missing policy metrics');
    assert.ok('baseline' in entry, 'per_seed entry missing baseline metrics');
    assert.ok('deltas' in entry, 'per_seed entry missing deltas');
    assert.ok('verdict' in entry, 'per_seed entry missing verdict');

    // Policy and baseline metrics should have the expected fields.
    for (const side of ['policy', 'baseline']) {
      assert.ok('survival_rate' in entry[side], `${side} missing survival_rate`);
      assert.ok('mean_energy' in entry[side], `${side} missing mean_energy`);
      assert.ok('food_efficiency' in entry[side], `${side} missing food_efficiency`);
    }

    // Deltas should have the expected fields.
    for (const f of REQUIRED_METRIC_FIELDS) {
      assert.ok(f in entry.deltas, `per_seed deltas missing ${f}`);
    }
  }
}

// ---------------------------------------------------------------------------
// Test 4: Greedy policy outperforms random walk on food efficiency
// ---------------------------------------------------------------------------
async function test_greedy_outperforms_random_on_food_efficiency() {
  // Run with enough steps and seeds that the greedy policy should reliably
  // collect more food than random walk.
  const scorecard = await runEvaluation({
    scenario: SCENARIO_PATH,
    seeds: [1, 2, 3],
    steps: 100,
    policy: GREEDY_POLICY_PATH,
    quiet: true,
  });

  // Greedy should eat more food than random walk on average.
  assert.ok(
    scorecard.metrics.efficiency_delta > 0,
    `Expected greedy to have positive food_efficiency delta, got ${scorecard.metrics.efficiency_delta}`,
  );
}

// ---------------------------------------------------------------------------
// Test 5: Invalid arguments throw appropriate errors
// ---------------------------------------------------------------------------
async function test_invalid_arguments() {
  // Missing scenario.
  await assert.rejects(
    () => runEvaluation({ seeds: [42], steps: 50, quiet: true }),
    /scenario.*required/i,
  );

  // Empty seeds.
  await assert.rejects(
    () => runEvaluation({ scenario: SCENARIO_PATH, seeds: [], steps: 50, quiet: true }),
    /seeds/i,
  );

  // Invalid steps.
  await assert.rejects(
    () => runEvaluation({ scenario: SCENARIO_PATH, seeds: [42], steps: -1, quiet: true }),
    /steps/i,
  );
}

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------
const tests = [
  test_baseline_only_scorecard_shape,
  test_greedy_policy_loads_and_runs,
  test_per_seed_structure,
  test_greedy_outperforms_random_on_food_efficiency,
  test_invalid_arguments,
];

let passed = 0;
let failed = 0;

for (const t of tests) {
  try {
    await t();
    process.stdout.write(`  PASS  ${t.name}\n`);
    passed += 1;
  } catch (err) {
    process.stdout.write(`  FAIL  ${t.name}: ${err.message}\n`);
    if (err.stack) process.stderr.write(`${err.stack}\n`);
    failed += 1;
  }
}

process.stdout.write(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
