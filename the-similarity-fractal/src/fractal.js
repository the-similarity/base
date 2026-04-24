/**
 * Local fractal terrain generator used by the standalone browser demo.
 *
 * Conceptual model:
 * - We start from a very small triangle mesh (triangle / diamond / plane).
 * - Each refinement step splits every triangle into four smaller triangles.
 * - Every newly created midpoint gets a random vertical offset.
 * - The offset amplitude shrinks per subdivision level by `roughness^level`.
 *
 * Why that produces "fractal" looking terrain:
 * - Large scales are established first, with large displacements.
 * - Smaller scales are layered on top, with progressively smaller displacements.
 * - Repeating the same rule across scales is the core self-similarity idea.
 *
 * Important constraint:
 * - This file only generates geometry data. It does not know about Three.js
 *   meshes, materials, water, biomes, UI state, or backend API terrain.
 * - The return value is deliberately renderer-agnostic typed arrays.
 */

/**
 * Small deterministic pseudo-random number generator.
 *
 * Why this exists instead of using `Math.random()`:
 * - The same seed must reproduce the same terrain exactly.
 * - That makes the demo debuggable and lets agents reason from a stable world.
 * - The generator state is self-contained and cheap to serialize mentally.
 */
export class PRNG {
  constructor(seed = 42) {
    // Expand a single integer seed into four internal state values.
    // The xoshiro family expects multiple state slots; SplitMix-style mixing
    // gives us decorrelated starting values from one user-facing seed.
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
    // Bit rotation is part of the xoshiro transition function.
    return ((x << k) | (x >>> (32 - k))) >>> 0;
  }

  next() {
    // Generate one unsigned 32-bit sample, then map it into [0, 1).
    // The exact bit twiddling is less important than the guarantees:
    // deterministic, fast, and "random enough" for procedural terrain.
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

  // Signed variant used for midpoint displacement so terrain can move up or down.
  nextSigned() {
    return this.next() * 2 - 1;
  }
}

/**
 * Canonical string key for an undirected edge.
 *
 * Midpoints belong to edges, not to faces.
 * Adjacent triangles share edges, so they must also share midpoint vertices.
 * If we did not deduplicate here, every face would create its own midpoint and
 * the mesh would tear apart along subdivision boundaries.
 */
function edgeKey(a, b) {
  return a < b ? `${a}_${b}` : `${b}_${a}`;
}

/**
 * Generate fractal terrain mesh.
 *
 * @param {Object} opts
 * @param {number} opts.iterations   - subdivision depth. Soft cap 10:
 *   at level 10 a diamond base yields ~2M triangles with ~1M verts —
 *   comfortably interactive on a mid-range GPU. Levels 11+ still
 *   generate cleanly (no hard assert) but perf tanks at ~8M+ tris
 *   and the noise amplitude is already sub-pixel at default
 *   roughness (0.55^10 ≈ 2.5e-3). UI slider caps at 10.
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

  // Build the coarsest possible seed mesh.
  // Everything after this is refinement; the base shape controls only the
  // initial topology and silhouette, not the later high-frequency detail.
  let vertices, faces;

  if (baseShape === 'triangle') {
    // Equilateral triangle centered around the origin in the XZ plane.
    // Y is height, so all initial vertices start flat at y = 0.
    const h = scale * Math.sqrt(3) / 2;
    vertices = [
      [0, 0, -h * 2/3],
      [-scale / 2, 0, h / 3],
      [scale / 2, 0, h / 3],
    ];
    faces = [[0, 1, 2]];
  } else if (baseShape === 'diamond') {
    // Two triangles arranged as a diamond. This is the default because it
    // gives a compact footprint with a slightly more interesting initial shape
    // than a single triangle, while still staying topologically simple.
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
    // Plane variant: a standard square split into two triangles.
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

  // Refine the mesh `iterations` times.
  //
  // At each level:
  // - Every face becomes four faces.
  // - Newly created midpoint vertices receive vertical noise.
  // - Noise amplitude decays geometrically with level.
  //
  // That geometric decay is the whole "fractal roughness" control.
  for (let level = 0; level < iterations; level++) {
    const amp = displacement * Math.pow(roughness, level);
    const midpointCache = new Map();
    const newFaces = [];

    function getMidpoint(ia, ib) {
      // One midpoint per undirected edge, shared by all incident triangles.
      const key = edgeKey(ia, ib);
      if (midpointCache.has(key)) return midpointCache.get(key);

      const a = vertices[ia];
      const b = vertices[ib];
      const mid = [
        (a[0] + b[0]) / 2,
        // Only the vertical axis is displaced.
        // Horizontal coordinates stay centered on the original edge midpoint so
        // the mesh refines rather than shearing sideways.
        (a[1] + b[1]) / 2 + rng.nextSigned() * amp,
        (a[2] + b[2]) / 2,
      ];
      const idx = vertices.length;
      vertices.push(mid);
      midpointCache.set(key, idx);
      return idx;
    }

    for (const [i0, i1, i2] of faces) {
      // Create the three edge midpoints for this triangle.
      const a = getMidpoint(i0, i1);
      const b = getMidpoint(i1, i2);
      const c = getMidpoint(i2, i0);

      // Standard 1-to-4 triangle subdivision pattern.
      // This preserves the overall surface while increasing local resolution.
      newFaces.push(
        [i0, a, c],
        [a, i1, b],
        [c, b, i2],
        [a, b, c],
      );
    }

    faces = newFaces;
  }

  // Flatten the dynamic JS arrays into typed arrays that are friendly to both
  // GPU upload and downstream renderer code.
  const numVerts = vertices.length;
  const positions = new Float32Array(numVerts * 3);
  const heights = new Float32Array(numVerts);

  for (let i = 0; i < numVerts; i++) {
    // Position layout is tightly packed XYZXYZXYZ...
    positions[i * 3] = vertices[i][0];
    positions[i * 3 + 1] = vertices[i][1];
    positions[i * 3 + 2] = vertices[i][2];

    // Height-only view is kept because coloring and analysis often care just
    // about Y without re-parsing the position buffer.
    heights[i] = vertices[i][1];
  }

  const numFaces = faces.length;
  const indices = new Uint32Array(numFaces * 3);
  for (let i = 0; i < numFaces; i++) {
    // Triangle index layout is ABCABCABC...
    indices[i * 3] = faces[i][0];
    indices[i * 3 + 1] = faces[i][1];
    indices[i * 3 + 2] = faces[i][2];
  }

  // Compute smooth vertex normals from face normals.
  //
  // Strategy:
  // - Compute one unnormalized face normal per triangle.
  // - Accumulate that vector into each vertex participating in the face.
  // - Normalize the accumulated per-vertex vectors at the end.
  //
  // This is a classic "average surrounding face normals" approach.
  const normals = new Float32Array(numVerts * 3);
  for (let i = 0; i < numFaces; i++) {
    const ia = faces[i][0], ib = faces[i][1], ic = faces[i][2];

    const ax = positions[ia*3], ay = positions[ia*3+1], az = positions[ia*3+2];
    const bx = positions[ib*3], by = positions[ib*3+1], bz = positions[ib*3+2];
    const cx = positions[ic*3], cy = positions[ic*3+1], cz = positions[ic*3+2];

    // Cross product of (b - a) x (c - a) gives the face normal.
    const e1x = bx-ax, e1y = by-ay, e1z = bz-az;
    const e2x = cx-ax, e2y = cy-ay, e2z = cz-az;
    const nx = e1y*e2z - e1z*e2y;
    const ny = e1z*e2x - e1x*e2z;
    const nz = e1x*e2y - e1y*e2x;

    // Accumulate the same face contribution into each of the triangle's
    // vertices so shared vertices become smoothly shaded.
    for (const idx of [ia, ib, ic]) {
      normals[idx*3]   += nx;
      normals[idx*3+1] += ny;
      normals[idx*3+2] += nz;
    }
  }

  // Normalize each accumulated normal vector to unit length.
  for (let i = 0; i < numVerts; i++) {
    const x = normals[i*3], y = normals[i*3+1], z = normals[i*3+2];
    const len = Math.sqrt(x*x + y*y + z*z) || 1;
    normals[i*3]   /= len;
    normals[i*3+1] /= len;
    normals[i*3+2] /= len;
  }

  // The consumer gets raw geometry buffers plus counts for UI stats.
  return { positions, indices, normals, heights, vertexCount: numVerts, faceCount: numFaces };
}
