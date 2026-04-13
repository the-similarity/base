/**
 * Procedural tree vegetation system with wind animation.
 *
 * Renders four tree species (Oak, Pine, Birch, Palm) as merged BufferGeometry
 * instances driven by InstancedMesh for minimal draw calls. Each species has
 * a distinct silhouette built entirely from procedural Three.js primitives.
 *
 * Wind animation:
 *   The sway uses a self-similar sinusoidal pattern injected via
 *   `onBeforeCompile`. Upper vertices (above trunk height) are displaced
 *   in X/Z by:
 *
 *     displacement = amplitude * sin(time * freq + worldPos.x * 0.5 + instancePhase)
 *
 *   The phase offset per instance is derived from the instance's world X
 *   coordinate (encoded into the instance matrix), so neighboring trees
 *   sway in near-unison while distant clusters drift out of phase — a
 *   self-similar cascade that reads as natural wind propagation across
 *   a canopy without any explicit fluid simulation.
 *
 * Lifecycle:
 *   1. Construct TreeSystem(scene, options)
 *   2. Call populate(features, terrainMesh) once terrain data arrives
 *   3. Call update(time) every frame for wind animation
 *   4. Call dispose() on scene teardown to free GPU resources
 *
 * Immutability: After populate(), the instance matrices are frozen. Only the
 * vertex shader uniform `uTime` mutates each frame.
 */

import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Minimum Y threshold (normalized 0-1 within the tree mesh) above which
 *  wind displacement is applied. Vertices below this are trunk and stay rigid. */
const WIND_TRUNK_CUTOFF = 0.35;

/** Default wind amplitude in world units. Kept small for gentle sway. */
const DEFAULT_WIND_AMPLITUDE = 0.015;

/** Default angular frequency for the wind sine wave. */
const DEFAULT_WIND_SPEED = 1.2;

/** Species enum — used as keys for geometry/material caches. */
const SPECIES = {
  OAK: 'oak',
  PINE: 'pine',
  BIRCH: 'birch',
  PALM: 'palm',
};

// ---------------------------------------------------------------------------
// Geometry builders — one merged BufferGeometry per species
// ---------------------------------------------------------------------------

/**
 * Oak / broadleaf tree.
 * Thick tapered trunk cylinder + deformed sphere canopy with vertex noise
 * for organic irregular edges.
 *
 * @returns {THREE.BufferGeometry} Merged geometry centered at base origin.
 */
function buildOakGeometry() {
  // Trunk: tapered cylinder — bottom radius > top radius gives visual weight.
  const trunk = new THREE.CylinderGeometry(0.008, 0.014, 0.18, 6);
  // Shift trunk so its base sits at Y=0.
  trunk.translate(0, 0.09, 0);

  // Canopy: sphere deformed with per-vertex noise for organic silhouette.
  const canopy = new THREE.SphereGeometry(0.09, 8, 6);
  const pos = canopy.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const z = pos.getZ(i);
    // Deterministic noise from vertex position — cheap pseudo-random.
    // The sin products create a bumpy organic surface without importing
    // a noise library.
    const noise = 1.0 + 0.18 * Math.sin(x * 37.0 + y * 13.0) *
                                Math.cos(z * 23.0 + x * 7.0);
    pos.setXYZ(i, x * noise, y * noise, z * noise);
  }
  // Place canopy above trunk.
  canopy.translate(0, 0.24, 0);

  const merged = mergeGeometries([trunk, canopy], false);
  merged.computeVertexNormals();
  return merged;
}

/**
 * Pine / conifer tree.
 * Straight trunk + 3 stacked cone layers that decrease in radius going up,
 * producing the classic Christmas-tree silhouette.
 *
 * @returns {THREE.BufferGeometry}
 */
function buildPineGeometry() {
  const trunk = new THREE.CylinderGeometry(0.006, 0.01, 0.22, 5);
  trunk.translate(0, 0.11, 0);

  const parts = [trunk];

  // Three cone layers: each smaller and higher than the previous.
  // radii and heights chosen so the silhouette reads clearly at distance.
  const layers = [
    { radius: 0.08, height: 0.12, y: 0.18 },
    { radius: 0.06, height: 0.10, y: 0.26 },
    { radius: 0.04, height: 0.08, y: 0.32 },
  ];
  for (const l of layers) {
    const cone = new THREE.ConeGeometry(l.radius, l.height, 6);
    cone.translate(0, l.y, 0);
    parts.push(cone);
  }

  const merged = mergeGeometries(parts, false);
  merged.computeVertexNormals();
  return merged;
}

/**
 * Birch tree.
 * Thin white trunk + small oval (vertically stretched sphere) canopy.
 *
 * @returns {THREE.BufferGeometry}
 */
function buildBirchGeometry() {
  const trunk = new THREE.CylinderGeometry(0.004, 0.006, 0.2, 5);
  trunk.translate(0, 0.1, 0);

  // Oval canopy: sphere scaled vertically to 1.4x for an elongated crown.
  const canopy = new THREE.SphereGeometry(0.055, 7, 5);
  canopy.scale(1.0, 1.4, 1.0);
  canopy.translate(0, 0.24, 0);

  const merged = mergeGeometries([trunk, canopy], false);
  merged.computeVertexNormals();
  return merged;
}

/**
 * Palm tree.
 * Curved trunk (chain of offset cylinders) + fan-shaped top (flat cone
 * crossed with perpendicular planes to suggest fronds).
 *
 * Only placed in sand/coastal biomes by the populate() caller logic.
 *
 * @returns {THREE.BufferGeometry}
 */
function buildPalmGeometry() {
  const parts = [];

  // Curved trunk: 5 short cylinder segments, each with increasing X offset
  // to create a gentle lean. The offset follows a quadratic curve.
  const segments = 5;
  const segH = 0.05;
  for (let i = 0; i < segments; i++) {
    const seg = new THREE.CylinderGeometry(0.005, 0.007, segH, 5);
    // Quadratic lean: higher segments drift further in X.
    const xOff = (i / segments) * (i / segments) * 0.03;
    seg.translate(xOff, segH * 0.5 + i * segH, 0);
    parts.push(seg);
  }

  // Fan top: a flat cone for the central crown.
  const fan = new THREE.ConeGeometry(0.06, 0.04, 6);
  fan.translate(0.03, segments * segH + 0.02, 0);
  parts.push(fan);

  // Cross-planes for frond suggestion: two perpendicular thin quads
  // that break the cone silhouette and hint at individual leaves.
  for (let a = 0; a < 2; a++) {
    const frond = new THREE.PlaneGeometry(0.12, 0.03);
    frond.rotateY(a * Math.PI / 2);
    frond.translate(0.03, segments * segH + 0.02, 0);
    parts.push(frond);
  }

  const merged = mergeGeometries(parts, false);
  merged.computeVertexNormals();
  return merged;
}

// ---------------------------------------------------------------------------
// Wind shader injection
// ---------------------------------------------------------------------------

/**
 * Inject wind sway into a MeshStandardMaterial via onBeforeCompile.
 *
 * The injected vertex shader code:
 *   1. Reads a uniform `uTime` updated each frame.
 *   2. Computes a phase offset from the instance's world X (column 3 of
 *      the instance matrix) so each tree sways independently.
 *   3. Displaces X and Z of vertices whose local Y exceeds `trunkCutoff`,
 *      weighted by how far above the cutoff they are (linear ramp).
 *
 * The displacement formula produces a self-similar wave field: trees that
 * are spatially close share a similar phase (worldPos.x * 0.5 varies slowly),
 * creating the visual effect of wind sweeping across a canopy in waves.
 *
 * @param {THREE.MeshStandardMaterial} material - Material to patch.
 * @param {number} amplitude - Sway magnitude in world units.
 * @param {number} trunkCutoff - Normalized Y below which vertices are rigid.
 * @returns {{ timeUniform: THREE.IUniform }} Handle to the time uniform for updates.
 */
function injectWindShader(material, amplitude, trunkCutoff) {
  // Shared uniform object so all materials reference the same time value.
  const timeUniform = { value: 0.0 };

  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = timeUniform;
    shader.uniforms.uWindAmplitude = { value: amplitude };
    shader.uniforms.uTrunkCutoff = { value: trunkCutoff };

    // Inject uniform declarations before main().
    shader.vertexShader = shader.vertexShader.replace(
      '#include <common>',
      /* glsl */ `
        #include <common>
        uniform float uTime;
        uniform float uWindAmplitude;
        uniform float uTrunkCutoff;
      `
    );

    // Inject displacement after all transforms are applied but before projection.
    // We operate in world space so the phase is spatially coherent.
    shader.vertexShader = shader.vertexShader.replace(
      '#include <begin_vertex>',
      /* glsl */ `
        #include <begin_vertex>

        // --- Wind sway ---
        // Extract world-space X from the instance matrix (column 3, row 0)
        // to derive a per-instance phase offset.
        // instanceMatrix is the 4x4 transform for this instance.
        float instancePhase = instanceMatrix[3][0] * 2.7 + instanceMatrix[3][2] * 1.3;

        // Normalized height factor: 0 at trunk cutoff, 1 at top of mesh.
        // Vertices below cutoff get zero displacement (rigid trunk).
        float heightFactor = smoothstep(uTrunkCutoff, 1.0, position.y / 0.4);

        // Self-similar sinusoidal displacement.
        // The sin argument includes worldPos.x * 0.5 so the wave propagates
        // spatially — nearby trees share phase, distant trees drift apart.
        float wave = sin(uTime * 1.2 + instancePhase + position.x * 0.5);

        // Secondary harmonic at higher frequency for organic irregularity.
        float wave2 = sin(uTime * 2.1 + instancePhase * 0.7) * 0.3;

        transformed.x += (wave + wave2) * uWindAmplitude * heightFactor;
        transformed.z += wave * uWindAmplitude * heightFactor * 0.6;
      `
    );
  };

  // Force material to be re-compiled with our modifications.
  material.needsUpdate = true;

  return { timeUniform };
}

// ---------------------------------------------------------------------------
// TreeSystem
// ---------------------------------------------------------------------------

export class TreeSystem {
  /**
   * Create a tree vegetation system.
   *
   * @param {THREE.Scene} scene - Scene to add tree meshes to.
   * @param {Object} [options={}] - Configuration overrides.
   * @param {number} [options.maxTrees=500] - Upper bound on total tree instances.
   * @param {number} [options.windSpeed=1.2] - Wind animation speed multiplier.
   * @param {number} [options.windAmplitude=0.015] - Wind sway magnitude.
   */
  constructor(scene, options = {}) {
    /** @type {THREE.Scene} */
    this.scene = scene;

    /** Maximum trees across all species combined. */
    this.maxTrees = options.maxTrees || 500;

    /** Wind speed multiplier applied to the time uniform each frame. */
    this.windSpeed = options.windSpeed || DEFAULT_WIND_SPEED;

    /** Wind amplitude in world units. */
    this.windAmplitude = options.windAmplitude || DEFAULT_WIND_AMPLITUDE;

    /**
     * Per-species instanced mesh groups.
     * Populated by populate(). Each entry holds { mesh, timeUniform }.
     * @type {Array<{ mesh: THREE.InstancedMesh, timeUniform: THREE.IUniform }>}
     */
    this._instances = [];

    /** Root group added to the scene — holds all instanced meshes. */
    this._group = new THREE.Group();
    this._group.name = 'TreeSystem';
    this.scene.add(this._group);
  }

  /**
   * Place trees on the terrain from a feature list.
   *
   * Each feature object should have:
   *   { type: string, x: number, y: number, z: number, scale: number,
   *     rotation: number, variant: number, biome?: number }
   *
   * Tree type mapping:
   *   - 'tree_oak' / 'tree_broadleaf' / default → Oak
   *   - 'tree_pine' / 'tree_conifer' → Pine
   *   - 'tree_birch' → Birch
   *   - 'tree_palm' → Palm (only valid on sand biome)
   *
   * Ground Y is determined by raycasting downward onto the terrain mesh,
   * falling back to feature.z * heightScale if the raycast misses.
   *
   * @param {Array<Object>} features - Feature metadata from the backend API.
   * @param {THREE.Mesh} terrainMesh - The terrain surface mesh for raycasting.
   * @param {Object} [meta={}] - Additional context.
   * @param {number} [meta.size=64] - Heightmap grid size.
   * @param {number} [meta.worldScale=10] - World scale factor.
   * @param {number} [meta.heightScale=2.1] - Vertical exaggeration.
   */
  populate(features, terrainMesh, meta = {}) {
    const size = meta.size || 64;
    const worldScale = meta.worldScale || 10;
    const heightScale = meta.heightScale || 2.1;

    // Filter to tree-type features only.
    const treeFeatures = (features || []).filter(
      f => f.type && f.type.startsWith('tree_')
    );

    if (treeFeatures.length === 0) return;

    // Bucket features by species.
    const buckets = {
      [SPECIES.OAK]: [],
      [SPECIES.PINE]: [],
      [SPECIES.BIRCH]: [],
      [SPECIES.PALM]: [],
    };

    for (const f of treeFeatures) {
      const t = f.type;
      if (t === 'tree_pine' || t === 'tree_conifer') {
        buckets[SPECIES.PINE].push(f);
      } else if (t === 'tree_birch') {
        buckets[SPECIES.BIRCH].push(f);
      } else if (t === 'tree_palm') {
        buckets[SPECIES.PALM].push(f);
      } else {
        // Default: oak / broadleaf
        buckets[SPECIES.OAK].push(f);
      }
    }

    // Geometry builders keyed by species.
    const geoBuilders = {
      [SPECIES.OAK]: buildOakGeometry,
      [SPECIES.PINE]: buildPineGeometry,
      [SPECIES.BIRCH]: buildBirchGeometry,
      [SPECIES.PALM]: buildPalmGeometry,
    };

    // Per-species canonical colors (trunk is shared brown, canopy varies).
    const speciesColors = {
      [SPECIES.OAK]: 0x3a7a2a,   // Warm green
      [SPECIES.PINE]: 0x1a4a1a,  // Dark green
      [SPECIES.BIRCH]: 0x7aaa3a, // Light green / yellow-green
      [SPECIES.PALM]: 0x4a8a3a,  // Tropical green
    };

    // Raycaster for ground Y placement. Origin vector is reused per iteration
    // to avoid allocating a new Vector3 for each of potentially 500 trees.
    const raycaster = new THREE.Raycaster();
    const rayOrigin = new THREE.Vector3();
    const downDir = new THREE.Vector3(0, -1, 0);

    const dummy = new THREE.Object3D();
    // Scratch objects reused per instance to avoid GC pressure in the loop.
    const scratchColor = new THREE.Color();
    const scratchHSL = {};

    let budgetRemaining = this.maxTrees;

    for (const [species, bucket] of Object.entries(buckets)) {
      if (bucket.length === 0 || budgetRemaining <= 0) continue;

      // Enforce shared budget across all species (first-come allocation).
      const count = Math.min(bucket.length, budgetRemaining);
      budgetRemaining -= count;

      const geometry = geoBuilders[species]();
      const material = new THREE.MeshStandardMaterial({
        color: speciesColors[species],
        roughness: 0.82,
        metalness: 0.02,
        flatShading: false,
      });

      // Inject wind animation into the material's vertex shader.
      const { timeUniform } = injectWindShader(
        material,
        this.windAmplitude,
        WIND_TRUNK_CUTOFF
      );

      const instanced = new THREE.InstancedMesh(geometry, material, count);
      instanced.castShadow = true;
      instanced.receiveShadow = true;

      for (let i = 0; i < count; i++) {
        const f = bucket[i];

        // Convert grid coordinates to world space (centered).
        const wx = (f.x / size - 0.5) * worldScale;
        const wz = (f.y / size - 0.5) * worldScale;

        // Attempt raycast for precise ground Y.
        let wy = f.z * heightScale;
        rayOrigin.set(wx, 10, wz);
        raycaster.set(rayOrigin, downDir);
        const hits = raycaster.intersectObject(terrainMesh);
        if (hits.length > 0) {
          wy = hits[0].point.y;
        }

        const scale = f.scale || 1.0;
        dummy.position.set(wx, wy, wz);
        dummy.scale.set(scale, scale, scale);
        dummy.rotation.set(0, f.rotation || Math.random() * Math.PI * 2, 0);
        dummy.updateMatrix();
        instanced.setMatrixAt(i, dummy.matrix);

        // Per-instance color variation: shift hue slightly per variant.
        scratchColor.set(speciesColors[species]);
        scratchColor.getHSL(scratchHSL);
        const variantShift = ((f.variant || 0) * 0.02) + (Math.random() - 0.5) * 0.015;
        scratchColor.setHSL(
          scratchHSL.h + variantShift,
          scratchHSL.s + (Math.random() - 0.5) * 0.05,
          scratchHSL.l + (Math.random() - 0.5) * 0.04
        );
        instanced.setColorAt(i, scratchColor);
      }

      instanced.instanceMatrix.needsUpdate = true;
      if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;

      this._instances.push({ mesh: instanced, timeUniform });
      this._group.add(instanced);
    }
  }

  /**
   * Animate wind sway. Call once per frame.
   *
   * Updates the shared `uTime` uniform that the injected vertex shader reads.
   * The actual displacement computation happens entirely on the GPU.
   *
   * @param {number} time - Elapsed time in seconds (e.g., from clock.getElapsedTime()).
   */
  update(time) {
    const t = time * this.windSpeed;
    for (const entry of this._instances) {
      entry.timeUniform.value = t;
    }
  }

  /**
   * Release all GPU resources. Safe to call multiple times.
   *
   * Removes all instanced meshes from the scene and disposes their
   * geometry and material to prevent WebGL memory leaks.
   */
  dispose() {
    for (const entry of this._instances) {
      entry.mesh.geometry.dispose();
      entry.mesh.material.dispose();
      this._group.remove(entry.mesh);
    }
    this._instances = [];
    this.scene.remove(this._group);
  }
}
