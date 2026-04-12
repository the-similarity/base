/**
 * lifecycle-system.js — Handles agent spawning (birth) and death for the
 * 3D Society Simulation.
 *
 * Responsibilities:
 *   1. Initial population seeding across regions (spawnInitialAgents).
 *   2. Per-tick death checks (starvation, HP depletion, terminal disease).
 *   3. Per-tick birth logic when conditions are favorable.
 *
 * Design invariants:
 *   - This system never mutates agents that belong to other systems' concerns.
 *     It only sets `alive = false` on dead agents and creates new agent objects
 *     for births. All other field changes (hunger, hp, etc.) are the
 *     responsibility of upstream systems that run before lifecycle in the tick.
 *   - Events are emitted through the injected eventBus so other systems
 *     (economy, social, UI) can react without coupling.
 *   - The PRNG (rng) is injected so all randomness is deterministic and
 *     reproducible from a known seed.
 *
 * Lifecycle of this system:
 *   const sys = new LifecycleSystem(eventBus, rng);
 *   const agents = sys.spawnInitialAgents(count, regionMap, navGrid);
 *   // ... each tick:
 *   sys.tick(agents, worldState);
 *
 * Pure ES module. No Three.js, no DOM, fully headless-safe.
 */

import { createAgent, ROLES } from './agent-state.js';

// ---------------------------------------------------------------------------
// Tuning constants
// ---------------------------------------------------------------------------

/**
 * Death thresholds — agents die when a condition breaches these limits.
 *
 * HUNGER_DEATH_THRESHOLD: hunger need reaches 1.0 (completely starved).
 * HP_DEATH_THRESHOLD: hit points drop to 0 or below (combat/injury).
 * DISEASE_DEATH_THRESHOLD: diseaseSeverity reaches 1.0 (terminal illness).
 * DISEASE_DEATH_PROBABILITY: even at terminal severity, death is probabilistic
 *   per tick — this avoids all diseased agents dying in the exact same tick,
 *   which would look artificial and spike event processing.
 */
const HUNGER_DEATH_THRESHOLD       = 1.0;
const HP_DEATH_THRESHOLD           = 0;
const DISEASE_DEATH_THRESHOLD      = 1.0;
const DISEASE_DEATH_PROBABILITY    = 0.3;

/**
 * Birth conditions — all must be satisfied simultaneously.
 *
 * BIRTH_MAX_STRESS: prospective parent must be calm enough.
 * BIRTH_MIN_ENERGY: prospective parent must not be exhausted.
 * BIRTH_MIN_HUNGER_HEADROOM: parent's hunger must be below this (well-fed).
 * BIRTH_CHECK_PROBABILITY: even when conditions are met, birth is stochastic
 *   — this controls expected births per eligible agent per tick.
 * POPULATION_CAP_MULTIPLIER: population cannot exceed initial count * this.
 *   Prevents runaway growth that would tank simulation performance.
 */
const BIRTH_MAX_STRESS             = 0.3;
const BIRTH_MIN_ENERGY             = 0.5;
const BIRTH_MIN_HUNGER_HEADROOM    = 0.5;
const BIRTH_CHECK_PROBABILITY      = 0.02;
const POPULATION_CAP_MULTIPLIER    = 3;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a role string array from the ROLES enum for random assignment.
 * Cached once at module load so we don't rebuild every spawn call.
 */
const ROLE_VALUES = Object.values(ROLES);

/**
 * Pick a random element from an array using the injected PRNG.
 *
 * @param {Array} arr — Non-empty array.
 * @param {{ next(): number }} rng — PRNG with next() returning [0, 1).
 * @returns {*} A randomly selected element.
 */
function pickRandom(arr, rng) {
  // Math.floor(rng.next() * arr.length) is uniform over [0, arr.length - 1]
  // because rng.next() is in [0, 1) and arr.length is a positive integer.
  return arr[Math.floor(rng.next() * arr.length)];
}

// ---------------------------------------------------------------------------
// LifecycleSystem
// ---------------------------------------------------------------------------

export class LifecycleSystem {
  /**
   * @param {{ emit(type: string, payload: Object): void }} eventBus
   *   Event bus for broadcasting birth/death events to other systems.
   * @param {{ next(): number, nextSigned(): number }} rng
   *   Deterministic PRNG — all stochastic decisions route through this.
   */
  constructor(eventBus, rng) {
    /** @private */ this._eventBus = eventBus;
    /** @private */ this._rng = rng;

    /**
     * Monotonically increasing counter for generating unique agent IDs.
     * Starts at 0; spawnInitialAgents and birth logic both increment it.
     * Using a simple counter (not UUID) because the simulation is
     * single-threaded and deterministic — no collision risk.
     * @private
     */
    this._nextId = 0;

    /**
     * The initial population size, set once by spawnInitialAgents.
     * Used to compute the population cap (initial * POPULATION_CAP_MULTIPLIER).
     * @private
     */
    this._initialPopulation = 0;
  }

  // -------------------------------------------------------------------------
  // Initial spawn
  // -------------------------------------------------------------------------

  /**
   * Distribute `count` agents across regions proportional to region size,
   * placing each at a random walkable cell in its assigned region.
   *
   * @param {number} count — Total number of agents to spawn.
   * @param {Map<string, { id: string, cells: Array<{ x: number, y: number, z: number }> }>} regionMap
   *   Map of regionId → region descriptor. Each region must have a `cells`
   *   array of walkable positions. Regions with more cells get more agents.
   * @param {Object} navGrid — Navigation grid (reserved for future pathfinding
   *   integration; currently unused but accepted to lock the interface).
   * @returns {Array<Object>} Array of freshly created agent snapshots.
   */
  spawnInitialAgents(count, regionMap, navGrid) {
    this._initialPopulation = count;

    const regions = Array.from(regionMap.values());

    // Guard: if no regions or no walkable cells, return empty.
    if (regions.length === 0) {
      return [];
    }

    // Compute total walkable cells across all regions to derive proportional
    // allocation. Regions with zero cells get zero agents.
    const totalCells = regions.reduce((sum, r) => sum + r.cells.length, 0);
    if (totalCells === 0) {
      return [];
    }

    // Proportional allocation: region gets floor(count * regionCells / total).
    // Remainder agents are distributed round-robin to the largest regions
    // to avoid systematic bias toward small regions.
    const allocations = regions.map(r => ({
      region: r,
      base: Math.floor(count * r.cells.length / totalCells),
    }));

    // Distribute leftover agents (due to floor rounding).
    let allocated = allocations.reduce((s, a) => s + a.base, 0);
    let remainder = count - allocated;

    // Sort descending by cell count so remainders go to largest regions first.
    // This is a stable tie-breaking heuristic — deterministic given the same
    // regionMap insertion order and cell counts.
    const sortedBySize = [...allocations].sort(
      (a, b) => b.region.cells.length - a.region.cells.length
    );
    for (let i = 0; remainder > 0 && i < sortedBySize.length; i++) {
      sortedBySize[i].base += 1;
      remainder -= 1;
    }

    // Spawn agents into their assigned regions.
    const agents = [];

    for (const { region, base: agentCount } of allocations) {
      for (let i = 0; i < agentCount; i++) {
        // Pick a random walkable cell within this region.
        const cell = pickRandom(region.cells, this._rng);

        const agent = createAgent(`agent-${this._nextId++}`, {
          position: { x: cell.x, y: cell.y, z: cell.z },
          regionId: region.id,
          // Assign a random role — the decision system can reassign later.
          role: pickRandom(ROLE_VALUES, this._rng),
        });

        agents.push(agent);
      }
    }

    return agents;
  }

  // -------------------------------------------------------------------------
  // Per-tick update
  // -------------------------------------------------------------------------

  /**
   * Run death checks and birth logic for one simulation tick.
   *
   * Death is checked first so that the population count used for the birth
   * cap reflects deaths that just occurred this tick. This avoids a one-tick
   * lag where births could push past the cap because deaths hadn't been
   * counted yet.
   *
   * @param {Array<Object>} agents — Mutable array of agent snapshots.
   *   Dead agents are marked `alive = false` in place. Newborn agents are
   *   pushed onto the end of this array.
   * @param {Object} worldState — Global simulation state, must include:
   *   @param {Map<string, { cells: Array<{x,y,z}> }>} worldState.regionMap
   */
  tick(agents, worldState) {
    // --- Phase 1: Death ---
    this._processDeath(agents);

    // --- Phase 2: Birth ---
    this._processBirth(agents, worldState);
  }

  // -------------------------------------------------------------------------
  // Death logic (private)
  // -------------------------------------------------------------------------

  /**
   * Check each living agent for death conditions.
   *
   * Three independent causes, checked in priority order:
   *   1. Starvation (hunger >= 1.0)
   *   2. HP depletion (hp <= 0)
   *   3. Terminal disease (severity >= 1.0, probabilistic)
   *
   * Only the first matching cause is reported — an agent can only die once.
   *
   * @param {Array<Object>} agents — Agent array; dead agents are mutated.
   * @private
   */
  _processDeath(agents) {
    for (const agent of agents) {
      // Skip already-dead agents to avoid duplicate death events.
      if (!agent.alive) continue;

      let cause = null;

      // Starvation check: hunger is a [0, 1] need where 1.0 means
      // completely starved. This is the most common death cause in
      // early simulation when food systems are sparse.
      if (agent.needs.hunger >= HUNGER_DEATH_THRESHOLD) {
        cause = 'starvation';
      }
      // HP depletion: combat, falls, or accumulated injury damage.
      else if (agent.health.hp <= HP_DEATH_THRESHOLD) {
        cause = 'hp_depletion';
      }
      // Terminal disease: severity has reached maximum, but death is
      // probabilistic to avoid mass simultaneous die-off.
      else if (
        agent.health.diseaseSeverity >= DISEASE_DEATH_THRESHOLD &&
        this._rng.next() < DISEASE_DEATH_PROBABILITY
      ) {
        cause = 'disease';
      }

      if (cause !== null) {
        agent.alive = false;

        this._eventBus.emit('death', {
          agentId:  agent.id,
          cause,
          position: { ...agent.position },
          regionId: agent.regionId,
        });
      }
    }
  }

  // -------------------------------------------------------------------------
  // Birth logic (private)
  // -------------------------------------------------------------------------

  /**
   * Attempt births from eligible living agents.
   *
   * Eligibility requires:
   *   - Agent is alive.
   *   - Stress below threshold (calm enough to reproduce).
   *   - Energy above threshold (not exhausted).
   *   - Hunger below threshold (well-fed).
   *   - Stochastic check passes (BIRTH_CHECK_PROBABILITY per tick).
   *   - Population is below the cap.
   *
   * Newborn agents inherit the parent's region and spawn at a random walkable
   * cell in that region. They start with default needs/health (fresh slate).
   *
   * @param {Array<Object>} agents — Agent array; newborns are pushed onto it.
   * @param {Object} worldState — Must contain regionMap.
   * @private
   */
  _processBirth(agents, worldState) {
    const populationCap = this._initialPopulation * POPULATION_CAP_MULTIPLIER;
    const regionMap = worldState.regionMap;

    // Count living agents once up front rather than per-candidate, since
    // the count only changes by +1 per birth and we recheck below.
    let livingCount = 0;
    for (const a of agents) {
      if (a.alive) livingCount++;
    }

    // Collect newborns in a separate array, then push all at once.
    // This avoids mutating the agents array while iterating over it, which
    // could cause newly born agents to be checked for birth in the same tick
    // (they shouldn't — they were just born).
    const newborns = [];

    for (const agent of agents) {
      // Population cap check — includes newborns accumulated this tick.
      if (livingCount + newborns.length >= populationCap) break;

      if (!agent.alive) continue;

      // Condition checks: all thresholds must be met simultaneously.
      if (agent.needs.stress > BIRTH_MAX_STRESS) continue;
      if (agent.needs.energy < BIRTH_MIN_ENERGY) continue;
      if (agent.needs.hunger >= BIRTH_MIN_HUNGER_HEADROOM) continue;

      // Stochastic gate: even when all conditions are favorable, birth
      // is rare per tick to keep population growth gradual.
      if (this._rng.next() >= BIRTH_CHECK_PROBABILITY) continue;

      // Find walkable cells in the parent's region for newborn placement.
      const region = agent.regionId ? regionMap.get(agent.regionId) : null;
      if (!region || region.cells.length === 0) continue;

      const cell = pickRandom(region.cells, this._rng);

      const child = createAgent(`agent-${this._nextId++}`, {
        position: { x: cell.x, y: cell.y, z: cell.z },
        regionId: agent.regionId,
        role:     pickRandom(ROLE_VALUES, this._rng),
        // Newborns may optionally inherit faction from parent.
        factionId: agent.factionId,
      });

      newborns.push(child);

      this._eventBus.emit('birth', {
        childId:  child.id,
        parentId: agent.id,
        position: { ...child.position },
        regionId: child.regionId,
      });
    }

    // Append all newborns to the agent array after iteration is complete.
    for (const nb of newborns) {
      agents.push(nb);
    }
  }
}
