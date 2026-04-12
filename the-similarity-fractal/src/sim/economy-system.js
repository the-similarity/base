/**
 * economy-system.js — Economic layer for the 3D society simulation.
 *
 * Responsibilities:
 *   1. Track per-agent wealth (sum of inventory item values).
 *   2. Resolve trades between co-located agents using regional supply/demand.
 *   3. Compute inequality (Gini coefficient) across the population.
 *   4. Emit 'scarcity_warning' when a region's food supply drops below threshold.
 *
 * Design notes:
 *   - Headless-safe: no Three.js dependency, pure ES module.
 *   - Supply/demand pricing: item price = BASE_PRICE * (DEMAND / max(SUPPLY, 1)).
 *     This creates natural trade incentives — agents in food-scarce regions pay
 *     more, which attracts traders from food-rich regions over time.
 *   - Gini is O(n log n) via the sorted-wealth formula, not the O(n^2) pairwise
 *     version, so it stays cheap even at large agent counts.
 *   - The system does NOT own agent state. It reads/writes inventory and wealth
 *     fields but the agent-state module is authoritative for schema.
 *
 * Lifecycle:
 *   constructor(eventBus) → tick(agents, resourceField, regionMap) each sim step.
 *   The system is stateless between ticks except for cached regional wealth
 *   snapshots (rebuilt every tick).
 *
 * @module economy-system
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Base price per unit of each tradeable good. */
const BASE_PRICES = {
  food: 1.0,
  material: 1.5,
  medicine: 3.0,
};

/**
 * When regional food stock falls below this fraction of the region's
 * agent count, a scarcity_warning event fires. The threshold is per-capita
 * so it scales naturally with population density.
 */
const FOOD_SCARCITY_PER_CAPITA = 2.0;

/**
 * Minimum trade surplus an agent must hold before offering goods.
 * Prevents agents from trading away their last food unit.
 */
const MIN_SURPLUS_TO_TRADE = 2;

/**
 * Maximum fraction of surplus an agent will offer in a single trade.
 * Keeps trades incremental so the market doesn't lurch.
 */
const MAX_TRADE_FRACTION = 0.5;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Compute agent wealth as the dot product of inventory quantities and
 * current regional prices. Falls back to base prices when no regional
 * price map is available.
 *
 * @param {Object} inventory - Map of item name → quantity.
 * @param {Object} [prices] - Map of item name → current price.
 * @returns {number} Total wealth value.
 */
function computeWealth(inventory, prices) {
  let total = 0;
  for (const [item, qty] of Object.entries(inventory)) {
    // Use regional price if available, else fall back to base price, else 1.
    const price = (prices && prices[item]) ?? BASE_PRICES[item] ?? 1;
    total += qty * price;
  }
  return total;
}

/**
 * Build a per-region supply summary by summing every agent's inventory
 * within that region. Also counts population per region.
 *
 * @param {Array} agents - Array of agent state objects.
 * @returns {Map<string, {supply: Object, demand: Object, population: number}>}
 */
function buildRegionalEconomy(agents) {
  const regions = new Map();

  for (const agent of agents) {
    if (!agent.alive) continue;
    const rid = agent.regionId ?? 'unknown';

    if (!regions.has(rid)) {
      regions.set(rid, { supply: {}, demand: {}, population: 0 });
    }
    const entry = regions.get(rid);
    entry.population += 1;

    // Accumulate supply from inventory
    const inv = agent.inventory ?? {};
    for (const [item, qty] of Object.entries(inv)) {
      entry.supply[item] = (entry.supply[item] ?? 0) + qty;
    }

    // Demand is approximated by need: agents with low food have high food demand.
    // This is a heuristic — hunger > 0.5 means the agent wants food.
    const needs = agent.needs ?? {};
    if ((needs.hunger ?? 0) > 0.5) {
      entry.demand.food = (entry.demand.food ?? 0) + 1;
    }
    if ((needs.energy ?? 0) < 0.3) {
      entry.demand.material = (entry.demand.material ?? 0) + 1;
    }
  }

  return regions;
}

/**
 * Derive prices from supply/demand within a region.
 * price = BASE_PRICE * (demand + 1) / max(supply, 1)
 * The +1 on demand ensures prices don't collapse to zero.
 *
 * @param {Object} supply - Item → total quantity in region.
 * @param {Object} demand - Item → total demand units in region.
 * @returns {Object} Item → price.
 */
function derivePrices(supply, demand) {
  const prices = {};
  // Cover all items from both maps
  const items = new Set([
    ...Object.keys(supply),
    ...Object.keys(demand),
    ...Object.keys(BASE_PRICES),
  ]);
  for (const item of items) {
    const base = BASE_PRICES[item] ?? 1;
    const s = Math.max(supply[item] ?? 0, 1);
    const d = (demand[item] ?? 0) + 1;
    prices[item] = base * (d / s);
  }
  return prices;
}

// ---------------------------------------------------------------------------
// EconomySystem
// ---------------------------------------------------------------------------

/**
 * Core economic simulation system.
 *
 * Invariants:
 *   - Never creates or destroys agents; only mutates inventory fields.
 *   - All emitted events include { tick, regionId } for telemetry correlation.
 *   - Regional wealth cache is rebuilt every tick (no stale reads).
 */
export class EconomySystem {
  /**
   * @param {Object} eventBus - Event emitter with emit(eventName, payload).
   */
  constructor(eventBus) {
    /** @type {Object} Event bus for broadcasting economic events. */
    this._eventBus = eventBus;

    /**
     * Per-region wealth snapshot, rebuilt each tick.
     * @type {Map<string, number>}
     */
    this._regionalWealth = new Map();
  }

  /**
   * Run one economic tick: recompute prices, resolve trades, check scarcity.
   *
   * @param {Array} agents - Mutable array of agent state objects.
   * @param {Object} resourceField - Grid-based resource lookup (used for
   *   regional food totals when agents alone don't tell the full story).
   * @param {Object} regionMap - Region metadata keyed by regionId.
   * @param {number} [tick=0] - Current simulation tick for event tagging.
   */
  tick(agents, resourceField, regionMap, tick = 0) {
    // Step 1: Build regional supply/demand picture
    const regionalEcon = buildRegionalEconomy(agents);

    // Step 2: Derive prices per region
    const regionalPrices = new Map();
    for (const [rid, econ] of regionalEcon) {
      regionalPrices.set(rid, derivePrices(econ.supply, econ.demand));
    }

    // Step 3: Resolve trades within each region
    this._resolveTrades(agents, regionalEcon, regionalPrices, tick);

    // Step 4: Update agent wealth values using new prices
    for (const agent of agents) {
      if (!agent.alive) continue;
      const rid = agent.regionId ?? 'unknown';
      const prices = regionalPrices.get(rid) ?? BASE_PRICES;
      agent.wealth = computeWealth(agent.inventory ?? {}, prices);
    }

    // Step 5: Rebuild regional wealth cache
    this._rebuildRegionalWealth(agents);

    // Step 6: Check for scarcity warnings
    this._checkScarcity(agents, regionalEcon, resourceField, regionMap, tick);
  }

  /**
   * Resolve trades between agents in the same region.
   *
   * Trade logic:
   *   - For each region, find sellers (agents with surplus food) and
   *     buyers (agents with high hunger and some material/medicine to offer).
   *   - Match sellers to buyers greedily (no auction — keep it O(n)).
   *   - Transfer items, emit 'trade' events.
   *
   * @private
   */
  _resolveTrades(agents, regionalEcon, regionalPrices, tick) {
    // Group living agents by region for trade matching
    const byRegion = new Map();
    for (const agent of agents) {
      if (!agent.alive) continue;
      const rid = agent.regionId ?? 'unknown';
      if (!byRegion.has(rid)) byRegion.set(rid, []);
      byRegion.get(rid).push(agent);
    }

    for (const [rid, regionAgents] of byRegion) {
      const prices = regionalPrices.get(rid) ?? BASE_PRICES;

      // Identify sellers: agents with food surplus above threshold
      const sellers = [];
      const buyers = [];

      for (const agent of regionAgents) {
        const inv = agent.inventory ?? {};
        const foodQty = inv.food ?? 0;
        const needs = agent.needs ?? {};

        if (foodQty > MIN_SURPLUS_TO_TRADE) {
          sellers.push(agent);
        } else if ((needs.hunger ?? 0) > 0.5 && this._hasTradeableGoods(inv)) {
          buyers.push(agent);
        }
      }

      // Greedy matching: pair each buyer with the first willing seller
      for (const buyer of buyers) {
        if (sellers.length === 0) break;

        const seller = sellers[0];
        const sellerInv = seller.inventory ?? {};
        const sellerFood = sellerInv.food ?? 0;
        const surplus = sellerFood - MIN_SURPLUS_TO_TRADE;
        // Trade amount: fraction of surplus, at least 1
        const tradeAmount = Math.max(1, Math.floor(surplus * MAX_TRADE_FRACTION));

        // Buyer pays with whatever non-food good they have
        const buyerInv = buyer.inventory ?? {};
        const paymentItem = this._findPaymentItem(buyerInv);
        if (!paymentItem) continue;

        const foodPrice = prices.food ?? BASE_PRICES.food;
        const payPrice = prices[paymentItem] ?? BASE_PRICES[paymentItem] ?? 1;

        // Payment quantity: value-equivalent exchange
        // buyer pays ceil(tradeAmount * foodPrice / payPrice) units
        const paymentQty = Math.min(
          buyerInv[paymentItem] ?? 0,
          Math.ceil((tradeAmount * foodPrice) / payPrice)
        );
        if (paymentQty <= 0) continue;

        // Execute the transfer
        sellerInv.food = (sellerInv.food ?? 0) - tradeAmount;
        buyerInv.food = (buyerInv.food ?? 0) + tradeAmount;
        buyerInv[paymentItem] = (buyerInv[paymentItem] ?? 0) - paymentQty;
        sellerInv[paymentItem] = (sellerInv[paymentItem] ?? 0) + paymentQty;

        // Ensure inventory refs are written back (defensive)
        seller.inventory = sellerInv;
        buyer.inventory = buyerInv;

        this._eventBus.emit('trade', {
          tick,
          regionId: rid,
          sellerId: seller.id,
          buyerId: buyer.id,
          soldItem: 'food',
          soldQty: tradeAmount,
          paidItem: paymentItem,
          paidQty: paymentQty,
        });

        // If seller is tapped out, remove from pool
        if ((sellerInv.food ?? 0) <= MIN_SURPLUS_TO_TRADE) {
          sellers.shift();
        }
      }
    }
  }

  /**
   * Check whether an agent has any non-food tradeable goods.
   * @private
   * @param {Object} inventory
   * @returns {boolean}
   */
  _hasTradeableGoods(inventory) {
    for (const [item, qty] of Object.entries(inventory)) {
      if (item !== 'food' && qty > 0) return true;
    }
    return false;
  }

  /**
   * Find the best non-food item an agent can use for payment.
   * Prefers material over medicine (medicine is more valuable, save it).
   * @private
   * @param {Object} inventory
   * @returns {string|null}
   */
  _findPaymentItem(inventory) {
    if ((inventory.material ?? 0) > 0) return 'material';
    if ((inventory.medicine ?? 0) > 0) return 'medicine';
    // Fall back to any non-food item
    for (const [item, qty] of Object.entries(inventory)) {
      if (item !== 'food' && qty > 0) return item;
    }
    return null;
  }

  /**
   * Rebuild the regional wealth cache from current agent state.
   * @private
   */
  _rebuildRegionalWealth(agents) {
    this._regionalWealth.clear();
    for (const agent of agents) {
      if (!agent.alive) continue;
      const rid = agent.regionId ?? 'unknown';
      this._regionalWealth.set(
        rid,
        (this._regionalWealth.get(rid) ?? 0) + (agent.wealth ?? 0)
      );
    }
  }

  /**
   * Emit scarcity_warning when a region's food falls below per-capita threshold.
   *
   * Checks both agent inventories and the resource field to get the full
   * picture — agents may have gathered food that hasn't regenerated yet.
   * @private
   */
  _checkScarcity(agents, regionalEcon, resourceField, regionMap, tick) {
    for (const [rid, econ] of regionalEcon) {
      if (econ.population === 0) continue;

      // Total food = agent-held food + field food (if resource field provides it)
      let totalFood = econ.supply.food ?? 0;

      // If the resource field exposes a per-region food accessor, add it
      if (resourceField && typeof resourceField.getRegionalFood === 'function') {
        totalFood += resourceField.getRegionalFood(rid);
      }

      const threshold = econ.population * FOOD_SCARCITY_PER_CAPITA;
      if (totalFood < threshold) {
        this._eventBus.emit('scarcity_warning', {
          tick,
          regionId: rid,
          totalFood,
          population: econ.population,
          threshold,
          severity: 1 - totalFood / threshold, // 0 = at threshold, 1 = zero food
        });
      }
    }
  }

  // -------------------------------------------------------------------------
  // Public query methods
  // -------------------------------------------------------------------------

  /**
   * Compute the Gini coefficient of wealth inequality across all living agents.
   *
   * Uses the sorted-wealth formula:
   *   G = (2 * sum_i(i * w_i)) / (n * sum(w)) - (n + 1) / n
   * where w is sorted ascending and i is 1-indexed rank.
   *
   * Returns 0 for perfectly equal, approaches 1 for maximum inequality.
   * Returns 0 when fewer than 2 agents are alive (degenerate case).
   *
   * Complexity: O(n log n) from the sort.
   *
   * @param {Array} agents - Array of agent state objects.
   * @returns {number} Gini coefficient in [0, 1).
   */
  getGini(agents) {
    const wealths = agents
      .filter((a) => a.alive)
      .map((a) => a.wealth ?? 0)
      .sort((a, b) => a - b);

    const n = wealths.length;
    if (n < 2) return 0;

    const totalWealth = wealths.reduce((s, w) => s + w, 0);
    if (totalWealth === 0) return 0; // Everyone is equally broke

    // Weighted rank sum: sum of (1-indexed rank * wealth)
    let rankWeightedSum = 0;
    for (let i = 0; i < n; i++) {
      rankWeightedSum += (i + 1) * wealths[i];
    }

    return (2 * rankWeightedSum) / (n * totalWealth) - (n + 1) / n;
  }

  /**
   * Get cached total wealth for a region.
   *
   * @param {string} regionId
   * @returns {number} Total wealth in the region, or 0 if unknown.
   */
  getRegionalWealth(regionId) {
    return this._regionalWealth.get(regionId) ?? 0;
  }
}
