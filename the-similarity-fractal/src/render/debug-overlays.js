/**
 * Debug Overlays — optional visualization layers for simulation debugging.
 *
 * Architectural role:
 * These overlays are developer/debug tools layered on top of the main scene.
 * They visualize simulation internals (nav grid, regions, POIs, agent paths)
 * that are not visible in the normal rendering pipeline.
 *
 * Each layer is independently togglable and renders with its own dedicated
 * Three.js objects. Layers are created lazily on first show and cached for
 * subsequent toggles.
 *
 * Performance note:
 * Debug overlays are expected to be active only during development or
 * debugging sessions. They use LineSegments and simple meshes which are
 * not optimized for thousands of elements. For large grids (128x128+),
 * the nav grid wireframe may impact frame rate — this is acceptable for
 * a debug tool.
 *
 * Lifecycle:
 * 1. Construct with scene and world geometry constants.
 * 2. Call show* methods to populate layers from simulation data.
 * 3. Call toggle(layerName) to show/hide individual layers.
 * 4. Call dispose() to free all GPU resources.
 *
 * Immutability: overlays never mutate the data objects passed to them.
 */

import * as THREE from 'three';

// ── Layer name constants ────────────────────────────────────────────────────
const LAYER_NAV_GRID = 'navGrid';
const LAYER_REGIONS = 'regions';
const LAYER_POIS = 'pois';
const LAYER_AGENT_PATHS = 'agentPaths';

// ── Visual tuning ───────────────────────────────────────────────────────────

// Nav grid wireframe is rendered slightly above the terrain to avoid z-fighting.
const NAV_GRID_Y_OFFSET = 0.02;

// Region boundary line width and elevation offset.
const REGION_Y_OFFSET = 0.04;

// POI marker size (sphere radius).
const POI_MARKER_RADIUS = 0.05;
const POI_MARKER_SEGMENTS = 8;

// Agent path line elevation offset above terrain.
const PATH_Y_OFFSET = 0.06;

// Distinct region hues — wraps for >12 regions.
const REGION_HUES = [
  0.0, 0.08, 0.16, 0.25, 0.33, 0.42, 0.50, 0.58, 0.66, 0.75, 0.83, 0.91
];

/**
 * Manages debug visualization layers overlaid on the simulation scene.
 */
export class DebugOverlays {
  /**
   * @param {THREE.Scene} scene - The live Three.js scene.
   * @param {number} worldScale - Horizontal world extent.
   * @param {number} heightScale - Vertical exaggeration factor.
   */
  constructor(scene, worldScale, heightScale) {
    /** @type {THREE.Scene} */
    this._scene = scene;

    /** @type {number} */
    this._worldScale = worldScale;

    /** @type {number} */
    this._heightScale = heightScale;

    /**
     * Container group for all overlay layers. Adding one group to the scene
     * keeps the scene graph clean and makes bulk removal simple.
     * @type {THREE.Group}
     */
    this._root = new THREE.Group();
    this._root.name = 'debug-overlays';
    this._scene.add(this._root);

    /**
     * Per-layer state: { object: THREE.Object3D, visible: boolean }.
     * Layers are created lazily and cached here.
     * @type {Map<string, { object: THREE.Object3D, visible: boolean }>}
     */
    this._layers = new Map();
  }

  // ── Public show methods ─────────────────────────────────────────────────

  /**
   * Show the navigation grid wireframe.
   *
   * The nav grid is a 2D boolean grid where each cell is passable or not.
   * Passable cells are drawn in green, impassable in red.
   *
   * @param {Object} navGrid - { width, height, cells: boolean[] }
   *   cells is row-major: cells[z * width + x] = passable.
   */
  showNavGrid(navGrid) {
    // Remove previous nav grid layer if it exists.
    this._removeLayer(LAYER_NAV_GRID);

    if (!navGrid || !navGrid.cells) return;

    const { width, height, cells } = navGrid;
    const group = new THREE.Group();
    group.name = 'overlay-nav-grid';

    // Build line segments for each cell edge. We draw a wireframe grid where
    // each cell is colored by passability. Using LineSegments with a position
    // buffer is efficient for this kind of structured debug display.
    const vertices = [];
    const colors = [];

    const cellW = this._worldScale / width;
    const cellH = this._worldScale / height;
    const halfWorld = this._worldScale / 2;

    for (let gz = 0; gz < height; gz++) {
      for (let gx = 0; gx < width; gx++) {
        const passable = !!cells[gz * width + gx];
        const r = passable ? 0.1 : 0.8;
        const g = passable ? 0.7 : 0.1;
        const b = 0.1;

        // World-space corners of this cell.
        const x0 = gx * cellW - halfWorld;
        const x1 = (gx + 1) * cellW - halfWorld;
        const z0 = gz * cellH - halfWorld;
        const z1 = (gz + 1) * cellH - halfWorld;
        const y = NAV_GRID_Y_OFFSET;

        // Four edges per cell (some edges are shared with neighbors, but the
        // overhead is acceptable for a debug tool).
        // Bottom edge
        vertices.push(x0, y, z0, x1, y, z0);
        colors.push(r, g, b, r, g, b);
        // Right edge
        vertices.push(x1, y, z0, x1, y, z1);
        colors.push(r, g, b, r, g, b);
        // Top edge
        vertices.push(x1, y, z1, x0, y, z1);
        colors.push(r, g, b, r, g, b);
        // Left edge
        vertices.push(x0, y, z1, x0, y, z0);
        colors.push(r, g, b, r, g, b);
      }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

    const material = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.5,
      depthTest: true,
    });

    const lines = new THREE.LineSegments(geometry, material);
    group.add(lines);

    this._addLayer(LAYER_NAV_GRID, group);
  }

  /**
   * Show region boundaries as colored outlines.
   *
   * @param {Object} regionMap - { width, height, cells: number[] }
   *   cells[z * width + x] = region ID integer.
   * @param {Object} navGrid - { width, height } for grid dimensions reference.
   */
  showRegions(regionMap, navGrid) {
    this._removeLayer(LAYER_REGIONS);

    if (!regionMap || !regionMap.cells) return;

    const { width, height, cells } = regionMap;
    const group = new THREE.Group();
    group.name = 'overlay-regions';

    // We draw boundary lines between adjacent cells that belong to different
    // regions. This produces clean region outlines without filling interiors.
    const vertices = [];
    const colors = [];

    const cellW = this._worldScale / width;
    const cellH = this._worldScale / height;
    const halfWorld = this._worldScale / 2;

    for (let gz = 0; gz < height; gz++) {
      for (let gx = 0; gx < width; gx++) {
        const regionId = cells[gz * width + gx];
        const hue = REGION_HUES[regionId % REGION_HUES.length];
        const color = new THREE.Color().setHSL(hue, 0.8, 0.6);

        const x0 = gx * cellW - halfWorld;
        const x1 = (gx + 1) * cellW - halfWorld;
        const z0 = gz * cellH - halfWorld;
        const z1 = (gz + 1) * cellH - halfWorld;
        const y = REGION_Y_OFFSET;

        // Check right neighbor — draw vertical boundary if different region.
        if (gx + 1 < width && cells[gz * width + gx + 1] !== regionId) {
          vertices.push(x1, y, z0, x1, y, z1);
          colors.push(color.r, color.g, color.b, color.r, color.g, color.b);
        }

        // Check bottom neighbor — draw horizontal boundary if different region.
        if (gz + 1 < height && cells[(gz + 1) * width + gx] !== regionId) {
          vertices.push(x0, y, z1, x1, y, z1);
          colors.push(color.r, color.g, color.b, color.r, color.g, color.b);
        }
      }
    }

    if (vertices.length > 0) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
      geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

      const material = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.7,
        linewidth: 1, // WebGL ignores linewidth >1 on most platforms, but we set it for intent clarity
      });

      group.add(new THREE.LineSegments(geometry, material));
    }

    this._addLayer(LAYER_REGIONS, group);
  }

  /**
   * Show Points of Interest as colored marker spheres.
   *
   * @param {Array<Object>} pois - Array of POI objects.
   *   Each POI: { x, y, z, type, name }
   *   - x, z: world-space horizontal position
   *   - y: world-space vertical position
   *   - type: string (determines color)
   */
  showPOIs(pois) {
    this._removeLayer(LAYER_POIS);

    if (!pois || pois.length === 0) return;

    const group = new THREE.Group();
    group.name = 'overlay-pois';

    // POI type to color mapping. Unknown types get white.
    const typeColors = {
      village:    0x4488ff,
      resource:   0x44ff44,
      danger:     0xff4444,
      landmark:   0xffaa22,
      water:      0x22aaff,
      shelter:    0xaa88ff,
    };

    const geometry = new THREE.SphereGeometry(POI_MARKER_RADIUS, POI_MARKER_SEGMENTS, POI_MARKER_SEGMENTS);

    // Cache materials by type so POIs sharing a type share one material object.
    // This avoids creating N identical materials for N POIs of the same type.
    const materialCache = new Map();

    for (let i = 0; i < pois.length; i++) {
      const poi = pois[i];
      const poiType = poi.type || '_default';
      const colorHex = typeColors[poiType] || 0xffffff;

      let material = materialCache.get(poiType);
      if (!material) {
        material = new THREE.MeshBasicMaterial({
          color: colorHex,
          transparent: true,
          opacity: 0.8,
        });
        materialCache.set(poiType, material);
      }

      const marker = new THREE.Mesh(geometry, material);
      marker.position.set(
        poi.x || 0,
        (poi.y || 0) + POI_MARKER_RADIUS * 2, // Float above terrain
        poi.z || 0
      );

      group.add(marker);
    }

    this._addLayer(LAYER_POIS, group);
  }

  /**
   * Show agent goal/path lines.
   *
   * Draws a line from each agent's current position to their goal position.
   * If the agent has a full path array, the line follows all waypoints.
   *
   * @param {Array<Object>} agents - Array of agent state objects.
   *   Each agent: { x, y, z, goalX, goalY, goalZ, path?, alive }
   *   - path: optional Array<{x, y, z}> of waypoints
   */
  showAgentPaths(agents) {
    this._removeLayer(LAYER_AGENT_PATHS);

    if (!agents || agents.length === 0) return;

    const group = new THREE.Group();
    group.name = 'overlay-agent-paths';

    const vertices = [];
    const colors = [];

    for (let i = 0; i < agents.length; i++) {
      const agent = agents[i];

      // Skip dead agents or agents without goals.
      if (!agent.alive) continue;
      if (agent.goalX === undefined && !agent.path) continue;

      // Line color: white with slight transparency.
      const r = 1.0, g = 0.9, b = 0.3;

      if (agent.path && agent.path.length > 1) {
        // Draw the full path as a polyline by emitting line segments
        // for each consecutive pair of waypoints.
        for (let j = 0; j < agent.path.length - 1; j++) {
          const a = agent.path[j];
          const b2 = agent.path[j + 1];
          vertices.push(
            a.x || 0, (a.y || 0) + PATH_Y_OFFSET, a.z || 0,
            b2.x || 0, (b2.y || 0) + PATH_Y_OFFSET, b2.z || 0
          );
          colors.push(r, g, b, r, g, b);
        }
      } else if (agent.goalX !== undefined) {
        // Simple direct line from current position to goal.
        vertices.push(
          agent.x || 0, (agent.y || 0) + PATH_Y_OFFSET, agent.z || 0,
          agent.goalX, (agent.goalY || 0) + PATH_Y_OFFSET, agent.goalZ || 0
        );
        colors.push(r, g, b, r, g, b);
      }
    }

    if (vertices.length > 0) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
      geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

      const material = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.6,
      });

      group.add(new THREE.LineSegments(geometry, material));
    }

    this._addLayer(LAYER_AGENT_PATHS, group);
  }

  // ── Toggle and layer management ───────────────────────────────────────

  /**
   * Toggle visibility of a named overlay layer.
   *
   * @param {string} layerName - One of: 'navGrid', 'regions', 'pois', 'agentPaths'.
   * @returns {boolean} New visibility state, or false if layer does not exist.
   */
  toggle(layerName) {
    const layer = this._layers.get(layerName);
    if (!layer) return false;

    layer.visible = !layer.visible;
    layer.object.visible = layer.visible;
    return layer.visible;
  }

  /**
   * Release all GPU resources and remove overlays from the scene.
   */
  dispose() {
    for (const [, layer] of this._layers) {
      this._disposeObject(layer.object);
    }
    this._layers.clear();
    this._scene.remove(this._root);
  }

  // ── Private helpers ───────────────────────────────────────────────────

  /**
   * Add a layer object to the overlay system.
   * @param {string} name
   * @param {THREE.Object3D} object
   * @private
   */
  _addLayer(name, object) {
    this._root.add(object);
    this._layers.set(name, { object, visible: true });
  }

  /**
   * Remove and dispose a layer by name.
   * @param {string} name
   * @private
   */
  _removeLayer(name) {
    const existing = this._layers.get(name);
    if (existing) {
      this._root.remove(existing.object);
      this._disposeObject(existing.object);
      this._layers.delete(name);
    }
  }

  /**
   * Recursively dispose geometry and materials in an object tree.
   * @param {THREE.Object3D} obj
   * @private
   */
  _disposeObject(obj) {
    obj.traverse((child) => {
      if (child.geometry) child.geometry.dispose();
      if (child.material) {
        // Material may be an array (multi-material) or a single material.
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => m.dispose());
        } else {
          child.material.dispose();
        }
      }
    });
  }
}
