/**
 * interaction-system.js — Resolves agent actions that involve other entities
 * or the environment.
 *
 * After the decision system picks each agent's action, this system executes
 * the side-effects: depleting resources, transferring inventory, dealing
 * damage, adjusting relationships, etc.  Every mutation emits an event on
 * the shared eventBus so downstream systems (UI, analytics, narrative) can
 * react without coupling.
 *
 * Event types emitted: 'gather', 'trade', 'fight', 'injury', 'heal', 'consume'.
 *
 * Lifecycle:
 *   const is = new InteractionSystem(eventBus, rng);
 *   is.tick(agents, perceptionSystem, resourceField, poiRegistry);
 *
 * Immutability: this system mutates agent fields (inventory, hp, needs,
 * relationships) and resourceField cells in place.  The eventBus and
 * poiRegistry are read-only from this system's perspective.
 */

import { clamp01, findNearest } from './utils.js';
import { ACTIONS } from './decision-system.js';

// ── Constants ───────────────────────────────────────────────────────────

/** Base damage range for a FIGHT action (before skill modifier). */
const BASE_DAMAGE_MIN = 2;
const BASE_DAMAGE_MAX = 8;

/** How much socialising reduces social need per tick. */
const SOCIALIZE_NEED_REDUCTION = 0.15;

/** How much socialising reduces stress per tick. */
const SOCIALIZE_STRESS_REDUCTION = 0.10;

/** Relationship valence delta per socialise tick. */
const SOCIALIZE_VALENCE_DELTA = 0.05;

/** Energy restored per REST tick (fraction of max). */
const REST_ENERGY_RESTORE = 0.12;

/** Thirst reduction when drinking near water. */
const DRINK_THIRST_REDUCTION = 0.35;

/** Amount of resource removed from a field cell per gather. */
const GATHER_YIELD = 1;

// ── InteractionSystem class ─────────────────────────────────────────────

export class InteractionSystem {
  /**
   * @param {object} eventBus — must expose emit(eventType, payload).
   * @param {object} rng      — PRNG with { next(), nextSigned() }.
   */
  constructor(eventBus, rng) {
    /** @private */ this._bus = eventBus;
    /** @private */ this._rng = rng;
  }

  /**
   * Run one interaction tick for all agents.
   *
   * @param {Array}  agents           — mutable agent objects with currentAction set.
   * @param {object} perceptionSystem — exposes getPerception(agent).
   * @param {object} resourceField    — grid of resources; exposes deplete(x, y, type, amount)
   *                                    and query(x, y, type) → amount.
   * @param {object} poiRegistry      — points-of-interest lookup (water sources, etc.).
   */
  tick(agents, perceptionSystem, resourceField, poiRegistry) {
    for (let i = 0; i < agents.length; i++) {
      const agent = agents[i];
      const action = agent.currentAction;
      if (!action) continue;

      // Dispatch to the appropriate handler.  Each handler is responsible
      // for its own event emission and guard checks.
      switch (action) {
        case ACTIONS.GATHER_FOOD:
          this._handleGather(agent, resourceField, 'food');
          break;
        case ACTIONS.GATHER_MATERIAL:
          this._handleGather(agent, resourceField, 'material');
          break;
        case ACTIONS.DRINK:
          this._handleDrink(agent, poiRegistry);
          break;
        case ACTIONS.REST:
          this._handleRest(agent);
          break;
        case ACTIONS.SOCIALIZE:
          this._handleSocialize(agent, agents, perceptionSystem);
          break;
        case ACTIONS.TRADE:
          this._handleTrade(agent, agents, perceptionSystem);
          break;
        case ACTIONS.FIGHT:
          this._handleFight(agent, agents, perceptionSystem);
          break;
        // FLEE, MIGRATE, PATROL are movement-only — resolved by the
        // movement system, not here.  No-op in the interaction system.
        default:
          break;
      }
    }
  }

  // ── Action handlers ─────────────────────────────────────────────────

  /**
   * GATHER — deplete a resource cell at the agent's position, add yield to
   * the agent's inventory.
   */
  _handleGather(agent, resourceField, type) {
    if (!resourceField) return;

    const available = resourceField.query?.(agent.x ?? 0, agent.y ?? 0, type) ?? 0;
    if (available <= 0) return; // nothing to gather

    const yielded = Math.min(GATHER_YIELD, available);
    resourceField.deplete?.(agent.x ?? 0, agent.y ?? 0, type, yielded);

    // Ensure inventory object exists.
    if (!agent.inventory) agent.inventory = {};
    agent.inventory[type] = (agent.inventory[type] ?? 0) + yielded;

    // Gathering food also reduces hunger slightly (the agent snacks).
    if (type === 'food' && agent.needs) {
      agent.needs.hunger = clamp01((agent.needs.hunger ?? 0) - 0.05);
    }

    this._bus.emit('gather', {
      agentId: agent.id,
      type,
      amount: yielded,
      x: agent.x,
      y: agent.y,
    });
  }

  /**
   * DRINK — reduce thirst need if the agent is near a water source.
   * Water proximity is checked via the poiRegistry (type 'water').
   */
  _handleDrink(agent, poiRegistry) {
    // Check if agent is near water.  Accept either poiRegistry.nearWater(agent)
    // or a simple query method.
    const nearWater =
      poiRegistry?.nearWater?.(agent) ??
      poiRegistry?.query?.(agent.x ?? 0, agent.y ?? 0, 'water') > 0;

    if (!nearWater) return; // can't drink without water

    if (!agent.needs) agent.needs = {};
    agent.needs.thirst = clamp01((agent.needs.thirst ?? 0) - DRINK_THIRST_REDUCTION);

    this._bus.emit('consume', {
      agentId: agent.id,
      type: 'water',
    });
  }

  /**
   * REST — restore energy.  No spatial requirement; the agent just stops
   * and recuperates wherever they are.
   */
  _handleRest(agent) {
    if (!agent.needs) agent.needs = {};
    agent.needs.energy = clamp01((agent.needs.energy ?? 0) + REST_ENERGY_RESTORE);

    // Resting also heals a tiny amount of HP if below max.
    if (agent.hp != null && agent.maxHp != null && agent.hp < agent.maxHp) {
      agent.hp = Math.min(agent.maxHp, agent.hp + 1);
      this._bus.emit('heal', {
        agentId: agent.id,
        amount: 1,
      });
    }
  }

  /**
   * SOCIALIZE — find a nearby agent and build relationship.  Reduces the
   * social need and stress for both participants.
   */
  _handleSocialize(agent, agents, perceptionSystem) {
    const perception = perceptionSystem?.getPerception?.(agent);
    const nearbyAgents = perception?.nearbyAgents ?? agents;

    // Pick the nearest non-hostile agent.
    const partner = findNearest(agent, nearbyAgents, (other) => {
      // Don't socialise with someone who is fighting or fleeing.
      return other.currentAction !== ACTIONS.FIGHT && other.currentAction !== ACTIONS.FLEE;
    });
    if (!partner) return;

    // Reduce social need and stress for both agents.
    if (!agent.needs) agent.needs = {};
    if (!partner.needs) partner.needs = {};

    agent.needs.social   = clamp01((agent.needs.social   ?? 0) - SOCIALIZE_NEED_REDUCTION);
    agent.needs.stress   = clamp01((agent.needs.stress   ?? 0) - SOCIALIZE_STRESS_REDUCTION);
    partner.needs.social = clamp01((partner.needs.social ?? 0) - SOCIALIZE_NEED_REDUCTION * 0.5);
    partner.needs.stress = clamp01((partner.needs.stress ?? 0) - SOCIALIZE_STRESS_REDUCTION * 0.5);

    // Adjust relationship valence.  Relationships are stored as a Map on
    // each agent: agent.relationships = Map<agentId, { valence: number }>.
    this._adjustRelationship(agent, partner, SOCIALIZE_VALENCE_DELTA);
    this._adjustRelationship(partner, agent, SOCIALIZE_VALENCE_DELTA * 0.5);
  }

  /**
   * TRADE — find a nearby willing trader, transfer inventory items, adjust
   * wealth for both agents.
   */
  _handleTrade(agent, agents, perceptionSystem) {
    const perception = perceptionSystem?.getPerception?.(agent);
    const nearbyAgents = perception?.nearbyAgents ?? agents;

    // A trade partner is someone who also wants to trade or is a trader by role.
    const partner = findNearest(agent, nearbyAgents, (other) => {
      return other.currentAction === ACTIONS.TRADE || other.role === 'trader';
    });
    if (!partner) return;

    // Simple barter: try to swap 1 unit of complementary resources.
    // Attempt food-for-material first, then the reverse.
    if (!agent.inventory)   agent.inventory   = {};
    if (!partner.inventory) partner.inventory = {};

    // Try both barter directions; first viable one wins.
    const traded =
      this._tryBarter(agent, partner, 'food', 'material') ||
      this._tryBarter(agent, partner, 'material', 'food');
    // If neither side has complementary surplus, trade simply fails
    // silently — the agent wasted a tick.
    void traded;
  }

  /**
   * Attempt a 1-for-1 barter: agent gives `giveType`, partner gives `getType`.
   * Returns true if the swap happened, false otherwise.
   *
   * @private
   */
  _tryBarter(agent, partner, giveType, getType) {
    const agentHas   = agent.inventory[giveType]   ?? 0;
    const partnerHas = partner.inventory[getType]   ?? 0;
    if (agentHas < 1 || partnerHas < 1) return false;

    agent.inventory[giveType]    -= 1;
    partner.inventory[giveType]   = (partner.inventory[giveType] ?? 0) + 1;
    partner.inventory[getType]   -= 1;
    agent.inventory[getType]      = (agent.inventory[getType] ?? 0) + 1;

    // Wealth adjustment: both gain a small amount (trade is positive-sum
    // because items move to where they are valued more).
    agent.wealth   = (agent.wealth   ?? 0) + 0.5;
    partner.wealth = (partner.wealth ?? 0) + 0.5;

    this._bus.emit('trade', {
      agentId: agent.id,
      partnerId: partner.id,
      given: { [giveType]: 1 },
      received: { [getType]: 1 },
    });
    return true;
  }

  /**
   * FIGHT — deal HP damage to the nearest threat.  Damage scales with
   * the agent's combat skill plus randomness.
   */
  _handleFight(agent, agents, perceptionSystem) {
    const perception = perceptionSystem?.getPerception?.(agent);
    const threats = perception?.nearbyThreats ?? [];

    // Pick the nearest threat as target.
    const target = findNearest(agent, threats) ??
                   findNearest(agent, agents, (other) => other.currentAction === ACTIONS.FIGHT);
    if (!target) return;

    // Calculate damage: base + skill modifier + randomness.
    const skill = agent.skills?.combat ?? 0;
    const base  = BASE_DAMAGE_MIN + this._rng.next() * (BASE_DAMAGE_MAX - BASE_DAMAGE_MIN);
    const damage = Math.round(base + skill * 0.5);

    // Apply damage to target.
    if (target.hp == null) target.hp = target.maxHp ?? 100;
    target.hp = Math.max(0, target.hp - damage);

    this._bus.emit('fight', {
      attackerId: agent.id,
      targetId: target.id,
      damage,
    });

    this._bus.emit('injury', {
      agentId: target.id,
      damage,
      attackerId: agent.id,
    });

    // Check for death.
    if (target.hp <= 0) {
      target.alive = false;
      this._bus.emit('injury', {
        agentId: target.id,
        damage: 0,
        attackerId: agent.id,
        death: true,
      });
    }
  }

  // ── Private utilities ───────────────────────────────────────────────

  /**
   * Adjust the relationship valence between two agents.
   * Creates the relationship entry if it doesn't exist.
   */
  _adjustRelationship(agent, other, delta) {
    if (!agent.relationships) agent.relationships = new Map();

    const key = other.id;
    const existing = agent.relationships.get(key);
    if (existing) {
      existing.valence = clamp01(existing.valence + delta);
    } else {
      agent.relationships.set(key, { valence: clamp01(0.5 + delta) });
    }
  }
}
