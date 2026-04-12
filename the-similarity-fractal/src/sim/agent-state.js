/**
 * agent-state.js — Canonical agent data model for the 3D Society Simulation.
 *
 * This module defines the shape of every agent in the simulation as an
 * immutable-by-convention "snapshot" object. The simulation engine never
 * mutates agent snapshots in place during a tick; instead, systems read
 * the current snapshot, compute deltas, and produce a new snapshot via
 * cloneAgent + field writes. This makes time-travel debugging and rollback
 * straightforward — just keep old snapshots around.
 *
 * Lifecycle:
 *   createAgent(id, options) → fresh snapshot with defaults merged
 *   cloneAgent(agent)        → deep copy suitable for mutation in a new tick
 *
 * Invariants:
 *   - Every agent has a unique string `id`.
 *   - `needs` values are clamped to [0, 1] by consuming systems (not enforced
 *     here — this module is a data definition, not a validator).
 *   - `health.hp` is an integer in [0, 100] by convention.
 *   - `relationships` is a Map<agentId, number> where the number encodes
 *     affinity (negative = hostile, positive = friendly, 0 = neutral).
 *   - `memorySummary` is a bounded FIFO of short strings; systems that push
 *     to it are responsible for pruning.
 *
 * Pure ES module. No Three.js, no DOM, fully headless-safe.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * All valid agent roles.
 *
 * Roles determine which goal-selection heuristics the decision system uses.
 * Agents may change roles at runtime (e.g., a gatherer promoted to leader),
 * so this is not a compile-time constraint — it is a runtime vocabulary.
 */
export const ROLES = Object.freeze({
  GATHERER: 'gatherer',
  HUNTER:   'hunter',
  TRADER:   'trader',
  BUILDER:  'builder',
  HEALER:   'healer',
  SOLDIER:  'soldier',
  LEADER:   'leader',
});

/**
 * Default need levels for a freshly spawned agent.
 *
 * Why these values: a new agent starts well-rested and hydrated (energy=1,
 * hydration=1), not yet hungry (hunger=0), moderately social (0.5 — neither
 * lonely nor overwhelmed), and calm (stress=0). Consuming systems will
 * decay/grow these each tick.
 */
export const NEEDS_DEFAULTS = Object.freeze({
  hunger:    0,
  energy:    1,
  hydration: 1,
  social:    0.5,
  stress:    0,
});

/**
 * Default health block for a freshly spawned agent.
 *
 * hp=100 is full health. injury/infection/diseaseSeverity start at safe
 * values. Disease severity is a [0,1] float where 1.0 = terminal.
 */
export const HEALTH_DEFAULTS = Object.freeze({
  hp:              100,
  injury:          0,
  infection:       false,
  diseaseSeverity: 0,
});

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create a new agent snapshot.
 *
 * @param {string} id      — Unique identifier for this agent.
 * @param {Object} [options] — Optional overrides merged onto defaults.
 * @param {Object} [options.position]  — { x, y, z } spawn coordinates.
 * @param {string} [options.regionId]  — Region the agent starts in.
 * @param {Object} [options.needs]     — Partial overrides for NEEDS_DEFAULTS.
 * @param {Object} [options.health]    — Partial overrides for HEALTH_DEFAULTS.
 * @param {string} [options.role]      — One of ROLES values.
 * @param {string} [options.factionId] — Starting faction, or null.
 * @returns {Object} A fully-populated agent snapshot.
 */
export function createAgent(id, options = {}) {
  const {
    position  = { x: 0, y: 0, z: 0 },
    regionId  = null,
    needs     = {},
    health    = {},
    role      = ROLES.GATHERER,
    factionId = null,
  } = options;

  return {
    id,
    alive: true,

    // Spatial placement — updated by the movement system each tick.
    position: { ...position },
    regionId,

    // Physiological needs — each in [0, 1]. Consuming systems clamp.
    needs: { ...NEEDS_DEFAULTS, ...needs },

    // Physical condition — hp is integer [0, 100], diseaseSeverity [0, 1].
    health: { ...HEALTH_DEFAULTS, ...health },

    // Carried items — array of item descriptor objects (shape TBD by
    // inventory system; this module does not constrain item structure).
    inventory: [],

    // Social / organizational state.
    role,
    factionId,

    // Relationships: Map<agentId, affinity (-1..1)>.
    // Using a Map instead of a plain object so iteration order is
    // insertion-order and `.size` is O(1) — both matter when the
    // social system scans for allies/enemies.
    relationships: new Map(),

    // Short textual memory entries for LLM-flavored decision context.
    // Bounded by consuming systems, not here.
    memorySummary: [],

    // Current behavioral state — set by the goal/action planners.
    currentGoal:   null,
    currentAction: null,
  };
}

// ---------------------------------------------------------------------------
// Deep clone
// ---------------------------------------------------------------------------

/**
 * Produce a deep copy of an agent snapshot.
 *
 * Why a manual clone instead of structuredClone:
 *   - structuredClone does handle Maps, but we want explicit control over
 *     which fields get shallow vs deep treatment (e.g., inventory items
 *     are plain objects — spread is sufficient; relationships is a Map).
 *   - Keeps the module dependency-free and predictable across runtimes.
 *
 * @param {Object} agent — An agent snapshot produced by createAgent.
 * @returns {Object} A new snapshot with no shared references to the original.
 */
export function cloneAgent(agent) {
  return {
    id:    agent.id,
    alive: agent.alive,

    // Position is a small {x,y,z} — shallow spread is a full copy.
    position: { ...agent.position },
    regionId: agent.regionId,

    // Needs and health are flat objects — spread copies all primitives.
    needs:  { ...agent.needs },
    health: { ...agent.health },

    // Inventory items are cloned individually. Each item is assumed to be
    // a shallow plain object; if items gain nested structure, this must
    // become a recursive clone.
    inventory: agent.inventory.map(item => ({ ...item })),

    role:      agent.role,
    factionId: agent.factionId,

    // Deep-copy the relationship Map.
    relationships: new Map(agent.relationships),

    // Memory entries are strings — spreading the array is a full deep copy.
    memorySummary: [...agent.memorySummary],

    currentGoal:   agent.currentGoal,
    currentAction: agent.currentAction,
  };
}
