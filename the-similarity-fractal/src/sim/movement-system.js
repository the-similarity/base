/**
 * Movement system for the 3D society simulation.
 *
 * Responsibilities:
 * - Translates agent goals/actions into physical movement on the nav-grid.
 * - Supports seven movement behaviors: WANDER, TRAVEL_TO_POI, FLEE, PURSUE,
 *   MIGRATE, RETURN_HOME, PATROL.
 * - Deducts energy proportional to movement cost (slope + climate modifiers).
 * - Updates agent `position` and `regionId` each tick.
 * - Emits 'move' events through the event bus for telemetry consumption.
 *
 * Design constraints:
 * - Pure ES module, no Three.js dependency — must run headless.
 * - All pathfinding delegates to navGrid.findPath(); this system only consumes
 *   paths and steps agents along them one cell per tick.
 * - Movement cost is the nav-grid cell cost multiplied by climate modifier,
 *   ensuring terrain slope and weather both affect agent stamina realistically.
 *
 * Lifecycle:
 * - Constructed once with a navGrid and eventBus reference.
 * - `tick()` called every simulation tick with the full agent array and worldState.
 * - Stateless between ticks except for the per-agent path cache stored ON the
 *   agent object (agent._path). This avoids a separate Map and keeps agent
 *   serialization self-contained.
 */

// ── Movement behavior constants ──────────────────────────────────────────────
// Upper-snake-case enum. Each maps to a distinct movement planning strategy.
export const MOVE_BEHAVIOR = Object.freeze({
  WANDER:        'WANDER',
  TRAVEL_TO_POI: 'TRAVEL_TO_POI',
  FLEE:          'FLEE',
  PURSUE:        'PURSUE',
  MIGRATE:       'MIGRATE',
  RETURN_HOME:   'RETURN_HOME',
  PATROL:        'PATROL',
});

// ── Tuning constants ─────────────────────────────────────────────────────────
// Base energy cost multiplier. The actual cost is BASE_ENERGY_COST * cellMoveCost * climateModifier.
// Kept low so agents can traverse several cells before resting.
const BASE_ENERGY_COST = 0.5;

// Maximum cells an agent can move in a single tick. Prevents runaway movement
// if pathfinding returns a very long path segment.
const MAX_STEPS_PER_TICK = 1;

// Wander radius in grid cells — how far an agent looks when picking a random
// walkable neighbor to wander toward.
const WANDER_RADIUS = 3;

// Flee distance in grid cells — how many cells away from threat we try to path.
const FLEE_DISTANCE = 5;

/**
 * Movement system that drives agent locomotion across the nav-grid.
 *
 * Invariants:
 * - Never mutates navGrid or eventBus.
 * - Only mutates agent.position, agent.regionId, agent.needs.energy, and
 *   the transient agent._path array.
 * - If an agent has zero energy, movement is skipped (fail-closed: no free movement).
 */
export class MovementSystem {
  /**
   * @param {Object} navGrid  - Navigation grid with getMoveCost, isPassable,
   *                             getHeight, neighbors, findPath, worldToGrid, gridToWorld.
   * @param {Object} eventBus - Event emitter with emit(eventName, payload).
   */
  constructor(navGrid, eventBus) {
    // Store references — never owned, never mutated by this system.
    this._navGrid = navGrid;
    this._eventBus = eventBus;
  }

  /**
   * Advance all agents' movement by one simulation tick.
   *
   * For each alive agent with remaining energy:
   * 1. Determine movement behavior from agent.currentAction.
   * 2. If no cached path exists (or goal changed), plan a new path.
   * 3. Step the agent one cell along the path.
   * 4. Deduct energy based on cell cost and climate.
   * 5. Update position and regionId.
   * 6. Emit 'move' event.
   *
   * @param {Array<Object>} agents     - Full agent array (may include dead agents).
   * @param {Object}        worldState - Current world snapshot (environment, climate, etc.).
   */
  tick(agents, worldState) {
    // Climate modifier defaults to 1.0 if not provided.
    // Harsh weather (storms, extreme heat) increases movement cost.
    const climateModifier = worldState?.environment?.climateMovementModifier ?? 1.0;

    for (const agent of agents) {
      // Dead agents do not move. This is the primary guard — everything below
      // assumes the agent is alive and has a position.
      if (!agent.alive) continue;

      // Agents without energy cannot move. This is intentional: starvation
      // immobilizes before it kills, creating observable distress signals.
      if ((agent.needs?.energy ?? 0) <= 0) continue;

      // Resolve which movement behavior applies this tick.
      const behavior = this._resolveBehavior(agent);
      if (!behavior) continue;

      // Ensure we have a valid path for the current behavior.
      // Re-plan if: no path, path exhausted, or goal changed since last plan.
      this._ensurePath(agent, behavior, worldState);

      // Step along the path up to MAX_STEPS_PER_TICK cells.
      this._stepAlongPath(agent, climateModifier, worldState);
    }
  }

  /**
   * Plan a path from an agent's current position to a target grid cell.
   *
   * This is the public API for external systems (e.g., decision system) that
   * want to pre-compute a path before assigning an action.
   *
   * @param {Object} agent    - Agent with a position {x, y, z}.
   * @param {number} targetGx - Target grid X coordinate.
   * @param {number} targetGz - Target grid Z coordinate.
   * @returns {Array<{gx: number, gz: number}>|null} Path as grid coords, or null if unreachable.
   */
  planPath(agent, targetGx, targetGz) {
    const { gx: startGx, gz: startGz } = this._navGrid.worldToGrid(
      agent.position.x,
      agent.position.z
    );

    // Delegate to navGrid's A* (or whatever algorithm it uses internally).
    const path = this._navGrid.findPath(startGx, startGz, targetGx, targetGz);
    return path; // null if no route exists
  }

  // ── Private helpers ──────────────────────────────────────────────────────

  /**
   * Map the agent's currentAction to a MOVE_BEHAVIOR enum value.
   *
   * Returns null if the agent's current action does not involve movement
   * (e.g., resting, gathering in place, socializing).
   *
   * @param {Object} agent
   * @returns {string|null} One of MOVE_BEHAVIOR values, or null.
   */
  _resolveBehavior(agent) {
    const action = agent.currentAction;
    if (!action) return MOVE_BEHAVIOR.WANDER;

    // The action type maps directly to movement behaviors.
    // Actions that do not require movement return null so the agent stays put.
    switch (action.type) {
      case 'wander':        return MOVE_BEHAVIOR.WANDER;
      case 'travel_to_poi': return MOVE_BEHAVIOR.TRAVEL_TO_POI;
      case 'flee':          return MOVE_BEHAVIOR.FLEE;
      case 'pursue':        return MOVE_BEHAVIOR.PURSUE;
      case 'migrate':       return MOVE_BEHAVIOR.MIGRATE;
      case 'return_home':   return MOVE_BEHAVIOR.RETURN_HOME;
      case 'patrol':        return MOVE_BEHAVIOR.PATROL;
      // Non-movement actions: agent stays in place.
      case 'rest':
      case 'gather':
      case 'trade':
      case 'socialize':
        return null;
      default:
        // Unknown action — default to idle (no movement).
        return null;
    }
  }

  /**
   * Ensure agent._path is populated and valid for the current behavior.
   *
   * Replans if:
   * - No path exists yet.
   * - Path is exhausted (empty array).
   * - The behavior/goal changed since the path was planned (tracked via agent._pathGoalKey).
   *
   * @param {Object} agent
   * @param {string} behavior - MOVE_BEHAVIOR value.
   * @param {Object} worldState
   */
  _ensurePath(agent, behavior, worldState) {
    const goalKey = this._goalKey(agent, behavior);

    // If the goal hasn't changed and we still have unconsumed path steps, keep it.
    const hasSteps = agent._path && (agent._pathIdx ?? 0) < agent._path.length;
    if (hasSteps && agent._pathGoalKey === goalKey) {
      return;
    }

    // Compute a target grid cell based on the behavior.
    const target = this._computeTarget(agent, behavior, worldState);
    if (!target) {
      // No valid target — clear path so agent stays put this tick.
      agent._path = null;
      agent._pathGoalKey = null;
      return;
    }

    // Plan the path via navGrid.
    const path = this.planPath(agent, target.gx, target.gz);
    // Store path on the agent for step-by-step consumption.
    // _pathIdx tracks the next cell to consume, avoiding O(n) array shifts.
    agent._path = path ?? null;
    agent._pathIdx = 0;
    agent._pathGoalKey = goalKey;
  }

  /**
   * Produce a string key that uniquely identifies the current movement goal.
   *
   * Used to detect when re-planning is needed because the goal changed.
   *
   * @param {Object} agent
   * @param {string} behavior
   * @returns {string}
   */
  _goalKey(agent, behavior) {
    const action = agent.currentAction || {};
    // Combine behavior with any target-specific info to detect goal changes.
    if (action.targetId !== undefined) return `${behavior}:${action.targetId}`;
    if (action.targetGx !== undefined) return `${behavior}:${action.targetGx},${action.targetGz}`;
    if (action.poiId !== undefined) return `${behavior}:poi:${action.poiId}`;
    // For wander, we generate a new key each time the path is exhausted
    // (handled by the empty-path check in _ensurePath).
    return `${behavior}:${agent.id}`;
  }

  /**
   * Compute the target grid cell for a given movement behavior.
   *
   * Each behavior has a distinct targeting strategy:
   * - WANDER: random walkable cell within WANDER_RADIUS.
   * - TRAVEL_TO_POI: the POI's grid location from agent.currentAction.
   * - FLEE: cell FLEE_DISTANCE away from threat, in the opposite direction.
   * - PURSUE: target agent's current grid cell.
   * - MIGRATE: target region's centroid (from action or best known region).
   * - RETURN_HOME: agent's home position on the grid.
   * - PATROL: next waypoint in a patrol route (cycles through action.waypoints).
   *
   * @param {Object} agent
   * @param {string} behavior
   * @param {Object} worldState
   * @returns {{gx: number, gz: number}|null}
   */
  _computeTarget(agent, behavior, worldState) {
    const { gx: agentGx, gz: agentGz } = this._navGrid.worldToGrid(
      agent.position.x,
      agent.position.z
    );
    const action = agent.currentAction || {};

    switch (behavior) {
      case MOVE_BEHAVIOR.WANDER:
        return this._pickWanderTarget(agentGx, agentGz);

      case MOVE_BEHAVIOR.TRAVEL_TO_POI: {
        // Action must carry targetGx/targetGz or a poiId resolvable from worldState.
        if (action.targetGx !== undefined && action.targetGz !== undefined) {
          return { gx: action.targetGx, gz: action.targetGz };
        }
        // Resolve POI position from worldState if poiId is provided.
        if (action.poiId !== undefined && worldState?.environment?.pois) {
          const poi = worldState.environment.pois.find(p => p.id === action.poiId);
          if (poi) {
            return this._navGrid.worldToGrid(poi.position.x, poi.position.z);
          }
        }
        return null;
      }

      case MOVE_BEHAVIOR.FLEE:
        return this._pickFleeTarget(agentGx, agentGz, action, worldState);

      case MOVE_BEHAVIOR.PURSUE: {
        // Find the target agent in the world and path toward their current cell.
        if (action.targetId !== undefined && worldState?.agents) {
          const target = worldState.agents.find(a => a.id === action.targetId && a.alive);
          if (target) {
            return this._navGrid.worldToGrid(target.position.x, target.position.z);
          }
        }
        return null;
      }

      case MOVE_BEHAVIOR.MIGRATE: {
        // Migrate to a specific grid target or a region centroid.
        if (action.targetGx !== undefined && action.targetGz !== undefined) {
          return { gx: action.targetGx, gz: action.targetGz };
        }
        return null;
      }

      case MOVE_BEHAVIOR.RETURN_HOME: {
        // Agent's home position is stored on the agent state.
        if (agent.homePosition) {
          return this._navGrid.worldToGrid(agent.homePosition.x, agent.homePosition.z);
        }
        return null;
      }

      case MOVE_BEHAVIOR.PATROL: {
        // Cycle through waypoints defined in the action.
        if (action.waypoints && action.waypoints.length > 0) {
          // Track patrol index on the agent to cycle through waypoints.
          const idx = (agent._patrolIndex ?? 0) % action.waypoints.length;
          const wp = action.waypoints[idx];
          return { gx: wp.gx, gz: wp.gz };
        }
        return null;
      }

      default:
        return null;
    }
  }

  /**
   * Pick a random walkable cell within WANDER_RADIUS of the agent.
   *
   * Strategy: collect all passable neighbors within radius, then pick one
   * using a simple modular index based on current position (deterministic
   * per-position but varied across agents).
   *
   * @param {number} agentGx
   * @param {number} agentGz
   * @returns {{gx: number, gz: number}|null}
   */
  _pickWanderTarget(agentGx, agentGz) {
    const candidates = [];

    for (let dx = -WANDER_RADIUS; dx <= WANDER_RADIUS; dx++) {
      for (let dz = -WANDER_RADIUS; dz <= WANDER_RADIUS; dz++) {
        if (dx === 0 && dz === 0) continue;
        const gx = agentGx + dx;
        const gz = agentGz + dz;
        if (this._navGrid.isPassable(gx, gz)) {
          candidates.push({ gx, gz });
        }
      }
    }

    if (candidates.length === 0) return null;

    // Deterministic selection using a position-based hash and an internal
    // counter. Date.now() is avoided because it breaks headless reproducibility.
    // The counter ensures different picks on successive wander calls from the
    // same grid cell.
    this._wanderCounter = ((this._wanderCounter ?? 0) + 1) & 0x7FFFFFFF;
    const hash = Math.abs((agentGx * 31 + agentGz * 17 + this._wanderCounter * 7) % candidates.length);
    return candidates[hash];
  }

  /**
   * Pick a flee target: a cell FLEE_DISTANCE away from the threat, in the
   * opposite direction.
   *
   * @param {number} agentGx
   * @param {number} agentGz
   * @param {Object} action  - Must contain threatX, threatZ (world coords) or threatGx, threatGz.
   * @param {Object} worldState
   * @returns {{gx: number, gz: number}|null}
   */
  _pickFleeTarget(agentGx, agentGz, action, worldState) {
    let threatGx, threatGz;

    if (action.threatGx !== undefined && action.threatGz !== undefined) {
      threatGx = action.threatGx;
      threatGz = action.threatGz;
    } else if (action.targetId !== undefined && worldState?.agents) {
      // Flee from a specific agent.
      const threat = worldState.agents.find(a => a.id === action.targetId);
      if (!threat) return null;
      const tg = this._navGrid.worldToGrid(threat.position.x, threat.position.z);
      threatGx = tg.gx;
      threatGz = tg.gz;
    } else {
      return null;
    }

    // Compute direction away from threat.
    const dx = agentGx - threatGx;
    const dz = agentGz - threatGz;
    const dist = Math.sqrt(dx * dx + dz * dz) || 1;

    // Normalize and scale to FLEE_DISTANCE.
    const targetGx = Math.round(agentGx + (dx / dist) * FLEE_DISTANCE);
    const targetGz = Math.round(agentGz + (dz / dist) * FLEE_DISTANCE);

    // Clamp to a passable cell if the exact target isn't passable.
    if (this._navGrid.isPassable(targetGx, targetGz)) {
      return { gx: targetGx, gz: targetGz };
    }

    // Fallback: find the nearest passable cell in the flee direction.
    // Try progressively closer cells along the flee vector.
    for (let scale = FLEE_DISTANCE - 1; scale >= 1; scale--) {
      const gx = Math.round(agentGx + (dx / dist) * scale);
      const gz = Math.round(agentGz + (dz / dist) * scale);
      if (this._navGrid.isPassable(gx, gz)) {
        return { gx, gz };
      }
    }

    return null;
  }

  /**
   * Step the agent along their cached path by up to MAX_STEPS_PER_TICK cells.
   *
   * Each step:
   * 1. Pop the next cell from agent._path.
   * 2. Check passability (terrain may have changed).
   * 3. Compute energy cost = BASE_ENERGY_COST * cellMoveCost * climateModifier.
   * 4. If agent has enough energy, move them and deduct cost.
   * 5. Convert grid coords back to world coords for position update.
   * 6. Update regionId from worldState if region map is available.
   * 7. Emit 'move' event.
   *
   * @param {Object} agent
   * @param {number} climateModifier
   * @param {Object} worldState
   */
  _stepAlongPath(agent, climateModifier, worldState) {
    const path = agent._path;
    if (!path) return;
    let idx = agent._pathIdx ?? 0;
    if (idx >= path.length) return;

    for (let step = 0; step < MAX_STEPS_PER_TICK; step++) {
      if (idx >= path.length) break;

      const nextCell = path[idx];

      // Verify the cell is still passable (terrain could change dynamically).
      if (!this._navGrid.isPassable(nextCell.gx, nextCell.gz)) {
        agent._path = null;
        agent._pathGoalKey = null;
        break;
      }

      const cellCost = this._navGrid.getMoveCost(nextCell.gx, nextCell.gz);
      const totalCost = BASE_ENERGY_COST * cellCost * climateModifier;

      if ((agent.needs?.energy ?? 0) < totalCost) break;

      // Advance the index pointer (O(1) vs O(n) array shift).
      idx++;
      agent._pathIdx = idx;

      const prevX = agent.position.x;
      const prevZ = agent.position.z;

      // navGrid.gridToWorld returns {x, z} per the nav-grid contract.
      const worldPos = this._navGrid.gridToWorld(nextCell.gx, nextCell.gz);
      agent.position.x = worldPos.x;
      agent.position.z = worldPos.z;

      // Y is always derived from terrain height, never from movement logic.
      agent.position.y = this._navGrid.getHeight(nextCell.gx, nextCell.gz);

      agent.needs.energy -= totalCost;

      if (worldState?.terrain?.regionMap) {
        const newRegion = worldState.terrain.regionMap[nextCell.gz]?.[nextCell.gx];
        if (newRegion !== undefined) {
          agent.regionId = newRegion;
        }
      }

      // Advance patrol waypoint when the current path is fully consumed.
      if (agent.currentAction?.type === 'patrol' && idx >= path.length) {
        agent._patrolIndex = ((agent._patrolIndex ?? 0) + 1) %
          (agent.currentAction.waypoints?.length || 1);
        agent._path = null;
        agent._pathGoalKey = null;
      }

      if (this._eventBus) {
        this._eventBus.emit('move', {
          agentId: agent.id,
          fromX: prevX,
          fromZ: prevZ,
          toX: agent.position.x,
          toZ: agent.position.z,
          energyCost: totalCost,
          regionId: agent.regionId,
        });
      }
    }
  }
}
