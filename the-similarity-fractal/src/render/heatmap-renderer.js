/**
 * Heatmap Renderer — projects 2D data fields onto the terrain as color overlays.
 *
 * Architectural role:
 * Simulation data fields (resource density, conflict density, disease load,
 * wealth density) are 2D scalar grids. This renderer creates a semi-transparent
 * plane geometry matching the terrain extent and colors each vertex from the
 * data field using a configurable color scale.
 *
 * The heatmap plane sits slightly above the terrain surface to avoid z-fighting
 * while remaining visually fused with the ground.
 *
 * Performance considerations:
 * - Vertex colors on a subdivided plane are GPU-cheap: one draw call, no textures.
 * - Grid resolution matches the data field (not the terrain), keeping vertex
 *   count proportional to the simulation grid rather than rendering detail.
 * - showHeatmap() rebuilds vertex colors in place rather than creating new geometry,
 *   avoiding GC pressure on repeated calls.
 *
 * Lifecycle:
 * 1. Construct with scene, world geometry constants, and data grid size.
 * 2. Call showHeatmap(fieldData, colorScale) to display a data field.
 * 3. Call hide() to make the heatmap invisible without disposing it.
 * 4. Call dispose() to free GPU resources.
 *
 * Immutability: the renderer never mutates the fieldData array.
 */

import * as THREE from 'three';

// ── Constants ───────────────────────────────────────────────────────────────

// The heatmap plane hovers this far above Y=0 to avoid z-fighting with terrain.
const HEATMAP_Y_OFFSET = 0.03;

// Default opacity for the heatmap overlay. Semi-transparent so the terrain
// biome colors remain partially visible underneath.
const HEATMAP_OPACITY = 0.55;

// ── Built-in color scales ───────────────────────────────────────────────────
// Each scale maps a normalized [0, 1] value to an RGB triplet.
// These are standard scientific visualization ramps chosen for perceptual
// uniformity and colorblind accessibility.

/**
 * Color scale definitions. Each is an array of { t, r, g, b } stops.
 * Linear interpolation between stops produces the final color.
 */
const COLOR_SCALES = {
  /** Heat: black -> red -> yellow -> white. Good for density/intensity fields. */
  heat: [
    { t: 0.0, r: 0.0, g: 0.0, b: 0.0 },
    { t: 0.25, r: 0.5, g: 0.0, b: 0.0 },
    { t: 0.5, r: 1.0, g: 0.2, b: 0.0 },
    { t: 0.75, r: 1.0, g: 0.8, b: 0.0 },
    { t: 1.0, r: 1.0, g: 1.0, b: 1.0 },
  ],

  /** Viridis-like: dark purple -> blue -> green -> yellow. Perceptually uniform. */
  viridis: [
    { t: 0.0, r: 0.27, g: 0.00, b: 0.33 },
    { t: 0.25, r: 0.28, g: 0.14, b: 0.55 },
    { t: 0.5, r: 0.13, g: 0.57, b: 0.55 },
    { t: 0.75, r: 0.48, g: 0.82, b: 0.21 },
    { t: 1.0, r: 0.99, g: 0.91, b: 0.14 },
  ],

  /** Red-green diverging: red -> white -> green. Good for conflict vs cooperation. */
  diverging: [
    { t: 0.0, r: 0.8, g: 0.1, b: 0.1 },
    { t: 0.5, r: 0.95, g: 0.95, b: 0.95 },
    { t: 1.0, r: 0.1, g: 0.7, b: 0.2 },
  ],

  /** Blue: transparent blue -> deep blue. Good for water/resource fields. */
  blue: [
    { t: 0.0, r: 0.9, g: 0.9, b: 1.0 },
    { t: 0.5, r: 0.3, g: 0.4, b: 0.9 },
    { t: 1.0, r: 0.05, g: 0.1, b: 0.6 },
  ],
};

/**
 * Sample a color scale at a given normalized value.
 *
 * @param {Array<{t:number, r:number, g:number, b:number}>} stops - Color stops.
 * @param {number} t - Normalized value in [0, 1].
 * @returns {{r: number, g: number, b: number}}
 */
function sampleScale(stops, t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i].t) {
      const a = stops[i - 1];
      const b = stops[i];
      const f = (t - a.t) / (b.t - a.t);
      return {
        r: a.r + (b.r - a.r) * f,
        g: a.g + (b.g - a.g) * f,
        b: a.b + (b.b - a.b) * f,
      };
    }
  }
  const last = stops[stops.length - 1];
  return { r: last.r, g: last.g, b: last.b };
}

/**
 * Projects 2D scalar data fields onto the terrain as vertex-colored overlays.
 */
export class HeatmapRenderer {
  /**
   * @param {THREE.Scene} scene - The live Three.js scene.
   * @param {number} worldScale - Horizontal world extent.
   * @param {number} heightScale - Vertical exaggeration factor.
   * @param {number} gridSize - Data field grid resolution (e.g. 64 for a 64x64 field).
   */
  constructor(scene, worldScale, heightScale, gridSize) {
    /** @type {THREE.Scene} */
    this._scene = scene;

    /** @type {number} */
    this._worldScale = worldScale;

    /** @type {number} */
    this._heightScale = heightScale;

    /** @type {number} Data field grid resolution along each axis. */
    this._gridSize = gridSize;

    // ── Build the heatmap plane geometry ──────────────────────────────────
    // PlaneGeometry subdivided to match the data grid. Each vertex maps to
    // one data cell, so vertex colors directly encode the field values.
    // The plane is rotated to lie in the XZ plane (matching terrain orientation).
    const geometry = new THREE.PlaneGeometry(
      worldScale,
      worldScale,
      gridSize - 1,
      gridSize - 1
    );
    geometry.rotateX(-Math.PI / 2);

    // Pre-allocate the vertex color buffer. Initially all zeros (black/transparent).
    const colorArray = new Float32Array(geometry.attributes.position.count * 3);
    geometry.setAttribute('color', new THREE.BufferAttribute(colorArray, 3));

    const material = new THREE.MeshBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: HEATMAP_OPACITY,
      side: THREE.DoubleSide,
      depthWrite: false, // Prevent the semi-transparent plane from occluding terrain
    });

    /** @type {THREE.Mesh} The heatmap overlay plane. */
    this._mesh = new THREE.Mesh(geometry, material);
    this._mesh.position.y = HEATMAP_Y_OFFSET;
    this._mesh.visible = false; // Hidden until showHeatmap() is called.

    this._scene.add(this._mesh);
  }

  /**
   * Display a data field as a colored heatmap overlay.
   *
   * @param {number[]|Float32Array} fieldData - Row-major 2D scalar field,
   *   length must equal gridSize * gridSize. Values should be normalized to [0, 1]
   *   for best visual results, but out-of-range values are clamped.
   * @param {string|Array} colorScale - Either a built-in scale name ('heat', 'viridis',
   *   'diverging', 'blue') or a custom array of { t, r, g, b } stops.
   */
  showHeatmap(fieldData, colorScale = 'heat') {
    if (!fieldData) return;

    const expectedLength = this._gridSize * this._gridSize;
    if (fieldData.length !== expectedLength) {
      // Dimension mismatch — the field does not match our grid. Log a warning
      // but do not crash. This is a debug tool; graceful degradation is preferred.
      console.warn(
        `[HeatmapRenderer] fieldData length ${fieldData.length} does not match ` +
        `expected ${expectedLength} (gridSize=${this._gridSize}). Skipping.`
      );
      return;
    }

    // Resolve the color scale: either a built-in name or a custom stops array.
    const stops = typeof colorScale === 'string'
      ? (COLOR_SCALES[colorScale] || COLOR_SCALES.heat)
      : colorScale;

    // ── Auto-normalize if values exceed [0, 1] ─────────────────────────
    // We find the actual data range and normalize to [0, 1]. If the data is
    // already in [0, 1], this is a near-noop (min~0, max~1).
    let min = Infinity;
    let max = -Infinity;
    for (let i = 0; i < fieldData.length; i++) {
      const v = fieldData[i];
      if (v < min) min = v;
      if (v > max) max = v;
    }
    const range = max - min;
    // Avoid division by zero when all values are identical.
    const invRange = range > 1e-10 ? 1.0 / range : 0;

    // ── Write vertex colors from the data field ─────────────────────────
    const colorAttr = this._mesh.geometry.attributes.color;
    const colors = colorAttr.array;

    for (let i = 0; i < fieldData.length; i++) {
      // Normalize the raw value to [0, 1].
      const normalized = (fieldData[i] - min) * invRange;
      const c = sampleScale(stops, normalized);

      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }

    // Mark the color buffer dirty for GPU re-upload.
    colorAttr.needsUpdate = true;

    this._mesh.visible = true;
  }

  /**
   * Hide the heatmap overlay without disposing resources.
   * Call showHeatmap() again to re-display with new or updated data.
   */
  hide() {
    this._mesh.visible = false;
  }

  /**
   * Release all GPU resources.
   *
   * After calling dispose(), this instance must not be used again.
   */
  dispose() {
    if (this._mesh) {
      this._scene.remove(this._mesh);
      this._mesh.geometry.dispose();
      this._mesh.material.dispose();
      this._mesh = null;
    }
  }
}
