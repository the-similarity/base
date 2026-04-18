#!/usr/bin/env node
/**
 * Test suite for the scenario DSL: schema validation, preset loading,
 * override merging, and CLI integration.
 *
 * Runnable via: node tests/test-scenarios.js
 * Exit 0 = all pass, exit 1 = failure.
 *
 * Uses only Node stdlib assert — no test framework dependencies.
 */

import { strict as assert } from 'node:assert';
import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  validateScenario,
  loadScenario,
  listPresets,
  mergeOverrides,
} from '../src/sim/scenario-loader.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const SCENARIOS_DIR = resolve(__dirname, '../scenarios');
const RUNNER_PATH = resolve(__dirname, '../src/sim/headless/runner.js');

let passed = 0;
let failed = 0;

/**
 * Run a named test case. Catches errors and reports pass/fail.
 */
function test(name, fn) {
  try {
    fn();
    passed++;
    process.stdout.write(`  PASS  ${name}\n`);
  } catch (e) {
    failed++;
    process.stderr.write(`  FAIL  ${name}\n    ${e.message}\n`);
    if (e.stack) {
      // Show only the first 3 stack frames for context
      const frames = e.stack.split('\n').slice(1, 4).join('\n');
      process.stderr.write(`    ${frames}\n`);
    }
  }
}

// ---------------------------------------------------------------------------
// 1. All preset JSONs parse without error
// ---------------------------------------------------------------------------
process.stdout.write('\n--- Preset JSON parsing ---\n');

const presetFiles = readdirSync(SCENARIOS_DIR)
  .filter((f) => f.endsWith('.json') && f !== 'schema.json')
  .sort();

for (const file of presetFiles) {
  test(`${file} parses and validates`, () => {
    const fullPath = join(SCENARIOS_DIR, file);
    const raw = readFileSync(fullPath, 'utf8');
    const scenario = JSON.parse(raw);

    const { valid, errors } = validateScenario(scenario);
    assert.ok(valid, `Validation errors: ${errors.join(', ')}`);

    // Required fields exist
    assert.ok(scenario.name, 'name is present');
    assert.ok(scenario.world, 'world is present');
    assert.ok(scenario.params, 'params is present');
    assert.ok(scenario.world.size > 0, 'world.size > 0');
    assert.ok(scenario.world.initial_population > 0, 'initial_population > 0');
  });
}

// ---------------------------------------------------------------------------
// 2. Schema validation catches missing required fields
// ---------------------------------------------------------------------------
process.stdout.write('\n--- Schema validation ---\n');

test('rejects null scenario', () => {
  const { valid, errors } = validateScenario(null);
  assert.ok(!valid);
  assert.ok(errors.some((e) => e.includes('non-null object')));
});

test('rejects missing name', () => {
  const { valid, errors } = validateScenario({
    world: { size: 64, initial_population: 20 },
    params: {},
  });
  assert.ok(!valid);
  assert.ok(errors.some((e) => e.includes('name')));
});

test('rejects missing world', () => {
  const { valid, errors } = validateScenario({
    name: 'test',
    params: {},
  });
  assert.ok(!valid);
  assert.ok(errors.some((e) => e.includes('world')));
});

test('rejects missing params', () => {
  const { valid, errors } = validateScenario({
    name: 'test',
    world: { size: 64, initial_population: 20 },
  });
  assert.ok(!valid);
  assert.ok(errors.some((e) => e.includes('params')));
});

test('rejects missing world.size', () => {
  const { valid, errors } = validateScenario({
    name: 'test',
    world: { initial_population: 20 },
    params: {},
  });
  assert.ok(!valid);
  assert.ok(errors.some((e) => e.includes('world.size')));
});

test('rejects missing world.initial_population', () => {
  const { valid, errors } = validateScenario({
    name: 'test',
    world: { size: 64 },
    params: {},
  });
  assert.ok(!valid);
  assert.ok(errors.some((e) => e.includes('initial_population')));
});

test('warns on out-of-range energy_decay', () => {
  const { valid, warnings } = validateScenario({
    name: 'test',
    world: { size: 64, initial_population: 20 },
    params: { energy_decay: 5.0 },
  });
  // Out-of-range is a warning, not an error
  assert.ok(valid, 'Should still be valid (warnings only)');
  assert.ok(warnings.some((w) => w.includes('energy_decay')));
});

test('accepts valid minimal scenario', () => {
  const { valid, errors } = validateScenario({
    name: 'minimal',
    world: { size: 64, initial_population: 10 },
    params: {},
  });
  assert.ok(valid, `Unexpected errors: ${errors.join(', ')}`);
});

// ---------------------------------------------------------------------------
// 3. mergeOverrides works correctly
// ---------------------------------------------------------------------------
process.stdout.write('\n--- mergeOverrides ---\n');

test('merges params overrides', () => {
  const base = {
    name: 'test',
    world: { size: 64, initial_population: 20 },
    params: { energy_decay: 0.01, food_spawn_rate: 0.1 },
  };
  const merged = mergeOverrides(base, { energy_decay: '0.05' });
  assert.equal(merged.params.energy_decay, 0.05);
  // Original unchanged
  assert.equal(base.params.energy_decay, 0.01);
  // Other params preserved
  assert.equal(merged.params.food_spawn_rate, 0.1);
});

test('merges world overrides with dot notation', () => {
  const base = {
    name: 'test',
    world: { size: 64, initial_population: 20 },
    params: {},
  };
  const merged = mergeOverrides(base, { 'world.size': '128' });
  assert.equal(merged.world.size, 128);
  assert.equal(merged.world.initial_population, 20);
  // Original unchanged
  assert.equal(base.world.size, 64);
});

test('merges top-level overrides (seed, steps)', () => {
  const base = {
    name: 'test',
    seed: 42,
    steps: 500,
    world: { size: 64, initial_population: 20 },
    params: {},
  };
  const merged = mergeOverrides(base, { seed: '314', steps: '100' });
  assert.equal(merged.seed, 314);
  assert.equal(merged.steps, 100);
});

test('returns copy when no overrides', () => {
  const base = {
    name: 'test',
    world: { size: 64, initial_population: 20 },
    params: { energy_decay: 0.01 },
  };
  const merged = mergeOverrides(base, {});
  assert.deepEqual(merged.params, base.params);
  assert.notStrictEqual(merged, base); // different reference
});

test('handles null/undefined overrides', () => {
  const base = {
    name: 'test',
    world: { size: 64, initial_population: 20 },
    params: {},
  };
  const merged = mergeOverrides(base, null);
  assert.deepEqual(merged.name, base.name);
});

// ---------------------------------------------------------------------------
// 4. listPresets returns all scenario presets
// ---------------------------------------------------------------------------
process.stdout.write('\n--- listPresets ---\n');

test('lists all preset files', () => {
  const presets = listPresets(SCENARIOS_DIR);
  assert.ok(Array.isArray(presets));
  assert.ok(presets.length >= 4, `Expected at least 4 presets, got ${presets.length}`);

  const names = presets.map((p) => p.name);
  assert.ok(names.includes('small_village'), 'Missing small_village');
  assert.ok(names.includes('stress_test'), 'Missing stress_test');
  assert.ok(names.includes('abundance'), 'Missing abundance');
  assert.ok(names.includes('sparse'), 'Missing sparse');
});

test('presets have name, path, description', () => {
  const presets = listPresets(SCENARIOS_DIR);
  for (const p of presets) {
    assert.ok(p.name, `preset missing name`);
    assert.ok(p.path, `preset ${p.name} missing path`);
    assert.ok(typeof p.description === 'string', `preset ${p.name} description not a string`);
  }
});

test('excludes schema.json from presets', () => {
  const presets = listPresets(SCENARIOS_DIR);
  const names = presets.map((p) => p.name);
  assert.ok(!names.includes('schema'), 'schema.json should not appear as a preset');
});

// ---------------------------------------------------------------------------
// 5. CLI --list-scenarios prints all presets
// ---------------------------------------------------------------------------
process.stdout.write('\n--- CLI integration ---\n');

test('--list-scenarios prints preset names', () => {
  const result = execFileSync(process.execPath, [RUNNER_PATH, '--list-scenarios'], {
    encoding: 'utf8',
    cwd: resolve(__dirname, '..'),
  });

  assert.ok(result.includes('small_village'), 'Output should include small_village');
  assert.ok(result.includes('stress_test'), 'Output should include stress_test');
  assert.ok(result.includes('abundance'), 'Output should include abundance');
  assert.ok(result.includes('sparse'), 'Output should include sparse');
});

test('--help exits 0 and shows usage', () => {
  const result = execFileSync(process.execPath, [RUNNER_PATH, '--help'], {
    encoding: 'utf8',
  });
  assert.ok(result.includes('--preset'));
  assert.ok(result.includes('--param'));
  assert.ok(result.includes('--list-scenarios'));
});

// ---------------------------------------------------------------------------
// 6. loadScenario validates and returns parsed scenario
// ---------------------------------------------------------------------------
process.stdout.write('\n--- loadScenario ---\n');

test('loadScenario loads and validates a preset', () => {
  const scenario = loadScenario(join(SCENARIOS_DIR, 'small_village.json'));
  assert.equal(scenario.name, 'small_village');
  assert.equal(scenario.world.size, 64);
  assert.equal(scenario.params.energy_decay, 0.01);
});

test('loadScenario throws on nonexistent file', () => {
  assert.throws(
    () => loadScenario('/nonexistent/path/scenario.json'),
    /Cannot read scenario file/
  );
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
process.stdout.write(`\n--- Results: ${passed} passed, ${failed} failed ---\n`);
process.exit(failed > 0 ? 1 : 0);
