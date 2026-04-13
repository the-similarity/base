/**
 * Agent Renderer — InstancedMesh pool for rendering simulation agents
 * as low-poly humanoid figures.
 *
 * Architectural role:
 * Each simulation tick produces an array of agent state objects. This renderer
 * maintains a single InstancedMesh (one draw call) that represents all agents
 * as procedural humanoid figures built from merged basic geometries. Positions,
 * visibility, and colors are updated from the snapshot data each frame.
 *
 * Performance rationale:
 * - All humanoid body parts (head, torso, arms, legs) are merged into a single
 *   BufferGeometry via mergeGeometries(), so the entire agent population is
 *   rendered in one draw call via InstancedMesh.
 * - We pre-allocate for maxAgents and hide unused instances by scaling to zero.
 * - Color updates use setColorAt which writes directly to the instance color buffer.
 * - Scratch objects (Object3D, Color, Matrix4) are reused to avoid per-frame GC pressure.
 *
 * Lifecycle:
 * 1. Construct with scene, maxAgents capacity, and heightScale.
 * 2. Call updateFromAgents(agents) each frame.
 * 3. Call setColorMode(mode) to change coloring strategy.
 * 4. Call dispose() to free GPU resources.
 *
 * Immutability: this renderer never mutates the agent snapshot array.
 */

import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

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
// These double as the "clothing accent" hue when computing unique per-agent colors.
const ROLE_COLORS = {
  warrior:   new THREE.Color(0.9, 0.2, 0.2),
  soldier:   new THREE.Color(0.85, 0.15, 0.15),
  farmer:    new THREE.Color(0.2, 0.7, 0.2),
  gatherer:  new THREE.Color(0.5, 0.65, 0.2),
  merchant:  new THREE.Color(0.9, 0.7, 0.1),
  trader:    new THREE.Color(0.85, 0.65, 0.15),
  builder:   new THREE.Color(0.4, 0.4, 0.8),
  healer:    new THREE.Color(0.2, 0.9, 0.8),
  explorer:  new THREE.Color(0.8, 0.5, 0.2),
  leader:    new THREE.Color(1.0, 0.85, 0.0),
  scout:     new THREE.Color(0.6, 0.8, 0.3),
  guard:     new THREE.Color(0.7, 0.3, 0.3),
  hunter:    new THREE.Color(0.6, 0.3, 0.15),
};

const DEFAULT_ROLE_COLOR = new THREE.Color(0.5, 0.5, 0.5);

// ── Humanoid geometry constants ─────────────────────────────────────────────
// Total humanoid height ~0.18 units (fitting the 0.15–0.2 range on worldScale=10 terrain).
// All measurements are relative to center-bottom of the figure.
const HUMANOID_HEIGHT = 0.18;

// Head: slightly oval sphere — sits on top of the torso.
const HEAD_RADIUS_X  = 0.018;  // horizontal radius
const HEAD_RADIUS_Y  = 0.022;  // vertical radius (taller = oval)
const HEAD_Y         = HUMANOID_HEIGHT - HEAD_RADIUS_Y; // center of head

// Torso: tapered cylinder (wider at shoulders, narrower at waist).
const TORSO_RADIUS_TOP    = 0.022;
const TORSO_RADIUS_BOTTOM = 0.016;
const TORSO_HEIGHT        = 0.065;
const TORSO_Y             = HEAD_Y - HEAD_RADIUS_Y - TORSO_HEIGHT / 2; // center of torso

// Arms: thin cylinders angled slightly outward from shoulders.
const ARM_RADIUS = 0.007;
const ARM_LENGTH = 0.06;
// Arms attach at shoulder level (top of torso) and angle outward ~15 degrees.
const ARM_Y      = TORSO_Y + TORSO_HEIGHT * 0.35; // near top of torso
const ARM_OFFSET_X = TORSO_RADIUS_TOP + ARM_RADIUS + 0.002; // horizontal offset from center
const ARM_ANGLE    = 0.26; // radians (~15 degrees outward tilt)

// Legs: thin cylinders hanging from bottom of torso.
const LEG_RADIUS = 0.009;
const LEG_LENGTH = 0.07;
const LEG_Y      = TORSO_Y - TORSO_HEIGHT / 2 - LEG_LENGTH / 2; // center of legs
const LEG_OFFSET_X = 0.012; // horizontal spread between legs

// Segment counts for geometry — low-poly look.
const SPHERE_SEGMENTS = 6;
const CYLINDER_SEGMENTS = 5;

/**
 * Build a single merged BufferGeometry representing a low-poly humanoid figure.
 *
 * The figure is centered at X=0, Z=0 with Y=0 at the feet (bottom of legs).
 * This allows placing instances directly at terrain height without manual offset.
 *
 * @returns {THREE.BufferGeometry} Merged humanoid geometry ready for InstancedMesh.
 */
function buildHumanoidGeometry() {
  const parts = [];

  // Helper: create a cylinder and position/rotate it via a matrix.
  // Three.js CylinderGeometry is centered at origin along Y axis by default.
  const makeCylinder = (radiusTop, radiusBottom, height, x, y, z, rotZ = 0) => {
    const geo = new THREE.CylinderGeometry(radiusTop, radiusBottom, height, CYLINDER_SEGMENTS);
    const mat = new THREE.Matrix4();
    // Compose: translate then rotate around Z axis (for arm tilt).
    // We apply rotation first, then translation to get the right placement.
    if (rotZ !== 0) {
      const rotMat = new THREE.Matrix4().makeRotationZ(rotZ);
      const transMat = new THREE.Matrix4().makeTranslation(x, y, z);
      mat.multiplyMatrices(transMat, rotMat);
    } else {
      mat.makeTranslation(x, y, z);
    }
    geo.applyMatrix4(mat);
    return geo;
  };

  // ── Head (slightly oval sphere) ───────────────────────────────────────────
  // Use a standard sphere and scale Y to create the oval shape.
  const headGeo = new THREE.SphereGeometry(HEAD_RADIUS_X, SPHERE_SEGMENTS, SPHERE_SEGMENTS);
  // Scale Y to make it taller (oval). We bake this into the geometry so the
  // InstancedMesh uniform scale still works correctly.
  const headScaleY = HEAD_RADIUS_Y / HEAD_RADIUS_X;
  headGeo.applyMatrix4(
    new THREE.Matrix4().compose(
      new THREE.Vector3(0, HEAD_Y, 0),
      new THREE.Quaternion(),
      new THREE.Vector3(1, headScaleY, 1)
    )
  );
  parts.push(headGeo);

  // ── Torso (tapered cylinder) ──────────────────────────────────────────────
  parts.push(makeCylinder(TORSO_RADIUS_TOP, TORSO_RADIUS_BOTTOM, TORSO_HEIGHT, 0, TORSO_Y, 0));

  // ── Left arm ──────────────────────────────────────────────────────────────
  // Tilted outward (positive Z rotation on left side).
  parts.push(makeCylinder(ARM_RADIUS, ARM_RADIUS, ARM_LENGTH,
    -ARM_OFFSET_X, ARM_Y - ARM_LENGTH * 0.15, 0, ARM_ANGLE));

  // ── Right arm ─────────────────────────────────────────────────────────────
  // Tilted outward (negative Z rotation on right side).
  parts.push(makeCylinder(ARM_RADIUS, ARM_RADIUS, ARM_LENGTH,
    ARM_OFFSET_X, ARM_Y - ARM_LENGTH * 0.15, 0, -ARM_ANGLE));

  // ── Left leg ──────────────────────────────────────────────────────────────
  parts.push(makeCylinder(LEG_RADIUS, LEG_RADIUS, LEG_LENGTH,
    -LEG_OFFSET_X, LEG_Y, 0));

  // ── Right leg ─────────────────────────────────────────────────────────────
  parts.push(makeCylinder(LEG_RADIUS, LEG_RADIUS, LEG_LENGTH,
    LEG_OFFSET_X, LEG_Y, 0));

  // ── Merge all parts into a single BufferGeometry ──────────────────────────
  // This is critical for instancing performance: one geometry = one draw call.
  const merged = mergeGeometries(parts, false);

  // Dispose individual part geometries since they are now baked into `merged`.
  for (const part of parts) {
    part.dispose();
  }

  return merged;
}

/**
 * Deterministic hash for agent ID strings.
 * Returns a float in [0, 1) derived from the agent's ID, used to generate
 * stable per-agent skin tones so appearance doesn't flicker across frames.
 *
 * @param {string} id - Agent ID string (e.g. 'agent-42').
 * @returns {number} Pseudo-random value in [0, 1).
 */
function hashAgentId(id) {
  // Simple string hash (djb2 variant) mapped to [0, 1).
  let hash = 5381;
  for (let i = 0; i < id.length; i++) {
    // hash * 33 + charCode, kept in 32-bit integer range.
    hash = ((hash << 5) + hash + id.charCodeAt(i)) | 0;
  }
  // Map to [0, 1) — take absolute value and mod by a large prime.
  return Math.abs(hash % 10007) / 10007;
}

/**
 * Compute a unique blended body color for an agent based on skin tone + role accent.
 *
 * Skin tone: warm hues (HSL hue 20-35 deg = 0.055–0.097), saturation 0.3–0.6,
 * lightness 0.3–0.8. The exact values are derived deterministically from agent ID.
 *
 * Role accent: blended in at 30% opacity so role is subtly visible even in
 * the default unique-color mode.
 *
 * @param {string} id - Agent ID for deterministic hashing.
 * @param {string} role - Agent role string.
 * @param {THREE.Color} out - Scratch color to write into (avoids allocation).
 * @returns {THREE.Color} The `out` color, modified in place.
 */
function computeUniqueColor(id, role, out) {
  const h = hashAgentId(id);
  // Use a second hash variant for a second independent random dimension.
  const h2 = hashAgentId(id + '_skin');

  // Skin tone in HSL space: hue 20–35 degrees mapped to Three.js 0–1 range.
  // 20 deg = 20/360 ≈ 0.055, 35 deg = 35/360 ≈ 0.097
  const skinHue = 0.055 + h * 0.042;
  const skinSat = 0.3 + h2 * 0.3;       // 0.3 – 0.6
  const skinLight = 0.3 + h * 0.5;       // 0.3 – 0.8

  out.setHSL(skinHue, skinSat, skinLight);

  // Blend in role accent at 30% to give a subtle role-based tint.
  const roleName = (role || '').toLowerCase();
  const roleColor = ROLE_COLORS[roleName] || DEFAULT_ROLE_COLOR;
  out.lerp(roleColor, 0.3);

  return out;
}

/**
 * Renders simulation agents as low-poly humanoid figures via InstancedMesh.
 *
 * Each agent is a procedural humanoid (head + torso + arms + legs) whose
 * position, color, and visibility are driven by the agent snapshot array.
 * All body parts are merged into a single geometry so the entire population
 * renders in one draw call.
 */
export class AgentRenderer {
  /**
   * @param {THREE.Scene} scene - The Three.js scene to add agents to.
   * @param {number} maxAgents - Pre-allocated instance capacity.
   * @param {number} heightScale - Vertical exaggeration factor matching the terrain renderer.
   *   Agent Y positions are multiplied by this so they sit on the terrain surface.
   *   Defaults to 1.0 (no exaggeration).
   */
  constructor(scene, maxAgents = 1024, heightScale = 1.0) {
    /** @type {THREE.Scene} */
    this._scene = scene;

    /** @type {number} Maximum agent instances. Determines GPU buffer sizes. */
    this._maxAgents = maxAgents;

    /** @type {number} Vertical exaggeration factor — must match terrain's heightScale. */
    this._heightScale = heightScale;

    /** @type {string} Current color mode — one of the COLOR_MODE_* constants. */
    this._colorMode = COLOR_MODE_BY_FACTION;

    // ── Build the humanoid geometry ─────────────────────────────────────────
    // All body parts merged into one BufferGeometry for single-draw-call instancing.
    const geometry = buildHumanoidGeometry();

    const material = new THREE.MeshStandardMaterial({
      roughness: 0.7,
      metalness: 0.05,
      // Flat shading emphasizes the low-poly aesthetic.
      flatShading: true,
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

    // Second scratch color for blending operations in computeUniqueColor.
    /** @type {THREE.Color} */
    this._scratchColor2 = new THREE.Color();

    this._scene.add(this._mesh);
  }

  /**
   * Update agent positions and colors from the simulation snapshot.
   *
   * Agent data shape (from the simulation engine):
   * {
   *   id: 'agent-0',
   *   alive: true,
   *   position: { x: -2.3, y: 0.45, z: 1.8 },
   *   health: { hp: 100, injury: 0, infection: false, diseaseSeverity: 0 },
   *   factionId: null | integer,
   *   role: 'gatherer' | 'hunter' | 'trader' | 'builder' | 'healer' | 'soldier' | 'leader',
   * }
   *
   * @param {Array<Object>} agents - Array of agent state objects.
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
        // Extract position — support both { position: {x,y,z} } shape (sim engine)
        // and flat { x, y, z } shape (legacy/test) for robustness.
        const pos = agent.position || agent;
        const ax = pos.x || 0;
        const ay = pos.y || 0;
        const az = pos.z || 0;

        // Apply heightScale to the Y coordinate so agents match the terrain's
        // vertical exaggeration. The humanoid geometry has Y=0 at the feet,
        // so no additional radius offset is needed — agents stand on the surface.
        this._dummy.position.set(ax, ay * this._heightScale, az);
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

    // Mark buffers dirty for GPU re-upload — done once after the batch,
    // NOT per-instance, to minimize driver overhead.
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
   * Color modes:
   * - BY_FACTION: Each faction gets a distinct hue from the palette.
   * - BY_HEALTH: Green-to-red gradient based on normalized HP.
   * - BY_ROLE: Unique per-agent color blending skin tone with role accent.
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
        // Support both agent.factionId (sim engine) and agent.faction (legacy).
        const factionId = agent.factionId ?? agent.faction ?? 0;
        const hue = FACTION_HUES[factionId % FACTION_HUES.length];
        // Saturation and lightness are fixed for readability against terrain.
        return c.setHSL(hue, 0.7, 0.5);
      }

      case COLOR_MODE_BY_HEALTH: {
        // Normalize HP: agent.health may be { hp: 100 } object or a 0-1 float.
        let health;
        if (agent.health && typeof agent.health === 'object') {
          // Assume max HP of 100 if not specified. Clamp to [0, 1].
          health = Math.max(0, Math.min(1, (agent.health.hp || 0) / 100));
        } else {
          health = Math.max(0, Math.min(1, agent.health || 0));
        }
        // Green (hue 0.33) at full health, red (hue 0.0) at zero health.
        const hue = health * 0.33;
        return c.setHSL(hue, 0.8, 0.45);
      }

      case COLOR_MODE_BY_ROLE: {
        // Use the unique per-agent color that blends skin tone with role accent.
        // This gives each agent a distinctive appearance while still showing role.
        const agentId = agent.id || `agent-${0}`;
        const role = agent.role || '';
        return computeUniqueColor(agentId, role, c);
      }

      default:
        return c.copy(DEFAULT_ROLE_COLOR);
    }
  }

  /**
   * Release GPU resources.
   *
   * After calling dispose(), this instance must not be used again.
   * The merged humanoid geometry and material are both freed.
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
