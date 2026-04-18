/**
 * Greedy food-seeking policy — proof-of-concept for the eval harness.
 *
 * Strategy: each agent moves toward the nearest visible food cell. If no food
 * exists on the map, the agent holds position (dx=0, dy=0) to conserve energy
 * by avoiding unnecessary movement on a torus where random walking burns the
 * same energy_decay regardless.
 *
 * This policy is intentionally simple — it demonstrates the `decide()` contract
 * and provides a meaningful comparison against the default random walk. A
 * greedy policy should outperform random walk on survival_rate and
 * food_efficiency because it directs movement toward known food rather than
 * wandering aimlessly.
 *
 * ## Distance calculation
 *
 * The world is a torus (wraps in both axes). Manhattan distance on a torus:
 *   d(a, b) = min(|a-b|, size-|a-b|)  per axis, then sum.
 * We use Manhattan rather than Euclidean because agents move in integer deltas
 * on the grid, so Manhattan better reflects actual movement cost.
 *
 * ## Policy contract
 *
 * @param {object} agentState - { id, x, y, energy, alive, age }
 * @param {object} worldState - { tick, size, food: [{x,y}...], agents: [...] }
 * @returns {{ action: "move", direction: {x: number, y: number} }}
 *
 * @module policies/greedy
 */

/** Human-readable policy name for scorecard output. */
export const name = 'greedy';

/**
 * Toroidal signed distance on one axis: shortest path with direction.
 * Returns a value in [-size/2, size/2] indicating the signed displacement
 * from `from` to `to` on a torus of the given size.
 */
function toroidalDelta(from, to, size) {
  let d = to - from;
  // Wrap into [-size/2, size/2] — pick the shorter direction around the torus.
  if (d > size / 2) d -= size;
  if (d < -size / 2) d += size;
  return d;
}

/**
 * Manhattan distance on a torus.
 */
function toroidalManhattan(ax, ay, bx, by, size) {
  const dx = Math.abs(toroidalDelta(ax, bx, size));
  const dy = Math.abs(toroidalDelta(ay, by, size));
  return dx + dy;
}

/**
 * Decide the next move for an agent: move toward the nearest food cell.
 *
 * @param {object} agentState - Current agent snapshot.
 * @param {object} worldState - Current world snapshot.
 * @returns {{ action: "move", direction: {x: number, y: number} }}
 */
export function decide(agentState, worldState) {
  const { x, y } = agentState;
  const { size, food } = worldState;

  // If no food exists, hold position to conserve energy.
  if (!food || food.length === 0) {
    return { action: 'move', direction: { x: 0, y: 0 } };
  }

  // Find nearest food by toroidal Manhattan distance.
  let bestDist = Infinity;
  let bestFood = null;
  for (const f of food) {
    const dist = toroidalManhattan(x, y, f.x, f.y, size);
    if (dist < bestDist) {
      bestDist = dist;
      bestFood = f;
    }
  }

  // Compute direction vector toward the nearest food.
  const dx = toroidalDelta(x, bestFood.x, size);
  const dy = toroidalDelta(y, bestFood.y, size);

  // Normalize to unit step: move one cell toward food per axis (integer).
  // The harness clamps to move_speed, so we just use sign.
  return {
    action: 'move',
    direction: {
      x: Math.sign(dx),
      y: Math.sign(dy),
    },
  };
}
