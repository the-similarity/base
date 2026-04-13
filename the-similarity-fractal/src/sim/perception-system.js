/**
 * Perception system for the 3D society simulation.
 *
 * Responsibilities:
 * - Maintains a spatial hash (grid-based bucketing) of agent positions for
 *   efficient proximity queries.
 * - Provides each agent with nearby agents within a configurable radius.
 * - Computes region summaries (population, average resources, hostility level).
 * - Exposes known remote regions from an agent's memory for decision-making.
 *
 * Design constraints:
 * - Pure ES module, no Three.js dependency — must run headless.
 * - The spatial hash is rebuilt every tick (O(n) rebuild, O(1) per bucket lookup).
 *   This is preferred over incremental updates because agent positions change
 *   frequently and the rebuild cost is dominated by the number of alive agents,
 *   which is modest (100-1000 range).
 * - Region summaries are computed lazily and cached for the duration of one tick.
 *
 * Performance characteristics:
 * - Spatial hash cell size should be >= the largest perception radius used.
 *   Default is 10 world units, which works for typical perception radii of 5-15.
 * - getNearby() checks at most 9 cells (3x3 neighborhood), so cost is O(k)
 *   where k is agents in those cells, not O(n) total agents.
 *
 * Lifecycle:
 * - Constructed once (no external dependencies required).
 * - `tick()` called every simulation tick to rebuild spatial index and region cache.
 * - Query methods (getNearby, getRegionSummary) are valid only after tick().
 */

// ── Configuration constants ──────────────────────────────────────────────────

// Spatial hash cell size in world units. Agents within the same cell or adjacent
// cells can be found in O(1) bucket lookups. This value should be >= the typical
// perception radius to ensure a 3x3 cell scan covers the full circle.
const DEFAULT_CELL_SIZE = 10;

/**
 * Perception system providing spatial awareness to agents.
 *
 * Invariants:
 * - The spatial hash is rebuilt from scratch every tick. No stale data persists.
 * - Region summaries are computed on first access per tick, then cached.
 * - This system is read-only with respect to agent state — it never mutates agents.
 * - All query results are snapshots: callers may mutate the returned arrays
 *   without affecting internal state.
 */
export class PerceptionSystem {
  /**
   * @param {Object} [config]           - Optional configuration.
   * @param {number} [config.cellSize]  - Spatial hash cell size in world units.
   */
  constructor(config = {}) {
    // Cell size for the spatial hash grid. Controls the granularity of
    // bucket assignment. Larger cells = fewer buckets but more agents per bucket.
    this._cellSize = config.cellSize ?? DEFAULT_CELL_SIZE;

    // The spatial hash: Map<string, Array<Object>>
    // Key is "cellX:cellZ", value is array of agent references in that cell.
    this._hash = new Map();

    // Reverse lookup: agentId -> {cellX, cellZ} for fast self-exclusion
    // and position retrieval during getNearby queries.
    this._agentCells = new Map();

    // Region summary cache: regionId -> summary object.
    // Rebuilt lazily each tick (cleared at tick start, populated on demand).
    this._regionCache = new Map();

    // Agent ID -> agent reference Map, built during tick() for O(1) lookups.
    // Avoids O(n) linear scans when getNearby() needs the querying agent's position.
    this._agentById = new Map();

    // Reference to the current agent array and worldState for lazy computation.
    // Set during tick(), cleared conceptually (overwritten) each tick.
    this._agents = null;
    this._worldState = null;
  }

  /**
   * Rebuild the spatial hash and clear caches for this tick.
   *
   * Must be called before any getNearby() or getRegionSummary() queries.
   * Iterates all alive agents once to bucket them into the spatial hash.
   *
   * @param {Array<Object>} agents     - Full agent array (may include dead agents).
   * @param {Object}        worldState - Current world snapshot.
   */
  tick(agents, worldState) {
    // Store references for lazy region summary computation.
    this._agents = agents;
    this._worldState = worldState;

    this._hash.clear();
    this._agentCells.clear();
    this._agentById.clear();
    this._regionCache.clear();

    // Insert every alive agent into the spatial hash.
    for (const agent of agents) {
      if (!agent.alive) continue;

      const cellX = Math.floor(agent.position.x / this._cellSize);
      const cellZ = Math.floor(agent.position.z / this._cellSize);
      const key = `${cellX}:${cellZ}`;

      // Get or create the bucket for this cell.
      let bucket = this._hash.get(key);
      if (!bucket) {
        bucket = [];
        this._hash.set(key, bucket);
      }
      bucket.push(agent);

      this._agentCells.set(agent.id, { cellX, cellZ });
      this._agentById.set(agent.id, agent);
    }
  }

  /**
   * Find all alive agents within `radius` world units of the given agent.
   *
   * Algorithm:
   * 1. Determine how many cells the radius spans.
   * 2. Scan all cells in that range around the agent's cell.
   * 3. For each candidate, compute exact Euclidean distance in the XZ plane.
   * 4. Return those within radius, excluding the querying agent itself.
   *
   * The result is a new array (safe to mutate) of agent references sorted by
   * ascending distance, so the closest agent is first.
   *
   * @param {string|number} agentId - The querying agent's ID.
   * @param {number}        radius  - Search radius in world units.
   * @returns {Array<{agent: Object, distance: number}>} Nearby agents with distances.
   */
  getNearby(agentId, radius) {
    const cellInfo = this._agentCells.get(agentId);
    if (!cellInfo) return []; // Agent not found (dead or not indexed).

    // Find the querying agent to get their exact position.
    // We need the precise world coords, not just the cell, for distance filtering.
    const queryAgent = this._findAgentById(agentId);
    if (!queryAgent) return [];

    const { x: ax, z: az } = queryAgent.position;
    const radiusSq = radius * radius; // Compare squared distances to avoid sqrt.

    // How many cells does the radius span? We need to check this many cells
    // in each direction from the agent's cell.
    const cellSpan = Math.ceil(radius / this._cellSize);

    const results = [];

    // Scan the neighborhood of cells that could contain agents within radius.
    for (let dx = -cellSpan; dx <= cellSpan; dx++) {
      for (let dz = -cellSpan; dz <= cellSpan; dz++) {
        const key = `${cellInfo.cellX + dx}:${cellInfo.cellZ + dz}`;
        const bucket = this._hash.get(key);
        if (!bucket) continue;

        for (const candidate of bucket) {
          if (candidate.id === agentId) continue;

          // Euclidean distance in the XZ plane (Y/height is irrelevant for
          // social perception — agents on different elevations but close in
          // map distance can still perceive each other).
          const dx2 = candidate.position.x - ax;
          const dz2 = candidate.position.z - az;
          const distSq = dx2 * dx2 + dz2 * dz2;

          if (distSq <= radiusSq) {
            results.push({
              agent: candidate,
              distance: Math.sqrt(distSq),
            });
          }
        }
      }
    }

    // Sort by distance so callers can prioritize closest agents.
    results.sort((a, b) => a.distance - b.distance);
    return results;
  }

  /**
   * Convenience wrapper: accepts an agent object (or ID) and returns a flat
   * array of nearby agent objects (no distance metadata). Used by systems
   * like DiseaseSystem that call getNearbyAgents(agent, radius).
   *
   * @param {Object|string} agentOrId - Agent object or agent ID string.
   * @param {number} radius - Search radius in world units.
   * @returns {Array<Object>} Flat array of nearby agent objects.
   */
  getNearbyAgents(agentOrId, radius) {
    const id = typeof agentOrId === 'string' ? agentOrId : agentOrId?.id;
    return this.getNearby(id, radius).map(entry => entry.agent);
  }

  /**
   * Get a summary of a specific region's current state.
   *
   * Computed lazily on first access per tick, then cached. The summary includes:
   * - population: number of alive agents in the region.
   * - avgResources: average of agents' inventory/wealth in the region.
   * - hostilityLevel: fraction of agents with stress above a threshold (0-1).
   *
   * @param {string|number} regionId - Region identifier.
   * @returns {{population: number, avgResources: number, hostilityLevel: number}}
   */
  getRegionSummary(regionId) {
    // Check cache first — summaries are stable within a single tick.
    if (this._regionCache.has(regionId)) {
      return this._regionCache.get(regionId);
    }

    // Compute the summary by iterating agents in this region.
    const summary = this._computeRegionSummary(regionId);
    this._regionCache.set(regionId, summary);
    return summary;
  }

  // ── Private helpers ──────────────────────────────────────────────────────

  /**
   * Find an agent by ID using the pre-built index (O(1) lookup).
   *
   * @param {string|number} agentId
   * @returns {Object|null}
   */
  _findAgentById(agentId) {
    return this._agentById.get(agentId) ?? null;
  }

  /**
   * Compute region summary from the current agent array.
   *
   * Scans all alive agents and aggregates those in the specified region.
   *
   * Hostility is defined as the fraction of agents whose stress exceeds 0.6
   * (a tunable threshold). This provides a simple proxy for regional tension
   * that the decision system can use without complex social graph analysis.
   *
   * @param {string|number} regionId
   * @returns {{population: number, avgResources: number, hostilityLevel: number}}
   */
  _computeRegionSummary(regionId) {
    if (!this._agents) {
      return { population: 0, avgResources: 0, hostilityLevel: 0 };
    }

    let population = 0;
    let totalResources = 0;
    let hostileCount = 0;

    // Stress threshold above which an agent is considered "hostile" for
    // the purpose of regional tension scoring. 0.6 is chosen as a moderate
    // threshold — agents under significant stress but not yet in crisis.
    const HOSTILITY_STRESS_THRESHOLD = 0.6;

    for (const agent of this._agents) {
      if (!agent.alive) continue;
      if (agent.regionId !== regionId) continue;

      population++;

      // Resources: sum of inventory value or wealth. Agents may store resources
      // differently; we support both a simple `wealth` number and an inventory
      // object with a `total` or individual item counts.
      if (typeof agent.inventory === 'number') {
        totalResources += agent.inventory;
      } else if (agent.inventory?.total !== undefined) {
        totalResources += agent.inventory.total;
      } else if (typeof agent.wealth === 'number') {
        totalResources += agent.wealth;
      }

      // Hostility: stress-based proxy.
      const stress = agent.needs?.stress ?? 0;
      if (stress > HOSTILITY_STRESS_THRESHOLD) {
        hostileCount++;
      }
    }

    return {
      population,
      avgResources: population > 0 ? totalResources / population : 0,
      // Hostility level is a ratio [0, 1] — fraction of stressed agents.
      hostilityLevel: population > 0 ? hostileCount / population : 0,
    };
  }
}
