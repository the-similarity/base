/**
 * sim-config.js — Default simulation configuration with all tuning knobs.
 *
 * Every number here is a design decision. Inline comments explain the
 * reasoning so future agents (and humans) can tune with confidence.
 *
 * The config uses Object.freeze on the top-level object (shallow freeze).
 * Nested sub-objects are not deeply frozen — callers should treat the
 * entire tree as read-only and use `mergeConfig()` to produce overridden
 * copies rather than mutating in place.
 */

// ─── Default Configuration ─────────────────────────────────────────────────

/**
 * Master simulation configuration object.
 *
 * Sections are grouped by subsystem. Each section is independently
 * overridable via `mergeConfig({ sectionName: { key: value } })`.
 *
 * @type {Readonly<Object>}
 */
export const DEFAULT_SIM_CONFIG = Object.freeze({

  // --- Timing / tick control ------------------------------------------------
  time: {
    ticksPerSecond: 6,
    // 6 Hz is fast enough to feel alive but slow enough that the similarity
    // engine's 50-tick window covers ~8 real seconds — a comfortable analysis
    // cadence for the UI.

    telemetryInterval: 1,
    // Sample metrics every tick. At 6 tps this yields 6 data points/sec, well
    // within the similarity engine's ingest budget.

    similarityInterval: 10,
    // Run pattern-matching every 10 ticks (~1.7 sec). Keeps the GPU/CPU
    // budget manageable while still catching rapid regime shifts.
  },

  // --- World geometry -------------------------------------------------------
  world: {
    gridSize: 128,
    // 128×128 = 16 384 cells. Large enough for emergent spatial patterns,
    // small enough that a brute-force resource scan stays under 1 ms per tick.

    worldScale: 10,
    // Visual scale multiplier for the 3D renderer (meters per cell).
    // 10 gives a 1.28 km² world — neighborhood-scale, not continent-scale.
  },

  // --- Agent population -----------------------------------------------------
  agents: {
    initialCount: 75,
    // Start modest so the first few seconds show visible growth. 75 agents
    // on a 128² grid means ~0.05% occupancy — sparse enough for migration
    // to matter.

    maxCount: 200,
    // Hard cap prevents runaway population from tanking frame rate.
    // 200 agents with full Tier-2 enrichment stay within the 16 ms budget.

    spawnRate: 0.01,
    // Probability per tick that a new agent spawns (if below maxCount).
    // At 6 tps this averages ~1 birth every 17 seconds — slow organic growth.
  },

  // --- Need decay rates (per tick) ------------------------------------------
  // All needs are [0, 1] where 1 = fully satisfied. Decay rates control how
  // fast agents become desperate — the core pressure that drives all behavior.
  needs: {
    hungerDecayRate: 0.003,
    // ~333 ticks (~55 sec) from full to zero. Agents must eat roughly once
    // a minute to survive, creating constant foraging pressure.

    energyDecayRate: 0.002,
    // ~500 ticks (~83 sec). Slower than hunger — agents can push through
    // fatigue but eventually must rest.

    hydrationDecayRate: 0.004,
    // ~250 ticks (~42 sec). Fastest basic need. Water scarcity should be
    // the first crisis a new settlement faces.

    socialDecayRate: 0.001,
    // ~1000 ticks (~167 sec). Social need decays slowly — isolation is a
    // background pressure, not an acute emergency.

    stressDecayRate: 0.001,
    // ~1000 ticks to naturally de-stress. Stress accumulates from combat,
    // scarcity, and crowding; slow decay means past trauma lingers.
  },

  // --- Combat ---------------------------------------------------------------
  combat: {
    baseDamage: 15,
    // Out of 100 HP baseline. A single hit removes ~15% health — fights are
    // dangerous but not instantly lethal, allowing flee decisions.

    damageVariance: 10,
    // Uniform ±10 around baseDamage. High variance makes combat outcomes
    // unpredictable, which drives interesting risk-assessment behavior.

    fleeThreshold: 0.3,
    // Agents attempt to flee when health drops below 30%. This prevents
    // every fight from ending in death and creates wounded-agent dynamics.
  },

  // --- Disease --------------------------------------------------------------
  disease: {
    transmissionRadius: 3,
    // Grid cells. Diseases spread in a small neighborhood — dense settlements
    // become hotspots, sparse nomads stay safe. Encourages spatial strategy.

    transmissionProbability: 0.05,
    // 5% chance per tick per susceptible neighbor. At 6 tps in a crowded cell
    // this means ~1 new infection every 3 seconds — fast enough to notice,
    // slow enough to react.

    severityRate: 0.02,
    // Health loss per tick while infected. An untreated disease kills in
    // ~50 ticks (~8 sec) from full health — urgency without instant death.

    recoveryProbability: 0.03,
    // 3% chance per tick of spontaneous recovery. Average illness lasts
    // ~33 ticks (~5.5 sec). Balances lethality so plagues don't wipe all.

    deathThreshold: 1.0,
    // Fraction of max severity at which the disease kills. 1.0 means the
    // agent must be fully depleted — disease alone won't kill unless
    // combined with other stressors (hunger, combat injuries).
  },

  // --- Economy / trade ------------------------------------------------------
  economy: {
    tradeRadius: 5,
    // Grid cells. Agents can trade with neighbors within 5 cells. Slightly
    // larger than disease radius so trade networks form before plagues.

    scarcityThreshold: 0.2,
    // When a region's food_pressure exceeds (1 / 0.2) = 5× demand/supply,
    // a SCARCITY_WARNING event fires. Triggers migration and conflict.
  },

  // --- Factions / alliances -------------------------------------------------
  factions: {
    formationThreshold: 0.6,
    // Minimum average relationship valence [0, 1] for a group to coalesce
    // into a faction. 0.6 is moderately high — factions require genuine
    // positive history, not just absence of conflict.

    fragmentationThreshold: -0.3,
    // Average internal valence below which a faction fragments. Negative
    // means active hostility is needed to break a group — inertia matters.

    betrayalProbability: 0.01,
    // 1% chance per tick that an alliance is betrayed. At 6 tps, an average
    // alliance lasts ~17 seconds before betrayal risk accumulates to 50%.
    // Creates dramatic narrative arcs.
  },

  // --- Level of Detail (LOD) ------------------------------------------------
  // The simulation runs a full tick for agents near the camera ("spotlight")
  // and a simplified tick for distant agents, saving CPU for rendering.
  lod: {
    spotlightRadius: 20,
    // Grid cells from camera focus. Agents inside get full AI evaluation
    // every tick — rich behavior visible to the viewer.

    activeRadius: 50,
    // Agents between spotlight and active radius get simplified decisions
    // (no pathfinding, reduced social checks) every tick.

    backgroundTickInterval: 4,
    // Agents beyond activeRadius only update every Nth tick. At 6 tps they
    // effectively run at 1.5 tps — enough to maintain macro trends without
    // burning CPU on invisible agents.
  },

  // --- Similarity engine integration ----------------------------------------
  similarity: {
    windowSize: 50,
    // Number of telemetry ticks in the sliding window. At 6 tps this is
    // ~8.3 seconds of history — matches the parent project's default motif
    // length for meaningful pattern detection.

    motifK: 5,
    // Top-K similar historical motifs to retrieve per analysis pass. 5 gives
    // enough diversity for the forecast cone without overwhelming the UI.

    regimeThresholds: {
      // Z-score thresholds on metric deltas that trigger regime-change alerts.
      // These map to the parent project's regime detection logic.
      growth: 1.5,    // Population growth spike
      decline: -1.5,  // Population crash
      conflict: 2.0,  // Conflict surge (higher bar — fights are noisy)
      peace: -1.0,    // Conflict lull (lower bar — peace is notable)
    },
  },
});

// ─── Deep Merge Helper ─────────────────────────────────────────────────────

/**
 * Recursively determine if a value is a plain object (not an array, Date, etc.).
 *
 * @param {*} value
 * @returns {boolean}
 */
function _isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Deep-merge user overrides onto a fresh clone of DEFAULT_SIM_CONFIG.
 *
 * Rules:
 *   - Unknown top-level keys are passed through (forward-compat).
 *   - Nested plain objects are merged recursively.
 *   - Arrays and primitives are replaced wholesale.
 *   - The original DEFAULT_SIM_CONFIG is never mutated (it's frozen).
 *
 * @param {Object} overrides - Partial config tree with user-specified values.
 * @returns {Object} A new config object with defaults + overrides applied.
 */
export function mergeConfig(overrides = {}) {
  // Structured clone gives us a deep, unfrozen copy of the defaults.
  const merged = structuredClone(DEFAULT_SIM_CONFIG);
  return _deepMerge(merged, overrides);
}

/**
 * In-place deep merge of `source` into `target`. Returns `target`.
 *
 * @param {Object} target
 * @param {Object} source
 * @returns {Object}
 */
function _deepMerge(target, source) {
  for (const key of Object.keys(source)) {
    if (_isPlainObject(source[key]) && _isPlainObject(target[key])) {
      // Both sides are objects — recurse to preserve unspecified leaves.
      _deepMerge(target[key], source[key]);
    } else {
      // Primitive, array, or new key — overwrite.
      target[key] = source[key];
    }
  }
  return target;
}
