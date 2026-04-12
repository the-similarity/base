/**
 * Region Map — flood-fill labeling of connected walkable areas.
 *
 * Purpose:
 * The navigation grid may contain disconnected walkable regions separated by
 * water, cliffs, or other impassable terrain. Agents need to know whether two
 * points are reachable from each other without running a full A* search. The
 * region map answers this in O(1) by assigning each walkable cell a region ID.
 *
 * Algorithm:
 * - Iterate over all cells in row-major order.
 * - When an unvisited passable cell is found, flood-fill (BFS) to label all
 *   connected passable cells with the same region ID.
 * - Impassable cells get region ID 0 (reserved for "no region").
 * - Region IDs start at 1 and increment.
 *
 * Why BFS instead of DFS:
 * - BFS uses a queue (bounded by grid perimeter at worst), DFS uses a stack
 *   that can grow as deep as the number of cells (64K+ for 256x256 grids),
 *   risking stack overflow in recursive implementations.
 * - Iterative BFS is simple, predictable, and cache-friendlier for row-major
 *   grid access patterns.
 *
 * Lifecycle:
 * 1. Construct with a NavGrid instance.
 * 2. Region labels are computed once and frozen.
 * 3. All queries are pure reads.
 * 4. If the NavGrid changes, construct a new RegionMap.
 *
 * No Three.js dependency. Headless-safe.
 *
 * @module region-map
 */

// Cardinal direction offsets, matching NavGrid's movement model.
// Module-level to avoid per-iteration allocation inside the BFS loop.
const CARDINAL_DX = [1, -1, 0, 0];
const CARDINAL_DZ = [0, 0, 1, -1];

/**
 * Flood-fill region labeling over a NavGrid.
 */
export class RegionMap {
  /**
   * Build region labels from a navigation grid.
   *
   * @param {import('./nav-grid.js').NavGrid} navGrid
   */
  constructor(navGrid) {
    /** @type {number} Grid dimension. */
    this.size = navGrid.size;

    /**
     * Region ID per cell. 0 = impassable / no region. 1+ = walkable region.
     * Row-major: index = z * size + x.
     * @type {Uint16Array}
     */
    this._regionIds = new Uint16Array(this.size * this.size);

    /**
     * Map from region ID to the list of flat cell indices in that region.
     * Built during flood fill for efficient per-region queries.
     * @type {Map<number, Array<number>>}
     */
    this._regionCells = new Map();

    /**
     * Map from region ID to its centroid in grid coordinates.
     * Computed after flood fill as the average (gx, gz) of all cells.
     * @type {Map<number, {gx: number, gz: number}>}
     */
    this._centroids = new Map();

    /**
     * Total number of walkable regions found.
     * @type {number}
     */
    this.regionCount = 0;

    this._buildRegions(navGrid);
    this._computeCentroids();
  }

  // ─── Public query methods ─────────────────────────────────────────────────

  /**
   * Get the region ID for a cell.
   *
   * Returns 0 for impassable cells or out-of-bounds coordinates.
   * Returns 1+ for walkable cells (the specific region they belong to).
   *
   * Two cells are mutually reachable if and only if they share the same
   * non-zero region ID.
   *
   * @param {number} gx - Grid X coordinate.
   * @param {number} gz - Grid Z coordinate.
   * @returns {number} Region ID (0 = impassable).
   */
  getRegionId(gx, gz) {
    if (gx < 0 || gx >= this.size || gz < 0 || gz >= this.size) return 0;
    return this._regionIds[gz * this.size + gx];
  }

  /**
   * Get all cell indices belonging to a region.
   *
   * Returns an array of flat indices (z * size + x). To convert back to
   * grid coordinates: gx = idx % size, gz = Math.floor(idx / size).
   *
   * Returns an empty array for unknown region IDs.
   *
   * @param {number} regionId
   * @returns {Array<number>} Flat cell indices.
   */
  getRegionCells(regionId) {
    return this._regionCells.get(regionId) || [];
  }

  /**
   * Get the centroid (average position) of all cells in a region.
   *
   * Returns null for unknown or impassable region IDs.
   *
   * @param {number} regionId
   * @returns {{gx: number, gz: number}|null}
   */
  getRegionCentroid(regionId) {
    return this._centroids.get(regionId) || null;
  }

  /**
   * Get all region centroids as a map from region ID to grid position.
   *
   * @returns {Map<number, {gx: number, gz: number}>}
   */
  get regionCentroids() {
    return this._centroids;
  }

  // ─── Private construction methods ─────────────────────────────────────────

  /**
   * Run BFS flood fill to label all connected walkable regions.
   *
   * @private
   * @param {import('./nav-grid.js').NavGrid} navGrid
   */
  _buildRegions(navGrid) {
    const size = this.size;
    const totalCells = size * size;
    let nextRegionId = 1;

    // Visited array prevents double-processing. Separate from _regionIds
    // because impassable cells also need to be marked as "visited" even
    // though they get region ID 0.
    const visited = new Uint8Array(totalCells);

    // Reusable BFS queue. Pre-allocating avoids repeated array resizing.
    // Maximum possible queue size is totalCells (if the entire grid is one region).
    const queue = new Int32Array(totalCells);

    for (let z = 0; z < size; z++) {
      for (let x = 0; x < size; x++) {
        const idx = z * size + x;
        if (visited[idx]) continue;

        // Mark impassable cells as visited but don't assign a region.
        if (!navGrid.isPassable(x, z)) {
          visited[idx] = 1;
          continue;
        }

        // Start a new region from this unvisited passable cell.
        const regionId = nextRegionId++;
        const cells = [];

        // BFS flood fill.
        let qHead = 0;
        let qTail = 0;
        queue[qTail++] = idx;
        visited[idx] = 1;

        while (qHead < qTail) {
          const currentIdx = queue[qHead++];
          const cx = currentIdx % size;
          const cz = (currentIdx - cx) / size;

          this._regionIds[currentIdx] = regionId;
          cells.push(currentIdx);

          // Expand cardinal neighbors (matching NavGrid's movement model).
          for (let d = 0; d < 4; d++) {
            const dx = CARDINAL_DX[d];
            const dz = CARDINAL_DZ[d];
            const nx = cx + dx;
            const nz = cz + dz;
            if (nx < 0 || nx >= size || nz < 0 || nz >= size) continue;

            const nIdx = nz * size + nx;
            if (visited[nIdx]) continue;

            if (navGrid.isPassable(nx, nz)) {
              visited[nIdx] = 1;
              queue[qTail++] = nIdx;
            } else {
              // Mark impassable neighbor as visited to skip it later.
              visited[nIdx] = 1;
            }
          }
        }

        this._regionCells.set(regionId, cells);
      }
    }

    this.regionCount = nextRegionId - 1;
  }

  /**
   * Compute the centroid of each region.
   *
   * The centroid is the arithmetic mean of all cell grid coordinates in the region.
   * This gives a representative "center" point useful for inter-region pathfinding
   * or agent spawn placement.
   *
   * Note: the centroid itself may not be a passable cell (e.g., for a C-shaped region).
   * Callers should snap to the nearest passable cell if needed.
   *
   * @private
   */
  _computeCentroids() {
    const size = this.size;

    for (const [regionId, cells] of this._regionCells) {
      let sumX = 0;
      let sumZ = 0;

      for (const idx of cells) {
        const gx = idx % size;
        const gz = (idx - gx) / size;
        sumX += gx;
        sumZ += gz;
      }

      this._centroids.set(regionId, {
        gx: Math.round(sumX / cells.length),
        gz: Math.round(sumZ / cells.length),
      });
    }
  }
}
