/**
 * environment-system.js — Per-tick world coordinator.
 *
 * Advances climate state, triggers resource regeneration, and updates
 * hazard fields. This is the "world tick" as opposed to the agent tick:
 * it models the physical / ecological processes that agents experience
 * but do not directly control.
 *
 * Design rationale:
 *   - The environment runs once per simulation tick, BEFORE agent systems,
 *     so agents always perceive the freshest world state.
 *   - Climate follows a deterministic seasonal cycle with stochastic
 *     perturbations (droughts, storms). The cycle period and amplitude
 *     are configurable.
 *   - Resource regeneration uses logistic growth:
 *       R(t+1) = R(t) + r * R(t) * (1 - R(t) / K)
 *     where r = growth rate and K = carrying capacity. This produces
 *     natural S-curve recovery and prevents infinite accumulation.
 *   - Hazard fields decay exponentially each tick unless refreshed by
 *     an active event (wildfire, flood, disease zone).
 *
 * Lifecycle:
 *   1. Construct with climate config and a resource field reference.
 *   2. Call tick(worldState) once per simulation step.
 *   3. Call getSnapshot() to read the current environment state.
 *
 * Immutability: The system mutates the climate and resourceField objects
 * it was given at construction. It does NOT create new field arrays each
 * tick (allocation-free hot path). getSnapshot() returns a shallow copy.
 *
 * @module environment-system
 */

// ── Constants ───────────────────────────────────────────────────────────────

/** Season labels derived from the annual cycle position. */
const SEASONS = Object.freeze(['SPRING', 'SUMMER', 'AUTUMN', 'WINTER']);

/** Default climate configuration. */
const DEFAULT_CLIMATE = Object.freeze({
  /** Ticks per full seasonal cycle (year). */
  yearLength: 360,

  /** Base temperature at cycle midpoint (arbitrary units, 0-1 normalised). */
  baseTemperature: 0.5,

  /** Seasonal amplitude (peak deviation from base). */
  seasonalAmplitude: 0.3,

  /** Base rainfall (0-1 normalised). */
  baseRainfall: 0.5,

  /** Rainfall seasonal amplitude — peaks in spring/autumn. */
  rainfallAmplitude: 0.2,

  /**
   * Probability per tick of a climate event (drought or storm).
   * Kept low so events are rare but impactful.
   */
  eventProbability: 0.005,

  /** Duration of a climate event in ticks. */
  eventDuration: 20,

  /** Temperature modifier during drought. */
  droughtTempMod: 0.25,

  /** Rainfall modifier during drought (multiplicative). */
  droughtRainMod: 0.1,

  /** Rainfall modifier during storm (multiplicative). */
  stormRainMod: 2.5,
});

/** Default resource-field configuration. */
const DEFAULT_RESOURCE_CONFIG = Object.freeze({
  /** Logistic growth rate for food per tick. */
  foodGrowthRate: 0.02,

  /** Carrying capacity multiplier per cell (actual K = baseCap * fertility). */
  foodBaseCap: 100,

  /** Logistic growth rate for materials per tick. */
  materialGrowthRate: 0.005,

  /** Carrying capacity for materials per cell. */
  materialBaseCap: 50,

  /** Hazard decay rate per tick (exponential: h *= (1 - decay)). */
  hazardDecay: 0.05,

  /** Minimum rainfall for food growth to occur (below = arid). */
  rainfallThreshold: 0.15,

  /**
   * Temperature range for optimal food growth.
   * Outside this range growth is halved.
   */
  optimalTempMin: 0.25,
  optimalTempMax: 0.75,
});

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Deterministic pseudo-random from a seed.
 * Uses a simple xorshift32 for reproducibility.
 *
 * @param {number} seed
 * @returns {function(): number} Returns values in [0, 1).
 */
function makeRng(seed) {
  let state = seed | 0 || 1; // must be non-zero
  return function xorshift32() {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    // Map to [0, 1)
    return (state >>> 0) / 4294967296;
  };
}

// ── EnvironmentSystem ───────────────────────────────────────────────────────

/**
 * Per-tick world coordinator: climate, resource regeneration, hazards.
 *
 * The system does not own the terrain heightmap or biome map — those
 * are static and belong to the world layer. It operates on the mutable
 * overlays (resource fields, hazard fields) that change each tick.
 */
export class EnvironmentSystem {
  /**
   * @param {object} [climate]       - Climate config overrides.
   * @param {object} [resourceField] - Resource field state. Expected shape:
   *   {
   *     width: number,
   *     height: number,
   *     food: Float32Array | number[][],      // current food per cell
   *     materials: Float32Array | number[][], // current materials per cell
   *     hazard: Float32Array | number[][],    // current hazard per cell [0,1]
   *     fertility: Float32Array | number[][], // static fertility per cell [0,1]
   *   }
   *   If null, the system initialises empty fields on first tick().
   * @param {object} [options]
   * @param {number} [options.seed=42] - RNG seed for climate events.
   */
  constructor(climate = {}, resourceField = null, options = {}) {
    /** @type {object} Climate parameters. */
    this.climateConfig = { ...DEFAULT_CLIMATE, ...climate };

    /** @type {object} Resource/hazard field parameters. */
    this.resourceConfig = { ...DEFAULT_RESOURCE_CONFIG };

    /**
     * Mutable resource field state.
     * Initialised lazily on first tick if not provided.
     * @type {object|null}
     */
    this.resourceField = resourceField;

    /** Current climate state (updated each tick). */
    this.climate = {
      temperature: this.climateConfig.baseTemperature,
      rainfall: this.climateConfig.baseRainfall,
      season: SEASONS[0],
      /** Active climate event or null. */
      activeEvent: null,
      /** Remaining ticks for the active event. */
      eventTicksLeft: 0,
    };

    /** Total ticks elapsed since construction. */
    this.tickCount = 0;

    /** @private Seeded RNG for climate events. */
    this._rng = makeRng(options.seed ?? 42);
  }

  // ── tick() — main entry point ──────────────────────────────────────

  /**
   * Advance the environment by one simulation step.
   *
   * Order of operations:
   *   1. Advance climate (season, temperature, rainfall, events).
   *   2. Regenerate resources using logistic growth modulated by climate.
   *   3. Decay hazard fields.
   *   4. Apply any active hazard sources from worldState.
   *
   * @param {object} worldState - Mutable world state container.
   *   Expected to have at minimum:
   *   {
   *     resourceField: { width, height, food, materials, hazard, fertility },
   *     hazardSources?: Array<{x, y, radius, intensity}>,
   *   }
   *   If this.resourceField is null, it will be set from worldState.resourceField.
   */
  tick(worldState) {
    // Lazily bind the resource field from worldState on first tick
    if (!this.resourceField && worldState?.resourceField) {
      this.resourceField = worldState.resourceField;
    }

    this._advanceClimate();

    if (this.resourceField) {
      this._regenerateResources();
      this._decayHazards();
      this._applyHazardSources(worldState?.hazardSources ?? []);
    }

    this.tickCount++;
  }

  // ── Private: climate ───────────────────────────────────────────────

  /**
   * Advance the climate by one tick.
   *
   * Temperature follows a cosine seasonal cycle:
   *   T(t) = T_base + A * cos(2*pi*t / yearLen)
   *
   * Rainfall follows a shifted cosine (peaks offset by quarter-year):
   *   R(t) = R_base + A_r * cos(2*pi*t / yearLen + pi/2)
   *
   * Climate events (drought, storm) are triggered stochastically and
   * override the baseline for their duration.
   *
   * @private
   */
  _advanceClimate() {
    const cfg = this.climateConfig;
    const t = this.tickCount;

    // ── Seasonal cycle ───────────────────────────────────────────
    const phase = (2 * Math.PI * t) / cfg.yearLength;

    // Season index: divide year into 4 equal quarters
    const seasonIndex = Math.floor((t % cfg.yearLength) / (cfg.yearLength / 4));
    this.climate.season = SEASONS[seasonIndex];

    // Baseline temperature and rainfall
    let temp = cfg.baseTemperature + cfg.seasonalAmplitude * Math.cos(phase);
    let rain = cfg.baseRainfall + cfg.rainfallAmplitude * Math.cos(phase + Math.PI / 2);

    // ── Climate events ───────────────────────────────────────────
    if (this.climate.eventTicksLeft > 0) {
      // Event still active — apply modifiers
      if (this.climate.activeEvent === 'drought') {
        temp += cfg.droughtTempMod;
        rain *= cfg.droughtRainMod;
      } else if (this.climate.activeEvent === 'storm') {
        rain *= cfg.stormRainMod;
      }
      this.climate.eventTicksLeft--;
      if (this.climate.eventTicksLeft === 0) {
        this.climate.activeEvent = null;
      }
    } else {
      // Roll for a new event
      const roll = this._rng();
      if (roll < cfg.eventProbability) {
        // 50/50 drought vs storm
        this.climate.activeEvent = this._rng() < 0.5 ? 'drought' : 'storm';
        this.climate.eventTicksLeft = cfg.eventDuration;
      }
    }

    // Clamp to [0, 1]
    this.climate.temperature = Math.max(0, Math.min(1, temp));
    this.climate.rainfall = Math.max(0, Math.min(1, rain));
  }

  // ── Private: resource regeneration ─────────────────────────────────

  /**
   * Apply logistic growth to food and material fields.
   *
   * Food growth is modulated by climate:
   *   - Below rainfallThreshold: no growth (arid).
   *   - Outside optimal temperature range: growth halved.
   *   - Fertility acts as a per-cell multiplier on carrying capacity.
   *
   * Logistic update per cell:
   *   R(t+1) = R(t) + r * R(t) * (1 - R(t) / K)
   *
   * This is O(width * height) per tick, but with simple arithmetic
   * and no allocations it stays well under 1 ms for typical grid sizes
   * (128x128 = 16 384 cells).
   *
   * @private
   */
  _regenerateResources() {
    const rf = this.resourceField;
    const rcfg = this.resourceConfig;
    const { temperature, rainfall } = this.climate;

    // Climate modifiers for food growth
    const rainOk = rainfall >= rcfg.rainfallThreshold;
    const tempOptimal = temperature >= rcfg.optimalTempMin && temperature <= rcfg.optimalTempMax;
    // Growth multiplier: 1.0 if both OK, 0.5 if temp suboptimal, 0 if too dry
    const climateMod = rainOk ? (tempOptimal ? 1.0 : 0.5) : 0.0;

    const w = rf.width ?? 0;
    const h = rf.height ?? 0;

    for (let i = 0; i < w * h; i++) {
      // ── Food ─────────────────────────────────────────────────
      const fertility = this._getCell(rf.fertility, i, w) ?? 1.0;
      const foodCap = rcfg.foodBaseCap * fertility;
      const food = this._getCell(rf.food, i, w) ?? 0;

      if (food > 0 && food < foodCap && climateMod > 0) {
        // Logistic growth: dR = r * R * (1 - R/K)
        const dFood = rcfg.foodGrowthRate * climateMod * food * (1 - food / foodCap);
        this._setCell(rf.food, i, w, Math.min(foodCap, food + dFood));
      }

      // ── Materials ────────────────────────────────────────────
      const matCap = rcfg.materialBaseCap;
      const mat = this._getCell(rf.materials, i, w) ?? 0;

      if (mat > 0 && mat < matCap) {
        // Materials grow independent of climate (geological processes)
        const dMat = rcfg.materialGrowthRate * mat * (1 - mat / matCap);
        this._setCell(rf.materials, i, w, Math.min(matCap, mat + dMat));
      }
    }
  }

  // ── Private: hazard decay ──────────────────────────────────────────

  /**
   * Exponentially decay all hazard values each tick.
   *
   *   h(t+1) = h(t) * (1 - decay_rate)
   *
   * Values below 0.001 are snapped to 0 to prevent floating-point dust
   * from accumulating.
   *
   * @private
   */
  _decayHazards() {
    const rf = this.resourceField;
    if (!rf.hazard) return;

    const decay = 1 - this.resourceConfig.hazardDecay;
    const w = rf.width ?? 0;
    const h = rf.height ?? 0;

    for (let i = 0; i < w * h; i++) {
      let val = this._getCell(rf.hazard, i, w) ?? 0;
      val *= decay;
      if (val < 0.001) val = 0;
      this._setCell(rf.hazard, i, w, val);
    }
  }

  // ── Private: hazard sources ────────────────────────────────────────

  /**
   * Apply active hazard sources (wildfires, floods, disease zones) to
   * the hazard field.
   *
   * Each source is a point with a radius and intensity. All cells within
   * the radius have their hazard set to max(current, intensity), so
   * overlapping sources combine by taking the worst.
   *
   * @private
   * @param {Array<{x: number, y: number, radius: number, intensity: number}>} sources
   */
  _applyHazardSources(sources) {
    const rf = this.resourceField;
    if (!rf.hazard || sources.length === 0) return;

    const w = rf.width ?? 0;
    const h = rf.height ?? 0;

    for (const src of sources) {
      const cx = Math.round(src.x);
      const cy = Math.round(src.y);
      const r = Math.ceil(src.radius);
      const r2 = src.radius * src.radius;

      // Iterate over bounding box of the circle
      const x0 = Math.max(0, cx - r);
      const x1 = Math.min(w - 1, cx + r);
      const y0 = Math.max(0, cy - r);
      const y1 = Math.min(h - 1, cy + r);

      for (let y = y0; y <= y1; y++) {
        for (let x = x0; x <= x1; x++) {
          const dx = x - cx;
          const dy = y - cy;
          if (dx * dx + dy * dy <= r2) {
            const idx = y * w + x;
            const current = this._getCell(rf.hazard, idx, w) ?? 0;
            this._setCell(rf.hazard, idx, w, Math.max(current, src.intensity));
          }
        }
      }
    }
  }

  // ── Private: field accessors ───────────────────────────────────────

  /**
   * Read a cell value from a field that may be a typed array or 2D array.
   *
   * Supports both flat (Float32Array / number[]) and 2D (number[][]) layouts.
   *
   * @private
   * @param {Float32Array|number[]|number[][]|null} field
   * @param {number} flatIndex - Index into flat layout.
   * @param {number} width     - Row width (for 2D conversion).
   * @returns {number|null}
   */
  _getCell(field, flatIndex, width) {
    if (!field) return null;
    // Flat array (TypedArray or regular)
    if (typeof field[flatIndex] === 'number') return field[flatIndex];
    // 2D array
    if (Array.isArray(field[0])) {
      const row = Math.floor(flatIndex / width);
      const col = flatIndex % width;
      return field[row]?.[col] ?? null;
    }
    return null;
  }

  /**
   * Write a cell value to a field (flat or 2D).
   *
   * @private
   * @param {Float32Array|number[]|number[][]|null} field
   * @param {number} flatIndex
   * @param {number} width
   * @param {number} value
   */
  _setCell(field, flatIndex, width, value) {
    if (!field) return;
    if (typeof field[flatIndex] === 'number' || field instanceof Float32Array || !Array.isArray(field[0])) {
      field[flatIndex] = value;
    } else if (Array.isArray(field[0])) {
      const row = Math.floor(flatIndex / width);
      const col = flatIndex % width;
      if (field[row]) field[row][col] = value;
    }
  }

  // ── getSnapshot() ──────────────────────────────────────────────────

  /**
   * Return a shallow-copy snapshot of the current environment state.
   *
   * Useful for telemetry or rendering layers that want to read climate
   * and resource state without holding a reference to mutable internals.
   *
   * @returns {{
   *   tickCount: number,
   *   climate: object,
   *   resourceSummary: { totalFood: number, totalMaterials: number, totalHazard: number }
   * }}
   */
  getSnapshot() {
    let totalFood = 0;
    let totalMaterials = 0;
    let totalHazard = 0;

    if (this.resourceField) {
      const rf = this.resourceField;
      const w = rf.width ?? 0;
      const h = rf.height ?? 0;
      for (let i = 0; i < w * h; i++) {
        totalFood += this._getCell(rf.food, i, w) ?? 0;
        totalMaterials += this._getCell(rf.materials, i, w) ?? 0;
        totalHazard += this._getCell(rf.hazard, i, w) ?? 0;
      }
    }

    return {
      tickCount: this.tickCount,
      climate: { ...this.climate },
      resourceSummary: {
        totalFood,
        totalMaterials,
        totalHazard,
      },
    };
  }
}

// ── Named exports ───────────────────────────────────────────────────────────

export { SEASONS, DEFAULT_CLIMATE, DEFAULT_RESOURCE_CONFIG };
