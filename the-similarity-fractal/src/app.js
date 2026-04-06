import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { PointerLockControls } from 'three/addons/controls/PointerLockControls.js';
import { generateTerrain } from './fractal.js';
import { buildTerrainMesh, buildFeatures } from './terrain-renderer.js';

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
 * There are two rendering modes:
 * 1. `classic`: fully local midpoint-displacement fractal terrain
 * 2. `engine`: terrain fetched from a backend API, then rendered locally
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
let currentMode = 'classic';  // 'classic' or 'engine'
let suppressHistoryRecording = false;

const API_URL = 'http://127.0.0.1:8000';

// FPS traversal scale constants.
// The terrain world is tiny relative to default first-person controller values,
// so the camera eye height and all movement forces need to stay very small.
const FPS_EYE_HEIGHT = 0.005;
const FPS_GROUND_SNAP_DISTANCE = 0.01;
const FPS_JUMP_VELOCITY = 0.08;
const FPS_GRAVITY = 0.5;
const FPS_WALK_SPEED = 0.3;
const FPS_RUN_SPEED = 0.8;
const WORLD_HISTORY_STORAGE_KEY = 'the-similarity:fractal-world-history';
const WORLD_CURRENT_STORAGE_KEY = 'the-similarity:fractal-current-world';
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
  document.getElementById('val-iterations').textContent = String(snapshot.classic.iterations);
  document.getElementById('val-roughness').textContent = Number(snapshot.classic.roughness).toFixed(2);
  document.getElementById('val-displacement').textContent = Number(snapshot.classic.displacement).toFixed(2);
  document.getElementById('val-scale').textContent = Number(snapshot.classic.scale).toFixed(2);

  document.getElementById('preset').value = snapshot.engine.preset;
  document.getElementById('engine-size').value = String(snapshot.engine.size);
  document.getElementById('val-engine-size').textContent = String(snapshot.engine.size);

  if (currentMode === 'engine') {
    document.getElementById('btn-engine').classList.add('active');
    document.getElementById('btn-classic').classList.remove('active');
    document.getElementById('classic-controls').style.display = 'none';
    document.getElementById('engine-controls').style.display = '';
    buildEngineTerrain();
  } else {
    document.getElementById('btn-classic').classList.add('active');
    document.getElementById('btn-engine').classList.remove('active');
    document.getElementById('classic-controls').style.display = '';
    document.getElementById('engine-controls').style.display = 'none';
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
  const colormap = document.getElementById('colormap').value;

  const t0 = performance.now();
  const terrain = generateTerrain({
    iterations, roughness, displacement: displacementVal,
    scale: scaleVal, seed: currentSeed, baseShape: 'diamond',
  });
  const genTime = (performance.now() - t0).toFixed(1);

  clearScene();

  // Convert raw typed arrays into a Three.js indexed triangle mesh.
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

  if (flatShading) {
    // Flat shading needs a non-indexed geometry so each face has distinct
    // vertices and therefore distinct face normals.
    const flatGeo = geometry.toNonIndexed();
    flatGeo.computeVertexNormals();
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

    // The renderer helper owns the mapping from backend arrays to visual meshes.
    const { mesh, waterMesh: water } = buildTerrainMesh(data, 10, 3);
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
      featureGroup = buildFeatures(data.features, data.size, 10, 3, data.heightmap);
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
  } else {
    buildClassicTerrain();
  }
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

['iterations', 'roughness', 'displacement', 'scale'].forEach(bindSlider);

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

  // If the user was orbiting far away, snap them into a sensible spawn point.
  if (camera.position.y > 10) {
    camera.position.set(0, FPS_EYE_HEIGHT, 0);
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
    fpsControls.lock();
  }
});

// Mode toggle wiring. Only one control panel is visible at a time.
document.getElementById('btn-classic').addEventListener('click', (e) => {
  currentMode = 'classic';
  e.target.classList.add('active');
  document.getElementById('btn-engine').classList.remove('active');
  document.getElementById('classic-controls').style.display = '';
  document.getElementById('engine-controls').style.display = 'none';
  buildClassicTerrain();
});

document.getElementById('btn-engine').addEventListener('click', (e) => {
  currentMode = 'engine';
  e.target.classList.add('active');
  document.getElementById('btn-classic').classList.remove('active');
  document.getElementById('classic-controls').style.display = 'none';
  document.getElementById('engine-controls').style.display = '';
  buildEngineTerrain();
});

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

document.getElementById('btn-save-world').addEventListener('click', () => {
  recordWorldInHistory();
});

document.getElementById('btn-load-world').addEventListener('click', () => {
  const selectedId = document.getElementById('history-select').value;
  if (!selectedId) return;
  const snapshot = readWorldHistory().find((item) => item.id === selectedId);
  if (!snapshot) return;
  applyWorldState(snapshot);
});

// Keep camera projection and renderer output in sync with the browser viewport.
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

/**
 * Main render loop.
 *
 * The frame loop has three jobs:
 * 1. Apply optional presentation animation to the terrain
 * 2. Update either orbit controls or first-person movement
 * 3. Render the scene
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
      const pos = fpsControls.getObject().position;
      raycaster.set(new THREE.Vector3(pos.x, 100, pos.z), downVector);
      const intersects = raycaster.intersectObject(terrainMesh);
      if (intersects.length > 0) {
        const groundHeight = intersects[0].point.y;
        const targetY = groundHeight + FPS_EYE_HEIGHT;

        // Snap onto the terrain a little before we visually penetrate it.
        // This reduces the "sinking into triangles" feeling that happens when
        // using a point-camera against an uneven mesh instead of a full capsule.
        if (pos.y <= targetY + FPS_GROUND_SNAP_DISTANCE && velocity.y <= 0) {
          velocity.y = 0;
          pos.y = targetY;
          canJump = true;
        } else {
          canJump = false;
        }
      } else {
        canJump = false;
      }
    }
  } else {
    controls.update();
  }

  prevTime = time;
  renderer.render(scene, camera);
}

refreshHistoryOptions();

// Restore the most recent world when available so refresh does not discard the
// current session. Fall back to the classic generator only on first launch.
if (!restoreInitialWorld()) {
  buildClassicTerrain();
  persistCurrentWorld();
}
animate();
