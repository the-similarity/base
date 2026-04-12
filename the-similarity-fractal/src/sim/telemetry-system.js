/**
 * telemetry-system.js — Structured observability for the 3D society simulation.
 *
 * Subscribes to the event bus and accumulates per-tick metrics across three
 * scopes: global, regional, and network. Maintains rolling windows of
 * configurable size and can export the full run history as JSON for offline
 * analysis or similarity-engine ingestion.
 *
 * Lifecycle:
 *   1. Construct with an EventBus instance (binds listeners immediately).
 *   2. Call tick() once per simulation step — it snapshots all metrics.
 *   3. Query with getSlice / getHistory / getRollingWindow at any time.
 *   4. exportRun() returns a deep-copy JSON blob of the entire history.
 *
 * Immutability: Internal ring buffers are append-only. getSlice and
 * getHistory return shallow copies so callers cannot corrupt the store.
 *
 * Memory budget: Each tick stores ~(16 global floats + R*9 regional floats +
 * 6 network floats). At 1 000 ticks with 20 regions this is ~200 KB — well
 * within budget for in-browser use.
 *
 * @module telemetry-system
 */

// ── Metric key enums ────────────────────────────────────────────────────────

/** Global metrics collected every tick. */
const GLOBAL_METRICS = Object.freeze([
  'population_alive',
  'births',
  'deaths',
  'injuries',
  'infections',
  'recoveries',
  'conflicts',
  'trades',
  'migrations',
  'food_stock',
  'material_stock',
  'average_hunger',
  'average_health',
  'average_stress',
  'inequality_gini',
  'faction_count',
  'alliance_count',
]);

/** Per-region metrics collected every tick. */
const REGIONAL_METRICS = Object.freeze([
  'population',
  'deaths',
  'conflicts',
  'food_pressure',
  'migration_in',
  'migration_out',
  'disease_load',
  'wealth_density',
  'hostility_index',
]);

/** Network / social-graph metrics collected at configurable intervals. */
const NETWORK_METRICS = Object.freeze([
  'average_relationship_valence',
  'polarization',
  'clustering',
  'faction_modularity',
  'betrayal_rate',
  'centralization',
]);

// ── Default config ──────────────────────────────────────────────────────────

const DEFAULT_CONFIG = Object.freeze({
  /** How many ticks between network-metric recomputation (expensive). */
  networkAnalysisInterval: 10,
  /** Default rolling-window size for getRollingWindow. */
  defaultWindowSize: 50,
  /** Maximum ticks retained before the oldest are evicted (0 = unlimited). */
  maxHistory: 0,
});

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Compute the Gini coefficient for a non-negative array of values.
 *
 * Uses the relative mean absolute difference formula:
 *   G = (sum_i sum_j |x_i - x_j|) / (2 * n * sum_i x_i)
 *
 * Returns 0 when all values are equal or the array is empty.
 * Worst-case O(n^2) but n (agent count) is small (~100s).
 *
 * @param {number[]} values - Non-negative wealth / resource values.
 * @returns {number} Gini in [0, 1].
 */
function computeGini(values) {
  const n = values.length;
  if (n === 0) return 0;

  const sum = values.reduce((a, b) => a + b, 0);
  if (sum === 0) return 0; // everyone has nothing — perfectly "equal"

  let absDiffSum = 0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      absDiffSum += Math.abs(values[i] - values[j]);
    }
  }

  return absDiffSum / (2 * n * sum);
}

/**
 * Safe arithmetic mean — returns 0 for empty arrays.
 *
 * @param {number[]} arr
 * @returns {number}
 */
function mean(arr) {
  if (arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

// ── Event-bus counters ──────────────────────────────────────────────────────

/**
 * Ephemeral per-tick event counters reset at the start of each tick().
 * The event bus fires during system updates that precede the telemetry tick,
 * so these counters accumulate within the current simulation step.
 */
function createEventCounters() {
  return {
    births: 0,
    deaths: 0,
    injuries: 0,
    infections: 0,
    recoveries: 0,
    conflicts: 0,
    trades: 0,
    migrations: 0,
    // Regional breakdown: regionId -> { deaths, conflicts, migration_in, migration_out }
    regional: {},
  };
}

// ── TelemetrySystem ─────────────────────────────────────────────────────────

/**
 * Accumulates per-tick simulation metrics in three scopes (global, regional,
 * network) and provides query / export interfaces.
 *
 * The system is purely passive — it reads agent arrays and event-bus signals
 * but never mutates simulation state. This keeps the observer principle from
 * the architecture plan intact.
 */
export class TelemetrySystem {
  /**
   * @param {object} eventBus - Event bus instance with on(event, handler).
   * @param {object} [config] - Optional overrides merged onto DEFAULT_CONFIG.
   */
  constructor(eventBus, config = {}) {
    /** @type {object} Merged configuration. */
    this.config = { ...DEFAULT_CONFIG, ...config };

    /** @type {object} Reference to the shared event bus. */
    this.eventBus = eventBus;

    /**
     * Tick-indexed array of global metric snapshots.
     * globalHistory[t] = { population_alive, births, ... }
     * @type {object[]}
     */
    this.globalHistory = [];

    /**
     * Tick-indexed array of regional metric maps.
     * regionalHistory[t] = Map<regionId, { population, deaths, ... }>
     * @type {Map[]}
     */
    this.regionalHistory = [];

    /**
     * Sparse array of network metric snapshots, only populated every
     * networkAnalysisInterval ticks to amortise the O(n^2) graph cost.
     * networkHistory[t] = { average_relationship_valence, ... } | undefined
     * @type {object[]}
     */
    this.networkHistory = [];

    /** Current simulation tick (0-based, incremented in tick()). */
    this.currentTick = 0;

    // ── Event-bus wiring ──────────────────────────────────────────────
    // Counters live for exactly one tick, then get snapshot and reset.
    /** @private */
    this._counters = createEventCounters();

    this._bindEvents();
  }

  // ── Private: event-bus subscriptions ────────────────────────────────

  /**
   * Wire up event-bus listeners that increment ephemeral counters.
   * Each handler is intentionally minimal — just a counter bump — so the
   * event bus stays non-blocking even at high event throughput.
   * @private
   */
  _bindEvents() {
    const bus = this.eventBus;
    if (!bus || typeof bus.on !== 'function') return; // graceful no-op

    bus.on('birth', () => { this._counters.births++; });
    bus.on('death', (evt) => {
      this._counters.deaths++;
      this._bumpRegional(evt?.regionId, 'deaths');
    });
    bus.on('injury', () => { this._counters.injuries++; });
    bus.on('infection', () => { this._counters.infections++; });
    bus.on('recovery', () => { this._counters.recoveries++; });
    bus.on('conflict', (evt) => {
      this._counters.conflicts++;
      this._bumpRegional(evt?.regionId, 'conflicts');
    });
    bus.on('trade', () => { this._counters.trades++; });
    bus.on('migration', (evt) => {
      this._counters.migrations++;
      this._bumpRegional(evt?.fromRegion, 'migration_out');
      this._bumpRegional(evt?.toRegion, 'migration_in');
    });
  }

  /**
   * Increment a regional counter for a given region.
   * @private
   * @param {string|number|undefined} regionId
   * @param {string} field
   */
  _bumpRegional(regionId, field) {
    if (regionId == null) return;
    if (!this._counters.regional[regionId]) {
      this._counters.regional[regionId] = { deaths: 0, conflicts: 0, migration_in: 0, migration_out: 0 };
    }
    this._counters.regional[regionId][field]++;
  }

  // ── tick() — main entry point per simulation step ──────────────────

  /**
   * Snapshot all metrics for the current simulation tick.
   *
   * Must be called exactly once per tick, AFTER all other systems have
   * updated (so event counters are complete and agent state is final).
   *
   * @param {object[]} agents     - Array of agent state objects.
   * @param {object[]} factions   - Array of faction objects (each with .members, .alliances).
   * @param {Map|object} regionMap - Map of regionId -> region descriptor (with .agents or computed from agent positions).
   */
  tick(agents, factions, regionMap) {
    const t = this.currentTick;

    // ── Global metrics ───────────────────────────────────────────────
    const alive = agents.filter(a => a.alive !== false);
    const globalSnap = this._computeGlobalMetrics(alive, factions);
    this.globalHistory.push(globalSnap);

    // ── Regional metrics ─────────────────────────────────────────────
    const regionalSnap = this._computeRegionalMetrics(alive, regionMap);
    this.regionalHistory.push(regionalSnap);

    // ── Network metrics (amortised) ──────────────────────────────────
    if (t % this.config.networkAnalysisInterval === 0) {
      const netSnap = this._computeNetworkMetrics(alive, factions);
      this.networkHistory[t] = netSnap;
    }

    // ── Evict old history if capped ──────────────────────────────────
    if (this.config.maxHistory > 0 && this.globalHistory.length > this.config.maxHistory) {
      // Shift the oldest entry out of each store.
      // This keeps memory bounded at the cost of losing ancient data.
      this.globalHistory.shift();
      this.regionalHistory.shift();
      // Network history is sparse — we just delete the oldest key.
      // (Shifting a sparse array would break index alignment.)
    }

    // Reset event counters for next tick
    this._counters = createEventCounters();
    this.currentTick++;
  }

  // ── Private: metric computation ────────────────────────────────────

  /**
   * Compute global metrics from alive agents and faction list.
   * @private
   */
  _computeGlobalMetrics(alive, factions) {
    const c = this._counters;

    // Wealth array for Gini — use agent.wealth, fallback to 0
    const wealths = alive.map(a => a.wealth ?? 0);

    // Count alliances: each faction may have an .alliances array
    let allianceCount = 0;
    if (Array.isArray(factions)) {
      // Count unique alliance pairs to avoid double-counting
      const seen = new Set();
      for (const f of factions) {
        if (Array.isArray(f.alliances)) {
          for (const allyId of f.alliances) {
            const key = [f.id, allyId].sort().join(':');
            seen.add(key);
          }
        }
      }
      allianceCount = seen.size;
    }

    // Total food and material stock across all alive agents
    let foodStock = 0;
    let materialStock = 0;
    for (const a of alive) {
      foodStock += a.food ?? a.inventory?.food ?? 0;
      materialStock += a.materials ?? a.inventory?.materials ?? 0;
    }

    return {
      tick: this.currentTick,
      population_alive: alive.length,
      births: c.births,
      deaths: c.deaths,
      injuries: c.injuries,
      infections: c.infections,
      recoveries: c.recoveries,
      conflicts: c.conflicts,
      trades: c.trades,
      migrations: c.migrations,
      food_stock: foodStock,
      material_stock: materialStock,
      average_hunger: mean(alive.map(a => a.hunger ?? 0)),
      average_health: mean(alive.map(a => a.health ?? 1)),
      average_stress: mean(alive.map(a => a.stress ?? 0)),
      inequality_gini: computeGini(wealths),
      faction_count: Array.isArray(factions) ? factions.length : 0,
      alliance_count: allianceCount,
    };
  }

  /**
   * Compute per-region metrics.
   *
   * regionMap can be either a Map or a plain object keyed by regionId.
   * Each region descriptor should expose .id. Agents are assigned to
   * regions via agent.regionId.
   *
   * @private
   */
  _computeRegionalMetrics(alive, regionMap) {
    const result = new Map();

    // Build a lookup: regionId -> [agents in that region]
    const regionAgents = {};
    for (const a of alive) {
      const rid = a.regionId ?? a.region ?? 'unknown';
      if (!regionAgents[rid]) regionAgents[rid] = [];
      regionAgents[rid].push(a);
    }

    // Iterate over all known regions (from regionMap keys)
    const regionIds = regionMap instanceof Map
      ? [...regionMap.keys()]
      : Object.keys(regionMap ?? {});

    // Also include any region that agents claim but regionMap doesn't list.
    // Use a Set for O(1) membership checks instead of O(n) .includes().
    const regionIdSet = new Set(regionIds);
    for (const rid of Object.keys(regionAgents)) {
      if (!regionIdSet.has(rid)) regionIds.push(rid);
    }

    const c = this._counters;

    for (const rid of regionIds) {
      const agentsHere = regionAgents[rid] || [];
      const rc = c.regional[rid] || { deaths: 0, conflicts: 0, migration_in: 0, migration_out: 0 };

      // Food pressure: ratio of hungry agents to total in region.
      // 0 = nobody hungry, 1 = everyone starving.
      const hungryCount = agentsHere.filter(a => (a.hunger ?? 0) > 0.6).length;
      const foodPressure = agentsHere.length > 0 ? hungryCount / agentsHere.length : 0;

      // Disease load: fraction of infected agents in the region
      const infectedCount = agentsHere.filter(a => a.infected === true).length;
      const diseaseLoad = agentsHere.length > 0 ? infectedCount / agentsHere.length : 0;

      // Wealth density: total wealth per agent (0 if empty)
      const totalWealth = agentsHere.reduce((s, a) => s + (a.wealth ?? 0), 0);
      const wealthDensity = agentsHere.length > 0 ? totalWealth / agentsHere.length : 0;

      // Hostility index: fraction of agents with stress > 0.7
      // This is a proxy for regional tension. High stress correlates
      // with conflict likelihood in the decision system.
      const hostileCount = agentsHere.filter(a => (a.stress ?? 0) > 0.7).length;
      const hostilityIndex = agentsHere.length > 0 ? hostileCount / agentsHere.length : 0;

      result.set(rid, {
        population: agentsHere.length,
        deaths: rc.deaths,
        conflicts: rc.conflicts,
        food_pressure: foodPressure,
        migration_in: rc.migration_in,
        migration_out: rc.migration_out,
        disease_load: diseaseLoad,
        wealth_density: wealthDensity,
        hostility_index: hostilityIndex,
      });
    }

    return result;
  }

  /**
   * Compute network / social-graph metrics.
   *
   * These are O(n^2) in agent count because they inspect pairwise
   * relationships, so they only run every networkAnalysisInterval ticks.
   *
   * @private
   */
  _computeNetworkMetrics(alive, factions) {
    // ── Average relationship valence ───────────────────────────────
    // Each agent may have a .relationships map: agentId -> valence [-1, 1].
    // We average all pairwise valences.
    let valenceSum = 0;
    let valenceCount = 0;
    for (const a of alive) {
      if (a.relationships && typeof a.relationships === 'object') {
        const vals = Object.values(a.relationships);
        for (const v of vals) {
          valenceSum += v;
          valenceCount++;
        }
      }
    }
    const avgValence = valenceCount > 0 ? valenceSum / valenceCount : 0;

    // ── Polarization ───────────────────────────────────────────────
    // Variance of relationship valences. High variance = polarized
    // (strong loves and strong hates coexist).
    let valenceVarSum = 0;
    if (valenceCount > 0) {
      for (const a of alive) {
        if (a.relationships && typeof a.relationships === 'object') {
          for (const v of Object.values(a.relationships)) {
            valenceVarSum += (v - avgValence) ** 2;
          }
        }
      }
    }
    const polarization = valenceCount > 0 ? valenceVarSum / valenceCount : 0;

    // ── Clustering coefficient (approximate) ───────────────────────
    // For each agent, look at positive-valence neighbours (valence > 0)
    // and count what fraction of those neighbours are also positively
    // connected to each other. Average across all agents.
    // This is the classic local clustering coefficient adapted for
    // weighted signed graphs, thresholded at valence > 0.
    let clusteringSum = 0;
    let clusteringAgents = 0;
    const relMap = new Map(); // agentId -> Set of positive neighbours
    for (const a of alive) {
      const positives = new Set();
      if (a.relationships) {
        for (const [id, v] of Object.entries(a.relationships)) {
          if (v > 0) positives.add(id);
        }
      }
      relMap.set(String(a.id), positives);
    }

    for (const [_aid, neighbors] of relMap) {
      const nArr = [...neighbors];
      const k = nArr.length;
      if (k < 2) continue; // need at least 2 neighbours for triangles
      let triangles = 0;
      const possibleTriangles = k * (k - 1) / 2;
      for (let i = 0; i < k; i++) {
        for (let j = i + 1; j < k; j++) {
          const ni = relMap.get(nArr[i]);
          if (ni && ni.has(nArr[j])) triangles++;
        }
      }
      clusteringSum += triangles / possibleTriangles;
      clusteringAgents++;
    }
    const clustering = clusteringAgents > 0 ? clusteringSum / clusteringAgents : 0;

    // ── Faction modularity (simplified Newman modularity) ──────────
    // Q = (1/2m) * sum_ij [ A_ij - k_i*k_j/(2m) ] * delta(c_i, c_j)
    // We approximate: fraction of positive edges that are within-faction
    // minus the expected fraction if edges were random.
    let withinFaction = 0;
    let totalPositive = 0;
    const agentFaction = new Map();
    if (Array.isArray(factions)) {
      for (const f of factions) {
        if (Array.isArray(f.members)) {
          for (const mid of f.members) {
            agentFaction.set(String(mid), f.id);
          }
        }
      }
    }
    for (const a of alive) {
      if (!a.relationships) continue;
      const fA = agentFaction.get(String(a.id));
      for (const [targetId, v] of Object.entries(a.relationships)) {
        if (v > 0) {
          totalPositive++;
          const fB = agentFaction.get(String(targetId));
          if (fA != null && fA === fB) withinFaction++;
        }
      }
    }
    // Modularity proxy: within-faction fraction minus uniform expectation
    const factionCount = Array.isArray(factions) ? factions.length : 1;
    const expectedWithin = factionCount > 0 ? 1 / factionCount : 0;
    const actualWithin = totalPositive > 0 ? withinFaction / totalPositive : 0;
    const factionModularity = actualWithin - expectedWithin;

    // ── Betrayal rate ──────────────────────────────────────────────
    // Fraction of relationships that flipped from positive to negative
    // since last network snapshot. We store the previous snapshot's
    // valences for comparison.
    let betrayals = 0;
    let stablePositives = 0;
    if (this._prevRelationships) {
      for (const a of alive) {
        const prev = this._prevRelationships.get(String(a.id));
        if (!prev || !a.relationships) continue;
        for (const [tid, v] of Object.entries(a.relationships)) {
          if (prev[tid] != null && prev[tid] > 0 && v < 0) {
            betrayals++;
          }
          if (prev[tid] != null && prev[tid] > 0) {
            stablePositives++;
          }
        }
      }
    }
    const betrayalRate = stablePositives > 0 ? betrayals / stablePositives : 0;

    // Store current relationships for next comparison
    this._prevRelationships = new Map();
    for (const a of alive) {
      if (a.relationships) {
        this._prevRelationships.set(String(a.id), { ...a.relationships });
      }
    }

    // ── Centralization ─────────────────────────────────────────────
    // Degree centralization: how much does the most-connected agent
    // dominate? C_D = sum(d_max - d_i) / ((n-1)*(n-2))
    // where d_i = number of positive connections for agent i.
    const degrees = alive.map(a => {
      if (!a.relationships) return 0;
      return Object.values(a.relationships).filter(v => v > 0).length;
    });
    const maxDeg = Math.max(0, ...degrees);
    const n = alive.length;
    let centralNum = 0;
    for (const d of degrees) centralNum += maxDeg - d;
    const centralDenom = (n - 1) * (n - 2);
    const centralization = centralDenom > 0 ? centralNum / centralDenom : 0;

    return {
      tick: this.currentTick,
      average_relationship_valence: avgValence,
      polarization,
      clustering,
      faction_modularity: factionModularity,
      betrayal_rate: betrayalRate,
      centralization,
    };
  }

  // ── Query interface ────────────────────────────────────────────────

  /**
   * Get the full metric snapshot for a single tick.
   *
   * @param {number} tick - 0-based tick index.
   * @returns {{ global: object, regional: Map, network: object|null }}
   */
  getSlice(tick) {
    return {
      global: this.globalHistory[tick] ? { ...this.globalHistory[tick] } : null,
      regional: this.regionalHistory[tick] ?? null,
      network: this.networkHistory[tick] ? { ...this.networkHistory[tick] } : null,
    };
  }

  /**
   * Get time-series values for a single global metric.
   *
   * @param {string} metric  - One of GLOBAL_METRICS.
   * @param {number} fromTick - Start tick (inclusive).
   * @param {number} toTick   - End tick (inclusive).
   * @returns {number[]} Array of values, one per tick in [fromTick, toTick].
   */
  getHistory(metric, fromTick, toTick) {
    const result = [];
    const start = Math.max(0, fromTick);
    const end = Math.min(this.globalHistory.length - 1, toTick);

    for (let t = start; t <= end; t++) {
      const snap = this.globalHistory[t];
      result.push(snap ? (snap[metric] ?? null) : null);
    }

    return result;
  }

  /**
   * Get the most recent `windowSize` values for a global metric,
   * ending at the latest tick.
   *
   * @param {string} metric     - One of GLOBAL_METRICS.
   * @param {number} [windowSize] - Defaults to config.defaultWindowSize.
   * @returns {number[]}
   */
  getRollingWindow(metric, windowSize) {
    const ws = windowSize ?? this.config.defaultWindowSize;
    const end = this.globalHistory.length - 1;
    const start = Math.max(0, end - ws + 1);
    return this.getHistory(metric, start, end);
  }

  /**
   * Export the full simulation run as a plain JSON-serializable object.
   *
   * Regional Maps are converted to plain objects for JSON compatibility.
   *
   * @returns {object} Deep-copy of { global, regional, network, tickCount }.
   */
  exportRun() {
    return {
      tickCount: this.currentTick,
      global: this.globalHistory.map(s => ({ ...s })),
      regional: this.regionalHistory.map(m => {
        const obj = {};
        if (m instanceof Map) {
          for (const [k, v] of m) obj[k] = { ...v };
        }
        return obj;
      }),
      network: this.networkHistory
        .filter(s => s != null)
        .map(s => ({ ...s })),
    };
  }
}

// ── Named exports ───────────────────────────────────────────────────────────

export { GLOBAL_METRICS, REGIONAL_METRICS, NETWORK_METRICS, computeGini };
