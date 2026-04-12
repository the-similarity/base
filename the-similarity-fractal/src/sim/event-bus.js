/**
 * Synchronous publish/subscribe event bus for the society simulation.
 *
 * Design rationale:
 * - Systems (movement, gathering, combat, trade) emit typed events during a tick.
 * - Other systems or telemetry layers subscribe to react or aggregate.
 * - Events are buffered within a tick so batch retrieval is possible after
 *   all systems have run, enabling cross-system analysis without ordering bugs.
 *
 * Lifecycle:
 * 1. At tick start, call clear() to reset the per-tick buffer.
 * 2. Systems emit() events as they execute.
 * 3. Subscribers receive events synchronously via on() handlers.
 * 4. After all systems run, call getEvents() to retrieve buffered events
 *    for telemetry, replay logging, or snapshot inclusion.
 * 5. flush() is available to drain and return all buffered events at once.
 *
 * Invariants:
 * - Handlers fire synchronously in registration order (deterministic).
 * - The buffer grows unbounded within a tick — call clear() between ticks.
 * - off() is idempotent: removing a non-registered handler is a no-op.
 *
 * NOT thread-safe, but JS is single-threaded so that is fine.
 */

export class EventBus {
  constructor() {
    /**
     * Map from event type string to array of handler functions.
     * @type {Map<string, Function[]>}
     */
    this._handlers = new Map();

    /**
     * Per-tick event buffer. Keyed by event type for efficient retrieval.
     * Each value is an array of payload objects emitted during the current tick.
     * @type {Map<string, object[]>}
     */
    this._buffer = new Map();
  }

  /**
   * Emit a typed event. The payload is delivered synchronously to all
   * registered handlers for the given type, then buffered for batch retrieval.
   *
   * @param {string} type  - Event type identifier (e.g. 'move', 'gather', 'death', 'trade').
   * @param {object} payload - Arbitrary event data. Should be a plain object.
   */
  emit(type, payload) {
    // Buffer the event for later batch retrieval via getEvents() / flush().
    if (!this._buffer.has(type)) {
      this._buffer.set(type, []);
    }
    this._buffer.get(type).push(payload);

    // Deliver to subscribers synchronously, in registration order.
    // This guarantees deterministic handler execution within a tick.
    const handlers = this._handlers.get(type);
    if (handlers) {
      for (let i = 0; i < handlers.length; i++) {
        handlers[i](payload);
      }
    }
  }

  /**
   * Register a handler for a given event type.
   *
   * @param {string}   type    - Event type to subscribe to.
   * @param {Function} handler - Callback invoked with the event payload.
   */
  on(type, handler) {
    if (!this._handlers.has(type)) {
      this._handlers.set(type, []);
    }
    this._handlers.get(type).push(handler);
  }

  /**
   * Unregister a handler. Idempotent — removing a handler that was never
   * registered (or already removed) is a silent no-op.
   *
   * @param {string}   type    - Event type the handler was registered for.
   * @param {Function} handler - The exact function reference to remove.
   */
  off(type, handler) {
    const handlers = this._handlers.get(type);
    if (!handlers) return;

    const idx = handlers.indexOf(handler);
    if (idx !== -1) {
      // Splice preserves registration order for remaining handlers.
      handlers.splice(idx, 1);
    }
  }

  /**
   * Drain and return all buffered events, then clear the buffer.
   * Useful for end-of-tick processing where you want everything at once.
   *
   * @returns {Map<string, object[]>} The full buffer (caller now owns it).
   */
  flush() {
    const flushed = this._buffer;
    // Replace with a fresh map so the bus is immediately reusable.
    this._buffer = new Map();
    return flushed;
  }

  /**
   * Retrieve buffered events, optionally filtered by type.
   *
   * @param {string} [type] - If provided, return only events of this type.
   *                          If omitted, return all buffered events as a flat array.
   * @returns {object[]} Array of event payloads.
   */
  getEvents(type) {
    if (type !== undefined) {
      return this._buffer.get(type) || [];
    }
    // No type filter — flatten all buffered events into a single array.
    const all = [];
    for (const events of this._buffer.values()) {
      for (let i = 0; i < events.length; i++) {
        all.push(events[i]);
      }
    }
    return all;
  }

  /**
   * Clear the per-tick event buffer. Call this at the start of each tick
   * to prevent unbounded memory growth.
   *
   * Note: this does NOT remove handler subscriptions — only buffered events.
   */
  clear() {
    this._buffer.clear();
  }
}
