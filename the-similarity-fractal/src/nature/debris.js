/**
 * Environmental debris system for the nature engine.
 *
 * Produces three debris archetypes (fallen logs, sticks/twigs, pebbles) and
 * scatters them across the terrain via InstancedMesh for minimal draw calls.
 *
 * These are small-scale environmental clutter -- not gameplay-significant,
 * purely visual density. Placement is entirely scatter-driven from biome data
 * (no explicit backend features). Three InstancedMesh draw calls total.
 *
 * @module nature/debris
 */

import * as THREE from 'three';
import {
  BIOME_WATER, BIOME_SAND, BIOME_GRASS,
  BIOME_FOREST, BIOME_ROCK,
  getGroundY, createLCG,
} from './shared.js';


// ─── Geometry factories ──────────────────────────────────────────────────────

/**
 * Fallen log: horizontal cylinder (radius 0.015, default length 0.2) with
 * parabolic sag. Created along Y then rotated to X-axis so Y-rotation
 * randomization places it flat on the ground.
 *
 * @param {number} [length=0.2] - Log length in world units.
 * @returns {THREE.BufferGeometry}
 */
function createFallenLogGeometry(length = 0.2) {
  const geo = new THREE.CylinderGeometry(0.015, 0.018, length, 5, 4);
  geo.rotateZ(Math.PI / 2); // align along X axis (flat on ground)

  // Parabolic sag: center droops, ends stay level.
  const pos = geo.attributes.position;
  const halfLen = length / 2;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const norm = x / halfLen; // [-1, 1]
    pos.setY(i, pos.getY(i) - (1.0 - norm * norm) * 0.01);
  }

  geo.computeVertexNormals();
  return geo;
}

/**
 * Stick/twig: minimal thin cylinder (radius 0.003, length 0.05, 3 radial segments).
 * Reads as tiny dark lines on the forest floor.
 * @returns {THREE.BufferGeometry}
 */
function createStickGeometry() {
  const geo = new THREE.CylinderGeometry(0.003, 0.002, 0.05, 3, 1);
  geo.rotateZ(Math.PI / 2);
  return geo;
}

/**
 * Pebble: tiny sphere (radius 0.005, 4x3 segments).
 * @returns {THREE.BufferGeometry}
 */
function createPebbleGeometry() {
  return new THREE.SphereGeometry(0.005, 4, 3);
}


// ─── Materials ───────────────────────────────────────────────────────────────

function createLogMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0x5c3a1e, roughness: 0.95, metalness: 0.0, flatShading: true,
  });
}

function createStickMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0x4a3015, roughness: 0.9, metalness: 0.0,
  });
}

function createPebbleMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0x888480, roughness: 0.85, metalness: 0.05, flatShading: true,
  });
}


// ─── Main system class ──────────────────────────────────────────────────────

/**
 * DebrisSystem manages environmental clutter (logs, sticks, pebbles).
 *
 * Lifecycle:
 * 1. Construct with scene reference and options.
 * 2. Call populate() with terrain maps and mesh to scatter debris.
 * 3. Call dispose() on scene teardown.
 *
 * After populate(), all transforms are static. Calling populate() again is safe
 * (disposes previous). Three draw calls total regardless of instance count.
 */
export class DebrisSystem {
  /**
   * @param {THREE.Scene} scene
   * @param {Object} [options={}]
   * @param {number} [options.maxLogs=200]
   * @param {number} [options.maxSticks=400]
   * @param {number} [options.maxPebbles=600]
   * @param {number} [options.seed=123]
   */
  constructor(scene, options = {}) {
    this.scene = scene;
    this.maxLogs    = options.maxLogs || 200;
    this.maxSticks  = options.maxSticks || 400;
    this.maxPebbles = options.maxPebbles || 600;
    this.seed       = options.seed || 123;

    /** @type {THREE.Group|null} */
    this._group = null;
    /** @type {THREE.BufferGeometry[]} */
    this._geometries = [];
    /** @type {THREE.Material[]} */
    this._materials = [];
  }

  /**
   * Scatter debris across terrain using biome data.
   *
   * Unlike rocks, debris is entirely scatter-driven -- no explicit backend
   * features. All placement comes from biome sampling + randomized grid walk.
   *
   * @param {Object} terrainMaps - {biomeMap, heightMap, waterMap, size, worldScale}
   * @param {THREE.Mesh} terrainMesh - Terrain mesh for raycasting ground Y.
   */
  populate(terrainMaps, terrainMesh) {
    this.dispose();

    this._group = new THREE.Group();
    this._group.name = 'DebrisSystem';

    // Only one log geometry variant -- scale variation provides enough diversity
    // without tripling draw calls.
    const logGeo    = createFallenLogGeometry(0.2);
    const stickGeo  = createStickGeometry();
    const pebbleGeo = createPebbleGeometry();
    this._geometries = [logGeo, stickGeo, pebbleGeo];

    const logMat    = createLogMaterial();
    const stickMat  = createStickMaterial();
    const pebbleMat = createPebbleMaterial();
    this._materials = [logMat, stickMat, pebbleMat];

    const gridSize   = terrainMaps?.size || 128;
    const worldScale = terrainMaps?.worldScale || 10;
    const biomes     = terrainMaps?.biomeMap || null;
    const waterMap   = terrainMaps?.waterMap || null;

    if (!biomes) {
      // No biome data (e.g., classic fractal mode) -- nothing to scatter.
      this.scene.add(this._group);
      return;
    }

    const rng = createLCG(this.seed);
    const raycaster = new THREE.Raycaster();

    const logPlacements    = [];
    const stickPlacements  = [];
    const pebblePlacements = [];

    // Grid walk step sizes balance density vs raycast cost.
    const logStep    = Math.max(3, Math.floor(gridSize / 20));
    const stickStep  = Math.max(2, Math.floor(gridSize / 28));
    const pebbleStep = Math.max(2, Math.floor(gridSize / 32));

    // Helper: convert grid coords to jittered world coords.
    const toWorld = (gx, gz, step) => {
      const cellWorld = (worldScale / gridSize) * step;
      return {
        wx: (gx / gridSize - 0.5) * worldScale + (rng() - 0.5) * cellWorld * 0.7,
        wz: (gz / gridSize - 0.5) * worldScale + (rng() - 0.5) * cellWorld * 0.7,
      };
    };

    // ── Fallen logs (forest only, 20% chance) ──────────────────────────
    for (let gz = 0; gz < gridSize; gz += logStep) {
      for (let gx = 0; gx < gridSize; gx += logStep) {
        if (logPlacements.length >= this.maxLogs) break;
        if (biomes[gz * gridSize + gx] !== BIOME_FOREST) continue;
        if (rng() > 0.2) continue;

        const { wx, wz } = toWorld(gx, gz, logStep);
        const groundY = getGroundY(raycaster, terrainMesh, wx, wz);
        if (groundY === null) continue;

        logPlacements.push({
          x: wx, y: groundY, z: wz,
          rotation: rng() * Math.PI * 2,
          variant: Math.floor(rng() * 3),
          scale: 0.8 + rng() * 0.5,
        });
      }
    }

    // ── Sticks/twigs (forest only, 30% chance) ─────────────────────────
    for (let gz = 0; gz < gridSize; gz += stickStep) {
      for (let gx = 0; gx < gridSize; gx += stickStep) {
        if (stickPlacements.length >= this.maxSticks) break;
        if (biomes[gz * gridSize + gx] !== BIOME_FOREST) continue;
        if (rng() > 0.3) continue;

        const { wx, wz } = toWorld(gx, gz, stickStep);
        const groundY = getGroundY(raycaster, terrainMesh, wx, wz);
        if (groundY === null) continue;

        stickPlacements.push({
          x: wx, y: groundY, z: wz,
          rotation: rng() * Math.PI,
          tilt: (rng() - 0.5) * 0.3,
          scale: 0.6 + rng() * 0.8,
        });
      }
    }

    // ── Pebbles (sand/rock/grass, density varies) ──────────────────────
    // Probability map: sand 35%, rock 25%, grass 8%.
    const pebbleProb = { [BIOME_SAND]: 0.35, [BIOME_ROCK]: 0.25, [BIOME_GRASS]: 0.08 };

    for (let gz = 0; gz < gridSize; gz += pebbleStep) {
      for (let gx = 0; gx < gridSize; gx += pebbleStep) {
        if (pebblePlacements.length >= this.maxPebbles) break;

        const idx = gz * gridSize + gx;
        const biome = biomes[idx];
        const prob = pebbleProb[biome];
        if (!prob || rng() > prob) continue;

        const { wx, wz } = toWorld(gx, gz, pebbleStep);
        const groundY = getGroundY(raycaster, terrainMesh, wx, wz);
        if (groundY === null) continue;

        // Near-water detection: check self + cardinal neighbors.
        const nearWater = waterMap && (
          waterMap[idx] === 1 ||
          (gx > 0 && waterMap[idx - 1] === 1) ||
          (gx < gridSize - 1 && waterMap[idx + 1] === 1) ||
          (gz > 0 && waterMap[idx - gridSize] === 1) ||
          (gz < gridSize - 1 && waterMap[idx + gridSize] === 1)
        );

        pebblePlacements.push({
          x: wx, y: groundY, z: wz,
          scale: 0.5 + rng() * 1.0,
          nearWater: !!nearWater,
        });
      }
    }

    // ── Build InstancedMeshes ──────────────────────────────────────────
    if (logPlacements.length > 0) {
      this._buildLogMesh(logGeo, logMat, logPlacements);
    }
    if (stickPlacements.length > 0) {
      this._buildStickMesh(stickGeo, stickMat, stickPlacements);
    }
    if (pebblePlacements.length > 0) {
      this._buildPebbleMesh(pebbleGeo, pebbleMat, pebblePlacements);
    }

    this.scene.add(this._group);
  }

  /** @private */
  _buildLogMesh(geo, mat, placements) {
    const count = Math.min(placements.length, this.maxLogs);
    const instanced = new THREE.InstancedMesh(geo, mat, count);
    instanced.name = 'debris_logs';
    instanced.frustumCulled = true;

    const dummy = new THREE.Object3D();
    const tmpColor = new THREE.Color();
    // Use the shared LCG for deterministic tilt (not Math.random which breaks determinism).
    const rng = createLCG(this.seed + 999);

    for (let i = 0; i < count; i++) {
      const p = placements[i];

      dummy.position.set(p.x, p.y + 0.008, p.z);
      // X scale controls length, Y/Z control thickness.
      const lengthScale = p.scale * (0.8 + p.variant * 0.3);
      dummy.scale.set(lengthScale, p.scale * 0.8, p.scale * 0.8);
      dummy.rotation.set((rng() - 0.5) * 0.1, p.rotation, 0);
      dummy.updateMatrix();
      instanced.setMatrixAt(i, dummy.matrix);

      // Brown color variation: darker to lighter bark tones.
      const warmth = 0.25 + (i % 5) * 0.03;
      tmpColor.setRGB(warmth + 0.1, warmth * 0.7, warmth * 0.4);
      instanced.setColorAt(i, tmpColor);
    }

    instanced.instanceMatrix.needsUpdate = true;
    if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;
    this._group.add(instanced);
  }

  /** @private */
  _buildStickMesh(geo, mat, placements) {
    const count = Math.min(placements.length, this.maxSticks);
    const instanced = new THREE.InstancedMesh(geo, mat, count);
    instanced.name = 'debris_sticks';
    instanced.frustumCulled = true;

    const dummy = new THREE.Object3D();

    for (let i = 0; i < count; i++) {
      const p = placements[i];
      dummy.position.set(p.x, p.y + 0.002, p.z);
      dummy.scale.set(p.scale, p.scale, p.scale);
      dummy.rotation.set(p.tilt || 0, p.rotation, 0);
      dummy.updateMatrix();
      instanced.setMatrixAt(i, dummy.matrix);
    }

    instanced.instanceMatrix.needsUpdate = true;
    this._group.add(instanced);
  }

  /** @private */
  _buildPebbleMesh(geo, mat, placements) {
    const count = Math.min(placements.length, this.maxPebbles);
    const instanced = new THREE.InstancedMesh(geo, mat, count);
    instanced.name = 'debris_pebbles';
    instanced.frustumCulled = true;

    const dummy = new THREE.Object3D();
    const tmpColor = new THREE.Color();
    const sandColor = new THREE.Color(0.78, 0.70, 0.52);
    const grayColor = new THREE.Color(0.55, 0.53, 0.50);

    for (let i = 0; i < count; i++) {
      const p = placements[i];

      dummy.position.set(p.x, p.y + 0.002, p.z);
      const s = p.scale;
      dummy.scale.set(s * 1.1, s * 0.7, s * 1.1); // flattened
      dummy.rotation.set(0, i * 1.37, 0); // pseudo-random via index
      dummy.updateMatrix();
      instanced.setMatrixAt(i, dummy.matrix);

      // Sand-colored near water, gray elsewhere.
      const base = p.nearWater ? sandColor : grayColor;
      const variation = ((i * 7 + 3) % 11) * 0.008 - 0.04;
      tmpColor.setRGB(
        base.r + variation,
        base.g + variation * 0.8,
        base.b + variation * 0.6,
      );
      instanced.setColorAt(i, tmpColor);
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

    this._geometries.forEach(g => g.dispose());
    this._materials.forEach(m => m.dispose());
    this._geometries = [];
    this._materials = [];
  }
}
