/**
 * Top-level simulation orchestrator for the 3D society simulation.
 *
 * Responsibilities:
 * - Holds world state: terrain data, agent list, faction list, environment.
 * - Maintains an ordered pipeline of registered systems (movement, gathering,
 *   combat, trade, etc.) that execute in sequence each tick.
 * - Delegates timing to TickScheduler — one call to tick(realDeltaMs) may
 *   fire zero or more simulation steps depending on accumulated real time.
 * - Provides getSnapshot() for the renderer to read a consistent view of
 *   the world without mutating simulation state.
 *
 * Lifecycle:
 * 1. Construct with config (ticksPerSecond, seed, etc.).
 * 2. Call init(terrainData, seed) to set up the world.
 * 3. Register systems via registerSystem() in desired execution order.
 * 4. Each render frame, call tick(realDeltaMs).
 * 5. Call getSnapshot() to read world state for rendering.
 * 6. Call reset() to tear down and allow re-init.
 *
 * Invariants:
 * - Systems execute in registration order every tick (deterministic).
 * - The event bus is cleared at the start of each simulation tick.
 * - getSnapshot() returns a fresh object each call (no shared references
 *   to mutable internal arrays — shallow copies are sufficient because
 *   the renderer should not mutate snapshot contents).
 */

import { PRNG } from './rng.js';
import { EventBus } from './event-bus.js';
import { TickScheduler } from './tick-scheduler.js';

export class SimEngine {
  /**
   * @param {object} [config={}] - Engine configuration.
   * @param {number} [config.ticksPerSecond=6] - Simulation rate.
   * @param {number} [config.seed=42]          - Default PRNG seed.
   */
  constructor(config = {}) {
    /** @type {object} Frozen copy of the config for inspection. */
    this._config = Object.freeze({ ...config });

    /** @type {number} Default seed, overridable via init(). */
    this._seed = config.seed ?? 42;

    /** @type {TickScheduler} Fixed-step simulation clock. */
    this._scheduler = new TickScheduler(config.ticksPerSecond ?? 6);

    /** @type {EventBus} Per-tick event publish/subscribe bus. */
    this._eventBus = new EventBus();

    /** @type {PRNG|null} Deterministic RNG — created on init(). */
    this._rng = null;

    /**
     * Ordered list of registered systems. Each system is an object with
     * at minimum an `update(context)` method. Systems run in the order
     * they were registered — this order defines the simulation's semantics
     * (e.g. movement before combat means agents move then fight at new positions).
     * @type {object[]}
     */
    this._systems = [];

    /**
     * World state — mutable, updated by systems each tick.
     * Initialized to empty/default values; populated by init().
     * @type {object}
     */
    this._world = this._createEmptyWorld();

    /** @type {boolean} Whether init() has been called successfully. */
    this._initialized = false;
  }

  /**
   * Create empty world state with all expected fields.
   * This ensures getSnapshot() always returns a well-shaped object even
   * before init() is called (fail-safe for early renderer queries).
   *
   * @returns {object} Empty world state.
   * @private
   */
  _createEmptyWorld() {
    return {
      terrain: {
        size: 0,
        worldScale: 1,
        heightMap: null,
        slopeMap: null,
        waterMap: null,
        biomeMap: null,
        regionMap: null,
        navGrid: null,
      },
      environment: {
        weather: 'clear',
        temperature: 20,
        diseasePressure: 0,
        resourceFields: [],
        pois: [],
      },
      agents: [],
      factions: [],
      events: [],
      telemetry: {},
    };
  }

  /**
   * Initialize (or re-initialize) the simulation world.
   *
   * @param {object} terrainData - Pre-generated terrain data. Expected to
   *   contain at minimum { size, worldScale } and optional map arrays
   *   (heightMap, slopeMap, waterMap, biomeMap, regionMap, navGrid).
   * @param {number} [seed] - PRNG seed for this run. Falls back to config seed.
   */
  init(terrainData, seed) {
    const effectiveSeed = seed ?? this._seed;

    // Create fresh RNG from seed so the simulation is deterministic from
    // this point forward regardless of any prior state.
    this._rng = new PRNG(effectiveSeed);

    // Reset scheduler so tick counter starts at 0 for the new run.
    this._scheduler.reset();

    // Clear any leftover events from a prior run.
    this._eventBus.clear();

    // Populate terrain from provided data. Spread over the empty-world defaults
    // so any missing fields retain their safe fallback values (null / 0 / 1).
    this._world = this._createEmptyWorld();
    if (terrainData) {
      this._world.terrain = { ...this._world.terrain, ...terrainData };
    }

    this._initialized = true;
  }

  /**
   * Register a system to the simulation pipeline.
   *
   * Systems execute in registration order. Each system must have an
   * `update(context)` method that receives the tick context object:
   *   { world, rng, eventBus, tick }
   *
   * @param {object} system - System object with an update(context) method.
   * @throws {Error} If system lacks an update method.
   */
  registerSystem(system) {
    // Accept systems with either .update(context) or .tick(...) methods.
    // All simulation subsystem modules expose .tick() with varying
    // signatures, so we wrap each in a uniform .update(context) adapter
    // at registration time rather than rewriting every module.
    if (!system) {
      throw new Error('SimEngine.registerSystem: system is null/undefined');
    }
    if (typeof system.update === 'function') {
      this._systems.push(system);
    } else if (typeof system.tick === 'function') {
      const wrapper = Object.create(system);
      wrapper._inner = system;
      wrapper.update = function(ctx) { system.tick(ctx.world.agents, ctx.world, ctx); };
      this._systems.push(wrapper);
    } else {
      throw new Error(
        'SimEngine.registerSystem: system must have an update(context) or tick() method'
      );
    }
  }

  /**
   * Advance the simulation by the given real-time delta.
   *
   * The TickScheduler converts wall-clock time into zero or more fixed-step
   * ticks. For each tick, all systems run in order with a shared context.
   *
   * @param {number} realDeltaMs - Wall-clock milliseconds since last call.
   *   Typically from requestAnimationFrame timestamp diff.
   */
  tick(realDeltaMs) {
    if (!this._initialized) {
      // Silently skip if not initialized — the renderer may call tick()
      // before the world is ready (e.g. during async terrain loading).
      return;
    }

    const tickCount = this._scheduler.update(realDeltaMs);

    for (let t = 0; t < tickCount; t++) {
      // Clear per-tick event buffer so events from the previous tick
      // do not leak into this one.
      this._eventBus.clear();

      // Build the context object that all systems receive. A fresh object
      // per tick prevents systems from caching stale references.
      const context = {
        world: this._world,
        rng: this._rng,
        eventBus: this._eventBus,
        tick: this._scheduler.getTick(),
      };

      // Execute each system in registration order.
      // Deterministic ordering is critical: if movement runs before combat,
      // agents fight at their new positions. Changing order changes semantics.
      for (let i = 0; i < this._systems.length; i++) {
        this._systems[i].update(context);
      }

      // Snapshot events from this tick into the world for getSnapshot().
      // We use getEvents() (not flush()) so the buffer remains available
      // for any late subscribers that read during the same tick.
      this._world.events = this._eventBus.getEvents();
    }
  }

  /**
   * Return a snapshot of the current world state for rendering.
   *
   * The returned object is a shallow copy — the renderer should treat it
   * as read-only. Arrays are spread-copied so pushing to the snapshot
   * does not affect the live simulation.
   *
   * @returns {object} World snapshot matching the canonical shape:
   *   { tick, terrain, environment, agents, factions, events, telemetry }
   */
  getSnapshot() {
    return {
      tick: this._scheduler.getTick(),
      terrain: { ...this._world.terrain },
      environment: { ...this._world.environment },
      agents: [...this._world.agents],
      factions: [...this._world.factions],
      events: [...this._world.events],
      telemetry: { ...this._world.telemetry },
    };
  }

  /**
   * Tear down the simulation and reset to pre-init state.
   * Clears systems, world state, RNG, and scheduler.
   * After reset(), init() must be called before tick() will do anything.
   */
  reset() {
    this._scheduler.reset();
    this._eventBus.clear();
    this._rng = null;
    this._systems = [];
    this._world = this._createEmptyWorld();
    this._initialized = false;
  }
}
