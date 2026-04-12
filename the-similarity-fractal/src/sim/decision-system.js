/**
 * decision-system.js — Utility-based decision model for agent behaviour.
 *
 * Each tick, every agent evaluates a set of candidate actions and picks the
 * one with the highest utility score.  Utility functions fold in the agent's
 * physiological needs, perception of nearby entities, and role-specific
 * bonuses so that behaviour emerges naturally without hard-coded state
 * machines.
 *
 * LOD awareness: agents at SPOTLIGHT tier evaluate the full action set;
 * agents at BACKGROUND tier use a fast path that only scores the top-3
 * most likely actions (determined by dominant need) to save CPU.
 *
 * Lifecycle:
 *   const ds = new DecisionSystem(rng);
 *   ds.tick(agents, perceptionSystem, lodSystem, worldState);
 *   // after tick, each agent has updated currentGoal & currentAction
 *
 * Immutability: the system mutates agent.currentGoal and agent.currentAction
 * in place.  All other agent fields are read-only during evaluation.
 */

import { clamp01 } from './utils.js';

// ── Action catalogue ────────────────────────────────────────────────────
/** Every action the decision system can select. */
export const ACTIONS = Object.freeze({
  GATHER_FOOD:     'GATHER_FOOD',
  GATHER_MATERIAL: 'GATHER_MATERIAL',
  DRINK:           'DRINK',
  REST:            'REST',
  SOCIALIZE:       'SOCIALIZE',
  TRADE:           'TRADE',
  MIGRATE:         'MIGRATE',
  FLEE:            'FLEE',
  FIGHT:           'FIGHT',
  PATROL:          'PATROL',
});

/** Ordered array for iteration — keeps evaluation deterministic. */
const ALL_ACTIONS = Object.freeze(Object.values(ACTIONS));

// ── Role bonuses ────────────────────────────────────────────────────────
/**
 * Additive bonus per role.  Only the actions listed get a bonus; everything
 * else implicitly gets 0.  Bonuses are moderate (0.1–0.3) so they nudge
 * rather than override physiological urgency.
 */
const ROLE_BONUSES = Object.freeze({
  soldier: { [ACTIONS.FIGHT]: 0.25, [ACTIONS.PATROL]: 0.20, [ACTIONS.FLEE]: -0.10 },
  trader:  { [ACTIONS.TRADE]: 0.30, [ACTIONS.SOCIALIZE]: 0.10 },
  farmer:  { [ACTIONS.GATHER_FOOD]: 0.25, [ACTIONS.GATHER_MATERIAL]: 0.15 },
  builder: { [ACTIONS.GATHER_MATERIAL]: 0.25, [ACTIONS.TRADE]: 0.10 },
  healer:  { [ACTIONS.SOCIALIZE]: 0.20, [ACTIONS.REST]: 0.10 },
});

// ── LOD tiers ───────────────────────────────────────────────────────────
const LOD_SPOTLIGHT  = 'SPOTLIGHT';
// Any tier that is not SPOTLIGHT is treated as BACKGROUND for fast-path.

// ── Utility helpers ─────────────────────────────────────────────────────

/**
 * Convert a "need" value (0 = satisfied, 1 = desperate) into a utility
 * curve.  We use a soft quadratic ramp so moderate needs don't dominate
 * until they become urgent.
 *
 *   u(need) = need^1.5
 *
 * The exponent > 1 means low needs produce little urgency while high needs
 * spike sharply, which gives agents "lazy" behaviour when comfortable and
 * panicky behaviour when deprived.
 */
function needToUtility(need) {
  const n = clamp01(need);
  return n * Math.sqrt(n); // equivalent to n^1.5, avoids Math.pow overhead
}

// ── Per-action utility scorers ──────────────────────────────────────────
/**
 * Each scorer takes (agent, perception, worldState, rng) and returns a raw
 * utility in [0, 1].  The decision system adds role bonuses on top.
 *
 * "perception" is the pre-computed result for this agent from
 * perceptionSystem — an object with { nearbyAgents, nearbyResources,
 * nearbyThreats, nearWater }.  If the perception system is absent or
 * returns null the scorer must degrade gracefully.
 */

const SCORERS = {
  /**
   * GATHER_FOOD — driven by hunger need.  Boosted slightly when the agent
   * can see a food resource nearby (perception.nearbyResources includes food).
   */
  [ACTIONS.GATHER_FOOD](agent, perception, _ws, _rng) {
    const hunger = needToUtility(agent.needs?.hunger ?? 0);
    // Nearby food resource makes gathering more attractive (less travel cost).
    const foodNear = perception?.nearbyResources?.some(r => r.type === 'food') ? 0.1 : 0;
    return clamp01(hunger + foodNear);
  },

  /** GATHER_MATERIAL — driven by a material-need proxy (low inventory). */
  [ACTIONS.GATHER_MATERIAL](agent, perception, _ws, _rng) {
    // Material need: inverse of how much material the agent already has.
    const inv = agent.inventory?.material ?? 0;
    const need = clamp01(1 - inv / 10); // 10 units = "enough"
    const matNear = perception?.nearbyResources?.some(r => r.type === 'material') ? 0.1 : 0;
    return clamp01(needToUtility(need) * 0.6 + matNear);
  },

  /** DRINK — driven by hydration need; requires water nearby to score high. */
  [ACTIONS.DRINK](agent, perception, _ws, _rng) {
    const thirst = needToUtility(agent.needs?.thirst ?? 0);
    const waterNear = perception?.nearWater ? 0.15 : -0.3;
    return clamp01(thirst + waterNear);
  },

  /** REST — driven by low energy.  Always available (no spatial requirement). */
  [ACTIONS.REST](agent, _perc, _ws, _rng) {
    const fatigue = needToUtility(1 - clamp01(agent.needs?.energy ?? 1));
    return clamp01(fatigue);
  },

  /**
   * SOCIALIZE — driven by social need plus proximity of friendly agents.
   * Agents with high stress also seek socialisation as a coping mechanism.
   */
  [ACTIONS.SOCIALIZE](agent, perception, _ws, _rng) {
    const socialNeed = needToUtility(agent.needs?.social ?? 0);
    const stress = clamp01(agent.needs?.stress ?? 0) * 0.3;
    const friendsNear = (perception?.nearbyAgents?.length ?? 0) > 0 ? 0.1 : -0.2;
    return clamp01(socialNeed + stress + friendsNear);
  },

  /**
   * TRADE — driven by having surplus inventory AND nearby willing traders.
   * Role bonuses (trader) push this up further.
   */
  [ACTIONS.TRADE](agent, perception, _ws, _rng) {
    const surplus = clamp01(((agent.inventory?.food ?? 0) + (agent.inventory?.material ?? 0)) / 15);
    const tradersNear = perception?.nearbyAgents?.some(a => a.role === 'trader' || a.currentAction === ACTIONS.TRADE) ? 0.15 : 0;
    return clamp01(surplus * 0.5 + tradersNear + 0.05);
  },

  /**
   * MIGRATE — triggered by resource scarcity in the current area or
   * overcrowding.  This is a "slow burn" action: only wins when the agent
   * has no urgent physiological need AND the local environment is poor.
   */
  [ACTIONS.MIGRATE](agent, perception, _ws, _rng) {
    const resourcesNear = perception?.nearbyResources?.length ?? 0;
    const scarcity = clamp01(1 - resourcesNear / 5);
    // Overcrowding penalty: many agents nearby with few resources.
    const crowding = clamp01((perception?.nearbyAgents?.length ?? 0) / 10);
    // Only migrate when not desperate for anything else.
    const calm = 1 - clamp01(
      (agent.needs?.hunger ?? 0) + (agent.needs?.thirst ?? 0) + (1 - (agent.needs?.energy ?? 1))
    );
    return clamp01(scarcity * 0.4 + crowding * 0.2 + calm * 0.1);
  },

  /**
   * FLEE — threat-driven.  High utility when threats are near and the agent
   * is weak (low hp) or non-combatant.
   */
  [ACTIONS.FLEE](agent, perception, _ws, _rng) {
    const threats = perception?.nearbyThreats?.length ?? 0;
    if (threats === 0) return 0; // no threat, no flee
    const vulnerability = clamp01(1 - (agent.hp ?? 1) / (agent.maxHp ?? 1));
    return clamp01(threats * 0.3 + vulnerability * 0.4);
  },

  /**
   * FIGHT — threat-driven but for agents that are strong enough to engage.
   * Soldiers get a role bonus on top.
   */
  [ACTIONS.FIGHT](agent, perception, _ws, _rng) {
    const threats = perception?.nearbyThreats?.length ?? 0;
    if (threats === 0) return 0;
    const strength = clamp01((agent.hp ?? 1) / (agent.maxHp ?? 1));
    const skill = clamp01((agent.skills?.combat ?? 0) / 10);
    return clamp01(threats * 0.2 + strength * 0.3 + skill * 0.2);
  },

  /** PATROL — low-urgency security action, mainly role-driven (soldiers). */
  [ACTIONS.PATROL](agent, perception, _ws, _rng) {
    // Base utility is very low; role bonus for soldiers makes it competitive.
    const threats = perception?.nearbyThreats?.length ?? 0;
    const calm = threats === 0 ? 0.15 : 0;
    return clamp01(calm + 0.05);
  },
};

// ── Fast-path: top-3 action shortlist for BACKGROUND agents ─────────────
/**
 * Returns the 3 actions most likely to win for this agent, based on the
 * agent's single most pressing need.  This avoids evaluating all 10
 * scorers for low-detail agents.
 */
function fastPathShortlist(agent) {
  const hunger  = agent.needs?.hunger  ?? 0;
  const thirst  = agent.needs?.thirst  ?? 0;
  const energy  = agent.needs?.energy  ?? 1;
  const social  = agent.needs?.social  ?? 0;

  // Pick the dominant deprivation axis.
  const fatigue = 1 - energy;
  const max = Math.max(hunger, thirst, fatigue, social);

  if (max === hunger)  return [ACTIONS.GATHER_FOOD, ACTIONS.TRADE, ACTIONS.MIGRATE];
  if (max === thirst)  return [ACTIONS.DRINK, ACTIONS.MIGRATE, ACTIONS.REST];
  if (max === fatigue) return [ACTIONS.REST, ACTIONS.SOCIALIZE, ACTIONS.DRINK];
  if (max === social)  return [ACTIONS.SOCIALIZE, ACTIONS.TRADE, ACTIONS.GATHER_FOOD];

  // Fallback (all needs are zero): idle-ish actions.
  return [ACTIONS.PATROL, ACTIONS.SOCIALIZE, ACTIONS.MIGRATE];
}

// ── DecisionSystem class ────────────────────────────────────────────────

export class DecisionSystem {
  /**
   * @param {object} rng  PRNG with { next(), nextSigned() }.
   *   next() → [0, 1), nextSigned() → [-1, 1).
   */
  constructor(rng) {
    /** @private */ this._rng = rng;
  }

  /**
   * Run one decision tick for every agent.
   *
   * @param {Array}  agents           — mutable agent objects.
   * @param {object} perceptionSystem — must expose getPerception(agent).
   * @param {object} lodSystem        — must expose getTier(agent) → string.
   * @param {object} worldState       — global state (time, season, etc.).
   */
  tick(agents, perceptionSystem, lodSystem, worldState) {
    for (let i = 0; i < agents.length; i++) {
      const agent = agents[i];

      // Perception may be null if the system is missing or the agent is
      // out-of-bounds.  Scorers degrade gracefully on null.
      const perception = perceptionSystem?.getPerception?.(agent) ?? null;

      // Determine LOD tier — SPOTLIGHT gets full evaluation, everything
      // else gets the fast path.
      const tier = lodSystem?.getTier?.(agent) ?? LOD_SPOTLIGHT;
      const isSpotlight = tier === LOD_SPOTLIGHT;

      // Choose which actions to evaluate.
      const candidates = isSpotlight ? ALL_ACTIONS : fastPathShortlist(agent);

      let bestAction = candidates[0];
      let bestScore  = -Infinity;

      const roleKey = agent.role ?? '';
      const bonuses = ROLE_BONUSES[roleKey] ?? {};

      for (let j = 0; j < candidates.length; j++) {
        const action = candidates[j];
        const scorer = SCORERS[action];
        if (!scorer) continue; // defensive — should not happen

        // Raw utility from the scorer.
        let score = scorer(agent, perception, worldState, this._rng);

        // Additive role bonus (can be negative, e.g. soldiers penalised
        // for fleeing).
        score += bonuses[action] ?? 0;

        // Tiny stochastic jitter (±0.02) prevents identical agents from
        // making perfectly synchronised decisions, which looks uncanny.
        score += this._rng.next() * 0.04 - 0.02;

        if (score > bestScore) {
          bestScore  = score;
          bestAction = action;
        }
      }

      // Write results back onto the agent.
      agent.currentAction = bestAction;
      agent.currentGoal   = bestAction; // goal mirrors action for now
    }
  }
}
