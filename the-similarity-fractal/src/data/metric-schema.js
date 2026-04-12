/**
 * metric-schema.js — Canonical definitions for all telemetry metrics.
 *
 * Three metric scopes: Global (whole-world aggregates), Regional (per-grid-cell
 * or per-region), and Network (social-graph-level). Each scope has a flat list
 * of named metrics and a factory that returns a zero-initialized snapshot
 * object for one tick.
 *
 * WHY three scopes?
 *   - Global lets the similarity engine run pattern-matching on civilisation-
 *     level time series (population curves, Gini index, etc.).
 *   - Regional feeds the heatmap / terrain overlay and per-cell LOD decisions.
 *   - Network captures social-graph dynamics that don't reduce to a spatial
 *     coordinate (polarization, faction modularity, betrayal cascades).
 *
 * All metric names use snake_case to stay consistent with the parent project's
 * time-series column conventions in `the-similarity-data`.
 */

// ─── Global Metrics ────────────────────────────────────────────────────────
// Whole-simulation scalar counters and averages, sampled every telemetry tick.

/** @type {string[]} */
export const GLOBAL_METRICS = [
  'population_alive',    // Living agents at sample time
  'births',              // New agents spawned since last sample
  'deaths',              // Agent deaths since last sample
  'injuries',            // Injuries inflicted (combat, disease, hazard)
  'infections',          // New disease transmissions
  'recoveries',          // Disease recoveries
  'conflicts',           // Fights initiated
  'trades',              // Successful trade events
  'migrations',          // Cross-region moves
  'food_stock',          // Total food resource across all cells
  'material_stock',      // Total building / crafting material
  'average_hunger',      // Mean hunger level [0-1], 1 = starving
  'average_health',      // Mean health [0-1], 1 = full health
  'average_stress',      // Mean psychological stress [0-1]
  'inequality_gini',     // Gini coefficient of agent wealth distribution [0-1]
  'faction_count',       // Number of active factions
  'alliance_count',      // Number of active inter-faction alliances
];

// ─── Regional Metrics ──────────────────────────────────────────────────────
// Per-region (grid cell or cluster) counters for spatial analysis / heatmaps.

/** @type {string[]} */
export const REGIONAL_METRICS = [
  'population',          // Agents currently in region
  'deaths',              // Deaths in region since last sample
  'conflicts',           // Fights in region
  'food_pressure',       // demand / supply ratio — >1 means scarcity
  'migration_in',        // Agents entering region
  'migration_out',       // Agents leaving region
  'disease_load',        // Fraction of region population infected [0-1]
  'wealth_density',      // Sum of agent wealth in region
  'hostility_index',     // Average inter-agent hostility in region [0-1]
];

// ─── Network Metrics ───────────────────────────────────────────────────────
// Social-graph-level statistics — computed from the relationship adjacency
// matrix, not from spatial positions.

/** @type {string[]} */
export const NETWORK_METRICS = [
  'average_relationship_valence', // Mean edge weight across all relationships [-1, 1]
  'polarization',                 // Variance of faction-mean valences — high = divided
  'clustering',                   // Graph clustering coefficient [0-1]
  'faction_modularity',           // Newman modularity of faction partition [−0.5, 1]
  'betrayal_rate',                // Fraction of alliances broken this tick [0-1]
  'centralization',               // Degree centralization — 1 = star graph, 0 = uniform
];

// ─── Factory Helpers ───────────────────────────────────────────────────────

/**
 * Build a zero-initialized object from an array of metric names.
 *
 * @param {string[]} keys - Metric name array (one of the *_METRICS constants).
 * @returns {Record<string, number>} Object with every key set to 0.
 */
function _emptySlice(keys) {
  // Loop is slightly faster than Object.fromEntries for small arrays;
  // telemetry snapshots are created once per tick interval, not per frame,
  // so either approach is fine — loop chosen for clarity.
  const slice = {};
  for (const key of keys) {
    slice[key] = 0;
  }
  return slice;
}

/**
 * Create a zero-initialized global telemetry slice.
 *
 * @returns {Record<string, number>} All GLOBAL_METRICS fields set to 0.
 */
export function createEmptyGlobalSlice() {
  return _emptySlice(GLOBAL_METRICS);
}

/**
 * Create a zero-initialized regional telemetry slice.
 *
 * @returns {Record<string, number>} All REGIONAL_METRICS fields set to 0.
 */
export function createEmptyRegionalSlice() {
  return _emptySlice(REGIONAL_METRICS);
}

/**
 * Create a zero-initialized network telemetry slice.
 *
 * @returns {Record<string, number>} All NETWORK_METRICS fields set to 0.
 */
export function createEmptyNetworkSlice() {
  return _emptySlice(NETWORK_METRICS);
}
