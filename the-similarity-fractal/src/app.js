import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { generateTerrain } from './fractal.js';
import { buildTerrainMesh, buildFeatures } from './terrain-renderer.js';

// ── Nature engine imports ────────────────────────────────────────────────────
// Procedural environment systems for Engine mode. Each module was built
// independently and merged via separate PRs. They attach to the terrain mesh
// after it is constructed and update per-frame in the animation loop.
import { createTerrainMaterial } from './nature/terrain-material.js';
import { Water } from './nature/water.js';
import { TreeSystem } from './nature/trees.js';
import { GrassSystem } from './nature/grass.js';
import { FlowerSystem } from './nature/flowers.js';
import { ProceduralSky } from './nature/sky.js';
import { Atmosphere } from './nature/atmosphere.js';
import { PostProcessing } from './nature/post-processing.js';
import { RockSystem } from './nature/rocks.js';
import { DebrisSystem } from './nature/debris.js';

// ── Simulation module imports ────────────────────────────────────────────────
// These power the 3D society simulation mode ("sim"). Each module was built
// independently and merged via separate PRs. The integration wires them into
// the existing app lifecycle alongside classic and engine terrain modes.
import { SimEngine } from './sim/engine.js';
import { PRNG } from './sim/rng.js';
import { sampleTerrain as sampleTerrainGrids } from './world/terrain-sampler.js';
import { NavGrid } from './world/nav-grid.js';
import { RegionMap } from './world/region-map.js';
import { ResourceField } from './world/resource-field.js';
import { generatePOIs } from './world/poi-generator.js';
// Climate is managed internally by EnvironmentSystem — no direct import needed.
// createAgent is not imported directly — agents are spawned via LifecycleSystem.
import { LifecycleSystem } from './sim/lifecycle-system.js';
import { MovementSystem } from './sim/movement-system.js';
import { PerceptionSystem } from './sim/perception-system.js';
import { LODSystem } from './sim/lod-system.js';
import { DecisionSystem } from './sim/decision-system.js';
import { InteractionSystem } from './sim/interaction-system.js';
import { EconomySystem } from './sim/economy-system.js';
import { DiseaseSystem } from './sim/disease-system.js';
import { FactionSystem } from './sim/faction-system.js';
import { TelemetrySystem } from './sim/telemetry-system.js';
import { SimilaritySystem } from './sim/similarity-system.js';
import { EnvironmentSystem } from './sim/environment-system.js';
import { EventBus } from './sim/event-bus.js';
import { DEFAULT_SIM_CONFIG } from './data/sim-config.js';
import { SceneBridge } from './render/scene-bridges.js';
import {
  AgentRenderer,
  COLOR_MODE_BY_FACTION,
  COLOR_MODE_BY_HEALTH,
  COLOR_MODE_BY_ROLE,
} from './render/agent-renderer.js';
import { DebugOverlays } from './render/debug-overlays.js';
import { HeatmapRenderer } from './render/heatmap-renderer.js';

/**
 * Browser entrypoint for the fractal terrain demo.
 *
 * This file owns:
 * - scene setup
 * - camera / controls
 * - DOM wiring
 * - switching between the two terrain sources
 * - animation and lightweight first-person exploration
 *
 * It does not own:
 * - the local fractal generation algorithm itself (`fractal.js`)
 * - API terrain semantics / biome generation
 * - the engine-mode terrain mesh construction details (`terrain-renderer.js`)
 *
 * There are three rendering modes:
 * 1. `classic`: fully local midpoint-displacement fractal terrain
 * 2. `engine`: terrain fetched from a backend API, then rendered locally
 * 3. `sim`: 3D society simulation — agent-based model running on terrain
 *
 * Future-agent note:
 * - If terrain math looks wrong, start in `fractal.js`.
 * - If materials / feature placement look wrong, start in `terrain-renderer.js`.
 * - If controls, mode switching, or scene lifecycle look wrong, this file owns it.
 */

// Color ramps used only by Classic mode.
// Engine mode receives biome semantics from the backend instead of a single
// height-to-color mapping.
const COLOR_MAPS = {
  terrain: [
    { t: 0.0,  r: 0.18, g: 0.32, b: 0.12 },
    { t: 0.25, r: 0.35, g: 0.55, b: 0.20 },
    { t: 0.45, r: 0.55, g: 0.50, b: 0.30 },
    { t: 0.60, r: 0.60, g: 0.50, b: 0.35 },
    { t: 0.75, r: 0.70, g: 0.65, b: 0.55 },
    { t: 0.88, r: 0.82, g: 0.80, b: 0.78 },
    { t: 1.0,  r: 1.00, g: 0.98, b: 0.96 },
  ],
  snow: [
    { t: 0.0,  r: 0.20, g: 0.25, b: 0.35 },
    { t: 0.3,  r: 0.45, g: 0.50, b: 0.58 },
    { t: 0.6,  r: 0.70, g: 0.75, b: 0.80 },
    { t: 0.8,  r: 0.88, g: 0.90, b: 0.93 },
    { t: 1.0,  r: 1.00, g: 1.00, b: 1.00 },
  ],
  volcanic: [
    { t: 0.0,  r: 0.10, g: 0.02, b: 0.02 },
    { t: 0.2,  r: 0.40, g: 0.05, b: 0.02 },
    { t: 0.4,  r: 0.80, g: 0.15, b: 0.02 },
    { t: 0.6,  r: 0.95, g: 0.40, b: 0.05 },
    { t: 0.8,  r: 0.30, g: 0.25, b: 0.25 },
    { t: 1.0,  r: 0.15, g: 0.12, b: 0.12 },
  ],
  ocean: [
    { t: 0.0,  r: 0.02, g: 0.05, b: 0.20 },
    { t: 0.3,  r: 0.05, g: 0.15, b: 0.40 },
    { t: 0.5,  r: 0.10, g: 0.30, b: 0.50 },
    { t: 0.7,  r: 0.20, g: 0.50, b: 0.55 },
    { t: 0.85, r: 0.40, g: 0.65, b: 0.60 },
    { t: 1.0,  r: 0.70, g: 0.85, b: 0.75 },
  ],
  alien: [
    { t: 0.0,  r: 0.05, g: 0.00, b: 0.15 },
    { t: 0.2,  r: 0.20, g: 0.00, b: 0.40 },
    { t: 0.4,  r: 0.50, g: 0.05, b: 0.60 },
    { t: 0.6,  r: 0.20, g: 0.80, b: 0.40 },
    { t: 0.8,  r: 0.90, g: 0.90, b: 0.10 },
    { t: 1.0,  r: 1.00, g: 0.50, b: 0.80 },
  ],
  mono: [
    { t: 0.0, r: 0.08, g: 0.08, b: 0.10 },
    { t: 0.5, r: 0.40, g: 0.42, b: 0.45 },
    { t: 1.0, r: 0.90, g: 0.90, b: 0.92 },
  ],
};

function sampleColorMap(map, t) {
  // Piecewise-linear interpolation between neighboring color stops.
  // Input `t` is expected in [0, 1], but we clamp defensively.
  const stops = COLOR_MAPS[map] || COLOR_MAPS.terrain;
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i].t) {
      const a = stops[i - 1], b = stops[i];
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

// Core Three.js scene graph setup.
// The scene is intentionally small and direct: one scene, one camera, one
// renderer, one terrain surface, plus optional overlays and feature groups.
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a0f);
scene.fog = new THREE.FogExp2(0x0a0a0f, 0.025);

// Perspective tuned for "tabletop terrain" viewing rather than true FPS-only play.
const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(6, 5, 8);
camera.lookAt(0, 0, 0);

// Tone mapping and shadows matter a lot for terrain readability.
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

// Orbit controls are the default inspection mode.
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.minDistance = 2;
controls.maxDistance = 30;
controls.maxPolarAngle = Math.PI / 2 + 0.3;

// Pointer-lock controls are only enabled for "explore mode".
const fpsControls = new PointerLockControls(camera, document.body);
scene.add(fpsControls.getObject());

// Transient state for first-person movement.
let isExploreMode = false;
const velocity = new THREE.Vector3();
const direction = new THREE.Vector3();
const moveState = { forward: false, backward: false, left: false, right: false, run: false };
let canJump = false;
let prevTime = performance.now();

// One raycaster is reused for all "what is under / in front of me?" queries.
const raycaster = new THREE.Raycaster();
const downVector = new THREE.Vector3(0, -1, 0);

// Lighting is slightly stylized but designed to keep slopes and silhouettes legible.
const ambientLight = new THREE.AmbientLight(0x334455, 0.6);
scene.add(ambientLight);

// Main sun-like key light.
const dirLight = new THREE.DirectionalLight(0xffeedd, 1.8);
dirLight.position.set(5, 10, 3);
dirLight.castShadow = true;
dirLight.shadow.mapSize.width = 2048;
dirLight.shadow.mapSize.height = 2048;
dirLight.shadow.camera.near = 0.5;
dirLight.shadow.camera.far = 30;
dirLight.shadow.camera.left = -8;
dirLight.shadow.camera.right = 8;
dirLight.shadow.camera.top = 8;
dirLight.shadow.camera.bottom = -8;
scene.add(dirLight);

// Secondary rim/fill light to stop the back side of hills from collapsing to black.
const backLight = new THREE.DirectionalLight(0x4488cc, 0.4);
backLight.position.set(-3, 4, -5);
scene.add(backLight);

// Gentle sky/ground ambient split for outdoor readability.
const hemiLight = new THREE.HemisphereLight(0x87CEEB, 0x362a1a, 0.3);
scene.add(hemiLight);

// Application-level state.
//
// Ownership notes:
// - Only one terrain is "live" at a time, but classic/engine share the same
//   scene slots (`terrainMesh`, `waterMesh`, `featureGroup`, etc.).
// - `currentSeed` is the main reproducibility handle for both modes.
let currentSeed = Math.floor(Math.random() * 100000);
let terrainMesh = null;
let wireframeMesh = null;
let waterMesh = null;
let featureGroup = null;
let showWireframe = false;
let flatShading = true;
let animating = false;
let animTime = 0;
let currentMode = 'classic';  // 'classic', 'engine', or 'sim'
let suppressHistoryRecording = false;

// ── Simulation mode state ────────────────────────────────────────────────────
// These are populated when entering sim mode and torn down when leaving it.
// All are null/false when sim mode is inactive, preventing accidental ticks.

/** @type {SimEngine|null} The active simulation engine instance. */
let simEngine = null;

/** @type {AgentRenderer|null} Instanced mesh renderer for agent positions. */
let simAgentRenderer = null;

/** @type {DebugOverlays|null} Debug visualization layers (nav grid, regions, etc). */
let simDebugOverlays = null;

/** @type {HeatmapRenderer|null} Heatmap overlay for resource/conflict/disease fields. */
let simHeatmapRenderer = null;

/** @type {SceneBridge|null} Bridge between simulation snapshot and Three.js scene. */
let simSceneBridge = null;

/** @type {boolean} Whether the simulation tick loop is running. */
let simPlaying = false;

/** @type {number} Simulation speed multiplier (1-4). */
let simSpeed = 1;

/** @type {NavGrid|null} Cached nav grid for overlay toggling. */
let simNavGrid = null;

/** @type {RegionMap|null} Cached region map for overlay toggling. */
let simRegionMap = null;

/** @type {Array|null} Cached POI list for overlay toggling. */
let simPOIs = null;

/** @type {PerceptionSystem|null} Cached perception system ref for overlay data. */
let simPerceptionSystem = null;

/** @type {number} Timestamp of the last animation frame, for delta calculation. */
let simLastFrameTime = 0;

/** @type {boolean} Whether the heatmap overlay is currently shown. */
let heatmapVisible = false;

// Derive API origin from the current page so localhost vs 127.0.0.1 never
// causes a CORS mismatch.  The similarity API runs on port 8001.
const API_URL = `${window.location.protocol}//${window.location.hostname}:8001`;

// FPS traversal scale constants.
// The terrain world is tiny relative to default first-person controller values,
// so the camera eye height and all movement forces need to stay very small.
const FPS_EYE_HEIGHT = 0.12;
const FPS_GROUND_SNAP_DISTANCE = 0.01;
const FPS_JUMP_VELOCITY = 0.18;
const FPS_GRAVITY = 0.32;
const FPS_WALK_SPEED = 0.3;
const FPS_RUN_SPEED = 0.8;
const FPS_LANDING_VELOCITY_THRESHOLD = -0.06;
const WORLD_HISTORY_STORAGE_KEY = 'the-similarity:fractal-world-history';
const WORLD_CURRENT_STORAGE_KEY = 'the-similarity:fractal-current-world';
const MENU_COLLAPSED_STORAGE_KEY = 'the-similarity:fractal-menu-collapsed';
const MAX_WORLD_HISTORY = 20;

/**
 * Dispose and detach the currently rendered terrain-related objects.
 *
 * This is the boundary between "old terrain" and "new terrain".
 * Any terrain rebuild should go through this cleanup step first so GPU memory
 * does not leak across repeated generations.
 */
function clearScene() {
  if (terrainMesh) {
    scene.remove(terrainMesh);
    terrainMesh.geometry.dispose();
    terrainMesh.material.dispose();
    terrainMesh = null;
  }
  if (wireframeMesh) {
    scene.remove(wireframeMesh);
    wireframeMesh.geometry.dispose();
    wireframeMesh.material.dispose();
    wireframeMesh = null;
  }
  if (waterMesh) {
    scene.remove(waterMesh);
    waterMesh.geometry.dispose();
    waterMesh.material.dispose();
    waterMesh = null;
  }
  if (featureGroup) {
    scene.remove(featureGroup);
    featureGroup.traverse((child) => {
      if (child.geometry) child.geometry.dispose();
      if (child.material) child.material.dispose();
    });
    featureGroup = null;
  }
}

/**
 * Capture the current control state as a deterministic world snapshot.
 *
 * We persist parameters and seed instead of generated geometry buffers so the
 * app can rebuild worlds cheaply and keep the saved format stable.
 */
function captureWorldState() {
  return {
    id: `${currentMode}-${currentSeed}`,
    mode: currentMode,
    seed: currentSeed,
    createdAt: new Date().toISOString(),
    classic: {
      iterations: parseInt(document.getElementById('iterations').value),
      roughness: parseFloat(document.getElementById('roughness').value),
      displacement: parseFloat(document.getElementById('displacement').value),
      scale: parseFloat(document.getElementById('scale').value),
      flatness: parseFloat(document.getElementById('flatness').value),
      colormap: document.getElementById('colormap').value,
    },
    engine: {
      preset: document.getElementById('preset').value,
      size: parseInt(document.getElementById('engine-size').value),
    },
  };
}

function worldLabel(snapshot) {
  if (snapshot.mode === 'engine') {
    return `Engine · ${snapshot.engine.preset} · ${snapshot.engine.size} · seed ${snapshot.seed}`;
  }
  return `Classic · iter ${snapshot.classic.iterations} · seed ${snapshot.seed}`;
}

function readWorldHistory() {
  try {
    const raw = localStorage.getItem(WORLD_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeWorldHistory(history) {
  localStorage.setItem(WORLD_HISTORY_STORAGE_KEY, JSON.stringify(history.slice(0, MAX_WORLD_HISTORY)));
}

function persistCurrentWorld() {
  localStorage.setItem(WORLD_CURRENT_STORAGE_KEY, JSON.stringify(captureWorldState()));
}

function refreshHistoryOptions(selectedId = '') {
  const select = document.getElementById('history-select');
  if (!select) return;
  const history = readWorldHistory();

  select.innerHTML = '';
  if (history.length === 0) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No saved worlds yet';
    select.appendChild(option);
    return;
  }

  for (const snapshot of history) {
    const option = document.createElement('option');
    option.value = snapshot.id;
    option.textContent = worldLabel(snapshot);
    if (snapshot.id === selectedId) option.selected = true;
    select.appendChild(option);
  }
}

function recordWorldInHistory() {
  const snapshot = captureWorldState();
  const history = readWorldHistory().filter((item) => item.id !== snapshot.id);
  history.unshift(snapshot);
  writeWorldHistory(history);
  refreshHistoryOptions(snapshot.id);
}

function applyMenuCollapsedState(isCollapsed) {
  const controlsPanel = document.getElementById('controls');
  const toggleButton = document.getElementById('menu-toggle');
  if (!controlsPanel || !toggleButton) return;

  controlsPanel.classList.toggle('is-collapsed', isCollapsed);
  toggleButton.classList.toggle('is-inline', !isCollapsed);
  toggleButton.textContent = isCollapsed ? 'Menu' : 'Hide';
  toggleButton.setAttribute('aria-expanded', String(!isCollapsed));
  localStorage.setItem(MENU_COLLAPSED_STORAGE_KEY, JSON.stringify(isCollapsed));
}

function restoreMenuCollapsedState() {
  try {
    const raw = localStorage.getItem(MENU_COLLAPSED_STORAGE_KEY);
    applyMenuCollapsedState(raw ? JSON.parse(raw) === true : false);
  } catch {
    applyMenuCollapsedState(false);
  }
}

/**
 * Restore a saved world snapshot into the controls and rebuild from it.
 *
 * History recording is temporarily suppressed during restore so loading a
 * snapshot does not create an immediate duplicate history entry.
 */
function applyWorldState(snapshot) {
  suppressHistoryRecording = true;

  currentSeed = snapshot.seed;
  currentMode = snapshot.mode === 'engine' ? 'engine' : 'classic';

  document.getElementById('iterations').value = String(snapshot.classic.iterations);
  document.getElementById('roughness').value = String(snapshot.classic.roughness);
  document.getElementById('displacement').value = String(snapshot.classic.displacement);
  document.getElementById('scale').value = String(snapshot.classic.scale);
  document.getElementById('colormap').value = snapshot.classic.colormap;
  // Flatness is new and may be absent on older snapshots — fall back
  // to the 0.35 default so pre-flatness saved worlds still hydrate.
  const flatnessVal = snapshot.classic.flatness ?? 0.35;
  document.getElementById('flatness').value = String(flatnessVal);
  document.getElementById('val-iterations').textContent = String(snapshot.classic.iterations);
  document.getElementById('val-roughness').textContent = Number(snapshot.classic.roughness).toFixed(2);
  document.getElementById('val-displacement').textContent = Number(snapshot.classic.displacement).toFixed(2);
  document.getElementById('val-scale').textContent = Number(snapshot.classic.scale).toFixed(2);
  document.getElementById('val-flatness').textContent = Number(flatnessVal).toFixed(2);

  document.getElementById('preset').value = snapshot.engine.preset;
  document.getElementById('engine-size').value = String(snapshot.engine.size);
  document.getElementById('val-engine-size').textContent = String(snapshot.engine.size);

  // Deactivate all mode buttons and hide all mode panels.
  document.getElementById('btn-classic').classList.remove('active');
  document.getElementById('btn-engine').classList.remove('active');
  document.getElementById('btn-sim').classList.remove('active');
  document.getElementById('classic-controls').style.display = 'none';
  document.getElementById('engine-controls').style.display = 'none';
  document.getElementById('sim-controls').style.display = 'none';

  if (currentMode === 'engine') {
    document.getElementById('btn-engine').classList.add('active');
    document.getElementById('engine-controls').style.display = '';
    buildEngineTerrain();
  } else {
    document.getElementById('btn-classic').classList.add('active');
    document.getElementById('classic-controls').style.display = '';
    buildClassicTerrain();
  }

  suppressHistoryRecording = false;
  persistCurrentWorld();
  refreshHistoryOptions(snapshot.id);
}

function restoreInitialWorld() {
  try {
    const raw = localStorage.getItem(WORLD_CURRENT_STORAGE_KEY);
    if (!raw) return false;
    const snapshot = JSON.parse(raw);
    if (!snapshot || !snapshot.mode || !snapshot.classic || !snapshot.engine) {
      return false;
    }
    applyWorldState(snapshot);
    return true;
  } catch {
    return false;
  }
}

/**
 * Build a Three.js terrain mesh from fractal generator output.
 *
 * Shared between buildClassicTerrain() and buildSimulation() to avoid
 * duplicating the geometry → color → material pipeline. The mesh is added
 * to the scene and assigned to the module-level `terrainMesh`.
 *
 * @param {object} terrain - Output from generateTerrain().
 * @param {string} colormap - Color ramp name from COLOR_MAPS.
 * @param {boolean} useFlat - Whether to use flat shading.
 */
function buildTerrainMeshFromFractal(terrain, colormap, useFlat) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(terrain.positions, 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(terrain.normals, 3));
  geometry.setIndex(new THREE.BufferAttribute(terrain.indices, 1));

  // Derive a normalized [0, 1] height coordinate for color lookup.
  let minH = Infinity, maxH = -Infinity;
  for (let i = 0; i < terrain.heights.length; i++) {
    minH = Math.min(minH, terrain.heights[i]);
    maxH = Math.max(maxH, terrain.heights[i]);
  }
  const range = maxH - minH || 1;

  // Color every vertex by sampled colormap height.
  const colors = new Float32Array(terrain.vertexCount * 3);
  for (let i = 0; i < terrain.vertexCount; i++) {
    const t = (terrain.heights[i] - minH) / range;
    const c = sampleColorMap(colormap, t);
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  if (useFlat) {
    const flatGeo = geometry.toNonIndexed();
    flatGeo.computeVertexNormals();
    // Raycaster needs bounding volumes for intersection testing.
    flatGeo.computeBoundingSphere();
    flatGeo.computeBoundingBox();
    const material = new THREE.MeshStandardMaterial({
      vertexColors: true, flatShading: true,
      roughness: 0.8, metalness: 0.1, side: THREE.DoubleSide,
    });
    terrainMesh = new THREE.Mesh(flatGeo, material);
    geometry.dispose();
  } else {
    const material = new THREE.MeshStandardMaterial({
      vertexColors: true, flatShading: false,
      roughness: 0.8, metalness: 0.1, side: THREE.DoubleSide,
    });
    terrainMesh = new THREE.Mesh(geometry, material);
  }

  terrainMesh.castShadow = true;
  terrainMesh.receiveShadow = true;
  scene.add(terrainMesh);
}

/**
 * Build terrain entirely in the browser using the local midpoint-displacement engine.
 *
 * Data flow:
 * DOM controls -> `generateTerrain(...)` -> typed arrays -> Three.js geometry
 *
 * This path is self-contained and does not require the backend API.
 */
function buildClassicTerrain() {
  const iterations = parseInt(document.getElementById('iterations').value);
  const roughness = parseFloat(document.getElementById('roughness').value);
  const displacementVal = parseFloat(document.getElementById('displacement').value);
  const scaleVal = parseFloat(document.getElementById('scale').value);
  const flatnessEl = document.getElementById('flatness');
  const flatnessVal = flatnessEl ? parseFloat(flatnessEl.value) : 0.35;
  const colormap = document.getElementById('colormap').value;

  const t0 = performance.now();
  const terrain = generateTerrain({
    iterations, roughness, displacement: displacementVal,
    scale: scaleVal, seed: currentSeed, baseShape: 'diamond',
    flatness: flatnessVal,
  });
  const genTime = (performance.now() - t0).toFixed(1);

  clearScene();
  buildTerrainMeshFromFractal(terrain, colormap, flatShading);

  // Separate wireframe mesh keeps toggling cheap and avoids mutating the main material.
  const wireGeo = new THREE.BufferGeometry();
  wireGeo.setAttribute('position', new THREE.BufferAttribute(terrain.positions.slice(), 3));
  wireGeo.setIndex(new THREE.BufferAttribute(terrain.indices.slice(), 1));
  const wireMat = new THREE.MeshBasicMaterial({
    color: 0x4fc3f7, wireframe: true, transparent: true, opacity: 0.15,
  });
  wireframeMesh = new THREE.Mesh(wireGeo, wireMat);
  wireframeMesh.visible = showWireframe;
  scene.add(wireframeMesh);

  document.getElementById('stats').textContent =
    `Classic · ${terrain.vertexCount.toLocaleString()} verts · ${terrain.faceCount.toLocaleString()} faces · ${genTime}ms`;
  document.getElementById('seed-display').textContent = `seed: ${currentSeed}`;
  persistCurrentWorld();
  if (!suppressHistoryRecording) refreshHistoryOptions();
}

/**
 * Build terrain from the backend "engine" endpoint.
 *
 * Expected backend contract:
 * - `heightmap`
 * - `biome`
 * - optional `flow`
 * - optional feature list
 * - terrain params such as water level
 *
 * Rendering details are delegated to `terrain-renderer.js`.
 */
async function buildEngineTerrain() {
  const preset = document.getElementById('preset').value;
  const engineSize = parseInt(document.getElementById('engine-size').value);

  document.getElementById('stats').textContent = 'Generating terrain...';

  try {
    const url = `${API_URL}/terrain/generate?preset=${preset}&size=${engineSize}&seed=${currentSeed}`;
    const resp = await fetch(url, { method: 'POST' });

    if (!resp.ok) {
      const err = await resp.text();
      document.getElementById('stats').textContent = `Error: ${err}`;
      return;
    }

    const data = await resp.json();

    clearScene();

    // We derive visible vertical exaggeration from the preset so "rolling
    // hills" and "alpine" do not collapse into the same apparent relief after
    // the backend normalizes the final heightmap to [0, 1].
    const reliefScale = Math.max(0.55, Math.min(1.15, data.params?.elevation_range ?? 1.0));
    const verticalScale = 2.1 * reliefScale;

    // The renderer helper owns the mapping from backend arrays to visual meshes.
    const { mesh, waterMesh: water } = buildTerrainMesh(data, 10, verticalScale);
    terrainMesh = mesh;
    terrainMesh.castShadow = true;
    terrainMesh.receiveShadow = true;
    scene.add(terrainMesh);

    if (water) {
      waterMesh = water;
      scene.add(waterMesh);
    }

    // Decorative / semantic features are optional and rendered as instanced meshes.
    if (data.features && data.features.length > 0) {
      featureGroup = buildFeatures(data.features, data.size, 10, verticalScale, data.heightmap);
      scene.add(featureGroup);
    }

    const featureCount = data.features ? data.features.length : 0;
    document.getElementById('stats').textContent =
      `Engine · ${preset} · ${data.size}×${data.size} · ${featureCount} features`;
    document.getElementById('seed-display').textContent = `seed: ${currentSeed}`;
    persistCurrentWorld();
    if (!suppressHistoryRecording) refreshHistoryOptions();

  } catch (e) {
    document.getElementById('stats').textContent = `Error: ${e.message}. Is the API running?`;
  }
}

// Small dispatcher so UI controls do not need to duplicate mode checks.
function buildTerrain() {
  if (currentMode === 'engine') {
    buildEngineTerrain();
  } else if (currentMode === 'sim') {
    buildSimulation();
  } else {
    buildClassicTerrain();
  }
}

/**
 * Tear down all simulation-specific objects and free GPU resources.
 *
 * Called when switching away from sim mode or before rebuilding the simulation.
 * Safe to call even if sim mode was never entered (all guards check for null).
 */
function teardownSimulation() {
  if (simEngine) {
    simEngine.reset();
    simEngine = null;
  }
  if (simAgentRenderer) {
    simAgentRenderer.dispose();
    simAgentRenderer = null;
  }
  if (simDebugOverlays) {
    simDebugOverlays.dispose();
    simDebugOverlays = null;
  }
  if (simHeatmapRenderer) {
    simHeatmapRenderer.dispose();
    simHeatmapRenderer = null;
  }
  if (simSceneBridge) {
    simSceneBridge.dispose();
    simSceneBridge = null;
  }
  simNavGrid = null;
  simRegionMap = null;
  simPOIs = null;
  simPerceptionSystem = null;
  simPlaying = false;
  simSpeed = 1;
  heatmapVisible = false;

  // Hide sim-specific UI elements.
  const telemetryEl = document.getElementById('sim-telemetry');
  if (telemetryEl) telemetryEl.style.display = 'none';
}

/**
 * Convert a RegionMap into the iterable-of-regions format that LifecycleSystem
 * expects: a Map-like with .values() yielding { id, cells: [{x, y, z}] }.
 *
 * RegionMap stores flat cell indices internally. We convert each index to
 * world-space {x, y, z} coordinates using the NavGrid's coordinate transform
 * so spawned agents get proper 3D positions.
 *
 * @param {RegionMap} regionMap - The region map to adapt.
 * @param {NavGrid} navGrid - Navigation grid for coordinate conversion.
 * @returns {Map<number, {id: number, cells: Array<{x: number, y: number, z: number}>}>}
 */
function buildRegionMapForSpawning(regionMap, navGrid) {
  const result = new Map();
  const size = regionMap.size;

  for (let regionId = 1; regionId <= regionMap.regionCount; regionId++) {
    const flatIndices = regionMap.getRegionCells(regionId);
    const cells = flatIndices.map(idx => {
      const gx = idx % size;
      const gz = Math.floor(idx / size);
      const { wx, wz } = navGrid.gridToWorld(gx, gz);
      const y = navGrid.getHeight(gx, gz);
      return { x: wx, y: y, z: wz };
    });
    result.set(regionId, { id: regionId, cells });
  }

  return result;
}

/**
 * Initialize and start the 3D society simulation.
 *
 * This function:
 * 1. Generates terrain via the classic fractal generator (no backend required).
 * 2. Samples the terrain mesh into 2D grids for navigation / biome classification.
 * 3. Builds world infrastructure: NavGrid, RegionMap, ResourceField, POIs, Climate.
 * 4. Creates the SimEngine and registers all systems in the correct order.
 * 5. Spawns initial agents and sets up renderers.
 *
 * The simulation then ticks in the main animation loop when simPlaying is true.
 */
function buildSimulation() {
  // Tear down any prior sim instance so GPU resources do not leak.
  teardownSimulation();

  // ── Step 1: Generate terrain ──────────────────────────────────────────────
  // We reuse the classic fractal generator so sim mode works without the backend.
  // The terrain provides the height data that all world systems depend on.
  const iterations = parseInt(document.getElementById('iterations').value);
  const roughness = parseFloat(document.getElementById('roughness').value);
  const displacementVal = parseFloat(document.getElementById('displacement').value);
  const scaleVal = parseFloat(document.getElementById('scale').value);

  const terrain = generateTerrain({
    iterations, roughness, displacement: displacementVal,
    scale: scaleVal, seed: currentSeed, baseShape: 'diamond',
  });

  // ── Step 2: Build the visual terrain mesh ─────────────────────────────────
  // Reuse the shared helper with flat shading and earthy "terrain" colormap.
  clearScene();
  buildTerrainMeshFromFractal(terrain, 'terrain', true);

  // ── Step 3: Sample terrain into 2D grids ──────────────────────────────────
  // The simulation needs regular grids (heightMap, slopeMap, waterMap, biomeMap)
  // for pathfinding, region assignment, and resource generation.
  const gridSize = DEFAULT_SIM_CONFIG.world.gridSize;
  const worldScale = DEFAULT_SIM_CONFIG.world.worldScale;

  const terrainMaps = sampleTerrainGrids(terrain, gridSize, worldScale);

  // ── Step 4: Build world infrastructure ────────────────────────────────────
  const rng = new PRNG(currentSeed);
  const eventBus = new EventBus();

  simNavGrid = new NavGrid(terrainMaps);
  simRegionMap = new RegionMap(simNavGrid);

  const resourceField = new ResourceField(terrainMaps, rng);

  // Generate points of interest (villages, mines, shrines, etc.) from terrain.
  // The POI array is cached for debug overlay rendering. The POIRegistry is
  // not needed by any system currently — systems query POIs via world state.
  simPOIs = generatePOIs(terrainMaps, simRegionMap, rng);

  // ── Step 5: Create SimEngine and systems ───────────────────────────────────
  // Each system has a unique tick() signature (different dependencies), so we
  // wire them manually rather than using a generic registerSystem adapter.
  // This ensures every system gets exactly the arguments it expects.
  simEngine = new SimEngine({
    ticksPerSecond: DEFAULT_SIM_CONFIG.time.ticksPerSecond,
    seed: currentSeed,
  });

  const perceptionSystem = new PerceptionSystem();
  simPerceptionSystem = perceptionSystem;

  const environmentSystem = new EnvironmentSystem({}, resourceField);
  const lifecycleSystemInst = new LifecycleSystem(eventBus, rng);
  const lodSystem = new LODSystem();
  const decisionSystem = new DecisionSystem(rng);
  const movementSystem = new MovementSystem(simNavGrid, eventBus);
  const interactionSystem = new InteractionSystem(eventBus, rng);
  const economySystem = new EconomySystem(eventBus);
  const diseaseSystem = new DiseaseSystem(eventBus, rng);
  const factionSystem = new FactionSystem(eventBus, rng);
  const telemetrySystem = new TelemetrySystem(eventBus);

  // Custom tick function — defined here but lifecycleWorldState is set after
  // spawnMap is created in Step 7 below.
  let lifecycleWorldState = null;

  // Needs decay rates per tick — agents gradually get hungry, tired, thirsty,
  // lonely, and stressed. Without this, needs stay at spawn defaults forever
  // and the decision system has no motivation signal.
  const DECAY = DEFAULT_SIM_CONFIG.needs;

  simEngine._customTick = function() {
    const world = this._world;
    const agents = world.agents;

    try {
      // ── Needs decay: the engine of all agent behavior ──────────────────
      // Self-similar principle: the same pressure (scarcity → action → relief)
      // operates at individual, group, and regional scales.
      for (const agent of agents) {
        if (!agent.alive) continue;
        const n = agent.needs;
        n.hunger    = Math.min(1, (n.hunger    || 0) + (DECAY.hungerDecayRate    || 0.003));
        n.energy    = Math.max(0, (n.energy    || 0) - (DECAY.energyDecayRate    || 0.002));
        n.hydration = Math.max(0, (n.hydration || 0) - (DECAY.hydrationDecayRate || 0.004));
        n.social    = Math.min(1, (n.social    || 0) + (DECAY.socialDecayRate    || 0.001));
        n.stress    = Math.min(1, (n.stress    || 0) + (DECAY.stressDecayRate    || 0.001));
      }

      environmentSystem.tick(world);
      lifecycleSystemInst.tick(agents, lifecycleWorldState);
      perceptionSystem.tick(agents, world);
      lodSystem.tick(agents, { x: 0, y: 0, z: 0 });
      decisionSystem.tick(agents, perceptionSystem, lodSystem, world);
      movementSystem.tick(agents, world);
      interactionSystem.tick(agents, perceptionSystem, resourceField, null);
      economySystem.tick(agents, resourceField, simRegionMap);
      diseaseSystem.tick(agents, perceptionSystem, environmentSystem);
      factionSystem.tick(agents, perceptionSystem);
      telemetrySystem.tick(agents, factionSystem.getFactions?.() || [], simRegionMap);
    } catch (e) {
      // Log but don't kill the loop — partial ticks are better than frozen sim.
      console.warn('[sim] tick error:', e.message);
    }
  };

  // ── Step 6: Initialize engine with terrain data ───────────────────────────
  simEngine.init({
    size: gridSize,
    worldScale: worldScale,
    heightMap: terrainMaps.heightMap,
    slopeMap: terrainMaps.slopeMap,
    waterMap: terrainMaps.waterMap,
    biomeMap: terrainMaps.biomeMap,
    regionMap: simRegionMap,
    navGrid: simNavGrid,
  }, currentSeed);

  // ── Step 7: Spawn initial agents ──────────────────────────────────────────
  // Use the direct lifecycle instance (no adapter/find needed).
  const spawnMap = buildRegionMapForSpawning(simRegionMap, simNavGrid);
  const initialAgents = lifecycleSystemInst.spawnInitialAgents(
    DEFAULT_SIM_CONFIG.agents.initialCount,
    spawnMap,
    simNavGrid,
  );
  simEngine._world.agents = initialAgents;
  // Now that spawnMap exists, wire it into the lifecycle tick worldState.
  lifecycleWorldState = { regionMap: spawnMap };
  console.log(`[sim] Spawned ${initialAgents.length} agents across ${simRegionMap.regionCount} regions`);

  // ── Step 8: Set up renderers ──────────────────────────────────────────────
  // Classic terrain: vertex positions from generateTerrain() are already in
  // world-space — no heightScale multiplication needed. heightScale=1.0.
  // Engine terrain would use 2.1 * reliefScale, but we're on classic path.
  const heightScale = 1.0;

  simSceneBridge = new SceneBridge(scene, worldScale, heightScale);
  simAgentRenderer = new AgentRenderer(scene, DEFAULT_SIM_CONFIG.agents.maxCount, heightScale, terrainMesh);
  simDebugOverlays = new DebugOverlays(scene, worldScale, heightScale);
  simHeatmapRenderer = new HeatmapRenderer(scene, worldScale, heightScale, gridSize);

  // ── Step 9: Update UI ─────────────────────────────────────────────────────
  simPlaying = false;
  simSpeed = 1;
  simLastFrameTime = performance.now();

  const playBtn = document.getElementById('btn-sim-playpause');
  if (playBtn) playBtn.innerHTML = '&#9654; Play';

  const telemetryEl = document.getElementById('sim-telemetry');
  if (telemetryEl) telemetryEl.style.display = '';

  document.getElementById('val-sim-pop').textContent = String(
    simEngine._world.agents.length
  );
  document.getElementById('val-sim-tick').textContent = '0';

  const agentCount = simEngine._world.agents.length;
  document.getElementById('stats').textContent =
    `Sim · ${gridSize}x${gridSize} · ${simRegionMap.regionCount} regions · ${agentCount} agents`;
  document.getElementById('seed-display').textContent = `seed: ${currentSeed}`;
}

/**
 * Update simulation telemetry readouts from the current engine snapshot.
 *
 * Called every frame when sim mode is active to keep the UI counters in sync.
 * Reads directly from the snapshot to avoid coupling to telemetry system internals.
 *
 * @param {object} snapshot - World snapshot from SimEngine.getSnapshot().
 */
function updateSimTelemetry(snapshot) {
  const agents = snapshot.agents || [];

  // Single pass over agents to count alive, sum hunger — avoids allocating
  // a filtered array every frame (hot path at 60 fps).
  let aliveCount = 0;
  let totalHunger = 0;
  let hungerCount = 0;
  for (let i = 0; i < agents.length; i++) {
    const a = agents[i];
    if (a.alive === false) continue;
    aliveCount++;
    if (a.needs && typeof a.needs.hunger === 'number') {
      totalHunger += a.needs.hunger;
      hungerCount++;
    }
  }
  const deadCount = agents.length - aliveCount;

  document.getElementById('val-sim-pop').textContent = String(aliveCount);
  document.getElementById('val-sim-tick').textContent = String(snapshot.tick || 0);

  document.getElementById('telem-pop').textContent = `pop: ${aliveCount}`;
  document.getElementById('telem-deaths').textContent = `deaths: ${deadCount}`;

  // Count conflict events from this tick's event buffer.
  let conflicts = 0;
  const events = snapshot.events || [];
  for (let i = 0; i < events.length; i++) {
    const t = events[i].type;
    if (t === 'conflict' || t === 'interaction:fight') conflicts++;
  }
  document.getElementById('telem-conflicts').textContent = `conflicts: ${conflicts}`;

  const avgHunger = hungerCount > 0 ? (totalHunger / hungerCount).toFixed(2) : '0.00';
  document.getElementById('telem-hunger').textContent = `avg hunger: ${avgHunger}`;

  const factionCount = (snapshot.factions || []).length;
  document.getElementById('telem-factions').textContent = `factions: ${factionCount}`;
}

/**
 * Stop the presentation-only orbit animation when we need a stable world.
 *
 * Explore mode assumes the terrain is stationary beneath the player. If we
 * leave the showroom rotation enabled, the ground effectively slides under the
 * camera and movement feels like noclip even when grounding logic is correct.
 */
function stopPresentationAnimation() {
  if (!animating) return;
  animating = false;
  document.getElementById('btn-animate').classList.remove('active');
}

/**
 * Reset transient FPS motion state.
 *
 * We clear residual velocity whenever we enter or reposition the player so old
 * falling momentum does not carry into a new spawn point.
 */
function resetExploreMotion() {
  velocity.set(0, 0, 0);
  canJump = true;
}

/**
 * Place the FPS camera at a safe eye-height above the terrain.
 *
 * The current bug is mostly a spawn problem: pointer-lock can begin while the
 * camera is still orbiting from far away or while its eye point is already
 * inside the terrain. This helper casts straight down at a chosen X/Z and
 * snaps the player onto the first terrain surface hit.
 */
function snapPlayerToTerrain(x = fpsControls.getObject().position.x, z = fpsControls.getObject().position.z) {
  if (!terrainMesh) return false;

  raycaster.set(new THREE.Vector3(x, 100, z), downVector);
  const intersects = raycaster.intersectObject(terrainMesh);
  if (intersects.length === 0) return false;

  const groundHeight = intersects[0].point.y;
  const pos = fpsControls.getObject().position;
  pos.set(x, groundHeight + FPS_EYE_HEIGHT, z);
  resetExploreMotion();
  return true;
}

/**
 * Prevent the FPS camera from living underneath the terrain surface.
 *
 * The explore camera is effectively a point probe, not a full capsule body, so
 * we use a stronger recovery clamp than a normal character controller would.
 * If integration drift or a steep triangle ever leaves the eye point below the
 * terrain, we immediately pop it back to a safe eye-height.
 */
function clampPlayerAboveTerrain() {
  if (!terrainMesh) return;

  const pos = fpsControls.getObject().position;
  raycaster.set(new THREE.Vector3(pos.x, 100, pos.z), downVector);
  const intersects = raycaster.intersectObject(terrainMesh);
  if (intersects.length === 0) {
    canJump = false;
    return;
  }

  const groundHeight = intersects[0].point.y;
  const targetY = groundHeight + FPS_EYE_HEIGHT;
  const penetrationDepth = targetY - pos.y;

  // If we are genuinely under the terrain surface, recover immediately.
  if (penetrationDepth >= 0) {
    pos.y = targetY;
    velocity.y = 0;
    canJump = true;
    return;
  }

  // While falling, only snap at the very end of the descent. A large snap
  // window makes jumps look like a teleport to the landing point instead of a
  // continuous arc back to the ground.
  if (
    pos.y <= targetY + FPS_GROUND_SNAP_DISTANCE
    && velocity.y <= 0
    && velocity.y >= FPS_LANDING_VELOCITY_THRESHOLD
  ) {
    pos.y = targetY;
    velocity.y = 0;
    canJump = true;
    return;
  }

  canJump = false;
}

/**
 * Bind a slider so:
 * - its displayed numeric value stays in sync with the thumb
 * - Classic mode regenerates immediately on change
 *
 * Engine mode does not auto-regenerate for these sliders because they do not
 * apply there.
 */
function bindSlider(id) {
  const el = document.getElementById(id);
  const valEl = document.getElementById(`val-${id}`);
  el.addEventListener('input', () => {
    valEl.textContent = parseFloat(el.value).toFixed(id === 'iterations' ? 0 : 2);
    if (currentMode === 'classic') buildClassicTerrain();
  });
}

['iterations', 'roughness', 'displacement', 'scale', 'flatness'].forEach(bindSlider);

// Classic-mode-only aesthetic control.
document.getElementById('colormap').addEventListener('change', () => {
  if (currentMode === 'classic') buildClassicTerrain();
});

// Wireframe is represented as its own mesh, so toggling is just visibility state.
document.getElementById('btn-wireframe').addEventListener('click', (e) => {
  showWireframe = !showWireframe;
  e.target.classList.toggle('active', showWireframe);
  if (wireframeMesh) wireframeMesh.visible = showWireframe;
});

// Flat shading requires a terrain rebuild because geometry representation changes.
document.getElementById('btn-flat').addEventListener('click', (e) => {
  flatShading = !flatShading;
  e.target.classList.toggle('active', flatShading);
  if (currentMode === 'classic') buildClassicTerrain();
});
document.getElementById('btn-flat').classList.add('active');

// "Animate" is a lightweight orbiting presentation effect, not a simulation.
document.getElementById('btn-animate').addEventListener('click', (e) => {
  animating = !animating;
  e.target.classList.toggle('active', animating);
});

// Regeneration means "keep current parameters, change only the seed".
document.getElementById('btn-regenerate').addEventListener('click', () => {
  currentSeed = Math.floor(Math.random() * 100000);
  buildTerrain();
  recordWorldInHistory();
});

// Explore mode swaps the input model from orbit-inspection to first-person walking.
const btnExplore = document.getElementById('btn-explore');
const crosshair = document.getElementById('crosshair');
const instructions = document.getElementById('explore-instructions');

btnExplore.addEventListener('click', () => {
  if (currentMode !== 'engine' || !terrainMesh) {
    // Explore mode is intended for the engine terrain, so we switch modes on
    // behalf of the user rather than leaving the button inert.
    document.getElementById('btn-engine').click();
  }
  fpsControls.lock();
});

fpsControls.addEventListener('lock', () => {
  isExploreMode = true;
  controls.enabled = false;
  crosshair.style.display = 'block';
  instructions.style.display = 'block';
  stopPresentationAnimation();

  // Always re-ground the player when entering FPS. Relying on the current
  // orbit-camera position is what caused the "inside the mountain" state.
  if (!snapPlayerToTerrain()) {
    snapPlayerToTerrain(0, 0);
  }
});

fpsControls.addEventListener('unlock', () => {
  isExploreMode = false;
  controls.enabled = true;
  crosshair.style.display = 'none';
  instructions.style.display = 'none';
});

// Movement intent flags are updated from keyboard events and consumed each frame.
document.addEventListener('keydown', (event) => {
  switch (event.code) {
    case 'KeyW': moveState.forward = true; break;
    case 'KeyA': moveState.left = true; break;
    case 'KeyS': moveState.backward = true; break;
    case 'KeyD': moveState.right = true; break;
    case 'ShiftLeft': moveState.run = true; break;
    case 'Space':
      if (canJump === true) velocity.y += FPS_JUMP_VELOCITY;
      canJump = false;
      break;
  }
});

document.addEventListener('keyup', (event) => {
  switch (event.code) {
    case 'KeyW': moveState.forward = false; break;
    case 'KeyA': moveState.left = false; break;
    case 'KeyS': moveState.backward = false; break;
    case 'KeyD': moveState.right = false; break;
    case 'ShiftLeft': moveState.run = false; break;
  }
});

// Double-click teleport is a bridge between orbit mode and pointer-lock mode:
// click a point on the terrain, move the camera there, then enter explore mode.
renderer.domElement.addEventListener('dblclick', (e) => {
  if (isExploreMode || !terrainMesh) return;
  const mouse = new THREE.Vector2();
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);
  const intersects = raycaster.intersectObject(terrainMesh);
  if (intersects.length > 0) {
    const pt = intersects[0].point;
    camera.position.set(pt.x, pt.y + FPS_EYE_HEIGHT, pt.z);
    resetExploreMotion();
    fpsControls.lock();
  }
});

/**
 * Switch mode UI: hide all mode-specific control panels, deactivate all mode
 * buttons, then activate the selected mode. This avoids duplicating the
 * "deactivate everything" logic in each mode button handler.
 *
 * @param {'classic'|'engine'|'sim'} mode - The mode to switch to.
 */
function activateMode(mode) {
  // Tear down sim if leaving sim mode — free GPU resources and stop the tick loop.
  if (currentMode === 'sim' && mode !== 'sim') {
    teardownSimulation();
  }

  currentMode = mode;

  // Deactivate all mode buttons.
  document.getElementById('btn-classic').classList.remove('active');
  document.getElementById('btn-engine').classList.remove('active');
  document.getElementById('btn-sim').classList.remove('active');

  // Hide all mode-specific control panels.
  document.getElementById('classic-controls').style.display = 'none';
  document.getElementById('engine-controls').style.display = 'none';
  document.getElementById('sim-controls').style.display = 'none';

  // Activate the selected mode.
  if (mode === 'classic') {
    document.getElementById('btn-classic').classList.add('active');
    document.getElementById('classic-controls').style.display = '';
    buildClassicTerrain();
  } else if (mode === 'engine') {
    document.getElementById('btn-engine').classList.add('active');
    document.getElementById('engine-controls').style.display = '';
    buildEngineTerrain();
  } else if (mode === 'sim') {
    document.getElementById('btn-sim').classList.add('active');
    document.getElementById('sim-controls').style.display = '';
    buildSimulation();
  }
}

// Mode toggle wiring. Only one control panel is visible at a time.
document.getElementById('btn-classic').addEventListener('click', () => activateMode('classic'));
document.getElementById('btn-engine').addEventListener('click', () => activateMode('engine'));
document.getElementById('btn-sim').addEventListener('click', () => activateMode('sim'));

// Engine-specific controls.
document.getElementById('preset').addEventListener('change', () => {
  if (currentMode === 'engine') buildEngineTerrain();
});

// Size slider updates its numeric label immediately but rebuilds only when the
// user explicitly clicks Generate. That keeps API usage predictable.
document.getElementById('engine-size').addEventListener('input', () => {
  const val = document.getElementById('engine-size').value;
  document.getElementById('val-engine-size').textContent = val;
});

document.getElementById('btn-generate').addEventListener('click', () => {
  currentSeed = Math.floor(Math.random() * 100000);
  buildEngineTerrain();
  recordWorldInHistory();
});

// ── Simulation control wiring ────────────────────────────────────────────────
// These buttons only affect sim mode state. They are inert (but harmless) in
// other modes because the sim-controls panel is hidden.

const simPlayPauseBtn = document.getElementById('btn-sim-playpause');
if (simPlayPauseBtn) {
  simPlayPauseBtn.addEventListener('click', () => {
    if (currentMode !== 'sim' || !simEngine) return;
    simPlaying = !simPlaying;
    simPlayPauseBtn.innerHTML = simPlaying ? '&#9646;&#9646; Pause' : '&#9654; Play';
    // Reset frame timer so the first tick after unpause does not include
    // the entire duration the sim was paused.
    simLastFrameTime = performance.now();
  });
}

const simStepBtn = document.getElementById('btn-sim-step');
if (simStepBtn) {
  simStepBtn.addEventListener('click', () => {
    if (currentMode !== 'sim' || !simEngine) return;
    // Advance exactly one tick by feeding a fake delta equal to one tick period.
    const tickPeriodMs = 1000 / (DEFAULT_SIM_CONFIG.time.ticksPerSecond || 6);
    simEngine.tick(tickPeriodMs);
    const snapshot = simEngine.getSnapshot();
    if (simSceneBridge) simSceneBridge.updateFromSnapshot(snapshot);
    if (simAgentRenderer) simAgentRenderer.updateFromAgents(snapshot.agents);
    updateSimTelemetry(snapshot);
  });
}

const simSpeedSlider = document.getElementById('sim-speed');
if (simSpeedSlider) {
  simSpeedSlider.addEventListener('input', () => {
    simSpeed = parseInt(simSpeedSlider.value);
    document.getElementById('val-sim-speed').textContent = `${simSpeed}x`;
  });
}

// Overlay toggle buttons. Each toggles a debug layer in the DebugOverlays renderer.
// The overlays are built lazily on first toggle from cached world data.
const overlayButtons = [
  { btnId: 'btn-ov-navgrid', layer: 'navGrid', buildFn: () => {
    if (simDebugOverlays && simNavGrid) {
      simDebugOverlays.showNavGrid(simNavGrid);
    }
  }},
  { btnId: 'btn-ov-regions', layer: 'regions', buildFn: () => {
    if (simDebugOverlays && simRegionMap && simNavGrid) {
      simDebugOverlays.showRegions(simRegionMap, simNavGrid);
    }
  }},
  { btnId: 'btn-ov-pois', layer: 'pois', buildFn: () => {
    if (simDebugOverlays && simPOIs) {
      simDebugOverlays.showPOIs(simPOIs);
    }
  }},
  { btnId: 'btn-ov-paths', layer: 'agentPaths', buildFn: () => {
    if (simDebugOverlays && simEngine) {
      const snapshot = simEngine.getSnapshot();
      simDebugOverlays.showAgentPaths(snapshot.agents);
    }
  }},
];

for (const { btnId, layer, buildFn } of overlayButtons) {
  const btn = document.getElementById(btnId);
  if (!btn) continue;
  btn.addEventListener('click', () => {
    if (currentMode !== 'sim' || !simDebugOverlays) return;
    // Build the overlay data on first show, then toggle visibility.
    buildFn();
    const visible = simDebugOverlays.toggle(layer);
    btn.classList.toggle('active', visible);
  });
}

// Heatmap toggle — shows a resource/food heatmap overlay.
// heatmapVisible is module-scoped so teardownSimulation() can reset it.
const heatmapBtn = document.getElementById('btn-ov-heatmap');
if (heatmapBtn) {
  heatmapBtn.addEventListener('click', () => {
    if (currentMode !== 'sim' || !simHeatmapRenderer) return;
    heatmapVisible = !heatmapVisible;
    heatmapBtn.classList.toggle('active', heatmapVisible);
    if (heatmapVisible && simEngine) {
      // Use terrain biomeMap as a proxy heatmap — biome values [0-5] normalized.
      const snapshot = simEngine.getSnapshot();
      const biomeMap = snapshot.terrain?.biomeMap;
      if (biomeMap) {
        const maxBiome = 5;
        const normalized = new Float32Array(biomeMap.length);
        for (let i = 0; i < biomeMap.length; i++) {
          normalized[i] = biomeMap[i] / maxBiome;
        }
        simHeatmapRenderer.showHeatmap(normalized, 'heat');
      }
    } else {
      simHeatmapRenderer.hide();
    }
  });
}

// Agent color mode buttons.
const colorModeButtons = [
  { btnId: 'btn-color-faction', mode: COLOR_MODE_BY_FACTION },
  { btnId: 'btn-color-health', mode: COLOR_MODE_BY_HEALTH },
  { btnId: 'btn-color-role', mode: COLOR_MODE_BY_ROLE },
];

for (const { btnId, mode } of colorModeButtons) {
  const btn = document.getElementById(btnId);
  if (!btn) continue;
  btn.addEventListener('click', () => {
    if (currentMode !== 'sim' || !simAgentRenderer) return;
    simAgentRenderer.setColorMode(mode);
    // Update button active states — only one color mode is active at a time.
    for (const { btnId: otherId } of colorModeButtons) {
      document.getElementById(otherId)?.classList.remove('active');
    }
    btn.classList.add('active');
  });
}

// Spacebar play/pause when sim mode is active and not in explore mode.
document.addEventListener('keydown', (event) => {
  if (event.code === 'Space' && currentMode === 'sim' && !isExploreMode) {
    event.preventDefault();
    simPlayPauseBtn?.click();
  }
});

const saveWorldButton = document.getElementById('btn-save-world');
if (saveWorldButton) {
  saveWorldButton.addEventListener('click', () => {
    recordWorldInHistory();
  });
}

const loadWorldButton = document.getElementById('btn-load-world');
if (loadWorldButton) {
  loadWorldButton.addEventListener('click', () => {
    const historySelect = document.getElementById('history-select');
    if (!historySelect) return;

    const selectedId = historySelect.value;
    if (!selectedId) return;

    const snapshot = readWorldHistory().find((item) => item.id === selectedId);
    if (!snapshot) return;
    applyWorldState(snapshot);
  });
}

const menuToggleButton = document.getElementById('menu-toggle');
if (menuToggleButton) {
  menuToggleButton.addEventListener('click', () => {
    const controlsPanel = document.getElementById('controls');
    const isCollapsed = controlsPanel?.classList.contains('is-collapsed') ?? false;
    applyMenuCollapsedState(!isCollapsed);
  });
}

// Keep camera projection and renderer output in sync with the browser viewport.
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

/**
 * Main render loop.
 *
 * The frame loop has four jobs:
 * 1. Apply optional presentation animation to the terrain
 * 2. Tick the simulation engine if sim mode is active and playing
 * 3. Update either orbit controls or first-person movement
 * 4. Render the scene
 *
 * We keep the logic here intentionally explicit rather than abstract because
 * the state interactions are easier for future agents to audit in one place.
 */
function animate() {
  requestAnimationFrame(animate);

  const time = performance.now();

  if (animating && terrainMesh && !isExploreMode) {
    // Presentation-only rotation. This is disabled during exploration to avoid
    // moving the world underneath the player.
    animTime += 0.005;
    const rotY = Math.sin(animTime * 0.5) * 0.3;
    terrainMesh.rotation.y = rotY;
    if (wireframeMesh) wireframeMesh.rotation.y = rotY;
    if (waterMesh) waterMesh.rotation.y = rotY;
    if (featureGroup) featureGroup.rotation.y = rotY;
  }

  // A tiny vertical bob is enough to keep the water from feeling dead.
  // This is intentionally minimal and not physically modeled.
  if (waterMesh) {
    waterMesh.position.y += Math.sin(time * 0.002) * 0.0002;
  }

  // ── Simulation tick ─────────────────────────────────────────────────────
  // When sim mode is active and playing, advance the simulation by the
  // real-time delta (scaled by speed multiplier). The SimEngine internally
  // converts wall-clock time to fixed-step ticks via its TickScheduler.
  if (currentMode === 'sim' && simEngine && simPlaying) {
    const simDelta = (time - simLastFrameTime) * simSpeed;
    simEngine.tick(simDelta);

    // Pull a snapshot and update all renderers.
    const snapshot = simEngine.getSnapshot();

    if (simSceneBridge) simSceneBridge.updateFromSnapshot(snapshot);
    if (simAgentRenderer) simAgentRenderer.updateFromAgents(snapshot.agents);

    // Update telemetry readouts at a reasonable rate (every frame is fine
    // because DOM writes are cheap for small text nodes).
    updateSimTelemetry(snapshot);
  }
  // Track frame time for sim delta calculation regardless of play state,
  // so resuming after pause does not cause a huge time spike.
  simLastFrameTime = time;

  if (isExploreMode) {
    // Delta time keeps movement frame-rate independent.
    const delta = (time - prevTime) / 1000;

    // Damp horizontal motion so movement feels responsive rather than slippery.
    velocity.x -= velocity.x * 10.0 * delta;
    velocity.z -= velocity.z * 10.0 * delta;
    velocity.y -= FPS_GRAVITY * delta;

    direction.z = Number(moveState.forward) - Number(moveState.backward);
    direction.x = Number(moveState.right) - Number(moveState.left);
    direction.normalize(); // prevents diagonal movement from being faster

    const speed = moveState.run ? FPS_RUN_SPEED : FPS_WALK_SPEED;

    if (moveState.forward || moveState.backward) velocity.z -= direction.z * speed * delta;
    if (moveState.left || moveState.right) velocity.x -= direction.x * speed * delta;

    // PointerLockControls moves in local camera space.
    fpsControls.moveRight(-velocity.x * delta);
    fpsControls.moveForward(-velocity.z * delta);
    fpsControls.getObject().position.y += velocity.y * delta;

    // Ground collision is handled by casting downward and clamping the player
    // to a constant eye-height above the terrain surface.
    if (terrainMesh) {
      clampPlayerAboveTerrain();
    }
  } else {
    controls.update();
  }

  prevTime = time;
  renderer.render(scene, camera);
}

refreshHistoryOptions();
restoreMenuCollapsedState();

// Restore the most recent world when available so refresh does not discard the
// current session. Fall back to the classic generator only on first launch.
if (!restoreInitialWorld()) {
  buildClassicTerrain();
  persistCurrentWorld();
}
animate();
