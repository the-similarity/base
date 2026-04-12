/**
 * Scene Bridge — adapter between SimEngine world snapshots and Three.js scene.
 *
 * Architectural role:
 * The simulation engine produces a plain-object "world snapshot" each tick.
 * This bridge reads that snapshot and projects it into the Three.js scene graph.
 * It NEVER owns simulation truth — it is a pure visual projection layer.
 *
 * Lifecycle:
 * 1. Construct with a live Three.js scene and the world geometry constants.
 * 2. Call updateFromSnapshot(snapshot) every frame (or on snapshot change).
 * 3. Call dispose() when the scene bridge is no longer needed to free GPU resources.
 *
 * The snapshot object is expected to contain:
 *   { terrain, water, features, weather }
 * where each sub-object carries the data needed for its visual domain.
 *
 * Immutability: the bridge never mutates the snapshot. It reads values and
 * updates its own managed Three.js objects in place.
 */

import * as THREE from 'three';

// ── Internal constants ──────────────────────────────────────────────────────
// Fog density range for weather effects. These are tuned to match the
// FogExp2 density units used in the main app.js scene setup.
const FOG_CLEAR_DENSITY = 0.025;
const FOG_HEAVY_DENSITY = 0.12;

// Water opacity bounds — we interpolate between these based on the
// snapshot's water level or turbidity indicator.
const WATER_MIN_OPACITY = 0.4;
const WATER_MAX_OPACITY = 0.75;

/**
 * Adapter that keeps the Three.js scene in sync with simulation snapshots.
 *
 * The bridge manages:
 * - Terrain vertex displacement (height updates)
 * - Water plane level adjustments
 * - Feature group visibility
 * - Weather-driven fog and ambient light shifts
 */
export class SceneBridge {
  /**
   * @param {THREE.Scene} scene - The live Three.js scene graph.
   * @param {number} worldScale - Horizontal world extent (default 10 in app.js).
   * @param {number} heightScale - Vertical exaggeration factor.
   */
  constructor(scene, worldScale, heightScale) {
    /** @type {THREE.Scene} */
    this._scene = scene;

    /** @type {number} Horizontal world extent matching the terrain plane size. */
    this._worldScale = worldScale;

    /** @type {number} Vertical exaggeration applied to all height values. */
    this._heightScale = heightScale;

    // ── Managed scene objects ──────────────────────────────────────────────
    // These are created lazily on first snapshot and disposed explicitly.

    /** @type {THREE.Mesh|null} The terrain surface mesh. */
    this._terrainMesh = null;

    /** @type {THREE.Mesh|null} The water plane mesh. */
    this._waterMesh = null;

    /** @type {THREE.Group|null} Container for feature objects (trees, rocks, etc). */
    this._featureGroup = null;

    // ── Weather state cache ───────────────────────────────────────────────
    // We cache the last weather values to avoid re-applying identical fog/light
    // parameters every frame (GPU state changes are not free).

    /** @type {string|null} Last applied weather type string. */
    this._lastWeatherType = null;

    /** @type {number} Last applied weather intensity (0-1). */
    this._lastIntensity = 0;
  }

  /**
   * Synchronize the scene to match the given world snapshot.
   *
   * This is the main per-frame entry point. It performs incremental updates
   * where possible (e.g. only repositioning water rather than rebuilding it)
   * and full rebuilds only when the data shape changes.
   *
   * @param {Object} worldSnapshot - Plain data object from SimEngine.
   * @param {Object} [worldSnapshot.terrain] - Terrain state: { heightmap, biome, size }.
   * @param {Object} [worldSnapshot.water] - Water state: { level, turbidity }.
   * @param {Array}  [worldSnapshot.features] - Feature placement array.
   * @param {Object} [worldSnapshot.weather] - Weather state: { type, intensity }.
   */
  updateFromSnapshot(worldSnapshot) {
    if (!worldSnapshot) return;

    // ── Terrain height updates ──────────────────────────────────────────
    // If the snapshot includes terrain data and we already have a mesh,
    // we update vertex Y positions in place rather than rebuilding geometry.
    // This is cheaper than a full rebuild and avoids GC pressure from
    // discarding large BufferGeometry objects every frame.
    if (worldSnapshot.terrain && this._terrainMesh) {
      this._updateTerrainHeights(worldSnapshot.terrain);
    }

    // ── Water level ─────────────────────────────────────────────────────
    if (worldSnapshot.water && this._waterMesh) {
      const newLevel = (worldSnapshot.water.level || 0.2) * this._heightScale;
      // Only touch the transform if the level actually changed.
      if (Math.abs(this._waterMesh.position.y - newLevel) > 0.001) {
        this._waterMesh.position.y = newLevel;
      }

      // Turbidity affects visual opacity — muddy water after rain, etc.
      const turbidity = worldSnapshot.water.turbidity || 0;
      const targetOpacity = WATER_MIN_OPACITY + turbidity * (WATER_MAX_OPACITY - WATER_MIN_OPACITY);
      this._waterMesh.material.opacity = targetOpacity;
    }

    // ── Feature visibility ──────────────────────────────────────────────
    // Features (trees, rocks, bushes) may be toggled based on simulation
    // events (e.g. deforestation, fires). We toggle group visibility here.
    if (worldSnapshot.features !== undefined && this._featureGroup) {
      this._featureGroup.visible = worldSnapshot.features.visible !== false;
    }

    // ── Weather / environment ───────────────────────────────────────────
    if (worldSnapshot.weather) {
      this._applyWeather(worldSnapshot.weather);
    }
  }

  /**
   * Update terrain mesh vertex heights from snapshot heightmap data.
   *
   * @param {Object} terrain - { heightmap: number[], size: number }
   * @private
   */
  _updateTerrainHeights(terrain) {
    const posAttr = this._terrainMesh.geometry.attributes.position;
    const heightmap = terrain.heightmap;

    if (!heightmap || heightmap.length !== posAttr.count) {
      // Dimension mismatch — the terrain grid changed size. A full rebuild
      // would be needed here, but that is handled by the caller rebuilding
      // the scene bridge. We silently skip to avoid corrupting the mesh.
      return;
    }

    for (let i = 0; i < posAttr.count; i++) {
      posAttr.setY(i, (heightmap[i] || 0) * this._heightScale);
    }

    // Mark the position buffer as needing a GPU re-upload.
    posAttr.needsUpdate = true;

    // Normals must be recomputed after height changes so lighting stays correct.
    this._terrainMesh.geometry.computeVertexNormals();
  }

  /**
   * Apply weather effects to the scene environment.
   *
   * Weather affects:
   * - Scene fog density (rain/storm increases fog, clear reduces it)
   * - Scene background color tint (overcast skies darken the backdrop)
   *
   * @param {Object} weather - { type: string, intensity: number (0-1) }
   * @private
   */
  _applyWeather(weather) {
    const type = weather.type || 'clear';
    const intensity = Math.max(0, Math.min(1, weather.intensity || 0));

    // Skip redundant updates — weather changes infrequently relative to frame rate.
    if (type === this._lastWeatherType && Math.abs(intensity - this._lastIntensity) < 0.005) {
      return;
    }

    // ── Fog density ─────────────────────────────────────────────────────
    // Linear interpolation between clear and heavy fog based on intensity.
    // Storm and rain both increase fog; clear weather restores baseline.
    let targetDensity = FOG_CLEAR_DENSITY;
    if (type === 'rain' || type === 'storm') {
      targetDensity = FOG_CLEAR_DENSITY + intensity * (FOG_HEAVY_DENSITY - FOG_CLEAR_DENSITY);
    } else if (type === 'fog') {
      // Pure fog weather has a slightly different ceiling than storm fog.
      targetDensity = FOG_CLEAR_DENSITY + intensity * (FOG_HEAVY_DENSITY * 0.8 - FOG_CLEAR_DENSITY);
    }

    if (this._scene.fog && this._scene.fog.density !== undefined) {
      this._scene.fog.density = targetDensity;
    }

    // ── Background tint ─────────────────────────────────────────────────
    // Darken the scene background proportionally to overcast intensity.
    // The base color (0x0a0a0f) is the default from app.js.
    if (this._scene.background && this._scene.background.isColor) {
      const baseLuminance = 0.04; // approximate luminance of 0x0a0a0f
      const dimFactor = 1.0 - intensity * 0.5; // at full intensity, halve luminance
      const lum = baseLuminance * dimFactor;
      this._scene.background.setRGB(lum, lum, lum * 1.1);
    }

    this._lastWeatherType = type;
    this._lastIntensity = intensity;
  }

  /**
   * Register externally-built meshes so the bridge can manage them.
   *
   * The terrain mesh, water mesh, and feature group are typically built
   * by terrain-renderer.js during initial scene setup. The bridge does not
   * own construction — it only owns incremental updates.
   *
   * @param {Object} opts
   * @param {THREE.Mesh} [opts.terrainMesh] - The ground surface mesh.
   * @param {THREE.Mesh} [opts.waterMesh] - The water plane mesh.
   * @param {THREE.Group} [opts.featureGroup] - Feature container group.
   */
  registerMeshes({ terrainMesh, waterMesh, featureGroup } = {}) {
    if (terrainMesh) this._terrainMesh = terrainMesh;
    if (waterMesh) this._waterMesh = waterMesh;
    if (featureGroup) this._featureGroup = featureGroup;
  }

  /**
   * Release all GPU resources managed by this bridge.
   *
   * After calling dispose(), this instance must not be used again.
   * The caller is responsible for removing meshes from the scene if needed.
   */
  dispose() {
    // We do not dispose the meshes themselves here because they may be
    // shared with other systems (e.g. the main app owns the terrain mesh).
    // We only null our references so the GC can collect them if nothing
    // else holds a reference.
    this._terrainMesh = null;
    this._waterMesh = null;
    this._featureGroup = null;
    this._lastWeatherType = null;
    this._lastIntensity = 0;
  }
}
