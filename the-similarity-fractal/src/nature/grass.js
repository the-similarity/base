/**
 * Dense grass patch system using instanced cross-billboards.
 *
 * Renders thousands of grass clumps on grass/forest biome cells via
 * InstancedMesh. Each grass clump is two intersecting quads (planes at 90
 * degrees to each other), vertex-colored from dark green at the base to
 * bright yellow-green at the tips.
 *
 * Wind animation:
 *   A self-similar sinusoidal displacement is injected into the vertex
 *   shader via `onBeforeCompile`. Only the upper half of each blade
 *   (uv.y > 0.5) is displaced. The phase offset is derived from each
 *   instance's world-space X/Z coordinates, producing a spatially
 *   coherent wave that sweeps across the grassland — nearby blades sway
 *   in near-unison while distant patches drift out of phase, mimicking
 *   the self-similar pattern of wind rippling across a meadow.
 *
 * LOD:
 *   Grass beyond a configurable distance threshold alpha-fades to
 *   transparent. The fade is computed per-fragment in the fragment shader
 *   using the distance between the vertex world position and a `uCameraPos`
 *   uniform updated each frame via update(). No per-instance attribute
 *   rewrite is needed -- the GPU computes fade entirely from the uniform.
 *
 * Lifecycle:
 *   1. Construct GrassSystem(scene, options)
 *   2. Call populate(terrainMaps, terrainMesh) — terrainMaps carries
 *      biomeMap, size, worldScale, heightScale
 *   3. Call update(time, cameraPosition) every frame
 *   4. Call dispose() on teardown
 *
 * Immutability: Instance matrices are written once in populate() and
 * never mutated. Only the `uTime` and `uCameraPos` shader uniforms
 * change each frame.
 */

import * as THREE from 'three';
import { BIOME_GRASS, BIOME_FOREST } from '../world/terrain-sampler.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Width of each grass billboard quad in world units. */
const BLADE_WIDTH = 0.05;

/** Height of each grass billboard quad in world units. */
const BLADE_HEIGHT = 0.08;

/** Distance (world units) at which grass starts fading. */
const DEFAULT_FADE_START = 6.0;

/** Distance (world units) at which grass is fully transparent. */
const DEFAULT_FADE_END = 9.0;

/** Maximum number of grass instances (GPU budget guard). */
const DEFAULT_MAX_INSTANCES = 8000;

/** Number of grass clumps to attempt per qualifying biome cell. */
const CLUMPS_PER_CELL = 2;

// ---------------------------------------------------------------------------
// Geometry builder
// ---------------------------------------------------------------------------

/**
 * Build a single grass clump: two intersecting quads at 90 degrees.
 *
 * The quads share a common vertical center axis. Vertex colors encode
 * a dark-to-bright gradient from base to tip so the grass reads as
 * naturally lit without a texture.
 *
 * UV layout: U spans the blade width, V spans 0 (base) to 1 (tip).
 * The wind shader keys off V to displace only upper vertices.
 *
 * @returns {THREE.BufferGeometry} Cross-billboard geometry.
 */
function buildGrassGeometry() {
  const hw = BLADE_WIDTH * 0.5; // half-width
  const h = BLADE_HEIGHT;

  // Two quads: one on XY plane, one on ZY plane, crossing at the center.
  // Each quad has 4 vertices, 2 triangles (6 indices).
  const positions = new Float32Array([
    // Quad 1 (XY plane)
    -hw, 0, 0,    hw, 0, 0,    hw, h, 0,    -hw, h, 0,
    // Quad 2 (ZY plane)
    0, 0, -hw,    0, 0, hw,    0, h, hw,    0, h, -hw,
  ]);

  const uvs = new Float32Array([
    0, 0,  1, 0,  1, 1,  0, 1,
    0, 0,  1, 0,  1, 1,  0, 1,
  ]);

  // Vertex colors: dark green at base (v=0), bright yellow-green at tip (v=1).
  const colors = new Float32Array([
    // Quad 1
    0.12, 0.28, 0.06,  0.12, 0.28, 0.06,  0.45, 0.65, 0.15,  0.45, 0.65, 0.15,
    // Quad 2
    0.12, 0.28, 0.06,  0.12, 0.28, 0.06,  0.45, 0.65, 0.15,  0.45, 0.65, 0.15,
  ]);

  const indices = [
    0, 1, 2,  0, 2, 3,  // Quad 1
    4, 5, 6,  4, 6, 7,  // Quad 2
  ];

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

// ---------------------------------------------------------------------------
// Shader injection
// ---------------------------------------------------------------------------

/**
 * Inject wind sway and distance-based LOD fade into a grass material.
 *
 * Vertex shader additions:
 *   - `uTime` uniform drives the sinusoidal displacement.
 *   - Only vertices with uv.y > 0.5 are displaced (blade tips).
 *   - Phase derived from instance world position for spatial coherence.
 *
 * Fragment shader additions:
 *   - `uCameraPos` uniform for per-fragment distance fade.
 *   - Alpha decreases linearly between fadeStart and fadeEnd.
 *
 * @param {THREE.Material} material - Material to patch.
 * @param {number} fadeStart - Distance where fade begins.
 * @param {number} fadeEnd - Distance where alpha reaches 0.
 * @returns {{ timeUniform: Object, cameraPosUniform: Object }}
 */
function injectGrassShader(material, fadeStart, fadeEnd) {
  const timeUniform = { value: 0.0 };
  const cameraPosUniform = { value: new THREE.Vector3() };

  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = timeUniform;
    shader.uniforms.uCameraPos = cameraPosUniform;
    shader.uniforms.uFadeStart = { value: fadeStart };
    shader.uniforms.uFadeEnd = { value: fadeEnd };

    // -- Vertex shader: wind sway --
    shader.vertexShader = shader.vertexShader.replace(
      '#include <common>',
      /* glsl */ `
        #include <common>
        uniform float uTime;
        varying vec3 vWorldPos;
      `
    );

    shader.vertexShader = shader.vertexShader.replace(
      '#include <begin_vertex>',
      /* glsl */ `
        #include <begin_vertex>

        // Compute world position for this vertex.
        vec4 worldPos4 = instanceMatrix * vec4(transformed, 1.0);
        vWorldPos = worldPos4.xyz;

        // Phase from instance world X/Z for self-similar spatial coherence.
        float phase = worldPos4.x * 1.7 + worldPos4.z * 1.3;

        // Only displace upper portion of blade (uv.y > 0.5).
        float tipFactor = smoothstep(0.4, 1.0, uv.y);

        // Primary wave + secondary harmonic for organic motion.
        float wave = sin(uTime * 1.5 + phase) * 0.6
                   + sin(uTime * 2.3 + phase * 0.8) * 0.4;

        transformed.x += wave * 0.012 * tipFactor;
        transformed.z += wave * 0.008 * tipFactor;
      `
    );

    // -- Fragment shader: distance-based alpha fade --
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <common>',
      /* glsl */ `
        #include <common>
        uniform vec3 uCameraPos;
        uniform float uFadeStart;
        uniform float uFadeEnd;
        varying vec3 vWorldPos;
      `
    );

    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <dithering_fragment>',
      /* glsl */ `
        #include <dithering_fragment>

        // LOD alpha fade: fully opaque at fadeStart, fully transparent at fadeEnd.
        float dist = distance(vWorldPos, uCameraPos);
        float fadeFactor = 1.0 - smoothstep(uFadeStart, uFadeEnd, dist);
        gl_FragColor.a *= fadeFactor;

        // Discard fully transparent fragments to avoid depth-buffer pollution.
        if (gl_FragColor.a < 0.01) discard;
      `
    );
  };

  material.needsUpdate = true;
  return { timeUniform, cameraPosUniform };
}

// ---------------------------------------------------------------------------
// GrassSystem
// ---------------------------------------------------------------------------

export class GrassSystem {
  /**
   * Create a grass vegetation system.
   *
   * @param {THREE.Scene} scene - Scene to add grass meshes to.
   * @param {Object} [options={}] - Configuration overrides.
   * @param {number} [options.maxInstances=8000] - Upper bound on grass clumps.
   * @param {number} [options.fadeStart=6] - Distance where LOD fade begins.
   * @param {number} [options.fadeEnd=9] - Distance where grass is invisible.
   * @param {number} [options.clumpsPerCell=2] - Grass clumps per biome cell.
   */
  constructor(scene, options = {}) {
    /** @type {THREE.Scene} */
    this.scene = scene;

    this.maxInstances = options.maxInstances || DEFAULT_MAX_INSTANCES;
    this.fadeStart = options.fadeStart || DEFAULT_FADE_START;
    this.fadeEnd = options.fadeEnd || DEFAULT_FADE_END;
    this.clumpsPerCell = options.clumpsPerCell || CLUMPS_PER_CELL;

    /** @type {THREE.InstancedMesh|null} */
    this._mesh = null;

    /** Shader uniform handles, set after populate(). */
    this._timeUniform = null;
    this._cameraPosUniform = null;

    /** Root group for scene graph management. */
    this._group = new THREE.Group();
    this._group.name = 'GrassSystem';
    this.scene.add(this._group);
  }

  /**
   * Place grass instances on qualifying biome cells.
   *
   * Iterates the biome map grid. For each cell classified as GRASS or FOREST,
   * places 1-N grass clumps with random jitter within the cell. Water, rock,
   * snow, and sand cells are skipped entirely.
   *
   * Ground Y is determined by raycasting downward onto terrainMesh.
   *
   * @param {Object} terrainMaps - Terrain data bundle.
   * @param {Uint8Array|Array} terrainMaps.biomeMap - Flat array of biome IDs (size*size).
   * @param {number} terrainMaps.size - Grid dimension (e.g., 64).
   * @param {number} [terrainMaps.worldScale=10] - World scale factor.
   * @param {number} [terrainMaps.heightScale=2.1] - Vertical exaggeration.
   * @param {THREE.Mesh} terrainMesh - Terrain surface for raycasting.
   */
  populate(terrainMaps, terrainMesh) {
    const { biomeMap, size } = terrainMaps;
    const worldScale = terrainMaps.worldScale || 10;

    if (!biomeMap || !size) return;

    const cellSize = worldScale / size;

    // Pre-compute candidate positions. We collect them first, then trim
    // to maxInstances, so the budget is respected deterministically.
    const candidates = [];

    for (let row = 0; row < size; row++) {
      for (let col = 0; col < size; col++) {
        const biome = biomeMap[row * size + col];
        if (biome !== BIOME_GRASS && biome !== BIOME_FOREST) continue;

        // Place 1-N clumps per cell with random jitter within the cell bounds.
        const numClumps = 1 + Math.floor(Math.random() * this.clumpsPerCell);
        for (let c = 0; c < numClumps; c++) {
          const jx = (Math.random() - 0.5) * cellSize * 0.9;
          const jz = (Math.random() - 0.5) * cellSize * 0.9;
          const wx = (col / size - 0.5) * worldScale + jx;
          const wz = (row / size - 0.5) * worldScale + jz;

          candidates.push({ wx, wz });

          if (candidates.length >= this.maxInstances) break;
        }
        if (candidates.length >= this.maxInstances) break;
      }
      if (candidates.length >= this.maxInstances) break;
    }

    if (candidates.length === 0) return;

    const count = candidates.length;
    const geometry = buildGrassGeometry();
    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      transparent: true,
      alphaTest: 0.01,
      roughness: 0.9,
      metalness: 0.0,
    });

    const { timeUniform, cameraPosUniform } = injectGrassShader(
      material,
      this.fadeStart,
      this.fadeEnd
    );
    this._timeUniform = timeUniform;
    this._cameraPosUniform = cameraPosUniform;

    const instanced = new THREE.InstancedMesh(geometry, material, count);
    const dummy = new THREE.Object3D();
    const raycaster = new THREE.Raycaster();
    const rayOrigin = new THREE.Vector3();
    const downDir = new THREE.Vector3(0, -1, 0);

    for (let i = 0; i < count; i++) {
      const { wx, wz } = candidates[i];

      // Raycast for ground Y.
      let wy = 0;
      rayOrigin.set(wx, 10, wz);
      raycaster.set(rayOrigin, downDir);
      const hits = raycaster.intersectObject(terrainMesh);
      if (hits.length > 0) {
        wy = hits[0].point.y;
      }

      // Random Y rotation so blades don't all face the same direction.
      dummy.position.set(wx, wy, wz);
      dummy.rotation.set(0, Math.random() * Math.PI * 2, 0);
      // Slight scale variation for visual diversity.
      const s = 0.7 + Math.random() * 0.6;
      dummy.scale.set(s, s, s);
      dummy.updateMatrix();
      instanced.setMatrixAt(i, dummy.matrix);
    }

    instanced.instanceMatrix.needsUpdate = true;
    this._mesh = instanced;
    this._group.add(instanced);
  }

  /**
   * Animate wind and update LOD fade. Call once per frame.
   *
   * @param {number} time - Elapsed time in seconds.
   * @param {THREE.Vector3} cameraPosition - Current camera world position.
   */
  update(time, cameraPosition) {
    if (!this._mesh) return;

    if (this._timeUniform) {
      this._timeUniform.value = time;
    }
    if (this._cameraPosUniform && cameraPosition) {
      this._cameraPosUniform.value.copy(cameraPosition);
    }
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
    this._timeUniform = null;
    this._cameraPosUniform = null;
    this.scene.remove(this._group);
  }
}
