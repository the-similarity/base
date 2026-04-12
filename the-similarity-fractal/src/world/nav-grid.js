/**
 * Navigation Grid — walkability layer and A* pathfinding for simulation agents.
 *
 * Purpose:
 * Agents in the 3D society simulation need to move across the terrain. This module
 * builds a movement-cost grid from the terrain sampler's output maps and provides
 * coordinate conversion, neighbor queries, and a full A* pathfinder.
 *
 * Design decisions:
 * - The grid is a flat typed array, not a 2D object graph. This keeps memory
 *   compact and iteration cache-friendly. Index = z * size + x (row-major).
 * - Movement costs are precomputed once at construction. Agents query costs at
 *   runtime without re-deriving slope/biome penalties.
 * - The A* implementation uses a binary min-heap for the open set. For grid sizes
 *   up to 256x256 (65K cells) this is fast enough without more exotic structures.
 *
 * Lifecycle:
 * 1. Construct with terrain maps from `sampleTerrain()`.
 * 2. Costs are computed once and frozen. If terrain changes, construct a new NavGrid.
 * 3. All query methods are pure reads — no mutation after construction.
 *
 * Coordinate systems:
 * - Grid coords (gx, gz): integer cell indices in [0, size).
 * - World coords (wx, wz): floating-point positions in [-worldScale/2, +worldScale/2].
 *
 * No Three.js dependency. Headless-safe.
 *
 * @module nav-grid
 */

import {
  BIOME_WATER, BIOME_SAND, BIOME_GRASS, BIOME_FOREST, BIOME_ROCK, BIOME_SNOW,
} from './terrain-sampler.js';

// ─── Movement cost constants ──────────────────────────────────────────────────
// These are tuning knobs for how terrain features affect agent movement speed.
// Higher cost = slower movement. IMPASSABLE means the cell cannot be entered.

const IMPASSABLE = Infinity;

// Base cost per biome. Water is impassable; snow is very expensive.
// These values are unitless ratios; only relative magnitudes matter.
// Keys reference the canonical biome IDs from terrain-sampler.js.
const BIOME_COST = {
  [BIOME_WATER]:  IMPASSABLE,  // agents cannot swim (yet)
  [BIOME_SAND]:   1.3,         // slightly harder than grass
  [BIOME_GRASS]:  1.0,         // baseline
  [BIOME_FOREST]: 1.5,         // undergrowth slows movement
  [BIOME_ROCK]:   2.5,         // rough terrain, much slower
  [BIOME_SNOW]:   3.0,         // deep snow is very slow
};

// Slope thresholds (radians) for cost multipliers and impassability.
// A slope of ~0.78 rad is ~45 degrees — very steep for walking.
const SLOPE_COST_START    = 0.15;   // below this, slope adds no cost (~8.5 degrees)
const SLOPE_IMPASSABLE    = 1.2;    // above this, cell is a cliff (~69 degrees)
const SLOPE_COST_FACTOR   = 3.0;    // multiplier for slope penalty in the passable range

// Cardinal direction offsets, shared across all query methods to avoid
// per-call allocation on hot paths (neighbors, A* expansion).
const CARDINAL_DX = [1, -1, 0, 0];
const CARDINAL_DZ = [0, 0, 1, -1];

/**
 * Navigation grid with precomputed movement costs and A* pathfinding.
 */
export class NavGrid {
  /**
   * Build the navigation grid from terrain sampler output.
   *
   * @param {{
   *   heightMap: Float32Array,
   *   slopeMap: Float32Array,
   *   waterMap: Uint8Array,
   *   biomeMap: Uint8Array,
   *   size: number,
   *   worldScale: number
   * }} terrainMaps - Output of `sampleTerrain()`.
   */
  constructor(terrainMaps) {
    /** @type {number} Grid dimension (cells per side). */
    this.size = terrainMaps.size;

    /** @type {number} World-space extent of the terrain. */
    this.worldScale = terrainMaps.worldScale;

    /** @type {Float32Array} Height at each grid cell (world Y). */
    this._heightMap = terrainMaps.heightMap;

    /** @type {Float32Array} Slope in radians at each cell. */
    this._slopeMap = terrainMaps.slopeMap;

    /** @type {Uint8Array} Water flag per cell. */
    this._waterMap = terrainMaps.waterMap;

    /** @type {Uint8Array} Biome ID per cell. */
    this._biomeMap = terrainMaps.biomeMap;

    /**
     * Precomputed movement cost per cell.
     * IMPASSABLE (Infinity) for water and cliffs.
     * Otherwise, biome base cost * slope multiplier.
     *
     * @type {Float32Array}
     */
    this._costMap = new Float32Array(this.size * this.size);

    this._buildCostMap();

    /**
     * World-space distance between adjacent grid cells.
     * Used for coordinate conversion and A* distance heuristic.
     * @type {number}
     */
    this._cellSize = this.worldScale / this.size;
  }

  /**
   * Compute movement cost for every cell.
   *
   * Cost formula:
   *   cost = biomeCost * slopeMultiplier
   *
   * Where slopeMultiplier = 1 + SLOPE_COST_FACTOR * normalizedSlope
   * and normalizedSlope is how far the slope is between SLOPE_COST_START
   * and SLOPE_IMPASSABLE, mapped to [0, 1].
   *
   * @private
   */
  _buildCostMap() {
    const n = this.size * this.size;
    const slopeRange = SLOPE_IMPASSABLE - SLOPE_COST_START;

    for (let i = 0; i < n; i++) {
      const slope = this._slopeMap[i];
      const biome = this._biomeMap[i];
      const water = this._waterMap[i];

      // Water cells are always impassable, regardless of other factors.
      if (water === 1) {
        this._costMap[i] = IMPASSABLE;
        continue;
      }

      // Cliff cells (extreme slope) are impassable.
      if (slope >= SLOPE_IMPASSABLE) {
        this._costMap[i] = IMPASSABLE;
        continue;
      }

      // Base cost from biome type.
      const baseCost = BIOME_COST[biome] ?? 1.0;
      if (baseCost === IMPASSABLE) {
        this._costMap[i] = IMPASSABLE;
        continue;
      }

      // Slope penalty: ramps up linearly from 1x to (1 + SLOPE_COST_FACTOR)x
      // across the passable slope range.
      let slopeMultiplier = 1.0;
      if (slope > SLOPE_COST_START) {
        const normalizedSlope = (slope - SLOPE_COST_START) / slopeRange;
        slopeMultiplier = 1.0 + SLOPE_COST_FACTOR * normalizedSlope;
      }

      this._costMap[i] = baseCost * slopeMultiplier;
    }
  }

  // ─── Public query methods ─────────────────────────────────────────────────

  /**
   * Get the movement cost for entering a cell.
   *
   * Returns Infinity for impassable cells (water, cliffs, out-of-bounds).
   *
   * @param {number} gx - Grid X coordinate.
   * @param {number} gz - Grid Z coordinate.
   * @returns {number} Movement cost (>= 1.0 for passable, Infinity for impassable).
   */
  getMoveCost(gx, gz) {
    if (!this._inBounds(gx, gz)) return IMPASSABLE;
    return this._costMap[gz * this.size + gx];
  }

  /**
   * Check if a cell is passable (not water, not cliff, in bounds).
   *
   * @param {number} gx
   * @param {number} gz
   * @returns {boolean}
   */
  isPassable(gx, gz) {
    return this.getMoveCost(gx, gz) < IMPASSABLE;
  }

  /**
   * Get the terrain height at a grid cell in world Y units.
   *
   * @param {number} gx
   * @param {number} gz
   * @returns {number} Height value, or 0 for out-of-bounds.
   */
  getHeight(gx, gz) {
    if (!this._inBounds(gx, gz)) return 0;
    return this._heightMap[gz * this.size + gx];
  }

  /**
   * Get passable cardinal neighbors of a cell.
   *
   * Returns up to 4 neighbors (no diagonals). Each entry is { gx, gz, cost }
   * where cost is the movement cost to enter that neighbor cell.
   *
   * Why no diagonals:
   * - Diagonal movement on a grid requires sqrt(2) distance correction.
   * - For agent simulation, cardinal-only movement produces more natural-looking
   *   paths when combined with smooth world-space interpolation.
   * - A* with 4 neighbors is faster than 8 neighbors.
   *
   * @param {number} gx
   * @param {number} gz
   * @returns {Array<{gx: number, gz: number, cost: number}>}
   */
  neighbors(gx, gz) {
    const result = [];

    for (let d = 0; d < 4; d++) {
      const nx = gx + CARDINAL_DX[d];
      const nz = gz + CARDINAL_DZ[d];
      if (!this._inBounds(nx, nz)) continue;

      const cost = this._costMap[nz * this.size + nx];
      if (cost < IMPASSABLE) {
        result.push({ gx: nx, gz: nz, cost });
      }
    }

    return result;
  }

  // ─── Coordinate conversion ────────────────────────────────────────────────

  /**
   * Convert world-space XZ to grid coordinates.
   *
   * World origin is at the center of the terrain. Grid origin is top-left (0,0).
   *
   * @param {number} wx - World X position.
   * @param {number} wz - World Z position.
   * @returns {{gx: number, gz: number}} Grid coordinates (clamped to bounds).
   */
  worldToGrid(wx, wz) {
    const half = this.worldScale / 2;

    // Map [-half, +half] to [0, size-1] and clamp.
    let gx = Math.round(((wx + half) / this.worldScale) * (this.size - 1));
    let gz = Math.round(((wz + half) / this.worldScale) * (this.size - 1));

    gx = Math.max(0, Math.min(this.size - 1, gx));
    gz = Math.max(0, Math.min(this.size - 1, gz));

    return { gx, gz };
  }

  /**
   * Convert grid coordinates to world-space XZ position (cell center).
   *
   * @param {number} gx
   * @param {number} gz
   * @returns {{wx: number, wz: number}} World position.
   */
  gridToWorld(gx, gz) {
    const half = this.worldScale / 2;

    const wx = (gx / (this.size - 1)) * this.worldScale - half;
    const wz = (gz / (this.size - 1)) * this.worldScale - half;

    return { wx, wz };
  }

  // ─── A* Pathfinder ────────────────────────────────────────────────────────

  /**
   * Find the shortest path between two grid cells using A*.
   *
   * Returns an array of {gx, gz} waypoints from start to end (inclusive),
   * or null if no path exists.
   *
   * The heuristic is Manhattan distance scaled by the minimum possible
   * movement cost (1.0 for grass). This is admissible because no cell can
   * have cost < 1.0, so the heuristic never overestimates.
   *
   * Performance:
   * - Binary min-heap keeps open-set operations at O(log n).
   * - For a 128x128 grid (16K cells) worst case is ~50ms.
   * - For a 256x256 grid (65K cells) worst case is ~200ms.
   * - Paths across the full grid are rare in practice; most agent moves
   *   are short-range and resolve in < 1ms.
   *
   * @param {number} startGx - Start cell X.
   * @param {number} startGz - Start cell Z.
   * @param {number} endGx - End cell X.
   * @param {number} endGz - End cell Z.
   * @returns {Array<{gx: number, gz: number}>|null} Path waypoints or null.
   */
  findPath(startGx, startGz, endGx, endGz) {
    // Early exit: start or end is impassable.
    if (!this.isPassable(startGx, startGz) || !this.isPassable(endGx, endGz)) {
      return null;
    }

    // Early exit: already at destination.
    if (startGx === endGx && startGz === endGz) {
      return [{ gx: startGx, gz: startGz }];
    }

    const size = this.size;

    // Flat index helpers for the open/closed tracking arrays.
    const toIdx = (x, z) => z * size + x;
    const startIdx = toIdx(startGx, startGz);
    const endIdx = toIdx(endGx, endGz);

    // gScore[i] = cost of cheapest known path from start to cell i.
    // fScore[i] = gScore[i] + heuristic(i, end).
    // Both default to Infinity (unvisited).
    const gScore = new Float32Array(size * size).fill(Infinity);
    const fScore = new Float32Array(size * size).fill(Infinity);

    // cameFrom[i] = flat index of the cell we arrived from on the cheapest path.
    // -1 means "no predecessor" (start cell or unvisited).
    const cameFrom = new Int32Array(size * size).fill(-1);

    // Closed set: tracks cells whose optimal path has been finalized.
    const closed = new Uint8Array(size * size);

    // Manhattan distance heuristic, admissible with min cost = 1.0.
    const heuristic = (x, z) => Math.abs(x - endGx) + Math.abs(z - endGz);

    gScore[startIdx] = 0;
    fScore[startIdx] = heuristic(startGx, startGz);

    // Binary min-heap storing { idx, f } sorted by f-score.
    const heap = new MinHeap();
    heap.push(startIdx, fScore[startIdx]);

    while (heap.size > 0) {
      const currentIdx = heap.pop();

      // Skip if already finalized (heap may contain stale entries).
      if (closed[currentIdx]) continue;
      closed[currentIdx] = 1;

      // Reached the goal — reconstruct the path.
      if (currentIdx === endIdx) {
        return this._reconstructPath(cameFrom, endIdx);
      }

      const cx = currentIdx % size;
      const cz = (currentIdx - cx) / size;
      const currentG = gScore[currentIdx];

      // Expand cardinal neighbors using module-level offset constants.
      for (let d = 0; d < 4; d++) {
        const nx = cx + CARDINAL_DX[d];
        const nz = cz + CARDINAL_DZ[d];

        if (nx < 0 || nx >= size || nz < 0 || nz >= size) continue;

        const nIdx = toIdx(nx, nz);
        if (closed[nIdx]) continue;

        const moveCost = this._costMap[nIdx];
        if (moveCost >= IMPASSABLE) continue; // impassable

        const tentativeG = currentG + moveCost;

        if (tentativeG < gScore[nIdx]) {
          // This path to the neighbor is better than any previous one.
          gScore[nIdx] = tentativeG;
          fScore[nIdx] = tentativeG + heuristic(nx, nz);
          cameFrom[nIdx] = currentIdx;
          heap.push(nIdx, fScore[nIdx]);
        }
      }
    }

    // Open set exhausted without reaching the goal — no path exists.
    // This happens when start and end are in disconnected walkable regions.
    return null;
  }

  // ─── Private helpers ──────────────────────────────────────────────────────

  /**
   * Check if grid coordinates are within bounds.
   * @private
   */
  _inBounds(gx, gz) {
    return gx >= 0 && gx < this.size && gz >= 0 && gz < this.size;
  }

  /**
   * Reconstruct the A* path by walking cameFrom links backward.
   *
   * @private
   * @param {Int32Array} cameFrom
   * @param {number} endIdx
   * @returns {Array<{gx: number, gz: number}>}
   */
  _reconstructPath(cameFrom, endIdx) {
    const path = [];
    let idx = endIdx;

    // Walk backward from goal to start.
    while (idx !== -1) {
      const gx = idx % this.size;
      const gz = (idx - gx) / this.size;
      path.push({ gx, gz });
      idx = cameFrom[idx];
    }

    // Reverse to get start-to-end order.
    path.reverse();
    return path;
  }
}

// ─── Binary Min-Heap ──────────────────────────────────────────────────────────
/**
 * Simple binary min-heap for the A* open set.
 *
 * Stores (index, priority) pairs sorted by priority. Supports push and pop-min.
 *
 * Why a custom heap instead of a sorted array:
 * - push + pop on a sorted array is O(n) due to insertion sort.
 * - Binary heap gives O(log n) for both operations.
 * - For 65K-cell grids, this difference is significant.
 *
 * This is deliberately minimal — no decrease-key operation. Instead, we push
 * duplicate entries and skip stale ones when popping (lazy deletion). This is
 * the standard practical A* optimization and avoids the complexity of a
 * decrease-key-capable heap.
 */
class MinHeap {
  constructor() {
    /** @type {Array<number>} Flat interleaved [idx0, f0, idx1, f1, ...] */
    this._data = [];
    this.size = 0;
  }

  /**
   * Insert an element with the given priority.
   * @param {number} idx - Cell flat index.
   * @param {number} priority - f-score.
   */
  push(idx, priority) {
    // Append to the end and bubble up to restore heap property.
    const pos = this.size * 2;
    this._data[pos] = idx;
    this._data[pos + 1] = priority;
    this.size++;
    this._bubbleUp(this.size - 1);
  }

  /**
   * Remove and return the element with the lowest priority.
   * @returns {number} Cell flat index.
   */
  pop() {
    const idx = this._data[0];
    this.size--;

    if (this.size > 0) {
      // Move last element to root and sink down.
      this._data[0] = this._data[this.size * 2];
      this._data[1] = this._data[this.size * 2 + 1];
      this._sinkDown(0);
    }

    return idx;
  }

  /** @private */
  _bubbleUp(i) {
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this._data[i * 2 + 1] < this._data[parent * 2 + 1]) {
        this._swap(i, parent);
        i = parent;
      } else {
        break;
      }
    }
  }

  /** @private */
  _sinkDown(i) {
    while (true) {
      let smallest = i;
      const left = 2 * i + 1;
      const right = 2 * i + 2;

      if (left < this.size && this._data[left * 2 + 1] < this._data[smallest * 2 + 1]) {
        smallest = left;
      }
      if (right < this.size && this._data[right * 2 + 1] < this._data[smallest * 2 + 1]) {
        smallest = right;
      }

      if (smallest !== i) {
        this._swap(i, smallest);
        i = smallest;
      } else {
        break;
      }
    }
  }

  /** @private */
  _swap(a, b) {
    const ai = a * 2, bi = b * 2;
    const tmpIdx = this._data[ai];
    const tmpPri = this._data[ai + 1];
    this._data[ai] = this._data[bi];
    this._data[ai + 1] = this._data[bi + 1];
    this._data[bi] = tmpIdx;
    this._data[bi + 1] = tmpPri;
  }
}
