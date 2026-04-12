/**
 * event-schema.js — Event type enum and payload shapes.
 *
 * Every discrete thing that happens in the simulation (an agent moves, a fight
 * starts, a disease spreads) is represented as an immutable event object.
 * Events flow through:
 *   1. The simulation tick loop (emitter)
 *   2. The telemetry aggregator (increments metric counters)
 *   3. The event log / ring buffer (for UI replay and similarity analysis)
 *
 * WHY a flat event object instead of class hierarchies?
 *   - Events are serialized to the similarity engine as plain JSON rows.
 *   - Flat objects are cheaper to GC in high-throughput ticks.
 *   - The validator function provides the same safety net that a class
 *     constructor would, without forcing `new` allocation overhead.
 */

// ─── Event Type Enum ───────────────────────────────────────────────────────
// String constants keyed by UPPER_SNAKE name. Values are lowercase kebab-case
// strings so they serialize readably in logs and JSON exports.

/** @type {Record<string, string>} */
export const EVENT_TYPES = {
  MOVE:               'move',               // Agent changes grid cell
  GATHER:             'gather',             // Agent collects a resource
  CONSUME:            'consume',            // Agent consumes food / water / material
  TRADE:              'trade',              // Two agents exchange resources
  FIGHT:              'fight',              // Combat initiated between agents
  INJURY:             'injury',             // Agent takes damage (combat or hazard)
  DEATH:              'death',              // Agent dies
  BIRTH:              'birth',              // New agent spawned
  HEAL:               'heal',              // Agent recovers health
  INFECTION:          'infection',          // Disease transmitted to agent
  RECOVERY:           'recovery',           // Agent recovers from disease
  ALLIANCE:           'alliance',           // Two factions form an alliance
  BETRAYAL:           'betrayal',           // A faction breaks an alliance
  MIGRATE:            'migrate',            // Agent moves to a different region
  DISCOVER_RESOURCE:  'discover-resource',  // New resource node revealed
  SETTLEMENT_EXPAND:  'settlement-expand',  // Settlement grows in size
  SCARCITY_WARNING:   'scarcity-warning',   // Region food/material drops below threshold
};

// Pre-compute a Set for O(1) membership checks in the validator.
const _KNOWN_TYPES = new Set(Object.values(EVENT_TYPES));

// ─── Factory ───────────────────────────────────────────────────────────────

/**
 * Create a simulation event object.
 *
 * The factory stamps `timestamp` (wall-clock) immediately. The caller is
 * responsible for setting `tick` once the event is processed by the tick loop
 * — this two-phase design lets events be created speculatively and then
 * committed when the tick finalizes.
 *
 * @param {string} type    - One of EVENT_TYPES values.
 * @param {Object} payload - Arbitrary key-value data specific to the event type.
 *                           Common fields: targetId, resourceType, amount, position.
 * @returns {{ type: string, tick: null, agentId: null, timestamp: number, [key: string]: * }}
 */
export function createEvent(type, payload = {}) {
  return {
    tick: null,       // Filled by the tick loop when the event is committed
    agentId: null,    // Filled by the emitting agent or system
    ...payload,       // Spread after defaults so callers CAN override tick/agentId
    type,             // After spread so payload cannot accidentally override event type
    timestamp: Date.now(),
  };
}

// ─── Validator ─────────────────────────────────────────────────────────────

/**
 * Validate that an event object has a known type.
 *
 * Intentionally lightweight — only checks the `type` field against the enum.
 * Payload validation is left to per-system consumers (combat system validates
 * damage fields, economy system validates trade amounts, etc.) so the hot path
 * stays fast.
 *
 * @param {Object} event - An event object (ideally from createEvent).
 * @returns {boolean} True if event.type is a recognized EVENT_TYPES value.
 */
export function validateEvent(event) {
  if (!event || typeof event !== 'object') {
    return false;
  }
  return _KNOWN_TYPES.has(event.type);
}
