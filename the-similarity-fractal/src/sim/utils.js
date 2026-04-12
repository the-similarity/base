/**
 * utils.js — Shared utilities for the simulation layer.
 *
 * Headless-safe, no Three.js dependency.  Pure functions only.
 */

/**
 * Clamp a numeric value to the [0, 1] interval.
 *
 * Used pervasively by need/utility calculations and relationship valence
 * so that no single factor can exceed normalised bounds.
 *
 * @param {number} v — input value (may be outside [0,1]).
 * @returns {number} clamped result.
 */
export function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/**
 * Find the nearest entity in `candidates` that satisfies an optional
 * `predicate`, using squared 2D Euclidean distance on (x, y).
 *
 * Skips candidates that are reference-equal to `origin`.
 *
 * @param {object}   origin     — the reference entity ({ x, y }).
 * @param {Array}    candidates — array of entities to search.
 * @param {Function} [predicate] — optional filter; receives candidate, must return truthy.
 * @returns {object|null} nearest matching entity, or null if none found.
 */
export function findNearest(origin, candidates, predicate) {
  let best = null;
  let bestDist = Infinity;
  for (let i = 0; i < candidates.length; i++) {
    const other = candidates[i];
    if (other === origin) continue;
    if (predicate && !predicate(other)) continue;
    const dx = (other.x ?? 0) - (origin.x ?? 0);
    const dy = (other.y ?? 0) - (origin.y ?? 0);
    const dist = dx * dx + dy * dy; // skip sqrt — only comparing magnitudes
    if (dist < bestDist) {
      bestDist = dist;
      best = other;
    }
  }
  return best;
}
