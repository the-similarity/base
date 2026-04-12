/**
 * Terrain Sampler — converts raw terrain geometry into simulation-friendly 2D grids.
 *
 * Purpose:
 * The fractal terrain generator (`fractal.js`) outputs an irregular triangle mesh
 * with packed Float32Array buffers (positions, normals, heights). The backend API
 * terrain mode outputs a regular grid with heightmap/biome/moisture arrays. Neither
 * format is directly usable for agent navigation or simulation queries, which need
 * fast O(1) lookups by grid coordinate.
 *
 * This module resamples any terrain source onto a uniform NxN grid and derives
 * slope, water, and biome classification maps from it. All outputs are typed arrays
 * for cache-friendly iteration and minimal GC pressure.
 *
 * Data flow:
 *   generateTerrain() output  ─┐
 *                               ├──> sampleTerrain() ──> { heightMap, slopeMap, waterMap, biomeMap }
 *   Backend API heightmap     ─┘
 *
 * Invariants:
 * - All output maps are Float32Array (or Uint8Array for biome/water) of length gridSize * gridSize.
 * - Maps are row-major: index = y * gridSize + x, where y is the Z-axis row and x is the X-axis column.
 * - heightMap values are in world-space Y units (already scaled).
 * - slopeMap values are in radians [0, PI/2].
 * - waterMap is binary: 1 = underwater, 0 = dry.
 * - biomeMap uses integer IDs matching terrain-renderer.js constants (0-5).
 *
 * No Three.js dependency. Headless-safe.
 *
 * @module terrain-sampler
 */

// ─── Biome classification constants ───────────────────────────────────────────
// These must stay in sync with terrain-renderer.js biome IDs.
// The thresholds are tuned for the fractal generator's typical height distribution
// (roughness ~0.55, displacement ~1.2) which yields heights roughly in [-1.5, 1.5].

/** @type {number} */ export const BIOME_WATER  = 0;
/** @type {number} */ export const BIOME_SAND   = 1;
/** @type {number} */ export const BIOME_GRASS  = 2;
/** @type {number} */ export const BIOME_FOREST = 3;
/** @type {number} */ export const BIOME_ROCK   = 4;
/** @type {number} */ export const BIOME_SNOW   = 5;

// ─── Default thresholds for biome classification ──────────────────────────────
// Expressed as fractions of the normalized height range [0, 1] after min-max
// rescaling. This makes classification robust to different generator parameters.

const DEFAULT_WATER_LEVEL   = 0.20; // bottom 20% of height range is water
const DEFAULT_SAND_CEILING  = 0.25; // thin band just above water
const DEFAULT_GRASS_CEILING = 0.50; // mid elevations
const DEFAULT_FOREST_CEILING = 0.70; // forested hills
const DEFAULT_ROCK_CEILING  = 0.85; // rocky peaks
// Above ROCK_CEILING → snow

// Slope thresholds (radians) for biome override.
// Very steep slopes become rock regardless of height, because vegetation
// cannot establish on near-vertical surfaces.
const CLIFF_SLOPE_THRESHOLD = 1.0; // ~57 degrees

/**
 * Sample raw terrain data onto a regular grid and derive simulation maps.
 *
 * Accepts two input shapes:
 *
 * 1. **Fractal mesh** (from `generateTerrain()`):
 *    `{ positions: Float32Array, heights: Float32Array, vertexCount, ... }`
 *    The mesh is an irregular triangle soup. We scatter vertex heights onto the
 *    nearest grid cells and interpolate gaps. This is approximate but sufficient
 *    for navigation — agents do not need sub-triangle precision.
 *
 * 2. **Backend API grid** (from `/terrain/generate`):
 *    `{ heightmap: Array|Float32Array, size: number, biome?, moisture?, ... }`
 *    Already a regular grid. We resample to the requested gridSize if different
 *    from the source size.
 *
 * @param {Object} terrainData - Raw terrain output from either source.
 * @param {number} [gridSize=128] - Output grid resolution (NxN cells).
 * @param {number} [worldScale=10] - World-space extent of the terrain in XZ.
 * @returns {{
 *   heightMap: Float32Array,
 *   slopeMap: Float32Array,
 *   waterMap: Uint8Array,
 *   biomeMap: Uint8Array,
 *   size: number,
 *   worldScale: number
 * }}
 */
export function sampleTerrain(terrainData, gridSize = 128, worldScale = 10) {
  // ── Detect input format ──────────────────────────────────────────────────
  // The two formats are distinguished by the presence of `positions` (mesh)
  // vs `heightmap` (grid). Both are valid; we normalize to a heightMap grid.

  let heightMap;

  if (terrainData.positions && terrainData.heights) {
    // Fractal mesh path: scatter irregular vertices onto the grid.
    heightMap = _sampleFromMesh(terrainData, gridSize, worldScale);
  } else if (terrainData.heightmap) {
    // Backend API path: resample existing regular grid.
    heightMap = _sampleFromGrid(terrainData, gridSize);
  } else {
    // Fallback: treat raw flat array as a square heightmap.
    // This handles the case where someone passes just a Float32Array.
    const srcSize = Math.round(Math.sqrt(terrainData.length || 0));
    if (srcSize * srcSize === (terrainData.length || 0) && srcSize > 0) {
      heightMap = _bilinearResample(terrainData, srcSize, gridSize);
    } else {
      throw new Error(
        'sampleTerrain: unrecognized terrain data format. ' +
        'Expected { positions, heights } or { heightmap, size } or a flat array.'
      );
    }
  }

  // ── Derive slope map ─────────────────────────────────────────────────────
  // Slope at each cell is the steepest gradient to any cardinal neighbor.
  // We use the standard finite-difference approach: for each cell, compute
  // the height difference to its +X and +Z neighbors, then take the angle
  // of the resulting gradient vector.
  //
  // Why steepest-of-neighbors instead of central differences:
  // Central differences smooth over sharp cliffs. For navigation, we want
  // the worst-case slope so agents avoid cliff edges, not just averages.

  const slopeMap = new Float32Array(gridSize * gridSize);
  const cellSize = worldScale / gridSize; // world-space distance between adjacent cells

  for (let z = 0; z < gridSize; z++) {
    for (let x = 0; x < gridSize; x++) {
      const idx = z * gridSize + x;
      const h = heightMap[idx];

      // Compute partial derivatives via forward differences, clamped at grid edges.
      const hRight = (x < gridSize - 1) ? heightMap[idx + 1] : h;
      const hDown  = (z < gridSize - 1) ? heightMap[idx + gridSize] : h;

      const dhdx = (hRight - h) / cellSize;
      const dhdz = (hDown - h) / cellSize;

      // Slope angle in radians: atan of the gradient magnitude.
      // This gives 0 for flat terrain, PI/2 for vertical cliffs.
      const gradientMag = Math.sqrt(dhdx * dhdx + dhdz * dhdz);
      slopeMap[idx] = Math.atan(gradientMag);
    }
  }

  // ── Normalize heights for biome classification ───────────────────────────
  // We need the min/max to map absolute heights into [0, 1] for threshold-based
  // biome assignment. This makes classification independent of generator params.

  let hMin = Infinity;
  let hMax = -Infinity;
  for (let i = 0; i < heightMap.length; i++) {
    if (heightMap[i] < hMin) hMin = heightMap[i];
    if (heightMap[i] > hMax) hMax = heightMap[i];
  }
  const hRange = (hMax - hMin) || 1; // guard against flat terrain

  // ── Derive water map and biome map ───────────────────────────────────────
  const waterMap = new Uint8Array(gridSize * gridSize);
  const biomeMap = new Uint8Array(gridSize * gridSize);

  for (let i = 0; i < heightMap.length; i++) {
    const normalizedH = (heightMap[i] - hMin) / hRange; // [0, 1]
    const slope = slopeMap[i];

    // Water: anything below the water level threshold.
    if (normalizedH < DEFAULT_WATER_LEVEL) {
      waterMap[i] = 1;
      biomeMap[i] = BIOME_WATER;
      continue;
    }

    // Cliff override: very steep slopes become rock regardless of elevation.
    // This prevents forests from appearing on vertical cliff faces.
    if (slope > CLIFF_SLOPE_THRESHOLD) {
      biomeMap[i] = BIOME_ROCK;
      continue;
    }

    // Height-based classification for non-water, non-cliff cells.
    if (normalizedH < DEFAULT_SAND_CEILING) {
      biomeMap[i] = BIOME_SAND;
    } else if (normalizedH < DEFAULT_GRASS_CEILING) {
      biomeMap[i] = BIOME_GRASS;
    } else if (normalizedH < DEFAULT_FOREST_CEILING) {
      biomeMap[i] = BIOME_FOREST;
    } else if (normalizedH < DEFAULT_ROCK_CEILING) {
      biomeMap[i] = BIOME_ROCK;
    } else {
      biomeMap[i] = BIOME_SNOW;
    }
  }

  return {
    heightMap,
    slopeMap,
    waterMap,
    biomeMap,
    size: gridSize,
    worldScale,
  };
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

/**
 * Scatter irregular mesh vertices onto a regular grid via nearest-cell binning.
 *
 * Strategy:
 * 1. For each vertex, compute which grid cell it falls into based on its XZ position.
 * 2. If multiple vertices map to the same cell, average their heights.
 * 3. Fill any empty cells via neighbor interpolation (flood fill from populated cells).
 *
 * Why binning instead of barycentric interpolation:
 * - The mesh topology is not stored in a spatial index, so finding which triangle
 *   contains a given XZ point would require O(faces) per query.
 * - Binning is O(vertices) total and "good enough" for navigation grids.
 * - The grid resolution (128x128 default) is typically much coarser than the mesh
 *   vertex density at 5+ subdivision iterations, so most cells get multiple hits.
 *
 * @param {Object} meshData - { positions: Float32Array, heights: Float32Array, vertexCount }
 * @param {number} gridSize
 * @param {number} worldScale
 * @returns {Float32Array}
 */
function _sampleFromMesh(meshData, gridSize, worldScale) {
  const { positions, vertexCount } = meshData;
  const heightMap = new Float32Array(gridSize * gridSize);
  const countMap = new Uint16Array(gridSize * gridSize); // hits per cell for averaging

  const halfWorld = worldScale / 2;

  for (let v = 0; v < vertexCount; v++) {
    // Position layout: tightly packed XYZ triplets.
    const wx = positions[v * 3];       // world X
    const wy = positions[v * 3 + 1];   // world Y (height)
    const wz = positions[v * 3 + 2];   // world Z

    // Map world coordinates [-halfWorld, +halfWorld] to grid [0, gridSize-1].
    const gx = Math.floor(((wx + halfWorld) / worldScale) * (gridSize - 1));
    const gz = Math.floor(((wz + halfWorld) / worldScale) * (gridSize - 1));

    // Skip vertices outside the grid bounds (can happen with non-square base shapes).
    if (gx < 0 || gx >= gridSize || gz < 0 || gz >= gridSize) continue;

    const idx = gz * gridSize + gx;
    heightMap[idx] += wy;
    countMap[idx]++;
  }

  // Average accumulated heights for cells with multiple vertex hits.
  for (let i = 0; i < heightMap.length; i++) {
    if (countMap[i] > 0) {
      heightMap[i] /= countMap[i];
    }
  }

  // Fill empty cells by iterative neighbor averaging.
  // This handles grid cells that no vertex landed in (sparse mesh regions
  // or edge cells beyond the mesh boundary).
  _fillEmptyCells(heightMap, countMap, gridSize);

  return heightMap;
}

/**
 * Fill grid cells with zero vertex hits by averaging populated neighbors.
 *
 * Uses iterative passes: each pass fills cells that have at least one populated
 * cardinal neighbor. Repeats until all cells are filled or no progress is made.
 *
 * Why iterative instead of a priority queue / BFS:
 * - Grid is small (128x128 = 16K cells). Even 10 passes are instant.
 * - Code simplicity matters more than asymptotic optimality at this scale.
 *
 * @param {Float32Array} heightMap - Partially populated height grid (modified in place).
 * @param {Uint16Array} countMap - Hit counts (0 = empty cell).
 * @param {number} gridSize
 */
function _fillEmptyCells(heightMap, countMap, gridSize) {
  // Track which cells are still empty. We iterate until none remain.
  let emptyCount = 0;
  for (let i = 0; i < countMap.length; i++) {
    if (countMap[i] === 0) emptyCount++;
  }

  // Safety limit prevents infinite loops if the mesh covers no cells at all.
  const MAX_PASSES = gridSize;
  let pass = 0;

  while (emptyCount > 0 && pass < MAX_PASSES) {
    let filled = 0;

    for (let z = 0; z < gridSize; z++) {
      for (let x = 0; x < gridSize; x++) {
        const idx = z * gridSize + x;
        if (countMap[idx] > 0) continue; // already populated

        // Gather heights from populated cardinal neighbors.
        let sum = 0;
        let n = 0;

        if (x > 0 && countMap[idx - 1] > 0)        { sum += heightMap[idx - 1]; n++; }
        if (x < gridSize - 1 && countMap[idx + 1] > 0) { sum += heightMap[idx + 1]; n++; }
        if (z > 0 && countMap[idx - gridSize] > 0)  { sum += heightMap[idx - gridSize]; n++; }
        if (z < gridSize - 1 && countMap[idx + gridSize] > 0) { sum += heightMap[idx + gridSize]; n++; }

        if (n > 0) {
          heightMap[idx] = sum / n;
          countMap[idx] = 1; // mark as populated
          filled++;
        }
      }
    }

    emptyCount -= filled;
    if (filled === 0) break; // no progress possible (disconnected regions)
    pass++;
  }
}

/**
 * Resample a backend API regular grid to a different resolution.
 *
 * Uses bilinear interpolation for smooth downsampling/upsampling.
 *
 * @param {Object} gridData - { heightmap, size }
 * @param {number} gridSize - Target resolution.
 * @returns {Float32Array}
 */
function _sampleFromGrid(gridData, gridSize) {
  const src = gridData.heightmap;
  const srcSize = gridData.size;

  // If sizes match, just copy into a typed array.
  if (srcSize === gridSize) {
    const out = new Float32Array(gridSize * gridSize);
    for (let i = 0; i < out.length; i++) {
      out[i] = src[i] || 0;
    }
    return out;
  }

  return _bilinearResample(src, srcSize, gridSize);
}

/**
 * Core bilinear interpolation resampler.
 *
 * For each destination cell, we find the corresponding fractional position in the
 * source grid and interpolate from the four surrounding source cells.
 *
 * @param {ArrayLike<number>} src
 * @param {number} srcSize
 * @param {number} dstSize
 * @returns {Float32Array}
 */
function _bilinearResample(src, srcSize, dstSize) {
  const dst = new Float32Array(dstSize * dstSize);
  const ratio = (srcSize - 1) / (dstSize - 1 || 1);

  for (let dz = 0; dz < dstSize; dz++) {
    for (let dx = 0; dx < dstSize; dx++) {
      // Fractional source coordinates.
      const sx = dx * ratio;
      const sz = dz * ratio;

      // Integer corners of the source cell containing this point.
      const x0 = Math.floor(sx);
      const z0 = Math.floor(sz);
      const x1 = Math.min(x0 + 1, srcSize - 1);
      const z1 = Math.min(z0 + 1, srcSize - 1);

      // Fractional offsets within the cell.
      const fx = sx - x0;
      const fz = sz - z0;

      // Four corner samples.
      const h00 = src[z0 * srcSize + x0] || 0;
      const h10 = src[z0 * srcSize + x1] || 0;
      const h01 = src[z1 * srcSize + x0] || 0;
      const h11 = src[z1 * srcSize + x1] || 0;

      // Standard bilinear blend.
      dst[dz * dstSize + dx] =
        h00 * (1 - fx) * (1 - fz) +
        h10 * fx * (1 - fz) +
        h01 * (1 - fx) * fz +
        h11 * fx * fz;
    }
  }

  return dst;
}
