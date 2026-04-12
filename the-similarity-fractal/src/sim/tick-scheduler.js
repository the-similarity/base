/**
 * Fixed-step simulation clock decoupled from render frame rate.
 *
 * Why fixed-step:
 * - Variable delta leads to non-deterministic simulation outcomes because
 *   floating-point accumulation differs across machines and frame rates.
 * - A fixed tick interval (e.g. 150ms = ~6.67 ticks/sec) guarantees that
 *   the same sequence of inputs produces the same simulation state.
 * - The renderer can run at 60fps while the sim ticks at 4-10 Hz, saving
 *   CPU for rendering without slowing the world.
 *
 * Accumulator model:
 * - Each call to update(realDeltaMs) adds the wall-clock delta to an
 *   internal accumulator.
 * - update() returns the number of whole ticks that should fire.
 * - The remainder stays in the accumulator for the next frame.
 * - A safety cap prevents spiral-of-death if the tab was backgrounded
 *   (browser may deliver a huge delta after regaining focus).
 *
 * Lifecycle:
 * - Construct with desired ticks-per-second (default 6).
 * - Call update() from the render loop's requestAnimationFrame callback.
 * - Call reset() when restarting the simulation.
 *
 * Invariants:
 * - tick count is monotonically increasing (never decremented except by reset).
 * - accumulator is always in [0, tickIntervalMs) after update() returns.
 */

/** Maximum real-time delta we accept per frame, in milliseconds.
 *  Prevents spiral-of-death when the tab is backgrounded and the browser
 *  delivers a multi-second delta on refocus. */
const MAX_DELTA_MS = 500;

/** Default simulation rate: 6 ticks per second. Balanced between
 *  responsiveness (agents move visibly) and CPU budget (leaves headroom
 *  for rendering at 60fps). */
const DEFAULT_TICKS_PER_SECOND = 6;

export class TickScheduler {
  /**
   * @param {number} [ticksPerSecond=6] - Simulation ticks per wall-clock second.
   *   Valid range: 1-60. Values outside this range are clamped.
   */
  constructor(ticksPerSecond = DEFAULT_TICKS_PER_SECOND) {
    // Clamp to sane range: at least 1 tick/sec, at most 60 (one tick per
    // typical render frame — going higher is pointless).
    const clamped = Math.max(1, Math.min(60, ticksPerSecond));

    /** @type {number} Milliseconds per simulation tick. */
    this._tickIntervalMs = 1000 / clamped;

    /** @type {number} Accumulated real time not yet consumed by ticks. */
    this._accumulator = 0;

    /** @type {number} Monotonically increasing tick counter. */
    this._tick = 0;
  }

  /**
   * Accumulate real-time delta and return the number of simulation ticks
   * that should fire this frame.
   *
   * @param {number} realDeltaMs - Wall-clock milliseconds since last call.
   *   Typically from requestAnimationFrame's timestamp diff.
   * @returns {number} Integer count of ticks to execute (0 or more).
   */
  update(realDeltaMs) {
    // Clamp delta to prevent spiral-of-death after tab backgrounding.
    // Also reject negative deltas (can happen with clock adjustments).
    const clampedDelta = Math.min(Math.max(0, realDeltaMs), MAX_DELTA_MS);

    this._accumulator += clampedDelta;

    // Count how many whole ticks fit in the accumulator.
    let ticksThisFrame = 0;
    while (this._accumulator >= this._tickIntervalMs) {
      this._accumulator -= this._tickIntervalMs;
      this._tick++;
      ticksThisFrame++;
    }

    return ticksThisFrame;
  }

  /**
   * Current simulation tick number (zero-indexed, monotonically increasing).
   * @returns {number}
   */
  getTick() {
    return this._tick;
  }

  /**
   * Reset the scheduler to initial state. Call when restarting the simulation.
   * Zeroes both the tick counter and the accumulator.
   */
  reset() {
    this._tick = 0;
    this._accumulator = 0;
  }
}
