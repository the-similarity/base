/**
 * Deterministic pseudo-random number generator for the society simulation.
 *
 * Algorithm: xoshiro128** — a fast, small-state PRNG with good statistical
 * properties for procedural generation. Seeded from a single integer via
 * SplitMix-style expansion into four 32-bit state slots.
 *
 * Why deterministic:
 * - Identical seed reproduces identical simulation runs, making debugging
 *   and regression testing tractable.
 * - Agent behaviors, event outcomes, and resource spawns all flow from this
 *   single entropy source, so replaying a seed replays the entire world.
 *
 * Lifecycle:
 * - Construct once per simulation run with a chosen seed.
 * - Call next() / nextSigned() as needed — state advances monotonically.
 * - Instance is mutable (internal state changes on every call).
 * - NOT thread-safe, but JS is single-threaded so that is fine.
 *
 * Copied from fractal.js to keep the sim layer independent of the terrain
 * renderer. Both files use the same algorithm so seeds are cross-compatible.
 */

export class PRNG {
  /**
   * @param {number} seed - Integer seed. Defaults to 42 for reproducibility.
   */
  constructor(seed = 42) {
    // Expand a single integer seed into four internal state values.
    // The xoshiro family expects multiple state slots; SplitMix-style mixing
    // gives us decorrelated starting values from one user-facing seed.
    let s = seed >>> 0;
    const sm = () => {
      s = (s + 0x9e3779b9) >>> 0;
      let z = s;
      z = (z ^ (z >>> 16)) >>> 0;
      z = Math.imul(z, 0x85ebca6b);
      z = (z ^ (z >>> 13)) >>> 0;
      z = Math.imul(z, 0xc2b2ae35);
      z = (z ^ (z >>> 16)) >>> 0;
      return z >>> 0;
    };
    this.s = [sm(), sm(), sm(), sm()];
  }

  /**
   * Bitwise left rotation — part of the xoshiro state transition function.
   * @param {number} x - 32-bit unsigned integer
   * @param {number} k - rotation amount in bits
   * @returns {number} rotated value as unsigned 32-bit integer
   */
  _rotl(x, k) {
    return ((x << k) | (x >>> (32 - k))) >>> 0;
  }

  /**
   * Generate one pseudo-random float in [0, 1).
   *
   * Advances the internal state by one step. The output is the xoshiro128**
   * scrambled result divided by 2^32 to normalize into the unit interval.
   *
   * @returns {number} float in [0, 1)
   */
  next() {
    const s = this.s;
    const result = (Math.imul(this._rotl(Math.imul(s[1], 5), 7), 9)) >>> 0;
    const t = (s[1] << 9) >>> 0;

    // xoshiro state transition — each slot mixes with others to prevent
    // short cycles and ensure full-period coverage of the state space.
    s[2] = (s[2] ^ s[0]) >>> 0;
    s[3] = (s[3] ^ s[1]) >>> 0;
    s[1] = (s[1] ^ s[2]) >>> 0;
    s[0] = (s[0] ^ s[3]) >>> 0;
    s[2] = (s[2] ^ t) >>> 0;
    s[3] = this._rotl(s[3], 11);

    return result / 0x100000000; // [0, 1)
  }

  /**
   * Generate one pseudo-random float in [-1, 1).
   *
   * Useful for displacement, direction jitter, and any quantity that can
   * be positive or negative with equal probability.
   *
   * @returns {number} float in [-1, 1)
   */
  nextSigned() {
    return this.next() * 2 - 1;
  }
}
