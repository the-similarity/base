/**
 * Scenario loader for the headless worlds runner.
 *
 * Supports JSON only by default (no YAML dep — keeps Node 18 stdlib sufficient
 * and avoids pulling in a package manager just for a config format). A YAML
 * entry point can be added later by swapping the parse call here; the rest of
 * the pipeline is format-agnostic.
 *
 * Expected scenario shape (all fields optional except `name`):
 *
 *   {
 *     "name": "small_village",
 *     "seed": 42,                     // CLI --seed overrides
 *     "steps": 500,                   // CLI --steps/--duration overrides
 *     "world":  { "size": 64, "initial_population": 20 },
 *     "params": { "energy_decay": 0.01, "move_speed": 1,
 *                 "food_spawn_rate": 0.05, "food_energy": 0.3 }
 *   }
 *
 * Invariants:
 * - The returned object is a plain JSON-safe structure (no Dates, no Maps).
 * - Unknown fields are preserved so downstream tooling can attach metadata
 *   without the loader needing to know about it.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export function loadScenario(path) {
  const abs = resolve(process.cwd(), path);
  const raw = readFileSync(abs, 'utf8');

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    throw new Error(`Failed to parse scenario JSON at ${abs}: ${e.message}`);
  }

  if (!parsed || typeof parsed !== 'object') {
    throw new Error(`Scenario at ${abs} did not parse to an object`);
  }
  if (!parsed.name || typeof parsed.name !== 'string') {
    throw new Error(`Scenario at ${abs} is missing a string "name" field`);
  }

  return parsed;
}
