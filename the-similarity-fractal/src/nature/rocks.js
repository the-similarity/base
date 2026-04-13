/**
 * Procedural rock system for the nature engine.
 *
 * Produces four distinct rock archetypes (boulder, angular slab, rock cluster,
 * mossy rock) and places them via InstancedMesh for minimal draw calls.
 *
 * All geometry is baked at construction time -- vertex noise displacement is
 * applied once to the base geometry, not per frame or per instance.
 * Per-instance color variation uses the InstancedMesh color buffer so the
 * material itself is shared across all instances of a type.
 *
 * The simplex noise used for vertex displacement is the same family of noise
 * that drives the fractal terrain generator, evaluated at vertex-scale rather
 * than terrain-scale so the visual language stays coherent across scales.
 *
 * @module nature/rocks
 */

import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import {
  BIOME_WATER, BIOME_SAND, BIOME_GRASS,
  BIOME_FOREST, BIOME_ROCK, BIOME_SNOW,
  getGroundY, createLCG,
} from './shared.js';


// ─── Simplex 3D noise ────────────────────────────────────────────────────────
// Standard simplex noise implementation. Inlined to avoid external dependencies;
// same mathematical family used by fractal.js at terrain scale.

/** Canonical Ken Perlin permutation table, doubled for wrapping. */
const _p = new Uint8Array(512);
const _perm = [
  151,160,137,91,90,15,131,13,201,95,96,53,194,233,7,225,140,36,103,30,69,
  142,8,99,37,240,21,10,23,190,6,148,247,120,234,75,0,26,197,62,94,252,219,
  203,117,35,11,32,57,177,33,88,237,149,56,87,174,20,125,136,171,168,68,175,
  74,165,71,134,139,48,27,166,77,146,158,231,83,111,229,122,60,211,133,230,
  220,105,92,41,55,46,245,40,244,102,143,54,65,25,63,161,1,216,80,73,209,76,
  132,187,208,89,18,169,200,196,135,130,116,188,159,86,164,100,109,198,173,
  186,3,64,52,217,226,250,124,123,5,202,38,147,118,126,255,82,85,212,207,206,
  59,227,47,16,58,17,182,189,28,42,223,183,170,213,119,248,152,2,44,154,163,
  70,221,153,101,155,167,43,172,9,129,22,39,253,19,98,108,110,79,113,224,232,
  178,185,112,104,218,246,97,228,251,34,242,193,238,210,144,12,191,179,162,
  241,81,51,145,235,249,14,239,107,49,192,214,31,181,199,106,157,184,84,204,
  176,115,121,50,45,127,4,150,254,138,236,205,93,222,114,67,29,24,72,243,141,
  128,195,78,66,215,61,156,180
];
for (let i = 0; i < 256; i++) {
  _p[i] = _perm[i];
  _p[i + 256] = _perm[i];
}

/** 12 gradient vectors for 3D simplex (edges of a cube). */
const _grad3 = [
  [1,1,0],[-1,1,0],[1,-1,0],[-1,-1,0],
  [1,0,1],[-1,0,1],[1,0,-1],[-1,0,-1],
  [0,1,1],[0,-1,1],[0,1,-1],[0,-1,-1],
];

/**
 * 3D simplex noise in [-1, 1].
 *
 * Simplex noise partitions 3D space into tetrahedra via coordinate skewing.
 * F3 = 1/3 (skew) and G3 = 1/6 (unskew) are the exact constants for 3D.
 *
 * @param {number} x
 * @param {number} y
 * @param {number} z
 * @returns {number} Noise value in [-1, 1]
 */
function noise3D(x, y, z) {
  const F3 = 1.0 / 3.0;
  const s = (x + y + z) * F3;
  const i = Math.floor(x + s);
  const j = Math.floor(y + s);
  const k = Math.floor(z + s);

  const G3 = 1.0 / 6.0;
  const t = (i + j + k) * G3;

  const x0 = x - (i - t);
  const y0 = y - (j - t);
  const z0 = z - (k - t);

  // Determine which simplex (tetrahedron) we are in (6 possible orderings).
  let i1, j1, k1, i2, j2, k2;
  if (x0 >= y0) {
    if (y0 >= z0)      { i1=1; j1=0; k1=0; i2=1; j2=1; k2=0; }
    else if (x0 >= z0) { i1=1; j1=0; k1=0; i2=1; j2=0; k2=1; }
    else               { i1=0; j1=0; k1=1; i2=1; j2=0; k2=1; }
  } else {
    if (y0 < z0)       { i1=0; j1=0; k1=1; i2=0; j2=1; k2=1; }
    else if (x0 < z0)  { i1=0; j1=1; k1=0; i2=0; j2=1; k2=1; }
    else               { i1=0; j1=1; k1=0; i2=1; j2=1; k2=0; }
  }

  const x1 = x0 - i1 + G3;
  const y1 = y0 - j1 + G3;
  const z1 = z0 - k1 + G3;
  const x2 = x0 - i2 + 2.0 * G3;
  const y2 = y0 - j2 + 2.0 * G3;
  const z2 = z0 - k2 + 2.0 * G3;
  const x3 = x0 - 1.0 + 3.0 * G3;
  const y3 = y0 - 1.0 + 3.0 * G3;
  const z3 = z0 - 1.0 + 3.0 * G3;

  const ii = i & 255;
  const jj = j & 255;
  const kk = k & 255;

  const gi0 = _p[ii + _p[jj + _p[kk]]] % 12;
  const gi1 = _p[ii + i1 + _p[jj + j1 + _p[kk + k1]]] % 12;
  const gi2 = _p[ii + i2 + _p[jj + j2 + _p[kk + k2]]] % 12;
  const gi3 = _p[ii + 1 + _p[jj + 1 + _p[kk + 1]]] % 12;

  const _dot = (g, px, py, pz) => g[0] * px + g[1] * py + g[2] * pz;

  let n0 = 0, n1 = 0, n2 = 0, n3 = 0;

  let t0 = 0.6 - x0*x0 - y0*y0 - z0*z0;
  if (t0 >= 0) { t0 *= t0; n0 = t0 * t0 * _dot(_grad3[gi0], x0, y0, z0); }
  let t1 = 0.6 - x1*x1 - y1*y1 - z1*z1;
  if (t1 >= 0) { t1 *= t1; n1 = t1 * t1 * _dot(_grad3[gi1], x1, y1, z1); }
  let t2 = 0.6 - x2*x2 - y2*y2 - z2*z2;
  if (t2 >= 0) { t2 *= t2; n2 = t2 * t2 * _dot(_grad3[gi2], x2, y2, z2); }
  let t3 = 0.6 - x3*x3 - y3*y3 - z3*z3;
  if (t3 >= 0) { t3 *= t3; n3 = t3 * t3 * _dot(_grad3[gi3], x3, y3, z3); }

  return 32.0 * (n0 + n1 + n2 + n3);
}


// ─── Geometry factories ──────────────────────────────────────────────────────

/**
 * Boulder: IcosahedronGeometry(0.04, 1) with radial simplex vertex noise.
 * Frequency 5x, amplitude 0.015 -- visible but no surface self-intersection.
 * @returns {THREE.BufferGeometry}
 */
function createBoulderGeometry() {
  const geo = new THREE.IcosahedronGeometry(0.04, 1);
  const pos = geo.attributes.position;

  for (let i = 0; i < pos.count; i++) {
    const vx = pos.getX(i);
    const vy = pos.getY(i);
    const vz = pos.getZ(i);

    const len = Math.sqrt(vx * vx + vy * vy + vz * vz) || 1;
    const displacement = noise3D(vx * 5, vy * 5, vz * 5) * 0.015;
    pos.setXYZ(
      i,
      vx + (vx / len) * displacement,
      vy + (vy / len) * displacement,
      vz + (vz / len) * displacement,
    );
  }

  geo.computeVertexNormals();
  return geo;
}

/**
 * Angular slab: non-uniform box (0.06 x 0.03 x 0.05) with high-frequency
 * per-axis noise (8x freq, 0.012 amplitude). Creates sharp, dramatic shapes.
 * @returns {THREE.BufferGeometry}
 */
function createAngularSlabGeometry() {
  const geo = new THREE.BoxGeometry(0.06, 0.03, 0.05, 2, 2, 2);
  const pos = geo.attributes.position;

  for (let i = 0; i < pos.count; i++) {
    const vx = pos.getX(i);
    const vy = pos.getY(i);
    const vz = pos.getZ(i);

    // Independent per-axis displacement for angular (not smooth) protrusions.
    pos.setXYZ(
      i,
      vx + noise3D(vx * 8, vy * 8, vz * 8) * 0.012,
      vy + noise3D(vx * 8 + 100, vy * 8 + 100, vz * 8 + 100) * 0.008,
      vz + noise3D(vx * 8 + 200, vy * 8 + 200, vz * 8 + 200) * 0.012,
    );
  }

  geo.computeVertexNormals();
  return geo;
}

/**
 * Rock cluster: 4 small icosahedra merged at deterministic offsets.
 * Uses mergeGeometries so the entire cluster is a single buffer for instancing.
 * @returns {THREE.BufferGeometry}
 */
function createRockClusterGeometry() {
  const parts = [];
  const SUB_ROCK_COUNT = 4;

  for (let i = 0; i < SUB_ROCK_COUNT; i++) {
    const radius = Math.abs(0.012 + noise3D(i * 7.3, 0, 0) * 0.005) + 0.008;
    const sphere = new THREE.IcosahedronGeometry(radius, 0);

    // Deterministic offsets (seeded by index) form a stable pile shape.
    const offsetX = noise3D(i * 3.7, 1.2, 0) * 0.025;
    const offsetY = Math.abs(noise3D(i * 5.1, 2.3, 0)) * 0.01;
    const offsetZ = noise3D(i * 4.3, 3.1, 0) * 0.025;

    const posAttr = sphere.attributes.position;
    for (let v = 0; v < posAttr.count; v++) {
      posAttr.setXYZ(
        v,
        posAttr.getX(v) + offsetX,
        posAttr.getY(v) + offsetY,
        posAttr.getZ(v) + offsetZ,
      );
    }
    parts.push(sphere);
  }

  const merged = mergeGeometries(parts, false);
  merged.computeVertexNormals();
  parts.forEach(p => p.dispose());
  return merged;
}

/**
 * Mossy rock: boulder with vertex-color green tint on upward-facing faces
 * (normal.y > 0.5). Forest biome only -- placement logic enforces this.
 * @returns {THREE.BufferGeometry}
 */
function createMossyRockGeometry() {
  const geo = createBoulderGeometry();
  const normals = geo.attributes.normal;
  const count = geo.attributes.position.count;
  const colors = new Float32Array(count * 3);

  const baseR = 0.42, baseG = 0.40, baseB = 0.38; // warm gray
  const mossR = 0.22, mossG = 0.45, mossB = 0.18; // muted forest green

  for (let i = 0; i < count; i++) {
    const ny = normals.getY(i);
    // Linear blend: 0 below 0.5, ramps to 1.0 at ny=1.0.
    const blend = ny > 0.5 ? Math.min(1.0, (ny - 0.5) * 2.0) : 0;

    colors[i * 3]     = baseR + (mossR - baseR) * blend;
    colors[i * 3 + 1] = baseG + (mossG - baseG) * blend;
    colors[i * 3 + 2] = baseB + (mossB - baseB) * blend;
  }

  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  return geo;
}


// ─── Materials ───────────────────────────────────────────────────────────────

function createRockMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0x6b6560, roughness: 0.92, metalness: 0.05, flatShading: true,
  });
}

function createSlabMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0x4a4845, roughness: 0.95, metalness: 0.08, flatShading: true,
  });
}

function createMossyMaterial() {
  return new THREE.MeshStandardMaterial({
    vertexColors: true, roughness: 0.88, metalness: 0.02, flatShading: true,
  });
}


// ─── Biome-to-rock-type routing ──────────────────────────────────────────────

/**
 * Route a placement to the correct type bucket based on biome.
 *
 * Extracted to avoid duplicating the biome branching logic between the
 * explicit-feature pass and the scatter pass.
 *
 * @param {number} biome - Biome ID at placement location
 * @param {Object} placement - The placement object
 * @param {Object} buckets - { boulder, slab, cluster, mossy } arrays
 * @param {number} maxPerType - Cap per bucket
 * @param {() => number} rng - Seeded random function
 */
function routePlacement(biome, placement, buckets, maxPerType, rng) {
  if (biome === BIOME_FOREST) {
    if (buckets.mossy.length < maxPerType) buckets.mossy.push(placement);
  } else if (biome === BIOME_ROCK) {
    // Rock biome gets a mix of all non-mossy types.
    const roll = rng();
    if (roll < 0.4 && buckets.boulder.length < maxPerType) buckets.boulder.push(placement);
    else if (roll < 0.7 && buckets.slab.length < maxPerType) buckets.slab.push(placement);
    else if (buckets.cluster.length < maxPerType) buckets.cluster.push(placement);
  } else if (biome === BIOME_SAND || biome === BIOME_GRASS) {
    if (buckets.boulder.length < maxPerType) buckets.boulder.push(placement);
  } else if (biome === BIOME_SNOW) {
    if (buckets.slab.length < maxPerType) buckets.slab.push(placement);
  }
  // BIOME_WATER: no rocks
}


// ─── Main system class ──────────────────────────────────────────────────────

/**
 * RockSystem manages all rock instances in the scene.
 *
 * Lifecycle:
 * 1. Construct with scene reference and options.
 * 2. Call populate() with feature data and terrain info to place rocks.
 * 3. Call dispose() when tearing down the scene to free GPU resources.
 *
 * After populate(), instance transforms and colors are static -- no per-frame
 * updates. Calling populate() again disposes previous meshes first. The system
 * does not hold references to external terrain data after populate().
 *
 * 4 draw calls total (one InstancedMesh per rock type), capped by maxPerType.
 */
export class RockSystem {
  /**
   * @param {THREE.Scene} scene - Scene to add rock meshes to.
   * @param {Object} [options={}]
   * @param {number} [options.maxPerType=500] - Maximum instances per rock type.
   * @param {number} [options.seed=42] - Random seed for placement jitter.
   */
  constructor(scene, options = {}) {
    this.scene = scene;
    this.maxPerType = options.maxPerType || 500;
    this.seed = options.seed || 42;

    /** @type {THREE.Group|null} */
    this._group = null;
    /** @type {THREE.BufferGeometry[]} */
    this._geometries = [];
    /** @type {THREE.Material[]} */
    this._materials = [];
  }

  /**
   * Place rocks across the terrain from explicit features + biome scatter.
   *
   * @param {Array} features - Feature objects {x, y, z, type, scale, rotation, variant}.
   * @param {THREE.Mesh} terrainMesh - Terrain mesh for raycasting ground height.
   * @param {Object} biomeMap - Terrain maps {biomeMap, heightMap, size, worldScale}.
   */
  populate(features, terrainMesh, biomeMap) {
    this.dispose();

    this._group = new THREE.Group();
    this._group.name = 'RockSystem';

    const boulderGeo = createBoulderGeometry();
    const slabGeo    = createAngularSlabGeometry();
    const clusterGeo = createRockClusterGeometry();
    const mossyGeo   = createMossyRockGeometry();
    this._geometries = [boulderGeo, slabGeo, clusterGeo, mossyGeo];

    const rockMat  = createRockMaterial();
    const slabMat  = createSlabMaterial();
    const mossyMat = createMossyMaterial();
    this._materials = [rockMat, slabMat, mossyMat];

    const buckets = { boulder: [], slab: [], cluster: [], mossy: [] };
    const raycaster = new THREE.Raycaster();
    const rng = createLCG(this.seed);

    const gridSize   = biomeMap?.size || 128;
    const worldScale = biomeMap?.worldScale || 10;
    const biomes     = biomeMap?.biomeMap || null;

    // ── Explicit features from backend ─────────────────────────────────
    if (features && features.length > 0) {
      for (const f of features) {
        const wx = (f.x / gridSize - 0.5) * worldScale;
        const wz = (f.y / gridSize - 0.5) * worldScale;
        const groundY = getGroundY(raycaster, terrainMesh, wx, wz);
        if (groundY === null) continue;

        const gx = Math.round(f.x);
        const gz = Math.round(f.y);
        const biome = biomes ? biomes[gz * gridSize + gx] : BIOME_ROCK;

        const placement = {
          x: wx, y: groundY, z: wz,
          scale: f.scale || 1.0,
          rotation: f.rotation || 0,
          variant: f.variant || 0,
        };

        routePlacement(biome, placement, buckets, this.maxPerType, rng);
      }
    }

    // ── Biome scatter pass ─────────────────────────────────────────────
    if (biomes) {
      const scatterStep = Math.max(2, Math.floor(gridSize / 32));

      for (let gz = 0; gz < gridSize; gz += scatterStep) {
        for (let gx = 0; gx < gridSize; gx += scatterStep) {
          const biome = biomes[gz * gridSize + gx];

          // Per-biome scatter probability.
          let prob = 0;
          if (biome === BIOME_ROCK)        prob = 0.6;
          else if (biome === BIOME_FOREST) prob = 0.15;
          else if (biome === BIOME_GRASS)  prob = 0.05;
          else if (biome === BIOME_SAND)   prob = 0.08;
          else if (biome === BIOME_SNOW)   prob = 0.1;
          else continue;

          if (rng() > prob) continue;

          // Jitter to break grid alignment.
          const cellWorld = (worldScale / gridSize) * scatterStep * 0.8;
          const wx = (gx / gridSize - 0.5) * worldScale + (rng() - 0.5) * cellWorld;
          const wz = (gz / gridSize - 0.5) * worldScale + (rng() - 0.5) * cellWorld;

          const groundY = getGroundY(raycaster, terrainMesh, wx, wz);
          if (groundY === null) continue;

          const placement = {
            x: wx, y: groundY, z: wz,
            scale: 0.5 + rng() * 1.0,
            rotation: rng() * Math.PI * 2,
            variant: Math.floor(rng() * 4),
          };

          routePlacement(biome, placement, buckets, this.maxPerType, rng);
        }
      }
    }

    // ── Build InstancedMeshes ──────────────────────────────────────────
    this._buildInstancedMesh(boulderGeo, rockMat, buckets.boulder, 'boulders', false);
    this._buildInstancedMesh(slabGeo, slabMat, buckets.slab, 'slabs', false);
    this._buildInstancedMesh(clusterGeo, rockMat, buckets.cluster, 'clusters', false);
    this._buildInstancedMesh(mossyGeo, mossyMat, buckets.mossy, 'mossy', true);

    this.scene.add(this._group);
  }

  /**
   * Build one InstancedMesh from placements and add to the group.
   * @private
   */
  _buildInstancedMesh(geo, mat, placements, name, skipColor) {
    if (placements.length === 0) return;

    const count = Math.min(placements.length, this.maxPerType);
    const instanced = new THREE.InstancedMesh(geo, mat, count);
    instanced.name = `rock_${name}`;
    instanced.frustumCulled = true;

    const dummy = new THREE.Object3D();
    // Reuse a single Color object to avoid per-instance allocation.
    const tmpColor = new THREE.Color();

    for (let i = 0; i < count; i++) {
      const p = placements[i];

      // Small Y offset (0.005 * scale) prevents z-fighting with terrain.
      dummy.position.set(p.x, p.y + 0.005 * p.scale, p.z);
      dummy.scale.set(p.scale, p.scale * (0.5 + (p.variant % 3) * 0.2), p.scale);
      dummy.rotation.set(p.rotation * 0.2, p.rotation, 0);
      dummy.updateMatrix();
      instanced.setMatrixAt(i, dummy.matrix);

      if (!skipColor) {
        // Warm gray to cool gray variation per instance.
        const warmth = 0.33 + p.variant * 0.04 + (i % 7) * 0.02;
        tmpColor.setRGB(warmth + 0.02, warmth, warmth - 0.02);
        instanced.setColorAt(i, tmpColor);
      }
    }

    instanced.instanceMatrix.needsUpdate = true;
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;

    this._group.add(instanced);
  }

  /**
   * Dispose all GPU resources. Safe to call multiple times.
   */
  dispose() {
    if (this._group) {
      this.scene.remove(this._group);
      this._group.traverse((child) => {
        if (child.isMesh) {
          child.geometry?.dispose();
          child.material?.dispose();
        }
      });
      this._group = null;
    }

    // Defensive: dispose cached refs not yet attached to the group.
    this._geometries.forEach(g => g.dispose());
    this._materials.forEach(m => m.dispose());
    this._geometries = [];
    this._materials = [];
  }
}
