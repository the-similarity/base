/**
 * Shared utilities for the nature engine subsystems (rocks, debris, etc.).
 *
 * Centralizes common helpers so that each nature module does not independently
 * re-implement raycasting, RNG, or biome lookups. All functions here are
 * stateless or use reusable pre-allocated objects for performance.
 *
 * @module nature/shared
 */

import * as THREE from 'three';

// Re-export biome constants from terrain-sampler so nature modules have a single
// import path. The canonical definitions live in terrain-sampler.js.
export {
  BIOME_WATER,
  BIOME_SAND,
  BIOME_GRASS,
  BIOME_FOREST,
  BIOME_ROCK,
  BIOME_SNOW,
} from '../world/terrain-sampler.js';


// ─── Reusable raycasting objects ─────────────────────────────────────────────
// Pre-allocated to avoid GC pressure from per-call allocations.
// These are module-scoped singletons — safe because JS is single-threaded and
// nature population is synchronous.

const _rayOrigin = new THREE.Vector3();
const _rayDir    = new THREE.Vector3(0, -1, 0);

/**
 * Raycast downward to find the terrain surface Y at a given (x, z) position.
 *
 * The ray starts 10 units above (well above any expected terrain) and shoots
 * straight down. Returns null if the ray misses the terrain entirely (e.g.,
 * the query point is outside terrain bounds).
 *
 * Performance: reuses pre-allocated Vector3 objects. The raycaster itself
 * must be provided by the caller and can (should) be reused across calls.
 *
 * @param {THREE.Raycaster} raycaster - Caller-owned reusable raycaster
 * @param {THREE.Mesh} terrainMesh - The terrain mesh to intersect
 * @param {number} x - World X coordinate
 * @param {number} z - World Z coordinate
 * @returns {number|null} Ground Y, or null if no intersection
 */
export function getGroundY(raycaster, terrainMesh, x, z) {
  _rayOrigin.set(x, 10, z);
  raycaster.set(_rayOrigin, _rayDir);

  const hits = raycaster.intersectObject(terrainMesh);
  return hits.length > 0 ? hits[0].point.y : null;
}


/**
 * Create a simple seeded LCG (linear congruential generator).
 *
 * Returns a function that produces deterministic values in [0, 1) on each call.
 * Uses the Numerical Recipes LCG constants (multiplier 1664525, increment
 * 1013904223), which have a full period of 2^31.
 *
 * Why LCG instead of xoshiro (sim/rng.js):
 * Nature placement does not need high-quality randomness — visual scatter is
 * tolerant of LCG artifacts. The closure-based API is more ergonomic for
 * inline use than constructing a PRNG class instance.
 *
 * @param {number} seed - Integer seed
 * @returns {() => number} Function returning next value in [0, 1)
 */
export function createLCG(seed) {
  let state = seed & 0x7fffffff;
  return () => {
    state = (state * 1664525 + 1013904223) & 0x7fffffff;
    return state / 0x7fffffff;
  };
}
