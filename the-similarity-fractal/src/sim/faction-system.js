/**
 * faction-system.js — Dynamic faction emergence and diplomacy for the 3D
 * society simulation.
 *
 * Responsibilities:
 *   1. Detect clusters of agents with strong mutual relationships and form
 *      factions organically (no scripted faction creation).
 *   2. Recruit unaffiliated agents into nearby factions via social influence.
 *   3. Fragment factions when internal hostility exceeds tolerance.
 *   4. Track inter-faction diplomacy: hostility, alliances, betrayals.
 *   5. Emit 'alliance', 'betrayal', 'faction_formed', 'faction_split' events.
 *
 * Design notes:
 *   - Headless-safe: no Three.js dependency, pure ES module.
 *   - Factions are emergent, not predefined. They form from the bottom up
 *     when social relationships cross the affinity threshold.
 *   - The system uses the perceptionSystem for spatial proximity queries,
 *     keeping the spatial index amortized across all systems.
 *   - PRNG-driven: all stochastic outcomes (recruitment, betrayal) use the
 *     injected rng for reproducible simulation runs.
 *   - Faction IDs are monotonically increasing integers — never recycled.
 *     This keeps telemetry cross-referencing unambiguous.
 *
 * Lifecycle:
 *   constructor(eventBus, rng) → tick(agents, perceptionSystem) each step.
 *   The system owns faction state (the registry) and mutates agent.factionId
 *   in place. Agent creation/destruction is not its concern.
 *
 * @module faction-system
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Minimum mutual relationship valence (agent A → B and B → A both above
 * this) required for two agents to be considered "bonded" for faction
 * formation. Valence is expected in [-1, 1] where 1 = best friends.
 */
const AFFINITY_THRESHOLD = 0.4;

/**
 * Minimum cluster size for a new faction to form. Prevents trivial
 * two-agent "factions" that would fragment immediately.
 */
const MIN_FACTION_SIZE = 3;

/**
 * Radius passed to perceptionSystem.getNearbyAgents() for recruitment
 * and faction-formation proximity checks.
 */
const SOCIAL_RADIUS = 5.0;

/**
 * Relationship valence threshold for recruitment. An unaffiliated agent
 * joins a faction if their average valence toward faction members within
 * SOCIAL_RADIUS exceeds this value.
 */
const RECRUITMENT_THRESHOLD = 0.3;

/**
 * When the average internal valence among faction members drops below
 * this value, the faction fragments into sub-groups.
 */
const FRAGMENTATION_THRESHOLD = 0.1;

/**
 * Inter-faction hostility threshold above which alliances are impossible.
 * Hostility is in [0, 1] where 0 = neutral, 1 = war.
 */
const ALLIANCE_HOSTILITY_CEILING = 0.2;

/**
 * Inter-faction sentiment threshold above which an alliance can form.
 * Sentiment is derived from the average pairwise valence between members
 * of two factions who are within perception range of each other.
 */
const ALLIANCE_SENTIMENT_FLOOR = 0.3;

/**
 * When a faction member is attacked by a member of an allied faction,
 * betrayal is detected if the attack is above this damage threshold.
 * Currently we trigger betrayal on any hostile event — the threshold
 * exists for future granularity.
 */
const BETRAYAL_DAMAGE_THRESHOLD = 0;

/**
 * How many ticks between full faction-maintenance sweeps (formation,
 * fragmentation, diplomacy). Recruitment runs every tick, but the
 * expensive cluster detection and diplomacy recalc runs less often.
 */
const MAINTENANCE_INTERVAL = 10;

/**
 * Hostility decay per tick — factions slowly forget grievances.
 * At 0.01/tick and 10 tps, full hostility decays in ~10 seconds.
 */
const HOSTILITY_DECAY = 0.01;

/**
 * Hostility increase when an inter-faction attack occurs.
 */
const HOSTILITY_ATTACK_DELTA = 0.15;

// ---------------------------------------------------------------------------
// Faction data structure
// ---------------------------------------------------------------------------

/**
 * Create a new faction object.
 *
 * @param {number} id - Unique monotonic faction ID.
 * @param {string} name - Human-readable faction name.
 * @returns {Object} Faction record.
 */
function createFaction(id, name) {
  return {
    id,
    name,
    /** @type {Set<string>} Agent IDs belonging to this faction. */
    members: new Set(),
    /** @type {Map<number, number>} factionId → hostility [0, 1]. */
    hostility: new Map(),
    /** @type {Set<number>} IDs of allied factions. */
    alliances: new Set(),
  };
}

// ---------------------------------------------------------------------------
// FactionSystem
// ---------------------------------------------------------------------------

/**
 * Dynamic faction formation, recruitment, fragmentation, and diplomacy.
 *
 * Invariants:
 *   - An agent belongs to at most one faction at any time.
 *   - Faction IDs are never reused (monotonic counter).
 *   - Alliance is symmetric: if A allies B, B allies A.
 *   - Betrayal immediately breaks alliance (both directions).
 *   - Dead agents are pruned from factions every tick.
 */
export class FactionSystem {
  /**
   * @param {Object} eventBus - Event emitter with emit(eventName, payload).
   * @param {Object} rng - PRNG with { next(), nextSigned() }.
   */
  constructor(eventBus, rng) {
    /** @type {Object} */
    this._eventBus = eventBus;
    /** @type {Object} */
    this._rng = rng;

    /**
     * Registry of all active factions, keyed by faction ID.
     * @type {Map<number, Object>}
     */
    this._factions = new Map();

    /**
     * Monotonic ID counter. Never decremented, even when factions dissolve.
     * @type {number}
     */
    this._nextId = 1;

    /**
     * Tick counter for scheduling maintenance sweeps.
     * @type {number}
     */
    this._tickCount = 0;

    // Listen for attack events to update hostility and detect betrayal.
    // The interaction-system is expected to emit 'fight' events with
    // { attackerId, defenderId, damage }.
    this._eventBus.on?.('fight', (evt) => this._onFight(evt));
  }

  /**
   * Run one faction tick.
   *
   * Every tick:
   *   - Prune dead agents from factions.
   *   - Attempt recruitment of unaffiliated agents.
   *   - Decay inter-faction hostility.
   *
   * Every MAINTENANCE_INTERVAL ticks:
   *   - Detect new faction formation from unaffiliated clusters.
   *   - Check for faction fragmentation.
   *   - Update alliances.
   *   - Dissolve empty factions.
   *
   * @param {Array} agents - Mutable array of agent state objects.
   * @param {Object} perceptionSystem - Spatial query: getNearbyAgents(agent, radius).
   * @param {number} [tick=0] - Current simulation tick.
   */
  tick(agents, perceptionSystem, tick = 0) {
    this._tickCount++;

    // Always: prune dead agents and do lightweight recruitment
    this._pruneDead(agents);
    this._recruit(agents, perceptionSystem, tick);
    this._decayHostility();

    // Periodic: expensive maintenance
    if (this._tickCount % MAINTENANCE_INTERVAL === 0) {
      this._detectNewFactions(agents, perceptionSystem, tick);
      this._checkFragmentation(agents, tick);
      this._updateAlliances(agents, perceptionSystem, tick);
      this._dissolveEmpty();
    }
  }

  // -------------------------------------------------------------------------
  // Public query methods
  // -------------------------------------------------------------------------

  /**
   * Get all active factions as an array.
   * @returns {Array<Object>} Array of faction records.
   */
  getFactions() {
    return Array.from(this._factions.values());
  }

  /**
   * Get a specific faction by ID.
   * @param {number} id - Faction ID.
   * @returns {Object|undefined} Faction record or undefined.
   */
  getFaction(id) {
    return this._factions.get(id);
  }

  // -------------------------------------------------------------------------
  // Private: lifecycle operations
  // -------------------------------------------------------------------------

  /**
   * Remove dead agents from all factions and clear their factionId.
   * @private
   */
  _pruneDead(agents) {
    const deadIds = new Set();
    for (const agent of agents) {
      if (!agent.alive && agent.factionId != null) {
        deadIds.add(agent.id);
        agent.factionId = null;
      }
    }
    if (deadIds.size === 0) return;

    for (const faction of this._factions.values()) {
      for (const id of deadIds) {
        faction.members.delete(id);
      }
    }
  }

  /**
   * Attempt to recruit unaffiliated agents into nearby factions.
   *
   * For each unaffiliated living agent, check nearby agents. If a
   * significant number of nearby agents belong to the same faction
   * and the unaffiliated agent has positive average valence toward
   * those members, recruit them.
   *
   * @private
   */
  _recruit(agents, perceptionSystem, tick) {
    for (const agent of agents) {
      if (!agent.alive || agent.factionId != null) continue;

      const nearby = perceptionSystem.getNearbyAgents(agent, SOCIAL_RADIUS);
      if (nearby.length === 0) continue;

      // Count nearby agents per faction and compute average valence
      const factionScores = new Map(); // factionId → { count, totalValence }
      const relationships = agent.relationships ?? {};

      for (const other of nearby) {
        if (!other.alive || other.factionId == null) continue;
        const fid = other.factionId;
        if (!factionScores.has(fid)) {
          factionScores.set(fid, { count: 0, totalValence: 0 });
        }
        const entry = factionScores.get(fid);
        entry.count += 1;
        // Valence from agent toward this faction member
        entry.totalValence += relationships[other.id] ?? 0;
      }

      // Pick the faction with the highest average valence above threshold
      let bestFaction = null;
      let bestValence = RECRUITMENT_THRESHOLD;

      for (const [fid, { count, totalValence }] of factionScores) {
        if (count === 0) continue;
        const avgValence = totalValence / count;
        if (avgValence > bestValence) {
          bestValence = avgValence;
          bestFaction = fid;
        }
      }

      if (bestFaction != null && this._factions.has(bestFaction)) {
        agent.factionId = bestFaction;
        this._factions.get(bestFaction).members.add(agent.id);
      }
    }
  }

  /**
   * Detect new factions from clusters of unaffiliated agents with strong
   * mutual relationships.
   *
   * Algorithm:
   *   1. Collect all unaffiliated living agents.
   *   2. For each, find nearby unaffiliated agents with mutual valence
   *      above AFFINITY_THRESHOLD.
   *   3. Build connected components via BFS on the affinity graph.
   *   4. Components with >= MIN_FACTION_SIZE members become new factions.
   *
   * This is O(U * K) where U = unaffiliated count and K = avg nearby count,
   * which is bounded by the perception radius.
   *
   * @private
   */
  _detectNewFactions(agents, perceptionSystem, tick) {
    const unaffiliated = agents.filter(
      (a) => a.alive && a.factionId == null
    );
    if (unaffiliated.length < MIN_FACTION_SIZE) return;

    // Build adjacency: agent pairs with mutual affinity
    const agentMap = new Map();
    for (const a of unaffiliated) agentMap.set(a.id, a);

    const adjacency = new Map(); // agentId → Set<agentId>
    for (const agent of unaffiliated) {
      const nearby = perceptionSystem.getNearbyAgents(agent, SOCIAL_RADIUS);
      const rels = agent.relationships ?? {};

      for (const other of nearby) {
        if (!agentMap.has(other.id)) continue; // Only unaffiliated
        const otherRels = other.relationships ?? {};

        // Mutual affinity: both must like each other above threshold
        const aToB = rels[other.id] ?? 0;
        const bToA = otherRels[agent.id] ?? 0;
        if (aToB >= AFFINITY_THRESHOLD && bToA >= AFFINITY_THRESHOLD) {
          if (!adjacency.has(agent.id)) adjacency.set(agent.id, new Set());
          if (!adjacency.has(other.id)) adjacency.set(other.id, new Set());
          adjacency.get(agent.id).add(other.id);
          adjacency.get(other.id).add(agent.id);
        }
      }
    }

    // BFS to find connected components
    const visited = new Set();
    for (const agent of unaffiliated) {
      if (visited.has(agent.id)) continue;
      if (!adjacency.has(agent.id)) continue;

      // BFS from this agent
      const component = [];
      const queue = [agent.id];
      visited.add(agent.id);

      while (queue.length > 0) {
        const current = queue.shift();
        component.push(current);
        const neighbors = adjacency.get(current);
        if (!neighbors) continue;
        for (const nid of neighbors) {
          if (!visited.has(nid)) {
            visited.add(nid);
            queue.push(nid);
          }
        }
      }

      // Form faction if component is large enough
      if (component.length >= MIN_FACTION_SIZE) {
        const faction = this._createFaction(tick);
        for (const aid of component) {
          faction.members.add(aid);
          const a = agentMap.get(aid);
          if (a) a.factionId = faction.id;
        }
      }
    }
  }

  /**
   * Check each faction for internal fragmentation.
   *
   * A faction fragments when the average pairwise valence among its
   * members drops below FRAGMENTATION_THRESHOLD. When this happens,
   * the faction splits into two groups: those with above-average internal
   * valence stay, and those below form a new faction (if large enough)
   * or become unaffiliated.
   *
   * @private
   */
  _checkFragmentation(agents, tick) {
    const agentMap = new Map();
    for (const a of agents) agentMap.set(a.id, a);

    // Collect factions to split (avoid modifying _factions during iteration)
    const toSplit = [];

    for (const faction of this._factions.values()) {
      if (faction.members.size < MIN_FACTION_SIZE * 2) continue; // Too small to split

      // Compute average internal valence
      const members = Array.from(faction.members);
      let totalValence = 0;
      let pairCount = 0;

      for (let i = 0; i < members.length; i++) {
        const a = agentMap.get(members[i]);
        if (!a || !a.alive) continue;
        const rels = a.relationships ?? {};

        for (let j = i + 1; j < members.length; j++) {
          totalValence += rels[members[j]] ?? 0;
          pairCount++;
        }
      }

      const avgValence = pairCount > 0 ? totalValence / pairCount : 0;
      if (avgValence < FRAGMENTATION_THRESHOLD) {
        toSplit.push({ faction, members });
      }
    }

    // Execute splits
    for (const { faction, members } of toSplit) {
      // Partition: compute each member's average valence to other members.
      // Below-median members split off.
      const scores = [];
      for (const mid of members) {
        const a = agentMap.get(mid);
        if (!a || !a.alive) continue;
        const rels = a.relationships ?? {};
        let sum = 0;
        let count = 0;
        for (const oid of members) {
          if (oid === mid) continue;
          sum += rels[oid] ?? 0;
          count++;
        }
        scores.push({ id: mid, avg: count > 0 ? sum / count : 0 });
      }

      scores.sort((a, b) => a.avg - b.avg);
      const midpoint = Math.floor(scores.length / 2);
      const leavers = scores.slice(0, midpoint).map((s) => s.id);

      if (leavers.length >= MIN_FACTION_SIZE) {
        // Form new faction from the disaffected group
        const newFaction = this._createFaction(tick);
        for (const lid of leavers) {
          faction.members.delete(lid);
          newFaction.members.add(lid);
          const a = agentMap.get(lid);
          if (a) a.factionId = newFaction.id;
        }

        this._eventBus.emit('faction_split', {
          tick,
          originalFactionId: faction.id,
          newFactionId: newFaction.id,
          leaverCount: leavers.length,
        });
      } else {
        // Not enough leavers for a new faction — they become unaffiliated
        for (const lid of leavers) {
          faction.members.delete(lid);
          const a = agentMap.get(lid);
          if (a) a.factionId = null;
        }
      }
    }
  }

  /**
   * Update inter-faction alliances based on cross-faction sentiment.
   *
   * Two factions can form an alliance when:
   *   1. Mutual hostility is below ALLIANCE_HOSTILITY_CEILING.
   *   2. Average cross-faction member valence exceeds ALLIANCE_SENTIMENT_FLOOR.
   *
   * Alliances are symmetric and persist until broken by betrayal or
   * rising hostility.
   *
   * @private
   */
  _updateAlliances(agents, perceptionSystem, tick) {
    const agentMap = new Map();
    for (const a of agents) agentMap.set(a.id, a);

    const factionIds = Array.from(this._factions.keys());

    for (let i = 0; i < factionIds.length; i++) {
      for (let j = i + 1; j < factionIds.length; j++) {
        const fA = this._factions.get(factionIds[i]);
        const fB = this._factions.get(factionIds[j]);
        if (!fA || !fB) continue;

        const hostilityAB = fA.hostility.get(fB.id) ?? 0;
        const hostilityBA = fB.hostility.get(fA.id) ?? 0;
        const mutualHostility = Math.max(hostilityAB, hostilityBA);

        const alreadyAllied = fA.alliances.has(fB.id);

        // Break alliance if hostility has risen
        if (alreadyAllied && mutualHostility > ALLIANCE_HOSTILITY_CEILING * 2) {
          fA.alliances.delete(fB.id);
          fB.alliances.delete(fA.id);
          continue;
        }

        // Consider new alliance if hostility is low enough
        if (!alreadyAllied && mutualHostility > ALLIANCE_HOSTILITY_CEILING) {
          continue; // Too hostile
        }

        // Compute cross-faction sentiment from member relationships
        const sentiment = this._crossFactionSentiment(fA, fB, agentMap);
        if (!alreadyAllied && sentiment >= ALLIANCE_SENTIMENT_FLOOR) {
          fA.alliances.add(fB.id);
          fB.alliances.add(fA.id);

          this._eventBus.emit('alliance', {
            tick,
            factionA: fA.id,
            factionB: fB.id,
            sentiment,
          });
        }
      }
    }
  }

  /**
   * Compute average relationship valence between members of two factions.
   * Only samples up to 20 pairs to keep cost bounded for large factions.
   *
   * @private
   * @returns {number} Average cross-faction valence.
   */
  _crossFactionSentiment(factionA, factionB, agentMap) {
    const membersA = Array.from(factionA.members);
    const membersB = Array.from(factionB.members);
    if (membersA.length === 0 || membersB.length === 0) return 0;

    let totalValence = 0;
    let count = 0;
    const maxSamples = 20;

    for (const aidA of membersA) {
      if (count >= maxSamples) break;
      const a = agentMap.get(aidA);
      if (!a || !a.alive) continue;
      const rels = a.relationships ?? {};

      for (const aidB of membersB) {
        if (count >= maxSamples) break;
        totalValence += rels[aidB] ?? 0;
        count++;
      }
    }

    return count > 0 ? totalValence / count : 0;
  }

  /**
   * Decay inter-faction hostility toward zero over time.
   * Factions slowly forget grievances, allowing re-alliance.
   * @private
   */
  _decayHostility() {
    for (const faction of this._factions.values()) {
      for (const [fid, hostility] of faction.hostility) {
        const decayed = Math.max(0, hostility - HOSTILITY_DECAY);
        if (decayed === 0) {
          faction.hostility.delete(fid);
        } else {
          faction.hostility.set(fid, decayed);
        }
      }
    }
  }

  /**
   * Remove factions with zero living members.
   * @private
   */
  _dissolveEmpty() {
    const toDelete = [];
    for (const [id, faction] of this._factions) {
      if (faction.members.size === 0) {
        toDelete.push(id);
      }
    }
    for (const id of toDelete) {
      // Clean up alliance references in other factions
      for (const other of this._factions.values()) {
        other.alliances.delete(id);
        other.hostility.delete(id);
      }
      this._factions.delete(id);
    }
  }

  // -------------------------------------------------------------------------
  // Private: event handlers
  // -------------------------------------------------------------------------

  /**
   * Handle a fight event to update inter-faction hostility and detect betrayal.
   *
   * When an agent from faction A attacks an agent from faction B:
   *   1. Increase A→B and B→A hostility.
   *   2. If A and B are allied, emit a 'betrayal' event and break the alliance.
   *
   * @private
   * @param {Object} evt - Fight event { attackerId, defenderId, damage, tick }.
   */
  _onFight(evt) {
    const { attackerId, defenderId, damage, tick } = evt;

    // Look up faction membership
    let attackerFaction = null;
    let defenderFaction = null;

    for (const faction of this._factions.values()) {
      if (faction.members.has(attackerId)) attackerFaction = faction;
      if (faction.members.has(defenderId)) defenderFaction = faction;
    }

    // No inter-faction dynamics if either is unaffiliated or same faction
    if (!attackerFaction || !defenderFaction) return;
    if (attackerFaction.id === defenderFaction.id) return;

    // Increase mutual hostility
    const currentAB = attackerFaction.hostility.get(defenderFaction.id) ?? 0;
    const currentBA = defenderFaction.hostility.get(attackerFaction.id) ?? 0;
    attackerFaction.hostility.set(
      defenderFaction.id,
      Math.min(1, currentAB + HOSTILITY_ATTACK_DELTA)
    );
    defenderFaction.hostility.set(
      attackerFaction.id,
      Math.min(1, currentBA + HOSTILITY_ATTACK_DELTA * 1.5) // Defender side feels it more
    );

    // Betrayal detection: attack on an allied faction
    if (
      attackerFaction.alliances.has(defenderFaction.id) &&
      (damage ?? 0) >= BETRAYAL_DAMAGE_THRESHOLD
    ) {
      // Break alliance immediately — both directions
      attackerFaction.alliances.delete(defenderFaction.id);
      defenderFaction.alliances.delete(attackerFaction.id);

      this._eventBus.emit('betrayal', {
        tick: tick ?? 0,
        betrayerFactionId: attackerFaction.id,
        victimFactionId: defenderFaction.id,
        attackerId,
        defenderId,
      });
    }
  }

  // -------------------------------------------------------------------------
  // Private: factory helpers
  // -------------------------------------------------------------------------

  /**
   * Create and register a new faction with a generated name.
   * @private
   * @param {number} tick - Current tick for event tagging.
   * @returns {Object} The new faction record.
   */
  _createFaction(tick) {
    const id = this._nextId++;
    // Generate a simple name. In a richer system this could use
    // region names, leader names, or cultural markers.
    const name = `Faction-${id}`;
    const faction = createFaction(id, name);
    this._factions.set(id, faction);

    this._eventBus.emit('faction_formed', {
      tick,
      factionId: id,
      name,
    });

    return faction;
  }
}
