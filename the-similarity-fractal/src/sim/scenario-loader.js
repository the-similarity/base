/**
 * Scenario loader with validation and preset discovery.
 *
 * This module provides the DSL layer between raw scenario JSON files and the
 * headless runner. It handles:
 *   1. Loading + validating scenarios against the JSON Schema
 *   2. Discovering all preset scenarios in the scenarios/ directory
 *   3. Deep-merging CLI overrides into a loaded scenario
 *
 * Design decisions:
 * - No external dependencies — validation is hand-rolled against the schema
 *   constraints rather than pulling in ajv/json-schema-validator. This keeps
 *   the runner zero-dep (pure Node 18 stdlib).
 * - Validation produces warnings (not errors) for out-of-range values so
 *   experimental scenarios can push beyond documented limits without failing.
 * - Unknown fields in the top-level object are preserved (additionalProperties
 *   is true in the schema) so downstream tooling can attach metadata.
 *
 * @module sim/scenario-loader
 */

import { readFileSync, readdirSync } from 'node:fs';
import { resolve, join, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Default scenarios directory — sibling to the src/ tree at repo root.
 * Overridable in listPresets() for testing.
 */
const DEFAULT_SCENARIOS_DIR = resolve(__dirname, '../../scenarios');

/**
 * Schema-derived range constraints for validation warnings.
 * These mirror the min/max values in scenarios/schema.json — kept as a
 * flat lookup table rather than parsing the schema at runtime to avoid
 * the complexity of a full JSON Schema validator.
 */
const RANGE_CONSTRAINTS = {
  'world.size':              { min: 8, max: 1024, type: 'integer' },
  'world.initial_population': { min: 1, max: 10000, type: 'integer' },
  'params.energy_decay':     { min: 0, max: 1, type: 'number' },
  'params.move_speed':       { min: 0, max: 10, type: 'integer' },
  'params.food_spawn_rate':  { min: 0, max: 1, type: 'number' },
  'params.food_energy':      { min: 0, max: 10, type: 'number' },
};

/**
 * Validate a scenario object against the schema constraints.
 *
 * Returns { valid: boolean, errors: string[], warnings: string[] }.
 * - errors: hard failures (missing required fields, wrong types)
 * - warnings: soft issues (out-of-range values that may still work)
 *
 * @param {object} scenario - Parsed scenario JSON
 * @returns {{ valid: boolean, errors: string[], warnings: string[] }}
 */
export function validateScenario(scenario) {
  const errors = [];
  const warnings = [];

  // Required top-level fields
  if (!scenario || typeof scenario !== 'object') {
    return { valid: false, errors: ['Scenario must be a non-null object'], warnings };
  }
  if (!scenario.name || typeof scenario.name !== 'string') {
    errors.push('Missing or non-string "name" field (required)');
  }
  if (scenario.name && scenario.name.length === 0) {
    errors.push('"name" must be a non-empty string');
  }

  // Optional typed fields at top level
  if (scenario.description !== undefined && typeof scenario.description !== 'string') {
    errors.push('"description" must be a string');
  }
  if (scenario.seed !== undefined) {
    if (!Number.isInteger(scenario.seed) || scenario.seed < 0) {
      errors.push('"seed" must be a non-negative integer');
    }
  }
  if (scenario.steps !== undefined) {
    if (!Number.isInteger(scenario.steps) || scenario.steps < 1) {
      errors.push('"steps" must be a positive integer');
    }
  }

  // Required sub-objects
  if (!scenario.world || typeof scenario.world !== 'object') {
    errors.push('Missing or non-object "world" field (required)');
  } else {
    if (scenario.world.size === undefined) {
      errors.push('"world.size" is required');
    }
    if (scenario.world.initial_population === undefined) {
      errors.push('"world.initial_population" is required');
    }
  }
  if (!scenario.params || typeof scenario.params !== 'object') {
    errors.push('Missing or non-object "params" field (required)');
  }

  // Range checks — produce warnings, not errors, so experiments can push limits
  for (const [path, constraint] of Object.entries(RANGE_CONSTRAINTS)) {
    const [section, key] = path.split('.');
    const value = scenario[section]?.[key];
    if (value === undefined) continue; // missing fields caught above

    // Type check
    if (constraint.type === 'integer' && !Number.isInteger(value)) {
      warnings.push(`${path} should be an integer, got ${typeof value} (${value})`);
    } else if (constraint.type === 'number' && typeof value !== 'number') {
      warnings.push(`${path} should be a number, got ${typeof value} (${value})`);
    }

    // Range check
    if (typeof value === 'number') {
      if (value < constraint.min) {
        warnings.push(`${path}=${value} is below minimum ${constraint.min}`);
      }
      if (value > constraint.max) {
        warnings.push(`${path}=${value} is above maximum ${constraint.max}`);
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings };
}

/**
 * Load a scenario from a JSON file path, validate it, and return the parsed
 * object. Throws on missing file, parse error, or validation failure.
 * Prints warnings to stderr but does not fail on them.
 *
 * @param {string} path - Path to the scenario JSON file (absolute or relative to cwd)
 * @returns {object} Validated scenario object
 * @throws {Error} On file read, JSON parse, or validation errors
 */
export function loadScenario(path) {
  const abs = resolve(process.cwd(), path);
  let raw;
  try {
    raw = readFileSync(abs, 'utf8');
  } catch (e) {
    throw new Error(`Cannot read scenario file at ${abs}: ${e.message}`);
  }

  let scenario;
  try {
    scenario = JSON.parse(raw);
  } catch (e) {
    throw new Error(`Failed to parse scenario JSON at ${abs}: ${e.message}`);
  }

  const { valid, errors, warnings } = validateScenario(scenario);

  // Emit warnings to stderr so they're visible but don't break piping
  for (const w of warnings) {
    process.stderr.write(`[scenario-loader] warning: ${w}\n`);
  }

  if (!valid) {
    throw new Error(
      `Scenario validation failed for ${abs}:\n  - ${errors.join('\n  - ')}`
    );
  }

  return scenario;
}

/**
 * Scan the scenarios directory and return metadata for each preset.
 * A preset is any .json file in the directory (excluding schema.json).
 *
 * @param {string} [scenariosDir] - Directory to scan (default: scenarios/)
 * @returns {{ name: string, path: string, description: string }[]}
 */
export function listPresets(scenariosDir = DEFAULT_SCENARIOS_DIR) {
  const dir = resolve(scenariosDir);
  let entries;
  try {
    entries = readdirSync(dir);
  } catch (e) {
    throw new Error(`Cannot read scenarios directory at ${dir}: ${e.message}`);
  }

  const presets = [];
  for (const entry of entries.sort()) {
    // Skip non-JSON files and the schema itself
    if (!entry.endsWith('.json') || entry === 'schema.json') continue;

    const fullPath = join(dir, entry);
    try {
      const raw = readFileSync(fullPath, 'utf8');
      const parsed = JSON.parse(raw);
      presets.push({
        name: parsed.name || basename(entry, '.json'),
        path: fullPath,
        description: parsed.description || '',
      });
    } catch {
      // Skip files that fail to parse — don't crash the listing because
      // one file is broken
      process.stderr.write(`[scenario-loader] skipping unparseable file: ${entry}\n`);
    }
  }

  return presets;
}

/**
 * Deep-merge CLI overrides into a loaded scenario object. Overrides can
 * target nested paths using dot notation (e.g., "energy_decay" goes into
 * params, "world.size" goes into world).
 *
 * Mutation policy: returns a new object — the input scenario is not modified.
 *
 * @param {object} scenario - Base scenario object
 * @param {Record<string, string|number>} overrides - Key=value pairs from CLI
 * @returns {object} New scenario with overrides applied
 */
export function mergeOverrides(scenario, overrides) {
  if (!overrides || Object.keys(overrides).length === 0) return { ...scenario };

  // Deep-copy the mutable sub-trees so the caller's object is untouched
  const merged = {
    ...scenario,
    world: { ...(scenario.world ?? {}) },
    params: { ...(scenario.params ?? {}) },
  };

  for (const [key, rawValue] of Object.entries(overrides)) {
    // Coerce string values to numbers where appropriate. CLI args always
    // arrive as strings; scenario JSON has typed values. We try numeric
    // coercion first and fall back to string.
    const value = typeof rawValue === 'string' && rawValue !== '' && !isNaN(Number(rawValue))
      ? Number(rawValue)
      : rawValue;

    if (key.startsWith('world.')) {
      // Explicit world namespace: "world.size" -> merged.world.size
      merged.world[key.slice('world.'.length)] = value;
    } else if (key === 'seed' || key === 'steps' || key === 'name' || key === 'description') {
      // Top-level scenario fields
      merged[key] = value;
    } else {
      // Default: treat as a params knob. This matches how users think about
      // "tuning a scenario" — the knobs live in params.
      merged.params[key] = value;
    }
  }

  return merged;
}
