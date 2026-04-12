/**
 * Climate / weather state machine for the 3D society simulation.
 *
 * Provides a stochastic weather model that affects the simulation world:
 *   - Resource regeneration rate (drought slows it, rain boosts it)
 *   - Disease pressure (warm + wet = high, cold = moderate, dry = low)
 *   - Agent movement cost modifier (storm/snow penalize, clear is baseline)
 *
 * The weather is a discrete Markov chain with five states. Transition
 * probabilities are baked into a matrix so the tick() cost is O(1).
 * Temperature follows a slow sinusoidal cycle (seasons) with weather-driven
 * perturbations on top.
 *
 * Lifecycle:
 *   1. Construct with a seeded PRNG.
 *   2. Call tick() once per simulation step.
 *   3. Query getWeather(), getTemperature(), etc. between ticks.
 *   4. getSnapshot() for serialization / telemetry.
 *
 * Immutability:
 *   - The transition matrix is frozen at construction time.
 *   - tick() is the only state-mutating method.
 *   - All getters are pure reads of current state.
 */

// ─── Weather states ────────────────────────────────────────────────────────
// String constants for readability in logs and snapshots.
export const WEATHER = Object.freeze({
  CLEAR:     'CLEAR',
  RAIN:      'RAIN',
  STORM:     'STORM',
  DROUGHT:   'DROUGHT',
  COLD_SNAP: 'COLD_SNAP',
});

// Ordered list for matrix indexing. The index of each state in this array
// is its numeric ID in the transition matrix.
const STATES = [
  WEATHER.CLEAR,
  WEATHER.RAIN,
  WEATHER.STORM,
  WEATHER.DROUGHT,
  WEATHER.COLD_SNAP,
];

// ─── Transition matrix ────────────────────────────────────────────────────
// Row = current state, column = next state.
// Each row sums to 1.0. Designed so:
//   - CLEAR is the most common steady-state (~40% of time).
//   - STORM is rare and short-lived (high self-exit probability).
//   - DROUGHT has moderate persistence (multi-tick episodes).
//   - COLD_SNAP is short but can chain into CLEAR or RAIN.
//
// Rows indexed by STATES order: CLEAR, RAIN, STORM, DROUGHT, COLD_SNAP
const TRANSITION_MATRIX = [
  /* from CLEAR     → */ [0.50, 0.25, 0.05, 0.12, 0.08],
  /* from RAIN      → */ [0.35, 0.35, 0.15, 0.05, 0.10],
  /* from STORM     → */ [0.40, 0.30, 0.15, 0.05, 0.10],
  /* from DROUGHT   → */ [0.25, 0.10, 0.02, 0.55, 0.08],
  /* from COLD_SNAP → */ [0.35, 0.20, 0.05, 0.05, 0.35],
];

// ─── Effect parameters per weather state ───────────────────────────────────
// regenModifier:    multiplied with biome regen rates in ResourceField.
//                   >1 = faster regen, <1 = slower, 0 = no regen.
// diseasePressure:  base disease risk added per tick (unitless, 0-1 scale).
// moveCostModifier: multiplier on movement cost. 1.0 = normal.
// tempOffset:       added to the seasonal base temperature (Celsius-ish).
const WEATHER_EFFECTS = {
  [WEATHER.CLEAR]:     { regenModifier: 1.0,  diseasePressure: 0.01, moveCostModifier: 1.0, tempOffset: 0   },
  [WEATHER.RAIN]:      { regenModifier: 1.4,  diseasePressure: 0.05, moveCostModifier: 1.2, tempOffset: -2  },
  [WEATHER.STORM]:     { regenModifier: 0.6,  diseasePressure: 0.08, moveCostModifier: 1.8, tempOffset: -5  },
  [WEATHER.DROUGHT]:   { regenModifier: 0.3,  diseasePressure: 0.03, moveCostModifier: 1.0, tempOffset: 5   },
  [WEATHER.COLD_SNAP]: { regenModifier: 0.5,  diseasePressure: 0.06, moveCostModifier: 1.4, tempOffset: -12 },
};

// ─── Seasonal parameters ───────────────────────────────────────────────────
// Temperature follows: BASE_TEMP + SEASON_AMPLITUDE * sin(2π * tick / SEASON_PERIOD) + weatherOffset
const BASE_TEMP        = 15;    // Mean annual temperature (Celsius-ish units).
const SEASON_AMPLITUDE = 12;    // Peak-to-trough swing around BASE_TEMP.
const SEASON_PERIOD    = 2400;  // Ticks per full seasonal cycle. At 1 tick/sec,
                                 // this is ~40 minutes of real time per "year".

export class Climate {
  /**
   * @param {Object} rng - PRNG with { next(), nextSigned() }. Drives all
   *   stochastic transitions so weather is reproducible from the same seed.
   */
  constructor(rng) {
    this._rng = rng;

    // Start with clear weather — the most common baseline state.
    this._stateIndex = 0; // index into STATES
    this._tick = 0;

    // Cache current effects to avoid repeated lookups between ticks.
    this._effects = WEATHER_EFFECTS[STATES[this._stateIndex]];
  }

  /**
   * Advance the climate by one simulation tick.
   *
   * Performs a single Markov transition: draw a uniform random number,
   * walk the cumulative row of the transition matrix, and jump to the
   * first state whose cumulative probability exceeds the draw.
   *
   * Time complexity: O(|STATES|) = O(5) = effectively O(1).
   */
  tick() {
    this._tick++;

    const row = TRANSITION_MATRIX[this._stateIndex];
    const roll = this._rng.next();

    // Cumulative probability scan.
    let cumulative = 0;
    for (let i = 0; i < row.length; i++) {
      cumulative += row[i];
      if (roll < cumulative) {
        this._stateIndex = i;
        break;
      }
    }

    // Update cached effects for the new state.
    this._effects = WEATHER_EFFECTS[STATES[this._stateIndex]];
  }

  // ─── Queries ─────────────────────────────────────────────────────────

  /**
   * Current weather state as a string (e.g., 'CLEAR', 'STORM').
   * @returns {string}
   */
  getWeather() {
    return STATES[this._stateIndex];
  }

  /**
   * Current temperature in abstract Celsius-ish units.
   *
   * Combines a slow seasonal sinusoid with a weather-driven offset.
   * Agents can use this for clothing / shelter decisions; resource systems
   * can use it for crop growth modifiers.
   *
   * @returns {number}
   */
  getTemperature() {
    // Seasonal oscillation: peaks at tick = SEASON_PERIOD/4, troughs at 3/4.
    const seasonalComponent = SEASON_AMPLITUDE * Math.sin(
      (2 * Math.PI * this._tick) / SEASON_PERIOD
    );
    return BASE_TEMP + seasonalComponent + this._effects.tempOffset;
  }

  /**
   * Current disease pressure (unitless, 0-1 scale).
   *
   * Higher values mean agents are more likely to contract illness per tick.
   * The base pressure from weather is modulated by temperature: warm + wet
   * conditions amplify disease (tropical logic), while extreme cold adds
   * a smaller boost (hypothermia / respiratory risk).
   *
   * @returns {number}
   */
  getDiseasePressure() {
    const temp = this.getTemperature();
    const basePressure = this._effects.diseasePressure;

    // Warm-wet amplification: above 25 degrees, disease scales up.
    // Below 0 degrees, a smaller cold-stress factor kicks in.
    let tempFactor = 1.0;
    if (temp > 25) {
      // Linear ramp: +50% pressure at 35 degrees.
      tempFactor = 1.0 + (temp - 25) * 0.05;
    } else if (temp < 0) {
      // Cold stress: +30% pressure at -10 degrees.
      tempFactor = 1.0 + Math.abs(temp) * 0.03;
    }

    // Clamp to [0, 1] — disease pressure is a probability-like value.
    return Math.min(1.0, Math.max(0, basePressure * tempFactor));
  }

  /**
   * Movement cost multiplier under current weather.
   *
   * 1.0 = normal. Storms and cold snaps increase it; clear weather is baseline.
   * The agent locomotion system multiplies base movement cost by this value.
   *
   * @returns {number}
   */
  getMoveCostModifier() {
    return this._effects.moveCostModifier;
  }

  /**
   * Resource regeneration rate multiplier under current weather.
   *
   * ResourceField.regenerate() should multiply per-cell regen rates by this
   * value so weather dynamically affects food/material availability.
   *
   * @returns {number}
   */
  getRegenModifier() {
    return this._effects.regenModifier;
  }

  /**
   * Current simulation tick count (for external time-keeping / telemetry).
   * @returns {number}
   */
  getTick() {
    return this._tick;
  }

  /**
   * Produce a plain-object snapshot for serialization / telemetry.
   *
   * @returns {{ tick: number, weather: string, temperature: number,
   *             diseasePressure: number, moveCostModifier: number,
   *             regenModifier: number }}
   */
  getSnapshot() {
    return {
      tick: this._tick,
      weather: this.getWeather(),
      temperature: this.getTemperature(),
      diseasePressure: this.getDiseasePressure(),
      moveCostModifier: this.getMoveCostModifier(),
      regenModifier: this.getRegenModifier(),
    };
  }
}
