/**
 * Colorful flower accents scattered across grass biome cells.
 *
 * Renders sparse flower instances as tiny 5-petal star shapes via
 * InstancedMesh with per-instance color. Flowers are purely decorative
 * and have no animation — they provide static color contrast against
 * the green grass and swaying blades.
 *
 * Placement:
 *   Flowers are placed at roughly 1 per 4-5 grass biome cells, making
 *   them noticeably sparser than grass. Each instance gets a random color
 *   from a palette of 6 flower types (red, yellow, white, purple, blue, pink).
 *
 * Lifecycle:
 *   1. Construct FlowerSystem(scene, options)
 *   2. Call populate(terrainMaps, terrainMesh)
 *   3. Call dispose() on teardown
 *
 * Immutability: After populate(), no buffers are mutated. Flowers are
 * fully static geometry with no per-frame update cost.
 */

import * as THREE from 'three';
import { BIOME_GRASS } from '../world/terrain-sampler.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Radius of each flower disc/star in world units. */
const FLOWER_RADIUS = 0.015;

/** Number of petals in the star shape. */
const PETAL_COUNT = 5;

/** Maximum flower instances (GPU budget). */
const DEFAULT_MAX_FLOWERS = 2000;

/**
 * Probability that any qualifying grass cell gets a flower.
 * At ~0.22, roughly 1 in 4-5 cells will have a flower.
 */
const FLOWER_PROBABILITY = 0.22;

/**
 * Flower color palette — 6 types.
 * Colors are chosen to contrast well against green terrain.
 */
const FLOWER_COLORS = [
  new THREE.Color(0.85, 0.15, 0.15), // Red
  new THREE.Color(0.90, 0.85, 0.15), // Yellow
  new THREE.Color(0.95, 0.95, 0.92), // White
  new THREE.Color(0.55, 0.20, 0.70), // Purple
  new THREE.Color(0.20, 0.35, 0.80), // Blue
  new THREE.Color(0.85, 0.40, 0.60), // Pink
];

// ---------------------------------------------------------------------------
// Geometry builder
// ---------------------------------------------------------------------------

/**
 * Build a 5-petal star flower as a flat BufferGeometry.
 *
 * The star is constructed as a triangle fan from the center. Alternating
 * vertices sit at the outer radius (petal tips) and inner radius (notches
 * between petals), creating a recognizable flower silhouette.
 *
 * The geometry lies in the XZ plane (flat on the ground) with Y=0,
 * plus a tiny Y offset so it sits just above the terrain surface.
 *
 * @returns {THREE.BufferGeometry} Star-shaped petal geometry.
 */
function buildFlowerGeometry() {
  const outerR = FLOWER_RADIUS;
  const innerR = FLOWER_RADIUS * 0.45; // Notch depth between petals
  const vertCount = PETAL_COUNT * 2;   // Alternating outer/inner
  const yOffset = 0.005;               // Tiny lift above ground to avoid z-fighting

  // Center vertex + ring vertices.
  const positions = [0, yOffset, 0]; // Center
  const indices = [];

  for (let i = 0; i < vertCount; i++) {
    const angle = (i / vertCount) * Math.PI * 2;
    const r = i % 2 === 0 ? outerR : innerR;
    positions.push(
      Math.cos(angle) * r,
      yOffset,
      Math.sin(angle) * r
    );
  }

  // Triangle fan from center (vertex 0) to each pair of ring vertices.
  for (let i = 1; i <= vertCount; i++) {
    const next = i < vertCount ? i + 1 : 1;
    indices.push(0, i, next);
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(positions, 3)
  );
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

// ---------------------------------------------------------------------------
// FlowerSystem
// ---------------------------------------------------------------------------

export class FlowerSystem {
  /**
   * Create a flower accent system.
   *
   * @param {THREE.Scene} scene - Scene to add flower meshes to.
   * @param {Object} [options={}] - Configuration overrides.
   * @param {number} [options.maxFlowers=2000] - Upper bound on flower instances.
   * @param {number} [options.probability=0.22] - Per-cell spawn probability.
   */
  constructor(scene, options = {}) {
    /** @type {THREE.Scene} */
    this.scene = scene;

    this.maxFlowers = options.maxFlowers || DEFAULT_MAX_FLOWERS;
    this.probability = options.probability || FLOWER_PROBABILITY;

    /** @type {THREE.InstancedMesh|null} */
    this._mesh = null;

    /** Root group for scene graph management. */
    this._group = new THREE.Group();
    this._group.name = 'FlowerSystem';
    this.scene.add(this._group);
  }

  /**
   * Place flower instances on grass biome cells.
   *
   * Iterates the biome map. For each grass cell, rolls against the spawn
   * probability. Winners get a single flower with a random color from the
   * 6-type palette. Ground Y is raycast onto the terrain mesh.
   *
   * @param {Object} terrainMaps - Terrain data bundle.
   * @param {Uint8Array|Array} terrainMaps.biomeMap - Flat biome ID array.
   * @param {number} terrainMaps.size - Grid dimension.
   * @param {number} [terrainMaps.worldScale=10] - World scale factor.
   * @param {THREE.Mesh} terrainMesh - Terrain surface for raycasting.
   */
  populate(terrainMaps, terrainMesh) {
    const { biomeMap, size } = terrainMaps;
    const worldScale = terrainMaps.worldScale || 10;

    if (!biomeMap || !size) return;

    const cellSize = worldScale / size;

    // Collect candidate positions — sparse sampling of grass cells.
    const candidates = [];

    for (let row = 0; row < size; row++) {
      for (let col = 0; col < size; col++) {
        const biome = biomeMap[row * size + col];
        if (biome !== BIOME_GRASS) continue;

        // Probabilistic placement: ~1 in 4-5 cells.
        if (Math.random() > this.probability) continue;

        // Random position within the cell.
        const jx = (Math.random() - 0.5) * cellSize * 0.8;
        const jz = (Math.random() - 0.5) * cellSize * 0.8;
        const wx = (col / size - 0.5) * worldScale + jx;
        const wz = (row / size - 0.5) * worldScale + jz;

        // Random color from the palette.
        const colorIdx = Math.floor(Math.random() * FLOWER_COLORS.length);

        candidates.push({ wx, wz, colorIdx });

        if (candidates.length >= this.maxFlowers) break;
      }
      if (candidates.length >= this.maxFlowers) break;
    }

    if (candidates.length === 0) return;

    const count = candidates.length;
    const geometry = buildFlowerGeometry();
    const material = new THREE.MeshStandardMaterial({
      side: THREE.DoubleSide,
      roughness: 0.7,
      metalness: 0.0,
      // Flowers are small enough that flat shading reads fine
      // and avoids the cost of smooth normal interpolation.
      flatShading: true,
    });

    const instanced = new THREE.InstancedMesh(geometry, material, count);
    const dummy = new THREE.Object3D();
    const raycaster = new THREE.Raycaster();
    const rayOrigin = new THREE.Vector3();
    const downDir = new THREE.Vector3(0, -1, 0);
    // Scratch objects reused per instance to avoid GC pressure in the loop.
    const scratchColor = new THREE.Color();
    const scratchHSL = {};

    for (let i = 0; i < count; i++) {
      const { wx, wz, colorIdx } = candidates[i];

      // Raycast for ground Y.
      let wy = 0;
      rayOrigin.set(wx, 10, wz);
      raycaster.set(rayOrigin, downDir);
      const hits = raycaster.intersectObject(terrainMesh);
      if (hits.length > 0) {
        wy = hits[0].point.y;
      }

      // Random Y rotation + slight random tilt for natural look.
      dummy.position.set(wx, wy, wz);
      dummy.rotation.set(
        (Math.random() - 0.5) * 0.15,  // Subtle X tilt
        Math.random() * Math.PI * 2,    // Full Y rotation
        0
      );
      // Scale variation: 0.6x to 1.4x base size.
      const s = 0.6 + Math.random() * 0.8;
      dummy.scale.set(s, s, s);
      dummy.updateMatrix();
      instanced.setMatrixAt(i, dummy.matrix);

      // Per-instance color from the palette with slight random variation
      // so flowers of the same type don't look identical.
      scratchColor.copy(FLOWER_COLORS[colorIdx]);
      scratchColor.getHSL(scratchHSL);
      scratchColor.setHSL(
        scratchHSL.h + (Math.random() - 0.5) * 0.03,
        Math.min(1.0, scratchHSL.s + (Math.random() - 0.5) * 0.08),
        Math.min(1.0, scratchHSL.l + (Math.random() - 0.5) * 0.06)
      );
      instanced.setColorAt(i, scratchColor);
    }

    instanced.instanceMatrix.needsUpdate = true;
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;

    this._mesh = instanced;
    this._group.add(instanced);
  }

  /**
   * Release all GPU resources. Safe to call multiple times.
   */
  dispose() {
    if (this._mesh) {
      this._mesh.geometry.dispose();
      this._mesh.material.dispose();
      this._group.remove(this._mesh);
      this._mesh = null;
    }
    this.scene.remove(this._group);
  }
}
