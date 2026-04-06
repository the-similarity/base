/**
 * Rendering helpers for the API-driven terrain mode.
 *
 * Separation of concerns:
 * - The backend decides terrain semantics: heightmap, biome, flow, features.
 * - This file decides how those semantics become visual objects in Three.js.
 * - It does not own camera controls, UI events, or scene lifecycle.
 *
 * A useful mental model for future agents:
 * - `buildTerrainMesh(...)` renders the ground surface and water layer.
 * - `buildFeatures(...)` renders discrete objects placed on top of the terrain.
 * - All coordinates coming in are grid-space or normalized domain-space, and
 *   this file maps them into world-space.
 */

import * as THREE from 'three';

// Biome IDs are contract values from the Python terrain generator.
// These constants are duplicated here so the renderer can remain lightweight
// and not depend on a shared generated schema artifact.
const BIOME_WATER  = 0;
const BIOME_SAND   = 1;
const BIOME_GRASS  = 2;
const BIOME_FOREST = 3;
const BIOME_ROCK   = 4;
const BIOME_SNOW   = 5;

// Default representative colors per biome.
// These are not physically accurate materials; they are intentionally stylized
// base tones that still read clearly from a distance.
const BIOME_COLORS = {
  [BIOME_WATER]:  { r: 0.12, g: 0.30, b: 0.50 },
  [BIOME_SAND]:   { r: 0.82, g: 0.74, b: 0.55 },
  [BIOME_GRASS]:  { r: 0.28, g: 0.52, b: 0.18 },
  [BIOME_FOREST]: { r: 0.15, g: 0.38, b: 0.12 },
  [BIOME_ROCK]:   { r: 0.45, g: 0.42, b: 0.40 },
  [BIOME_SNOW]:   { r: 0.95, g: 0.96, b: 0.98 },
};

/**
 * Build terrain mesh from generated data.
 *
 * @param {Object} data - Response from /terrain/generate
 * @param {number} worldScale - World-space scale factor
 * @param {number} heightScale - Vertical exaggeration
 * @returns {{ mesh: THREE.Mesh, waterMesh: THREE.Mesh|null }}
 */
export function buildTerrainMesh(data, worldScale = 10, heightScale = 2.1) {
  const size = data.size;
  const heightmap = data.heightmap;
  const biome = data.biome;
  const moisture = data.moisture;
  const params = data.params || {};

  // Build a regular grid in the XZ plane. The backend gives us a scalar field
  // (height per cell), so a subdivided plane is the natural base geometry.
  const geometry = new THREE.PlaneGeometry(worldScale, worldScale, size - 1, size - 1);
  geometry.rotateX(-Math.PI / 2);

  const posAttr = geometry.attributes.position;
  const colors = new Float32Array(posAttr.count * 3);

  for (let i = 0; i < posAttr.count; i++) {
    // Lift each grid vertex vertically using the normalized backend heightmap.
    const h = heightmap[i] || 0;
    posAttr.setY(i, h * heightScale);

    // Start from the biome's canonical base color.
    const b = biome[i] || BIOME_GRASS;
    let baseColor = BIOME_COLORS[b] || BIOME_COLORS[BIOME_GRASS];

    // River/stream hinting:
    // high flow on non-water biomes gets blended toward the water palette so
    // drainage channels remain visible even before modeling explicit rivers.
    const flowVal = data.flow[i] || 0;
    if (b !== BIOME_WATER && flowVal > 1.2) {
      // Flow magnitude spans orders of magnitude, so log scale prevents a few
      // very large values from dominating the whole visual range.
      const flowNorm = (Math.log10(flowVal) - 0.05) / 2.0; 
      const blend = Math.max(0, Math.min(1.0, flowNorm));
      if (blend > 0) {
        const waterColor = BIOME_COLORS[BIOME_WATER];
        baseColor = {
          r: baseColor.r * (1 - blend) + waterColor.r * blend,
          g: baseColor.g * (1 - blend) + waterColor.g * blend,
          b: baseColor.b * (1 - blend) + waterColor.b * blend,
        };
      }
    }

    // Add small variation so the surface does not look like flat poster paint.
    // Moisture shifts the palette subtly greener / darker, while random noise
    // breaks up overly uniform patches.
    const m = moisture[i] || 0;
    const variation = (Math.random() - 0.5) * 0.05;

    colors[i * 3]     = Math.max(0, Math.min(1, baseColor.r + variation - m * 0.05));
    colors[i * 3 + 1] = Math.max(0, Math.min(1, baseColor.g + variation + m * 0.08));
    colors[i * 3 + 2] = Math.max(0, Math.min(1, baseColor.b + variation));
  }

  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  // We recompute normals after moving vertices vertically so lighting matches
  // the actual terrain slopes rather than the original flat plane.
  geometry.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    flatShading: false,
    roughness: 0.85,
    metalness: 0.05,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(geometry, material);

  // Water is modeled as one simple translucent plane at a global water level.
  // That is much cheaper than meshing water against the terrain surface.
  const waterLevel = (params.water_level || 0.2) * heightScale;
  const waterMesh = createWaterPlane(worldScale, waterLevel);

  return { mesh, waterMesh };
}


/**
 * Create the global water surface used in engine mode.
 *
 * The plane is deliberately oversized so the user does not see terrain edges
 * peeking beyond the water at shallow viewing angles.
 */
function createWaterPlane(worldScale, waterLevel) {
  const waterGeo = new THREE.PlaneGeometry(worldScale * 1.2, worldScale * 1.2);
  waterGeo.rotateX(-Math.PI / 2);

  const waterMat = new THREE.MeshStandardMaterial({
    color: 0x1a6b8a,
    transparent: true,
    opacity: 0.6,
    roughness: 0.1,
    metalness: 0.3,
    side: THREE.DoubleSide,
  });

  const waterMesh = new THREE.Mesh(waterGeo, waterMat);
  waterMesh.position.y = waterLevel;
  return waterMesh;
}


/**
 * Convert backend feature metadata into grouped instanced meshes.
 *
 * Why instancing:
 * - Trees / rocks / bushes can number in the hundreds.
 * - Instanced meshes keep draw calls low and are the right default for this
 *   kind of repeated decorative geometry.
 *
 * @param {Array} features - Feature list from /terrain/generate
 * @param {number} size - Heightmap size
 * @param {number} worldScale - World-space scale
 * @param {number} heightScale - Vertical exaggeration
 * @param {Float32Array|Array} heightmap - Raw heightmap
 * @returns {THREE.Group}
 */
export function buildFeatures(features, size, worldScale, heightScale, heightmap) {
  const group = new THREE.Group();

  if (!features || features.length === 0) return group;

  // Partition by coarse family so each family can use geometry and material
  // that suits it without per-instance branching during rendering.
  const treeFeatures = features.filter(f => f.type.startsWith('tree_'));
  const rockFeatures = features.filter(f => f.type.startsWith('rock_') || f.type === 'boulder');
  const bushFeatures = features.filter(f => f.type === 'bush');

  // Trees are approximated as trunk + canopy meshes.
  if (treeFeatures.length > 0) {
    const treeMeshes = buildInstancedTrees(treeFeatures, size, worldScale, heightScale, heightmap);
    group.add(treeMeshes);
  }

  // Rocks use a chunky low-poly primitive to stay visually readable.
  if (rockFeatures.length > 0) {
    const rockMeshes = buildInstancedRocks(rockFeatures, size, worldScale, heightScale, heightmap);
    group.add(rockMeshes);
  }

  // Bushes are the cheapest filler asset: small flattened spheres.
  if (bushFeatures.length > 0) {
    const bushMeshes = buildInstancedBushes(bushFeatures, size, worldScale, heightScale, heightmap);
    group.add(bushMeshes);
  }

  return group;
}


function buildInstancedTrees(features, size, worldScale, heightScale, heightmap) {
  const group = new THREE.Group();

  // Tree asset decomposition:
  // - one instanced mesh for trunks
  // - one instanced mesh for canopies
  // Using two primitive meshes keeps the asset cheap but still legible.
  const trunkGeo = new THREE.CylinderGeometry(0.01, 0.015, 0.2, 5);
  const trunkMat = new THREE.MeshStandardMaterial({
    color: 0x5c3a1e,
    roughness: 0.9,
    metalness: 0.0,
  });

  const canopyGeo = new THREE.ConeGeometry(0.06, 0.18, 6);
  const canopyMat = new THREE.MeshStandardMaterial({
    color: 0x1a5c1a,
    roughness: 0.8,
    metalness: 0.0,
  });

  const trunkInstanced = new THREE.InstancedMesh(trunkGeo, trunkMat, features.length);
  const canopyInstanced = new THREE.InstancedMesh(canopyGeo, canopyMat, features.length);

  // `dummy` is the standard Three.js pattern for composing per-instance
  // transforms before copying the resulting matrix into an InstancedMesh.
  const dummy = new THREE.Object3D();

  for (let i = 0; i < features.length; i++) {
    const f = features[i];

    // Backend feature coordinates are in terrain grid space.
    // We remap them into centered world coordinates here.
    const wx = (f.x / size - 0.5) * worldScale;
    const wz = (f.y / size - 0.5) * worldScale;
    const wy = f.z * heightScale;
    const scale = f.scale || 1.0;

    // Trunk sits lower; canopy is stacked above it with the same transform
    // family so both pieces read as one tree.
    dummy.position.set(wx, wy + 0.1 * scale, wz);
    dummy.scale.set(scale, scale, scale);
    dummy.rotation.set(0, f.rotation || 0, 0);
    dummy.updateMatrix();
    trunkInstanced.setMatrixAt(i, dummy.matrix);

    // Canopy
    dummy.position.set(wx, wy + 0.22 * scale, wz);
    dummy.updateMatrix();
    canopyInstanced.setMatrixAt(i, dummy.matrix);

    // Variant-based hue shifts stop forests from looking copy-pasted.
    const hue = 0.28 + (f.variant || 0) * 0.03;
    canopyInstanced.setColorAt(i, new THREE.Color().setHSL(hue, 0.6, 0.25 + Math.random() * 0.1));
  }

  // Explicitly mark instance buffers dirty after bulk writes.
  trunkInstanced.instanceMatrix.needsUpdate = true;
  canopyInstanced.instanceMatrix.needsUpdate = true;
  if (canopyInstanced.instanceColor) canopyInstanced.instanceColor.needsUpdate = true;

  group.add(trunkInstanced);
  group.add(canopyInstanced);
  return group;
}


function buildInstancedRocks(features, size, worldScale, heightScale, heightmap) {
  // Rock geometry stays intentionally low resolution so large fields of rocks
  // remain cheap to draw and visually consistent with the terrain style.
  const rockGeo = new THREE.DodecahedronGeometry(0.03, 0);
  const rockMat = new THREE.MeshStandardMaterial({
    color: 0x6b6560,
    roughness: 0.95,
    metalness: 0.05,
    flatShading: true,
  });

  const instanced = new THREE.InstancedMesh(rockGeo, rockMat, features.length);
  const dummy = new THREE.Object3D();

  for (let i = 0; i < features.length; i++) {
    const f = features[i];
    const wx = (f.x / size - 0.5) * worldScale;
    const wz = (f.y / size - 0.5) * worldScale;
    const wy = f.z * heightScale;
    const scale = f.scale || 1.0;

    dummy.position.set(wx, wy + 0.01 * scale, wz);
    dummy.scale.set(scale, scale * 0.7, scale);
    dummy.rotation.set(f.rotation * 0.3, f.rotation, 0);
    dummy.updateMatrix();
    instanced.setMatrixAt(i, dummy.matrix);

    // Tiny value variation keeps the rocks from reading as identical clones.
    const gray = 0.35 + (f.variant || 0) * 0.05 + Math.random() * 0.05;
    instanced.setColorAt(i, new THREE.Color(gray, gray * 0.98, gray * 0.95));
  }

  instanced.instanceMatrix.needsUpdate = true;
  if (instanced.instanceColor) instanced.instanceColor.needsUpdate = true;
  return instanced;
}


function buildInstancedBushes(features, size, worldScale, heightScale, heightmap) {
  // Bushes are simple filler details. We do not color-vary them yet because
  // they are visually secondary and their geometry is already cheap.
  const bushGeo = new THREE.SphereGeometry(0.025, 5, 4);
  const bushMat = new THREE.MeshStandardMaterial({
    color: 0x2d7a2d,
    roughness: 0.85,
    metalness: 0.0,
  });

  const instanced = new THREE.InstancedMesh(bushGeo, bushMat, features.length);
  const dummy = new THREE.Object3D();

  for (let i = 0; i < features.length; i++) {
    const f = features[i];
    const wx = (f.x / size - 0.5) * worldScale;
    const wz = (f.y / size - 0.5) * worldScale;
    const wy = f.z * heightScale;
    const scale = f.scale || 1.0;

    dummy.position.set(wx, wy + 0.012 * scale, wz);
    dummy.scale.set(scale, scale * 0.6, scale);
    dummy.rotation.set(0, f.rotation, 0);
    dummy.updateMatrix();
    instanced.setMatrixAt(i, dummy.matrix);
  }

  // Bushes only update transforms, not per-instance colors.
  instanced.instanceMatrix.needsUpdate = true;
  return instanced;
}
