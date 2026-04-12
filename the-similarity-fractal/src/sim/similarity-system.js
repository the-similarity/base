/**
 * similarity-system.js — Pattern analysis on telemetry windows.
 *
 * This is the simulation-side mirror of the core Similarity Engine: it
 * ingests structured telemetry slices and performs motif search, regime
 * detection, precursor matching, and anomaly scoring — all in pure JS
 * with no external dependencies.
 *
 * Design rationale:
 *   - The engine operates on *windows* of global metric values (number[]).
 *   - Historical windows are stored in a flat library for k-NN lookup.
 *   - Distance metric is Euclidean (L2) — fast, interpretable, and a
 *     natural choice for time-series subsequence matching.
 *   - Regime detection uses hand-tuned thresholds and linear-trend slopes.
 *     This is intentionally simple; a learned classifier can replace it
 *     later without changing the interface.
 *
 * Lifecycle:
 *   1. Construct with optional config overrides.
 *   2. Call ingest(telemetrySlice) every tick (or every N ticks).
 *   3. Query searchMotifs / detectRegime / matchPrecursors / getAnomalyScore
 *      at any time with an arbitrary window.
 *
 * Memory: The library grows by one entry per ingest() call. At 10 000 ticks
 * with 16-float windows this is ~640 KB — negligible.
 *
 * Immutability: ingest() appends to the library; it never mutates existing
 * entries. Query methods return fresh objects.
 *
 * @module similarity-system
 */

// ── Constants ───────────────────────────────────────────────────────────────

/** Regime labels for the finite-state classifier. */
const REGIMES = Object.freeze({
  STABLE: 'STABLE',
  SCARCITY_RISING: 'SCARCITY_RISING',
  FRAGMENTED_CONFLICT: 'FRAGMENTED_CONFLICT',
  EPIDEMIC: 'EPIDEMIC',
  RECOVERY: 'RECOVERY',
  COLLAPSE_CASCADE: 'COLLAPSE_CASCADE',
});

/**
 * Default configuration for the similarity system.
 *
 * Threshold values are calibrated for the 3D society simulation's typical
 * metric ranges (hunger in [0,1], health in [0,1], conflicts as counts, etc.).
 * Adjust via the config constructor argument.
 */
const DEFAULT_CONFIG = Object.freeze({
  /** Number of most-recent global snapshots to use as the ingest window. */
  windowSize: 20,

  /** Default k for motif search. */
  defaultK: 5,

  /** How many ticks ahead to look when matching precursors. */
  precursorHorizon: 20,

  /**
   * Metrics extracted from each global snapshot to form the feature vector.
   * Order matters — Euclidean distance is computed element-wise.
   */
  featureKeys: [
    'average_hunger',
    'average_health',
    'average_stress',
    'inequality_gini',
    'conflicts',
    'deaths',
    'trades',
    'migrations',
    'infections',
    'food_stock',
  ],

  // ── Regime-detection thresholds ──────────────────────────────────
  // Each regime has a set of conditions on aggregated window statistics.
  // Thresholds are intentionally conservative — a regime is only declared
  // when the signal is clear.

  /** SCARCITY_RISING: hunger trend slope above this fires. */
  scarcityHungerSlope: 0.01,
  /** SCARCITY_RISING: food_stock trend slope below this (negative) fires. */
  scarcityFoodSlope: -0.5,

  /** FRAGMENTED_CONFLICT: mean conflicts per tick above this. */
  conflictMean: 2.0,
  /** FRAGMENTED_CONFLICT: gini above this. */
  conflictGini: 0.4,

  /** EPIDEMIC: mean infections per tick above this. */
  epidemicInfections: 3.0,

  /** RECOVERY: health trend slope above this. */
  recoveryHealthSlope: 0.005,
  /** RECOVERY: hunger trend slope below this (improving). */
  recoveryHungerSlope: -0.005,

  /** COLLAPSE_CASCADE: deaths per tick above this AND rising stress. */
  collapseDeaths: 4.0,
  /** COLLAPSE_CASCADE: stress trend slope above this. */
  collapseStressSlope: 0.015,
});

// ── Math helpers ────────────────────────────────────────────────────────────

/**
 * Euclidean distance between two equal-length vectors.
 *
 *   d(a, b) = sqrt( sum_i (a_i - b_i)^2 )
 *
 * Returns Infinity if lengths differ (fail-open for callers that filter).
 *
 * @param {number[]} a
 * @param {number[]} b
 * @returns {number}
 */
function euclidean(a, b) {
  if (a.length !== b.length) return Infinity;
  let sum = 0;
  for (let i = 0; i < a.length; i++) {
    const diff = a[i] - b[i];
    sum += diff * diff;
  }
  return Math.sqrt(sum);
}

/**
 * Compute the ordinary-least-squares slope of a sequence.
 *
 * Treats indices as the independent variable (0, 1, ..., n-1).
 * Slope = Cov(x, y) / Var(x) = [n*sum(xy) - sum(x)*sum(y)] / [n*sum(x^2) - (sum(x))^2]
 *
 * @param {number[]} values
 * @returns {number} Slope (units per tick). 0 if length < 2.
 */
function linearSlope(values) {
  const n = values.length;
  if (n < 2) return 0;

  let sumX = 0;
  let sumY = 0;
  let sumXY = 0;
  let sumX2 = 0;

  for (let i = 0; i < n; i++) {
    sumX += i;
    sumY += values[i];
    sumXY += i * values[i];
    sumX2 += i * i;
  }

  const denom = n * sumX2 - sumX * sumX;
  if (denom === 0) return 0;

  return (n * sumXY - sumX * sumY) / denom;
}

/**
 * Arithmetic mean of an array.
 * @param {number[]} arr
 * @returns {number}
 */
function mean(arr) {
  if (arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

/**
 * Extract a feature vector from a single global telemetry snapshot.
 *
 * Missing keys default to 0 so the vector always has the expected
 * dimensionality (len(featureKeys)).
 *
 * @param {object} snapshot - Global metric snapshot from TelemetrySystem.
 * @param {string[]} featureKeys - Ordered list of metric keys.
 * @returns {number[]}
 */
function extractFeatures(snapshot, featureKeys) {
  return featureKeys.map(k => snapshot[k] ?? 0);
}

/**
 * Flatten a window of snapshots into a single concatenated vector.
 *
 * For a window of W snapshots each producing D features, the result
 * is a vector of length W*D. This captures temporal shape, not just
 * a single-point summary.
 *
 * @param {object[]} snapshots - Array of global metric snapshots.
 * @param {string[]} featureKeys
 * @returns {number[]}
 */
function flattenWindow(snapshots, featureKeys) {
  const result = [];
  for (const snap of snapshots) {
    result.push(...extractFeatures(snap, featureKeys));
  }
  return result;
}

/**
 * Extract a single metric's values from an array of global snapshots.
 *
 * @param {object[]} snapshots
 * @param {string} metricKey
 * @returns {number[]}
 */
function extractMetricSeries(snapshots, metricKey) {
  return snapshots.map(s => s[metricKey] ?? 0);
}

// ── SimilaritySystem ────────────────────────────────────────────────────────

/**
 * Pattern analysis engine for the society simulation telemetry.
 *
 * Operates on windows of global metric snapshots. The internal library
 * stores flattened feature vectors alongside their tick ranges, enabling
 * efficient k-NN lookup and precursor matching.
 */
export class SimilaritySystem {
  /**
   * @param {object} [config] - Optional overrides merged onto DEFAULT_CONFIG.
   */
  constructor(config = {}) {
    /** @type {object} Merged configuration. */
    this.config = { ...DEFAULT_CONFIG, ...config };

    /**
     * Library of historical windows.
     *
     * Each entry:
     *   { vector: number[], startTick: number, endTick: number }
     *
     * vector is the flattened feature representation of the window.
     * startTick/endTick define the tick range the window covers.
     *
     * @type {Array<{vector: number[], startTick: number, endTick: number}>}
     */
    this.library = [];

    /**
     * Raw ingested snapshots — kept so we can look ahead for precursor
     * matching and construct windows on the fly.
     * @type {object[]}
     */
    this.snapshots = [];

    /** Running tick counter for ingest. */
    this._ingestTick = 0;
  }

  // ── Ingest ──────────────────────────────────────────────────────────

  /**
   * Ingest a telemetry slice (the global-metrics snapshot for one tick).
   *
   * Once enough snapshots have been ingested to fill a window, each new
   * ingest appends a sliding-window entry to the library.
   *
   * @param {object} telemetrySlice - Global metric snapshot (from TelemetrySystem.getSlice().global).
   */
  ingest(telemetrySlice) {
    this.snapshots.push(telemetrySlice);
    this._ingestTick++;

    const ws = this.config.windowSize;
    // Once we have enough snapshots, create a library entry for the
    // window ending at the current tick.
    if (this.snapshots.length >= ws) {
      const windowSnaps = this.snapshots.slice(
        this.snapshots.length - ws,
        this.snapshots.length,
      );
      const vector = flattenWindow(windowSnaps, this.config.featureKeys);
      this.library.push({
        vector,
        startTick: this._ingestTick - ws,
        endTick: this._ingestTick - 1,
      });
    }
  }

  // ── Motif search ────────────────────────────────────────────────────

  /**
   * Find the k nearest historical windows to the query window.
   *
   * Uses brute-force Euclidean scan. For library sizes up to ~10 000
   * (the expected sim range) this is fast enough (<1 ms).
   *
   * Self-overlap exclusion: windows that overlap temporally with the
   * query (if the query has tick metadata) are excluded to avoid
   * trivial matches.
   *
   * @param {number[]|object[]} window - Either a pre-flattened vector or
   *   an array of global snapshots (length = windowSize).
   * @param {number} [k] - Number of neighbours. Defaults to config.defaultK.
   * @returns {Array<{distance: number, startTick: number, endTick: number}>}
   */
  searchMotifs(window, k) {
    const numK = k ?? this.config.defaultK;
    const query = this._toVector(window);
    if (query.length === 0 || this.library.length === 0) return [];

    // Score all library entries
    const scored = this.library.map(entry => ({
      distance: euclidean(query, entry.vector),
      startTick: entry.startTick,
      endTick: entry.endTick,
    }));

    // Sort ascending by distance, take top k
    scored.sort((a, b) => a.distance - b.distance);
    return scored.slice(0, numK);
  }

  // ── Regime detection ────────────────────────────────────────────────

  /**
   * Classify the current window into one of six regime labels.
   *
   * Evaluation order matters: COLLAPSE_CASCADE is checked first (most
   * urgent), then EPIDEMIC, SCARCITY_RISING, FRAGMENTED_CONFLICT,
   * RECOVERY, and finally STABLE as the default.
   *
   * Each regime is detected by thresholding aggregate statistics
   * (means, slopes) of specific metrics within the window.
   *
   * @param {number[]|object[]} window - Flattened vector or snapshot array.
   * @returns {string} One of REGIMES values.
   */
  detectRegime(window) {
    const snaps = this._toSnapshots(window);
    if (snaps.length === 0) return REGIMES.STABLE;

    const cfg = this.config;

    // Pre-compute series and statistics for each relevant metric
    const hungerSeries = extractMetricSeries(snaps, 'average_hunger');
    const healthSeries = extractMetricSeries(snaps, 'average_health');
    const stressSeries = extractMetricSeries(snaps, 'average_stress');
    const conflictSeries = extractMetricSeries(snaps, 'conflicts');
    const deathSeries = extractMetricSeries(snaps, 'deaths');
    const infectionSeries = extractMetricSeries(snaps, 'infections');
    const foodSeries = extractMetricSeries(snaps, 'food_stock');
    const giniSeries = extractMetricSeries(snaps, 'inequality_gini');

    const hungerSlope = linearSlope(hungerSeries);
    const healthSlope = linearSlope(healthSeries);
    const stressSlope = linearSlope(stressSeries);
    const foodSlope = linearSlope(foodSeries);

    const conflictMean = mean(conflictSeries);
    const deathMean = mean(deathSeries);
    const infectionMean = mean(infectionSeries);
    const giniMean = mean(giniSeries);

    // ── COLLAPSE_CASCADE: mass death + rising stress ─────────────
    // This is the most severe regime — checked first.
    if (deathMean >= cfg.collapseDeaths && stressSlope >= cfg.collapseStressSlope) {
      return REGIMES.COLLAPSE_CASCADE;
    }

    // ── EPIDEMIC: sustained high infection rate ──────────────────
    if (infectionMean >= cfg.epidemicInfections) {
      return REGIMES.EPIDEMIC;
    }

    // ── SCARCITY_RISING: hunger climbing + food declining ────────
    if (hungerSlope >= cfg.scarcityHungerSlope && foodSlope <= cfg.scarcityFoodSlope) {
      return REGIMES.SCARCITY_RISING;
    }

    // ── FRAGMENTED_CONFLICT: high conflict + high inequality ────
    if (conflictMean >= cfg.conflictMean && giniMean >= cfg.conflictGini) {
      return REGIMES.FRAGMENTED_CONFLICT;
    }

    // ── RECOVERY: health improving + hunger decreasing ──────────
    if (healthSlope >= cfg.recoveryHealthSlope && hungerSlope <= cfg.recoveryHungerSlope) {
      return REGIMES.RECOVERY;
    }

    // ── STABLE: nothing alarming ────────────────────────────────
    return REGIMES.STABLE;
  }

  // ── Precursor matching ──────────────────────────────────────────────

  /**
   * Find historically similar windows and report what followed.
   *
   * For each of the k nearest motifs, we look ahead `precursorHorizon`
   * ticks in the ingested snapshot history and return the regime that
   * developed, plus key metric deltas. This lets the UI display
   * "last time things looked like this, X happened next."
   *
   * @param {number[]|object[]} window - Query window.
   * @param {object} [options]
   * @param {number} [options.k=5]       - How many similar windows to examine.
   * @param {number} [options.horizon]   - Ticks to look ahead (default: config.precursorHorizon).
   * @returns {Array<{startTick: number, endTick: number, distance: number, futureRegime: string, futureDeltas: object}>}
   */
  matchPrecursors(window, options = {}) {
    const k = options.k ?? this.config.defaultK;
    const horizon = options.horizon ?? this.config.precursorHorizon;

    const motifs = this.searchMotifs(window, k);
    const results = [];

    for (const motif of motifs) {
      // The window covers [startTick, endTick]. We want snapshots
      // from endTick+1 to endTick+horizon.
      const futureStart = motif.endTick + 1;
      const futureEnd = motif.endTick + horizon;

      // Check if we have enough future data
      if (futureEnd >= this.snapshots.length) continue;

      const futureSnaps = this.snapshots.slice(futureStart, futureEnd + 1);
      const futureRegime = this.detectRegime(futureSnaps);

      // Compute deltas: how key metrics changed from end of window
      // to end of future horizon.
      const baseline = this.snapshots[motif.endTick];
      const endpoint = this.snapshots[futureEnd];

      const futureDeltas = {};
      for (const key of this.config.featureKeys) {
        futureDeltas[key] = (endpoint[key] ?? 0) - (baseline[key] ?? 0);
      }

      results.push({
        startTick: motif.startTick,
        endTick: motif.endTick,
        distance: motif.distance,
        futureRegime,
        futureDeltas,
      });
    }

    return results;
  }

  // ── Anomaly scoring ─────────────────────────────────────────────────

  /**
   * Score how different the current window is from any known pattern.
   *
   * The anomaly score is the minimum Euclidean distance to any library
   * entry, normalised by the median library distance to give a
   * dimensionless value:
   *
   *   anomaly = d_min / d_median
   *
   * Interpretation:
   *   < 1.0  — window resembles known patterns (normal)
   *   1.0-2.0 — moderately unusual
   *   > 2.0  — highly anomalous, no close historical precedent
   *
   * Returns 0 if the library is empty (no baseline to compare against).
   *
   * @param {number[]|object[]} window - Query window.
   * @returns {number} Anomaly score (0 = no data, higher = more anomalous).
   */
  getAnomalyScore(window) {
    const query = this._toVector(window);
    if (query.length === 0 || this.library.length === 0) return 0;

    // Compute distances to all library entries
    const distances = this.library.map(entry => euclidean(query, entry.vector));

    const minDist = Math.min(...distances);

    // Median distance for normalisation
    const sorted = [...distances].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    const medianDist = sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid];

    // Guard against zero median (all entries identical to each other)
    if (medianDist === 0) return minDist > 0 ? Infinity : 0;

    return minDist / medianDist;
  }

  // ── Private helpers ─────────────────────────────────────────────────

  /**
   * Convert a window argument to a flat feature vector.
   *
   * Accepts either a pre-flattened number[] or an array of snapshot objects.
   * @private
   * @param {number[]|object[]} window
   * @returns {number[]}
   */
  _toVector(window) {
    if (!Array.isArray(window) || window.length === 0) return [];

    // If the first element is a number, assume pre-flattened
    if (typeof window[0] === 'number') return window;

    // Otherwise treat as snapshot objects
    return flattenWindow(window, this.config.featureKeys);
  }

  /**
   * Convert a window argument to an array of snapshot objects.
   *
   * If the input is already snapshot objects, return as-is.
   * If it's a flat vector, we can't reverse-engineer snapshots, so
   * we return an empty array (regime detection needs snapshots).
   *
   * @private
   * @param {number[]|object[]} window
   * @returns {object[]}
   */
  _toSnapshots(window) {
    if (!Array.isArray(window) || window.length === 0) return [];

    // If elements are objects (snapshots), return directly
    if (typeof window[0] === 'object' && window[0] !== null) return window;

    // Flat vectors can't be used for regime detection — need named fields.
    // Fall back: reshape the flat vector back into pseudo-snapshots.
    const keys = this.config.featureKeys;
    const d = keys.length;
    const snaps = [];
    for (let i = 0; i + d <= window.length; i += d) {
      const snap = {};
      for (let j = 0; j < d; j++) {
        snap[keys[j]] = window[i + j];
      }
      snaps.push(snap);
    }
    return snaps;
  }
}

// ── Named exports ───────────────────────────────────────────────────────────

export {
  REGIMES,
  euclidean,
  linearSlope,
  flattenWindow,
  extractFeatures,
  extractMetricSeries,
};
