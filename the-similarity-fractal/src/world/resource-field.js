/**
 * Resource field manager for the 3D society simulation.
 *
 * Owns two 2D grids — food and material — whose values depend on terrain biome.
 * Resources are consumed by agents (deplete) and slowly regenerate each tick
 * at biome-dependent rates. This creates spatial scarcity that drives agent
 * movement, trade, and conflict.
 *
 * Lifecycle:
 *   1. Construct with terrainMaps from sampleTerrain() and a seeded PRNG.
 *   2. Each simulation tick: call regenerate(dt) to restore depleted cells.
 *   3. When an agent gathers: call deplete(gx, gz, type, amount).
 *   4. Query with getFoodAt / getMaterialAt for pathfinding, AI decisions, etc.
 *   5. getSnapshot() for serialization / telemetry.
 *
 * Immutability contract:
 *   - terrainMaps is read-only after construction; we never mutate it.
 *   - The two resource grids are the only mutable state.
 *   - deplete and regenerate are the only mutation paths.
 *
 * Grid layout: flat arrays indexed as [gz * size + gx], matching terrainMaps
 * convention. Values are clamped to [0, capacity] where capacity is the
 * biome-specific maximum.
 */

// ─── Biome constants (mirrored from terrain-renderer.js) ───────────────────
// Duplicated intentionally so this module stays headless-safe with zero
// imports from the rendering layer.
const BIOME_WATER  = 0;
const BIOME_SAND   = 1;
const BIOME_GRASS  = 2;
const BIOME_FOREST = 3;
const BIOME_ROCK   = 4;
const BIOME_SNOW   = 5;

// ─── Per-biome resource configuration ──────────────────────────────────────
// Each entry: { food, material, foodRegen, materialRegen }
//   food / material   — initial (and max) capacity for the cell
//   foodRegen / materialRegen — units restored per simulation second
//
// Design rationale:
//   - Forest: abundant food (game, berries), moderate wood/material.
//   - Grass: moderate food (grazing), low material.
//   - Sand: scarce food, moderate material (sandstone).
//   - Rock: no food, high material (ore, stone).
//   - Water: zero for both — agents cannot gather from water tiles.
//   - Snow: very scarce food (lichens), low material (ice).
const BIOME_RESOURCE_CONFIG = {
  [BIOME_WATER]:  { food: 0,    material: 0,    foodRegen: 0,      materialRegen: 0     },
  [BIOME_SAND]:   { food: 2,    material: 5,    foodRegen: 0.02,   materialRegen: 0.04  },
  [BIOME_GRASS]:  { food: 6,    material: 2,    foodRegen: 0.08,   materialRegen: 0.02  },
  [BIOME_FOREST]: { food: 10,   material: 6,    foodRegen: 0.12,   materialRegen: 0.06  },
  [BIOME_ROCK]:   { food: 0,    material: 10,   foodRegen: 0,      materialRegen: 0.08  },
  [BIOME_SNOW]:   { food: 1,    material: 2,    foodRegen: 0.01,   materialRegen: 0.02  },
};

// Fallback for unknown biome IDs — treat as barren grass.
const DEFAULT_CONFIG = { food: 1, material: 1, foodRegen: 0.01, materialRegen: 0.01 };

/**
 * Look up the resource config for a biome, falling back to DEFAULT_CONFIG
 * for any unexpected biome ID.
 */
function configForBiome(biomeId) {
  return BIOME_RESOURCE_CONFIG[biomeId] ?? DEFAULT_CONFIG;
}

export class ResourceField {
  /**
   * @param {Object} terrainMaps - Output of sampleTerrain():
   *   { heightMap, slopeMap, waterMap, biomeMap, size, worldScale }
   *   Each map is a flat array of length size*size, indexed [gz * size + gx].
   * @param {Object} rng - PRNG with { next(), nextSigned() }. Used to add
   *   slight variance to initial resource amounts so the grid doesn't look
   *   perfectly uniform.
   */
  constructor(terrainMaps, rng) {
    const { biomeMap, size } = terrainMaps;
    const totalCells = size * size;

    this.size = size;

    // ── Capacity grids ─────────────────────────────────────────────────
    // Store per-cell max so regeneration knows when to stop.
    // These never change after construction.
    this._foodCap      = new Float32Array(totalCells);
    this._materialCap  = new Float32Array(totalCells);

    // ── Current-value grids ────────────────────────────────────────────
    // Start near capacity with slight random jitter (0.8–1.0x) so the
    // world feels slightly lived-in from tick 0.
    this._food     = new Float32Array(totalCells);
    this._material = new Float32Array(totalCells);

    // ── Regen-rate grids ───────────────────────────────────────────────
    // Pre-baked per cell so regenerate() is a tight loop without lookups.
    this._foodRegen     = new Float32Array(totalCells);
    this._materialRegen = new Float32Array(totalCells);

    for (let i = 0; i < totalCells; i++) {
      const biome = biomeMap[i] ?? BIOME_GRASS;
      const cfg   = configForBiome(biome);

      this._foodCap[i]      = cfg.food;
      this._materialCap[i]  = cfg.material;
      this._foodRegen[i]    = cfg.foodRegen;
      this._materialRegen[i] = cfg.materialRegen;

      // Slight randomness: multiply by [0.8, 1.0) so initial state isn't
      // a boring uniform field. The 0.8 floor prevents cells from spawning
      // nearly empty.
      const jitterFood = 0.8 + rng.next() * 0.2;
      const jitterMat  = 0.8 + rng.next() * 0.2;
      this._food[i]     = cfg.food * jitterFood;
      this._material[i] = cfg.material * jitterMat;
    }
  }

  // ─── Bounds check ──────────────────────────────────────────────────────
  /**
   * Returns true if (gx, gz) is within the grid. All public accessors
   * silently return 0 for out-of-bounds to avoid crashes during agent
   * exploration near edges.
   */
  _inBounds(gx, gz) {
    return gx >= 0 && gx < this.size && gz >= 0 && gz < this.size;
  }

  // ─── Queries ───────────────────────────────────────────────────────────

  /**
   * Current food value at grid coordinates (gx, gz).
   * Returns 0 for out-of-bounds cells.
   */
  getFoodAt(gx, gz) {
    if (!this._inBounds(gx, gz)) return 0;
    return this._food[gz * this.size + gx];
  }

  /**
   * Current material value at grid coordinates (gx, gz).
   * Returns 0 for out-of-bounds cells.
   */
  getMaterialAt(gx, gz) {
    if (!this._inBounds(gx, gz)) return 0;
    return this._material[gz * this.size + gx];
  }

  // ─── Mutations ─────────────────────────────────────────────────────────

  /**
   * Remove resources from a cell. Called when an agent gathers.
   *
   * @param {number} gx - Grid x coordinate
   * @param {number} gz - Grid z coordinate
   * @param {'food'|'material'} type - Which resource to deplete
   * @param {number} amount - How much to remove (positive)
   * @returns {number} The actual amount removed (may be less if cell is
   *   nearly empty). Callers use this to credit the agent's inventory.
   */
  deplete(gx, gz, type, amount) {
    if (!this._inBounds(gx, gz) || amount <= 0) return 0;

    const idx = gz * this.size + gx;
    const grid = type === 'food' ? this._food : this._material;

    // Only remove what's actually available — prevents negative resources.
    const removed = Math.min(grid[idx], amount);
    grid[idx] -= removed;
    return removed;
  }

  /**
   * Advance resource regeneration by dt simulation seconds.
   *
   * Each cell grows toward its capacity at its biome-dependent rate.
   * The formula is simple linear growth clamped to capacity:
   *   value = min(value + rate * dt, capacity)
   *
   * Why linear instead of logistic:
   *   - Cheaper per cell (matters at large grid sizes).
   *   - Logistic overshoot near capacity is negligible for gameplay.
   *   - Easy to reason about for balancing.
   *
   * @param {number} dt - Elapsed simulation seconds since last call.
   */
  regenerate(dt) {
    const n = this.size * this.size;

    for (let i = 0; i < n; i++) {
      // Food regen: linear growth clamped to capacity.
      if (this._food[i] < this._foodCap[i]) {
        this._food[i] = Math.min(
          this._food[i] + this._foodRegen[i] * dt,
          this._foodCap[i]
        );
      }

      // Material regen: same formula, different rate.
      if (this._material[i] < this._materialCap[i]) {
        this._material[i] = Math.min(
          this._material[i] + this._materialRegen[i] * dt,
          this._materialCap[i]
        );
      }
    }
  }

  /**
   * Produce a plain-object snapshot of current resource state for
   * serialization, telemetry, or renderer overlay.
   *
   * @returns {{ size: number, food: Float32Array, material: Float32Array }}
   */
  getSnapshot() {
    return {
      size: this.size,
      // Return copies so callers cannot accidentally mutate our grids.
      food: new Float32Array(this._food),
      material: new Float32Array(this._material),
    };
  }
}
