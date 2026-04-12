/**
 * disease-system.js — SIR-style disease model for the 3D society simulation.
 *
 * Responsibilities:
 *   1. Track infection state per agent: HEALTHY, INFECTED, RECOVERING, IMMUNE.
 *   2. Model transmission via proximity, modified by region density, climate
 *      disease pressure, and water access (sanitation proxy).
 *   3. Progress infected agents through severity (0 → 1) over ticks.
 *   4. Resolve recovery (based on health and rest) and death (at high severity).
 *   5. Emit 'infection', 'recovery', 'death' events for telemetry.
 *
 * SIR model mapping:
 *   S (Susceptible) = HEALTHY
 *   I (Infectious)  = INFECTED
 *   R (Removed)     = RECOVERING → IMMUNE  (or dead)
 *
 * Design notes:
 *   - Headless-safe: no Three.js dependency, pure ES module.
 *   - Uses perceptionSystem.getNearbyAgents() for spatial queries instead of
 *     doing its own O(n^2) distance checks — the perception system owns the
 *     spatial index and amortizes the cost across all systems.
 *   - Severity is a continuous 0→1 float, not discrete stages. This gives
 *     smoother telemetry curves and lets the similarity engine detect gradual
 *     epidemiological shifts rather than step-function transitions.
 *   - PRNG-driven: all stochastic outcomes use the injected rng so runs are
 *     reproducible for pattern-mining across simulation batches.
 *
 * Lifecycle:
 *   constructor(eventBus, rng) → tick(agents, perceptionSystem, climate) each step.
 *   The system mutates agent.health.infection and agent.health.diseaseSeverity
 *   in place. It does not own agent creation or destruction.
 *
 * @module disease-system
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Infection states stored on agent.health.infection */
export const InfectionState = Object.freeze({
  HEALTHY: 'HEALTHY',
  INFECTED: 'INFECTED',
  RECOVERING: 'RECOVERING',
  IMMUNE: 'IMMUNE',
});

/**
 * Base probability of transmission per tick when a susceptible agent is
 * within perception range of an infected agent. This is the "clean room"
 * rate — actual probability is scaled by density, climate, and sanitation.
 */
const BASE_TRANSMISSION_PROB = 0.05;

/**
 * Per-tick severity increase for infected agents. At this rate an agent
 * reaches maximum severity in ~20 ticks if unmodified, which at 4-10 tps
 * means 2-5 real seconds — fast enough to create visible epidemic waves.
 */
const SEVERITY_INCREMENT = 0.05;

/**
 * Severity threshold above which the agent has a per-tick death risk.
 * Below this threshold infection is uncomfortable but not lethal.
 */
const LETHAL_SEVERITY_THRESHOLD = 0.7;

/**
 * Maximum per-tick death probability at severity = 1.0.
 * Actual death prob = BASE_DEATH_PROB * (severity - LETHAL_THRESHOLD) / (1 - LETHAL_THRESHOLD).
 */
const BASE_DEATH_PROB = 0.08;

/**
 * Base per-tick recovery probability. Modified upward by agent health and
 * energy (rest). An agent at full health+energy has ~2x this rate.
 */
const BASE_RECOVERY_PROB = 0.03;

/**
 * Ticks an agent stays in RECOVERING before transitioning to IMMUNE.
 * During recovery the agent is non-infectious but still weakened.
 */
const RECOVERY_DURATION = 10;

/**
 * Ticks an IMMUNE agent stays immune before returning to HEALTHY
 * (susceptible again). Set to 0 for permanent immunity.
 * Non-zero creates SIR-S cycling which produces richer epidemic waves.
 */
const IMMUNITY_DURATION = 100;

/**
 * Radius (in world units) for infection transmission checks.
 * This is passed to perceptionSystem.getNearbyAgents().
 */
const INFECTION_RADIUS = 3.0;

/**
 * Density multiplier: transmission prob is scaled by
 * min(nearbyCount / DENSITY_NORM, MAX_DENSITY_MULT).
 * Higher local density = faster spread. DENSITY_NORM is the "normal"
 * crowd size; above it the multiplier exceeds 1.
 */
const DENSITY_NORM = 5;
const MAX_DENSITY_MULT = 3.0;

/**
 * Sanitation modifier: agents near water (waterAccess > 0.5) get a
 * reduction in transmission probability. Represents better sanitation
 * infrastructure near water sources.
 */
const SANITATION_REDUCTION = 0.4;

// ---------------------------------------------------------------------------
// DiseaseSystem
// ---------------------------------------------------------------------------

/**
 * SIR-style disease simulation system.
 *
 * Invariants:
 *   - Only mutates agent.health.{infection, diseaseSeverity, infectedTick,
 *     recoveringTick, immuneTick}. Never touches position, inventory, etc.
 *   - All state transitions emit events through the event bus.
 *   - Dead agents (agent.alive === false) are skipped entirely.
 */
export class DiseaseSystem {
  /**
   * @param {Object} eventBus - Event emitter with emit(eventName, payload).
   * @param {Object} rng - PRNG with { next(): number in [0,1), nextSigned(): number in [-1,1) }.
   */
  constructor(eventBus, rng) {
    /** @type {Object} */
    this._eventBus = eventBus;
    /** @type {Object} */
    this._rng = rng;
  }

  /**
   * Run one disease tick across all agents.
   *
   * Processing order matters:
   *   1. Transmission (HEALTHY → INFECTED) — uses current-tick infected set.
   *   2. Severity progression (INFECTED agents get sicker).
   *   3. Death checks (high-severity INFECTED agents may die).
   *   4. Recovery checks (INFECTED agents may start recovering).
   *   5. Recovery completion (RECOVERING → IMMUNE after duration).
   *   6. Immunity expiry (IMMUNE → HEALTHY after duration).
   *
   * This order ensures new infections don't immediately progress in the
   * same tick, giving a 1-tick incubation delay.
   *
   * @param {Array} agents - Mutable array of agent state objects.
   * @param {Object} perceptionSystem - Spatial query system with
   *   getNearbyAgents(agent, radius): Agent[].
   * @param {Object} climate - Climate state with { diseasePressure: number }.
   *   diseasePressure in [0, 1] where 1 = maximum disease-favorable conditions.
   * @param {number} [tick=0] - Current simulation tick for event tagging.
   */
  tick(agents, perceptionSystem, climate, tick = 0) {
    const diseasePressure = climate?.diseasePressure ?? 0.5;

    // Phase 1: Transmission — find new infections
    // We snapshot the infected set first so newly infected agents don't
    // transmit in the same tick they caught the disease.
    const infectedSet = new Set();
    for (const agent of agents) {
      if (!agent.alive) continue;
      this._ensureHealthFields(agent);
      if (agent.health.infection === InfectionState.INFECTED) {
        infectedSet.add(agent.id);
      }
    }

    for (const agent of agents) {
      if (!agent.alive) continue;
      if (agent.health.infection !== InfectionState.HEALTHY) continue;

      // Check if any nearby agent is infected
      const nearby = perceptionSystem.getNearbyAgents(agent, INFECTION_RADIUS);
      const nearbyInfected = nearby.filter((a) => infectedSet.has(a.id));
      if (nearbyInfected.length === 0) continue;

      // Compute transmission probability with modifiers
      const prob = this._computeTransmissionProb(
        nearby.length,
        diseasePressure,
        agent
      );

      // Each nearby infected agent is an independent transmission chance
      // Probability of NOT getting infected = (1 - prob)^nearbyInfected
      // This compound probability naturally handles super-spreader density.
      const escapeProbability = Math.pow(1 - prob, nearbyInfected.length);
      if (this._rng.next() >= escapeProbability) {
        agent.health.infection = InfectionState.INFECTED;
        agent.health.diseaseSeverity = 0;
        agent.health.infectedTick = tick;

        this._eventBus.emit('infection', {
          tick,
          agentId: agent.id,
          regionId: agent.regionId,
          sourceCount: nearbyInfected.length,
        });
      }
    }

    // Phase 2-6: Progress existing infections
    for (const agent of agents) {
      if (!agent.alive) continue;
      this._ensureHealthFields(agent);

      switch (agent.health.infection) {
        case InfectionState.INFECTED:
          this._progressInfection(agent, tick);
          break;
        case InfectionState.RECOVERING:
          this._progressRecovery(agent, tick);
          break;
        case InfectionState.IMMUNE:
          this._progressImmunity(agent, tick);
          break;
        // HEALTHY: handled above in transmission phase
      }
    }
  }

  // -------------------------------------------------------------------------
  // Private: state transitions
  // -------------------------------------------------------------------------

  /**
   * Progress an INFECTED agent: increase severity, check death, check recovery.
   * @private
   */
  _progressInfection(agent, tick) {
    // Increase severity — sicker agents with low health progress faster
    const healthMod = 1 + (1 - (agent.health.hp ?? 1)); // low HP = faster progression
    agent.health.diseaseSeverity = Math.min(
      1.0,
      agent.health.diseaseSeverity + SEVERITY_INCREMENT * healthMod
    );

    // Death check: only above lethal threshold
    if (agent.health.diseaseSeverity > LETHAL_SEVERITY_THRESHOLD) {
      const deathProb =
        BASE_DEATH_PROB *
        ((agent.health.diseaseSeverity - LETHAL_SEVERITY_THRESHOLD) /
          (1 - LETHAL_SEVERITY_THRESHOLD));

      if (this._rng.next() < deathProb) {
        // Capture severity before reset for the event payload
        const finalSeverity = agent.health.diseaseSeverity;
        agent.alive = false;
        agent.health.infection = InfectionState.HEALTHY; // Reset for clean state
        agent.health.diseaseSeverity = 0;

        this._eventBus.emit('death', {
          tick,
          agentId: agent.id,
          regionId: agent.regionId,
          cause: 'disease',
          severity: finalSeverity,
        });
        return; // Dead — skip recovery check
      }
    }

    // Recovery check: better health and more energy = higher recovery chance
    const needs = agent.needs ?? {};
    const restBonus = (needs.energy ?? 0.5) * 0.5; // Well-rested agents recover faster
    const healthBonus = (agent.health.hp ?? 0.5) * 0.5;
    const recoveryProb = BASE_RECOVERY_PROB + restBonus + healthBonus;

    if (this._rng.next() < recoveryProb) {
      agent.health.infection = InfectionState.RECOVERING;
      agent.health.recoveringTick = tick;

      this._eventBus.emit('recovery', {
        tick,
        agentId: agent.id,
        regionId: agent.regionId,
        severityAtRecovery: agent.health.diseaseSeverity,
      });
    }
  }

  /**
   * Progress a RECOVERING agent: after duration, transition to IMMUNE.
   * Severity gradually decreases during recovery.
   * @private
   */
  _progressRecovery(agent, tick) {
    // Decrease severity during recovery — healing
    agent.health.diseaseSeverity = Math.max(
      0,
      agent.health.diseaseSeverity - SEVERITY_INCREMENT * 0.5
    );

    const elapsed = tick - (agent.health.recoveringTick ?? tick);
    if (elapsed >= RECOVERY_DURATION) {
      agent.health.infection = InfectionState.IMMUNE;
      agent.health.immuneTick = tick;
      agent.health.diseaseSeverity = 0;
    }
  }

  /**
   * Progress an IMMUNE agent: after duration, return to HEALTHY (susceptible).
   * If IMMUNITY_DURATION is 0, immunity is permanent.
   * @private
   */
  _progressImmunity(agent, tick) {
    if (IMMUNITY_DURATION === 0) return; // Permanent immunity

    const elapsed = tick - (agent.health.immuneTick ?? tick);
    if (elapsed >= IMMUNITY_DURATION) {
      agent.health.infection = InfectionState.HEALTHY;
    }
  }

  // -------------------------------------------------------------------------
  // Private: probability computation
  // -------------------------------------------------------------------------

  /**
   * Compute the per-source transmission probability with all modifiers.
   *
   * Modifiers (multiplicative):
   *   1. Density factor: more nearby agents = higher spread.
   *   2. Climate disease pressure: hot/wet climates amplify disease.
   *   3. Sanitation (water access): reduces transmission near water.
   *
   * @private
   * @param {number} nearbyCount - Total agents within infection radius.
   * @param {number} diseasePressure - Climate disease pressure [0, 1].
   * @param {Object} agent - The susceptible agent (for water access check).
   * @returns {number} Transmission probability in [0, 1].
   */
  _computeTransmissionProb(nearbyCount, diseasePressure, agent) {
    let prob = BASE_TRANSMISSION_PROB;

    // Density modifier: crowded areas spread disease faster
    const densityFactor = Math.min(nearbyCount / DENSITY_NORM, MAX_DENSITY_MULT);
    prob *= densityFactor;

    // Climate modifier: disease pressure amplifies base rate
    // At pressure=0, multiplier=0.5 (half rate); at pressure=1, multiplier=1.5
    prob *= 0.5 + diseasePressure;

    // Sanitation modifier: agents near water have better sanitation
    // waterAccess is expected on agent state, default 0 (no water nearby)
    const waterAccess = agent.waterAccess ?? 0;
    if (waterAccess > 0.5) {
      prob *= 1 - SANITATION_REDUCTION;
    }

    // Clamp to valid probability range
    return Math.min(Math.max(prob, 0), 1);
  }

  // -------------------------------------------------------------------------
  // Private: initialization helpers
  // -------------------------------------------------------------------------

  /**
   * Ensure an agent has all required health fields for disease tracking.
   * Defensive initialization — other systems may create agents without
   * these fields, and we must not crash on missing properties.
   * @private
   */
  _ensureHealthFields(agent) {
    if (!agent.health) {
      agent.health = {};
    }
    if (!agent.health.infection) {
      agent.health.infection = InfectionState.HEALTHY;
    }
    if (agent.health.diseaseSeverity == null) {
      agent.health.diseaseSeverity = 0;
    }
  }
}
