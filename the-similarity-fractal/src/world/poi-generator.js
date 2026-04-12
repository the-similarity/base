/**
 * Point-of-interest (POI) generator and spatial registry for the 3D society simulation.
 *
 * POIs are fixed landmarks that influence agent behavior: water sources attract
 * settlement, fertile land attracts farming, shelters attract resting, mines
 * attract material gathering. They are placed once at world-generation time
 * based on terrain features, then queried at runtime by agent AI.
 *
 * Two exports:
 *   1. generatePOIs(terrainMaps, regionMap, rng) — deterministic placement pass.
 *   2. POIRegistry — spatial index for fast nearest-POI and region-scoped queries.
 *
 * Lifecycle:
 *   const pois = generatePOIs(terrainMaps, regionMap, rng);
 *   const registry = new POIRegistry(pois);
 *   registry.nearestPOI(gx, gz, 'WATER_SOURCE');  // O(n) scan, n = POI count
 *
 * Immutability:
 *   - generatePOIs is pure (given deterministic rng).
 *   - POIRegistry is read-only after construction.
 *   - Neither mutates terrainMaps or regionMap.
 */

// ─── Biome constants (mirrored from terrain-renderer.js) ───────────────────
const BIOME_WATER  = 0;
const BIOME_SAND   = 1;
const BIOME_GRASS  = 2;
const BIOME_FOREST = 3;
const BIOME_ROCK   = 4;
const BIOME_SNOW   = 5;

// ─── POI type enum ─────────────────────────────────────────────────────────
// String constants rather than numeric so logs and snapshots are human-readable.
export const POI_TYPES = Object.freeze({
  WATER_SOURCE: 'WATER_SOURCE',
  FERTILE_LAND: 'FERTILE_LAND',
  SHELTER:      'SHELTER',
  MINE:         'MINE',
});

// ─── Placement parameters ──────────────────────────────────────────────────
// These control density. We scan the grid at SCAN_STEP intervals and place
// a POI when the local terrain meets the type's criteria, subject to a
// minimum spacing constraint (MIN_DISTANCE_BETWEEN_SAME_TYPE) to prevent
// clustering.

/** Grid cells to skip between candidate evaluations. */
const SCAN_STEP = 4;

/**
 * Minimum Chebyshev distance between two POIs of the same type.
 * Prevents degenerate clusters where every adjacent water tile spawns a POI.
 */
const MIN_DISTANCE_BETWEEN_SAME_TYPE = 6;

/**
 * Maximum slope (0-1 normalized) for SHELTER placement.
 * Shelters need relatively flat ground.
 */
const SHELTER_MAX_SLOPE = 0.3;

/**
 * Default capacity for each POI type. Capacity limits how many agents
 * can simultaneously use a POI before it is considered "full".
 */
const DEFAULT_CAPACITY = {
  [POI_TYPES.WATER_SOURCE]: 5,
  [POI_TYPES.FERTILE_LAND]: 8,
  [POI_TYPES.SHELTER]:      4,
  [POI_TYPES.MINE]:         6,
};

// ─── Helpers ───────────────────────────────────────────────────────────────

/**
 * Chebyshev distance between two grid points — the "chessboard" metric.
 * Used for spacing checks because it's cheaper than Euclidean and still
 * prevents tight clusters.
 */
function chebyshev(ax, az, bx, bz) {
  return Math.max(Math.abs(ax - bx), Math.abs(az - bz));
}

/**
 * Check whether a candidate position is far enough from all existing POIs
 * of the same type.
 */
function isFarEnough(existing, gx, gz, type) {
  for (const poi of existing) {
    if (poi.type === type) {
      if (chebyshev(gx, gz, poi.position.x, poi.position.z) < MIN_DISTANCE_BETWEEN_SAME_TYPE) {
        return false;
      }
    }
  }
  return true;
}

/**
 * Count how many of the 8 neighbors (plus the cell itself) have a given
 * biome. Useful for detecting biome edges — e.g., a WATER_SOURCE should
 * be placed on land cells adjacent to water, not in deep water.
 */
function countNeighborBiome(biomeMap, size, gx, gz, targetBiome) {
  let count = 0;
  for (let dz = -1; dz <= 1; dz++) {
    for (let dx = -1; dx <= 1; dx++) {
      const nx = gx + dx;
      const nz = gz + dz;
      if (nx >= 0 && nx < size && nz >= 0 && nz < size) {
        if (biomeMap[nz * size + nx] === targetBiome) count++;
      }
    }
  }
  return count;
}

// ─── Generator ─────────────────────────────────────────────────────────────

/**
 * Deterministically place POIs based on terrain features.
 *
 * Algorithm:
 *   Scan the grid at SCAN_STEP intervals. At each candidate cell, test the
 *   four POI types in order. If criteria pass and spacing is satisfied, place
 *   a POI with a small random jitter on position to avoid grid-aligned rows.
 *
 * @param {Object} terrainMaps - { heightMap, slopeMap, waterMap, biomeMap, size, worldScale }
 * @param {Object} regionMap   - { getRegionId(gx, gz) => number }
 * @param {Object} rng         - PRNG with { next(), nextSigned() }
 * @returns {Array<Object>} Array of POI objects.
 */
export function generatePOIs(terrainMaps, regionMap, rng) {
  const { biomeMap, slopeMap, size } = terrainMaps;
  const pois = [];
  let nextId = 0;

  /**
   * Helper to push a new POI if spacing allows.
   * Returns true if placed, false if rejected.
   */
  function tryPlace(gx, gz, type) {
    if (!isFarEnough(pois, gx, gz, type)) return false;

    const regionId = regionMap.getRegionId(gx, gz);

    pois.push({
      id: nextId++,
      type,
      position: {
        // Small sub-cell jitter so POIs don't align to the scan grid.
        // The 0.5 offset centers the jitter around the cell center.
        x: gx + (rng.next() - 0.5) * 0.4,
        z: gz + (rng.next() - 0.5) * 0.4,
      },
      regionId,
      capacity: DEFAULT_CAPACITY[type] ?? 4,
    });
    return true;
  }

  // ── Main scan ────────────────────────────────────────────────────────
  for (let gz = 1; gz < size - 1; gz += SCAN_STEP) {
    for (let gx = 1; gx < size - 1; gx += SCAN_STEP) {
      const idx   = gz * size + gx;
      const biome = biomeMap[idx] ?? BIOME_GRASS;
      const slope = slopeMap[idx] ?? 0;

      // ── WATER_SOURCE ─────────────────────────────────────────────
      // Placed on land cells adjacent to water biome. This represents
      // wells, springs, or riverbanks — not open water itself.
      if (biome !== BIOME_WATER) {
        const waterNeighbors = countNeighborBiome(biomeMap, size, gx, gz, BIOME_WATER);
        // Need at least 2 water neighbors to be considered "near water".
        if (waterNeighbors >= 2) {
          tryPlace(gx, gz, POI_TYPES.WATER_SOURCE);
        }
      }

      // ── FERTILE_LAND ─────────────────────────────────────────────
      // Forest and grass biomes with low slope. The probability filter
      // prevents every grass tile from becoming a POI.
      if ((biome === BIOME_FOREST || biome === BIOME_GRASS) && slope < 0.4) {
        // Use rng to thin placement — roughly 30% of candidates pass.
        if (rng.next() < 0.3) {
          tryPlace(gx, gz, POI_TYPES.FERTILE_LAND);
        }
      }

      // ── SHELTER ──────────────────────────────────────────────────
      // Forest biome + low slope = natural shelter (tree canopy, caves).
      if (biome === BIOME_FOREST && slope < SHELTER_MAX_SLOPE) {
        if (rng.next() < 0.25) {
          tryPlace(gx, gz, POI_TYPES.SHELTER);
        }
      }

      // ── MINE ─────────────────────────────────────────────────────
      // Rock biome only. Mines are rarer — tighter probability filter.
      if (biome === BIOME_ROCK) {
        if (rng.next() < 0.35) {
          tryPlace(gx, gz, POI_TYPES.MINE);
        }
      }
    }
  }

  return pois;
}

// ─── Registry ──────────────────────────────────────────────────────────────

/**
 * Read-only spatial index over placed POIs.
 *
 * Current implementation uses brute-force linear scan for nearest-POI queries.
 * This is acceptable for expected POI counts (low hundreds). If the world
 * scales to thousands of POIs, replace with a spatial hash or k-d tree.
 */
export class POIRegistry {
  /**
   * @param {Array<Object>} pois - Array from generatePOIs().
   */
  constructor(pois) {
    // Defensive copy so external mutations don't corrupt our index.
    this._pois = Object.freeze([...pois]);

    // ── Region index ─────────────────────────────────────────────────
    // Pre-group POIs by regionId for O(1) region lookup.
    this._byRegion = new Map();
    for (const poi of this._pois) {
      const rid = poi.regionId;
      if (!this._byRegion.has(rid)) {
        this._byRegion.set(rid, []);
      }
      this._byRegion.get(rid).push(poi);
    }

    // ── Type index ───────────────────────────────────────────────────
    // Pre-group by type so nearestPOI with a type filter only scans
    // the relevant subset.
    this._byType = new Map();
    for (const poi of this._pois) {
      if (!this._byType.has(poi.type)) {
        this._byType.set(poi.type, []);
      }
      this._byType.get(poi.type).push(poi);
    }
  }

  /**
   * Find the nearest POI to a grid position, optionally filtered by type.
   *
   * @param {number} gx - Grid x coordinate of the query point.
   * @param {number} gz - Grid z coordinate of the query point.
   * @param {string} [type] - If provided, only consider POIs of this type.
   * @returns {Object|null} The nearest POI object, or null if none exist.
   */
  nearestPOI(gx, gz, type) {
    // Choose the candidate set: type-filtered subset or all POIs.
    const candidates = type ? (this._byType.get(type) ?? []) : this._pois;

    let best = null;
    let bestDist = Infinity;

    for (const poi of candidates) {
      // Squared Euclidean distance — avoids sqrt since we only need ordering.
      const dx = poi.position.x - gx;
      const dz = poi.position.z - gz;
      const d2 = dx * dx + dz * dz;
      if (d2 < bestDist) {
        bestDist = d2;
        best = poi;
      }
    }

    return best;
  }

  /**
   * Get all POIs within a given region.
   *
   * @param {number} regionId
   * @returns {Array<Object>} POIs in the region (empty array if none).
   */
  getPOIsInRegion(regionId) {
    return this._byRegion.get(regionId) ?? [];
  }

  /**
   * Total number of POIs.
   */
  get count() {
    return this._pois.length;
  }

  /**
   * All POIs as a frozen array (safe to expose since entries are plain objects).
   */
  get all() {
    return this._pois;
  }
}
