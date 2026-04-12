/**
 * Agent Renderer — InstancedMesh pool for rendering simulation agents.
 *
 * Architectural role:
 * Each simulation tick produces an array of agent state objects. This renderer
 * maintains a single InstancedMesh (one draw call) that represents all agents
 * as small spheres. Positions, visibility, and colors are updated from the
 * snapshot data each frame.
 *
 * Performance rationale:
 * - InstancedMesh keeps draw calls at 1 regardless of agent count.
 * - We pre-allocate for maxAgents and hide unused instances by scaling to zero.
 * - Color updates use setColorAt which writes directly to the instance color buffer.
 *
 * Lifecycle:
 * 1. Construct with scene and maxAgents capacity.
 * 2. Call updateFromAgents(agents) each frame.
 * 3. Call setColorMode(mode) to change coloring strategy.
 * 4. Call dispose() to free GPU resources.
 *
 * Immutability: this renderer never mutates the agent snapshot array.
 */

import * as THREE from 'three';

// ── Color mode constants ────────────────────────────────────────────────────
/** Color each agent by its faction — each faction gets a distinct hue. */
export const COLOR_MODE_BY_FACTION = 'BY_FACTION';

/** Color each agent on a green-to-red gradient based on health (1.0 = green, 0.0 = red). */
export const COLOR_MODE_BY_HEALTH = 'BY_HEALTH';

/** Color each agent by its role — distinct color per role string. */
export const COLOR_MODE_BY_ROLE = 'BY_ROLE';

// ── Faction palette ─────────────────────────────────────────────────────────
// Up to 12 visually distinct hues for factions. If there are more factions
// than palette entries we wrap around — acceptable for a debug/overview tool.
const FACTION_HUES = [
  0.00,  // red
  0.08,  // orange
  0.16,  // yellow
  0.33,  // green
  0.50,  // cyan
  0.58,  // teal
  0.66,  // blue
  0.75,  // indigo
  0.83,  // violet
  0.91,  // magenta
  0.12,  // amber
  0.42,  // sea green
];

// ── Role color map ──────────────────────────────────────────────────────────
// Named roles get stable, readable colors. Unknown roles fall back to gray.
const ROLE_COLORS = {
  warrior:   new THREE.Color(0.9, 0.2, 0.2),
  farmer:    new THREE.Color(0.2, 0.7, 0.2),
  merchant:  new THREE.Color(0.9, 0.7, 0.1),
  builder:   new THREE.Color(0.4, 0.4, 0.8),
  healer:    new THREE.Color(0.2, 0.9, 0.8),
  explorer:  new THREE.Color(0.8, 0.5, 0.2),
  leader:    new THREE.Color(1.0, 0.85, 0.0),
  scout:     new THREE.Color(0.6, 0.8, 0.3),
  gatherer:  new THREE.Color(0.5, 0.6, 0.2),
  guard:     new THREE.Color(0.7, 0.3, 0.3),
};

const DEFAULT_ROLE_COLOR = new THREE.Color(0.5, 0.5, 0.5);

// ── Geometry constants ──────────────────────────────────────────────────────
// Agent sphere radius and segment count. Low segment count keeps the mesh
// cheap while still reading as a sphere at typical camera distances.
const AGENT_RADIUS = 0.03;
const AGENT_SEGMENTS = 6;

/**
 * Renders simulation agents as an InstancedMesh pool.
 *
 * Each agent is a small sphere whose position, color, and visibility
 * are driven by the agent snapshot array.
 */
export class AgentRenderer {
  /**
   * @param {THREE.Scene} scene - The Three.js scene to add agents to.
   * @param {number} maxAgents - Pre-allocated instance capacity.
   */
  constructor(scene, maxAgents = 1024) {
    /** @type {THREE.Scene} */
    this._scene = scene;

    /** @type {number} Maximum agent instances. Determines GPU buffer sizes. */
    this._maxAgents = maxAgents;

    /** @type {string} Current color mode — one of the COLOR_MODE_* constants. */
    this._colorMode = COLOR_MODE_BY_FACTION;

    // ── Build the instanced mesh ──────────────────────────────────────────
    const geometry = new THREE.SphereGeometry(AGENT_RADIUS, AGENT_SEGMENTS, AGENT_SEGMENTS);
    const material = new THREE.MeshStandardMaterial({
      roughness: 0.6,
      metalness: 0.1,
    });

    /** @type {THREE.InstancedMesh} The single draw-call mesh for all agents. */
    this._mesh = new THREE.InstancedMesh(geometry, material, maxAgents);

    // Enable per-instance colors. We must set an initial color for every
    // instance or Three.js will not allocate the instanceColor buffer.
    for (let i = 0; i < maxAgents; i++) {
      this._mesh.setColorAt(i, DEFAULT_ROLE_COLOR);
    }
    this._mesh.instanceColor.needsUpdate = true;

    // Start with all instances hidden (scaled to zero). As agents arrive
    // via updateFromAgents, we reveal only the active ones.
    this._dummy = new THREE.Object3D();
    this._dummy.scale.set(0, 0, 0);
    this._dummy.updateMatrix();
    for (let i = 0; i < maxAgents; i++) {
      this._mesh.setMatrixAt(i, this._dummy.matrix);
    }
    this._mesh.instanceMatrix.needsUpdate = true;

    // Track how many agents are currently visible so we can efficiently
    // hide only the surplus when agent count shrinks.
    /** @type {number} */
    this._activeCount = 0;

    // Scratch color object reused across all _computeColor calls to avoid
    // allocating a new THREE.Color per agent per frame (hot-path GC pressure).
    /** @type {THREE.Color} */
    this._scratchColor = new THREE.Color();

    this._scene.add(this._mesh);
  }

  /**
   * Update agent positions and colors from the simulation snapshot.
   *
   * @param {Array<Object>} agents - Array of agent state objects.
   *   Each agent: { x, y, z, health, faction, role, alive }
   *   - x, z: horizontal position in world space
   *   - y: vertical position (height above terrain)
   *   - health: 0.0 to 1.0
   *   - faction: integer faction ID
   *   - role: string role name
   *   - alive: boolean (dead agents are hidden)
   */
  updateFromAgents(agents) {
    if (!agents) return;

    const count = Math.min(agents.length, this._maxAgents);

    for (let i = 0; i < count; i++) {
      const agent = agents[i];

      if (!agent.alive) {
        // Dead agents are hidden by scaling to zero. This is cheaper than
        // removing instances or rebuilding the mesh.
        this._dummy.scale.set(0, 0, 0);
        this._dummy.position.set(0, 0, 0);
      } else {
        // Position the agent sphere at its world coordinates.
        // The Y offset lifts the sphere center above the terrain surface
        // so agents appear to stand on the ground rather than clip into it.
        this._dummy.position.set(
          agent.x || 0,
          (agent.y || 0) + AGENT_RADIUS,
          agent.z || 0
        );
        this._dummy.scale.set(1, 1, 1);
      }

      this._dummy.updateMatrix();
      this._mesh.setMatrixAt(i, this._dummy.matrix);

      // Apply color based on current color mode.
      this._mesh.setColorAt(i, this._computeColor(agent));
    }

    // Hide any surplus instances from the previous frame. If the agent count
    // shrank, we need to zero-scale the now-unused instances.
    if (count < this._activeCount) {
      this._dummy.scale.set(0, 0, 0);
      this._dummy.position.set(0, 0, 0);
      this._dummy.updateMatrix();
      for (let i = count; i < this._activeCount; i++) {
        this._mesh.setMatrixAt(i, this._dummy.matrix);
      }
    }

    this._activeCount = count;

    // Mark buffers dirty for GPU re-upload.
    this._mesh.instanceMatrix.needsUpdate = true;
    if (this._mesh.instanceColor) {
      this._mesh.instanceColor.needsUpdate = true;
    }
  }

  /**
   * Change the color coding strategy.
   *
   * @param {string} mode - One of COLOR_MODE_BY_FACTION, COLOR_MODE_BY_HEALTH, COLOR_MODE_BY_ROLE.
   */
  setColorMode(mode) {
    this._colorMode = mode;
    // Colors will refresh on next updateFromAgents call.
  }

  /**
   * Compute the color for a single agent based on the current color mode.
   *
   * @param {Object} agent - Agent state object.
   * @returns {THREE.Color}
   * @private
   */
  _computeColor(agent) {
    // Reuse the scratch color to avoid per-agent per-frame allocations.
    const c = this._scratchColor;

    if (!agent.alive) {
      // Dead agents are hidden anyway, but give them a muted gray in case
      // the caller disables the hide-dead behavior later.
      return c.setRGB(0.3, 0.3, 0.3);
    }

    switch (this._colorMode) {
      case COLOR_MODE_BY_FACTION: {
        const factionId = agent.faction || 0;
        const hue = FACTION_HUES[factionId % FACTION_HUES.length];
        // Saturation and lightness are fixed for readability against terrain.
        return c.setHSL(hue, 0.7, 0.5);
      }

      case COLOR_MODE_BY_HEALTH: {
        // Green (hue 0.33) at full health, red (hue 0.0) at zero health.
        // We interpolate hue linearly which gives a natural green->yellow->red ramp.
        const health = Math.max(0, Math.min(1, agent.health || 0));
        const hue = health * 0.33;
        return c.setHSL(hue, 0.8, 0.45);
      }

      case COLOR_MODE_BY_ROLE: {
        const roleName = (agent.role || '').toLowerCase();
        const roleColor = ROLE_COLORS[roleName] || DEFAULT_ROLE_COLOR;
        return c.copy(roleColor);
      }

      default:
        return c.copy(DEFAULT_ROLE_COLOR);
    }
  }

  /**
   * Release GPU resources.
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
