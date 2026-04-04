/**
 * Fractal terrain generation via midpoint displacement on triangle meshes.
 *
 * Algorithm:
 *   1. Start with a base mesh (single triangle, diamond, etc.)
 *   2. For each subdivision level:
 *      a. Split every triangle into 4 by inserting edge midpoints
 *      b. Displace each new midpoint vertically by random * scale
 *      c. Reduce scale by roughness^level (self-similarity)
 *   3. The fractal dimension ≈ 2 + roughness controls terrain character
 */

// --- Seeded PRNG (xoshiro128**) for reproducible terrain ---
export class PRNG {
  constructor(seed = 42) {
    // SplitMix64 to initialize state from a single seed
    let s = seed >>> 0;
    const sm = () => {
      s = (s + 0x9e3779b9) >>> 0;
      let z = s;
      z = (z ^ (z >>> 16)) >>> 0;
      z = Math.imul(z, 0x85ebca6b);
      z = (z ^ (z >>> 13)) >>> 0;
      z = Math.imul(z, 0xc2b2ae35);
      z = (z ^ (z >>> 16)) >>> 0;
      return z >>> 0;
    };
    this.s = [sm(), sm(), sm(), sm()];
  }

  _rotl(x, k) {
    return ((x << k) | (x >>> (32 - k))) >>> 0;
  }

  next() {
    const s = this.s;
    const result = (Math.imul(this._rotl(Math.imul(s[1], 5), 7), 9)) >>> 0;
    const t = (s[1] << 9) >>> 0;
    s[2] = (s[2] ^ s[0]) >>> 0;
    s[3] = (s[3] ^ s[1]) >>> 0;
    s[1] = (s[1] ^ s[2]) >>> 0;
    s[0] = (s[0] ^ s[3]) >>> 0;
    s[2] = (s[2] ^ t) >>> 0;
    s[3] = this._rotl(s[3], 11);
    return result / 0x100000000; // [0, 1)
  }

  // Uniform in [-1, 1)
  nextSigned() {
    return this.next() * 2 - 1;
  }
}

// --- Edge key for deduplication ---
function edgeKey(a, b) {
  return a < b ? `${a}_${b}` : `${b}_${a}`;
}

/**
 * Generate fractal terrain mesh.
 *
 * @param {Object} opts
 * @param {number} opts.iterations   - subdivision depth (0-8)
 * @param {number} opts.roughness    - fractal roughness (0.1-1.0)
 * @param {number} opts.displacement - initial displacement amplitude
 * @param {number} opts.scale        - base triangle scale
 * @param {number} opts.seed         - PRNG seed
 * @param {string} opts.baseShape    - 'triangle' | 'diamond' | 'plane'
 * @returns {{ positions: Float32Array, indices: Uint32Array, normals: Float32Array, heights: Float32Array }}
 */
export function generateTerrain(opts = {}) {
  const {
    iterations = 5,
    roughness = 0.55,
    displacement = 1.2,
    scale = 4.0,
    seed = 42,
    baseShape = 'diamond',
  } = opts;

  const rng = new PRNG(seed);

  // --- Build initial mesh ---
  let vertices, faces;

  if (baseShape === 'triangle') {
    // Equilateral triangle in XZ plane
    const h = scale * Math.sqrt(3) / 2;
    vertices = [
      [0, 0, -h * 2/3],
      [-scale / 2, 0, h / 3],
      [scale / 2, 0, h / 3],
    ];
    faces = [[0, 1, 2]];
  } else if (baseShape === 'diamond') {
    // Two triangles forming a diamond/square
    const s = scale;
    vertices = [
      [0, 0, -s],   // north
      [-s, 0, 0],   // west
      [0, 0, s],    // south
      [s, 0, 0],    // east
    ];
    faces = [
      [0, 1, 3],
      [1, 2, 3],
    ];
  } else {
    // plane: 2-triangle quad
    const s = scale;
    vertices = [
      [-s, 0, -s],
      [s, 0, -s],
      [s, 0, s],
      [-s, 0, s],
    ];
    faces = [
      [0, 1, 2],
      [0, 2, 3],
    ];
  }

  // --- Subdivide ---
  for (let level = 0; level < iterations; level++) {
    const amp = displacement * Math.pow(roughness, level);
    const midpointCache = new Map();
    const newFaces = [];

    function getMidpoint(ia, ib) {
      const key = edgeKey(ia, ib);
      if (midpointCache.has(key)) return midpointCache.get(key);

      const a = vertices[ia];
      const b = vertices[ib];
      const mid = [
        (a[0] + b[0]) / 2,
        (a[1] + b[1]) / 2 + rng.nextSigned() * amp,
        (a[2] + b[2]) / 2,
      ];
      const idx = vertices.length;
      vertices.push(mid);
      midpointCache.set(key, idx);
      return idx;
    }

    for (const [i0, i1, i2] of faces) {
      const a = getMidpoint(i0, i1);
      const b = getMidpoint(i1, i2);
      const c = getMidpoint(i2, i0);

      newFaces.push(
        [i0, a, c],
        [a, i1, b],
        [c, b, i2],
        [a, b, c],
      );
    }

    faces = newFaces;
  }

  // --- Convert to typed arrays ---
  const numVerts = vertices.length;
  const positions = new Float32Array(numVerts * 3);
  const heights = new Float32Array(numVerts);

  for (let i = 0; i < numVerts; i++) {
    positions[i * 3] = vertices[i][0];
    positions[i * 3 + 1] = vertices[i][1];
    positions[i * 3 + 2] = vertices[i][2];
    heights[i] = vertices[i][1];
  }

  const numFaces = faces.length;
  const indices = new Uint32Array(numFaces * 3);
  for (let i = 0; i < numFaces; i++) {
    indices[i * 3] = faces[i][0];
    indices[i * 3 + 1] = faces[i][1];
    indices[i * 3 + 2] = faces[i][2];
  }

  // --- Compute normals ---
  const normals = new Float32Array(numVerts * 3);
  for (let i = 0; i < numFaces; i++) {
    const ia = faces[i][0], ib = faces[i][1], ic = faces[i][2];

    const ax = positions[ia*3], ay = positions[ia*3+1], az = positions[ia*3+2];
    const bx = positions[ib*3], by = positions[ib*3+1], bz = positions[ib*3+2];
    const cx = positions[ic*3], cy = positions[ic*3+1], cz = positions[ic*3+2];

    // Cross product of (b-a) x (c-a)
    const e1x = bx-ax, e1y = by-ay, e1z = bz-az;
    const e2x = cx-ax, e2y = cy-ay, e2z = cz-az;
    const nx = e1y*e2z - e1z*e2y;
    const ny = e1z*e2x - e1x*e2z;
    const nz = e1x*e2y - e1y*e2x;

    for (const idx of [ia, ib, ic]) {
      normals[idx*3]   += nx;
      normals[idx*3+1] += ny;
      normals[idx*3+2] += nz;
    }
  }

  // Normalize
  for (let i = 0; i < numVerts; i++) {
    const x = normals[i*3], y = normals[i*3+1], z = normals[i*3+2];
    const len = Math.sqrt(x*x + y*y + z*z) || 1;
    normals[i*3]   /= len;
    normals[i*3+1] /= len;
    normals[i*3+2] /= len;
  }

  return { positions, indices, normals, heights, vertexCount: numVerts, faceCount: numFaces };
}
