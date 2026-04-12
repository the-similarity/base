/**
 * Level-of-Detail (LOD) system for agent simulation fidelity management.
 *
 * Responsibilities:
 * - Classifies every agent into one of three tiers each tick:
 *     SPOTLIGHT — full perception + social reasoning every tick.
 *     ACTIVE    — full survival/movement but reduced social detail.
 *     BACKGROUND — coarse updates every N ticks (skip intermediate ticks).
 * - Classification is based on distance from a configurable focus point
 *   (camera position, a named agent, or any world coordinate).
 * - Provides query methods so other systems can check an agent's tier and
 *   decide how much work to do for that agent on any given tick.
 *
 * Design constraints:
 * - Pure ES module, no Three.js dependency — must run headless.
 * - The tier map is rebuilt every tick. No stale classifications persist.
 * - This system is read-only with respect to agent state — it never mutates
 *   agents. It only reads agent.position and agent.id.
 *
 * Why three tiers (not two, not continuous):
 * - Two tiers (on/off) creates a visible pop-in boundary with no transition zone.
 * - Continuous LOD requires every system to handle fractional fidelity, which
 *   adds complexity without proportional benefit at our population scale (100-1000).
 * - Three tiers give a smooth falloff: full detail near focus, moderate detail
 *   in the mid-range, and cheap batch updates for distant agents.
 *
 * Performance characteristics:
 * - tick() is O(n) where n is the number of alive agents.
 * - Tier lookups (getTier, isSpotlight, isBackground) are O(1) Map lookups.
 * - Background agents only get full updates every backgroundTickInterval ticks,
 *   reducing per-tick work by up to (1 - 1/N) for the background population.
 *
 * Lifecycle:
 * - Constructed once with configuration (radii, tick interval).
 * - `tick()` called every simulation tick with agents and a focus point.
 * - Query methods are valid only after tick().
 */

// ── Tier constants ───────────────────────────────────────────────────────────
// Exported so other systems can compare: `if (lod.getTier(id) === LOD_TIER.SPOTLIGHT)`
export const LOD_TIER = Object.freeze({
  SPOTLIGHT:  'SPOTLIGHT',
  ACTIVE:     'ACTIVE',
  BACKGROUND: 'BACKGROUND',
});

// ── Default configuration ────────────────────────────────────────────────────

// Agents within this radius of the focus point get SPOTLIGHT tier.
const DEFAULT_SPOTLIGHT_RADIUS = 20;

// Agents within this radius (but outside spotlight) get ACTIVE tier.
const DEFAULT_ACTIVE_RADIUS = 60;

// Background agents update fully only every N ticks. On other ticks, systems
// should skip expensive computation for them.
const DEFAULT_BACKGROUND_TICK_INTERVAL = 4;

/**
 * LOD system that classifies agents into fidelity tiers.
 *
 * Invariants:
 * - Tier assignments are recomputed from scratch every tick (no stale data).
 * - The system never mutates agent objects.
 * - An agent not found in the tier map (e.g., dead) defaults to BACKGROUND
 *   in query methods, ensuring fail-closed behavior (less work, not more).
 */
export class LODSystem {
  /**
   * @param {Object} [config]
   * @param {number} [config.spotlightRadius]        - Radius for SPOTLIGHT tier (world units).
   * @param {number} [config.activeRadius]            - Radius for ACTIVE tier (world units).
   * @param {number} [config.backgroundTickInterval]  - How often BACKGROUND agents get full updates.
   * @param {Function} [config.focusFn]               - Optional custom focus function: (agents, worldState) => {x, z}.
   *                                                    Overrides the focusPoint parameter in tick().
   */
  constructor(config = {}) {
    this._spotlightRadius = config.spotlightRadius ?? DEFAULT_SPOTLIGHT_RADIUS;
    this._activeRadius = config.activeRadius ?? DEFAULT_ACTIVE_RADIUS;
    this._backgroundTickInterval = config.backgroundTickInterval ?? DEFAULT_BACKGROUND_TICK_INTERVAL;

    // Optional custom focus function. If provided, tick() will call this
    // instead of using the explicit focusPoint parameter. This allows
    // dynamic focus (e.g., always track a specific named agent).
    this._focusFn = config.focusFn ?? null;

    // Pre-compute squared radii to avoid sqrt in distance comparisons.
    // This is a standard optimization for radius-based spatial classification.
    this._spotlightRadiusSq = this._spotlightRadius * this._spotlightRadius;
    this._activeRadiusSq = this._activeRadius * this._activeRadius;

    // Agent ID -> LOD_TIER mapping. Rebuilt every tick.
    this._tiers = new Map();

    // Global tick counter for determining which background ticks are "active".
    // Incremented every tick() call. Background agents get full updates when
    // (tickCount % backgroundTickInterval === 0).
    this._tickCount = 0;
  }

  /**
   * Classify all alive agents into LOD tiers based on distance from focus.
   *
   * Algorithm:
   * 1. Determine the focus point (from parameter, focusFn, or default origin).
   * 2. For each alive agent, compute squared distance to focus in XZ plane.
   * 3. Assign tier based on distance thresholds.
   *
   * @param {Array<Object>} agents     - Full agent array (may include dead agents).
   * @param {{x: number, z: number}} [focusPoint] - World-space focus point.
   *   Ignored if a focusFn was provided in constructor config.
   */
  tick(agents, focusPoint) {
    this._tickCount++;
    this._tiers.clear();

    // Resolve the focus point. Priority:
    // 1. Custom focusFn (dynamic, e.g., tracking a specific agent).
    // 2. Explicit focusPoint parameter (e.g., camera position).
    // 3. Default to world origin (0, 0) — safe fallback that puts everyone
    //    at roughly equal distance, so all get ACTIVE or BACKGROUND.
    let focus;
    if (this._focusFn) {
      focus = this._focusFn(agents, focusPoint);
    }
    if (!focus) {
      focus = focusPoint ?? { x: 0, z: 0 };
    }

    const fx = focus.x ?? 0;
    const fz = focus.z ?? 0;

    for (const agent of agents) {
      if (!agent.alive) continue;

      // Squared Euclidean distance in the XZ plane.
      // Y (height) is excluded because LOD is about map proximity, not elevation.
      const dx = agent.position.x - fx;
      const dz = agent.position.z - fz;
      const distSq = dx * dx + dz * dz;

      // Classify into the highest-fidelity tier whose radius contains the agent.
      // Check from innermost to outermost.
      let tier;
      if (distSq <= this._spotlightRadiusSq) {
        tier = LOD_TIER.SPOTLIGHT;
      } else if (distSq <= this._activeRadiusSq) {
        tier = LOD_TIER.ACTIVE;
      } else {
        tier = LOD_TIER.BACKGROUND;
      }

      this._tiers.set(agent.id, tier);
    }
  }

  /**
   * Get the LOD tier for a specific agent.
   *
   * @param {string|number} agentId
   * @returns {string} One of LOD_TIER values. Defaults to BACKGROUND if not found.
   */
  getTier(agentId) {
    return this._tiers.get(agentId) ?? LOD_TIER.BACKGROUND;
  }

  /**
   * Check if an agent is in the SPOTLIGHT tier (full fidelity).
   *
   * @param {string|number} agentId
   * @returns {boolean}
   */
  isSpotlight(agentId) {
    return this._tiers.get(agentId) === LOD_TIER.SPOTLIGHT;
  }

  /**
   * Check if an agent is in the BACKGROUND tier (reduced fidelity).
   *
   * @param {string|number} agentId
   * @returns {boolean}
   */
  isBackground(agentId) {
    // Default to true for unknown agents — fail-closed means less work.
    const tier = this._tiers.get(agentId);
    return tier === LOD_TIER.BACKGROUND || tier === undefined;
  }

  /**
   * Check whether this tick is an "active" tick for BACKGROUND agents.
   *
   * Background agents should receive full updates only on active ticks.
   * Other systems should call this to decide whether to process background agents:
   *
   *   if (lod.isBackground(agent.id) && !lod.isBackgroundActiveTick()) continue;
   *
   * @returns {boolean} True if background agents should be fully updated this tick.
   */
  isBackgroundActiveTick() {
    return (this._tickCount % this._backgroundTickInterval) === 0;
  }

  /**
   * Get counts of agents in each tier. Useful for debug overlays and telemetry.
   *
   * @returns {{spotlight: number, active: number, background: number}}
   */
  getCounts() {
    let spotlight = 0;
    let active = 0;
    let background = 0;

    for (const tier of this._tiers.values()) {
      switch (tier) {
        case LOD_TIER.SPOTLIGHT:  spotlight++;  break;
        case LOD_TIER.ACTIVE:    active++;     break;
        case LOD_TIER.BACKGROUND: background++; break;
      }
    }

    return { spotlight, active, background };
  }

  /**
   * Get the current tick count. Useful for external systems that need to
   * coordinate their own background-tick logic with the LOD system.
   *
   * @returns {number}
   */
  getTickCount() {
    return this._tickCount;
  }
}
