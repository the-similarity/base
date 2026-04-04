import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { generateTerrain } from './fractal.js';

// --- Color maps ---
const COLOR_MAPS = {
  terrain: [
    { t: 0.0,  r: 0.18, g: 0.32, b: 0.12 },  // deep green
    { t: 0.25, r: 0.35, g: 0.55, b: 0.20 },  // green
    { t: 0.45, r: 0.55, g: 0.50, b: 0.30 },  // brown-green
    { t: 0.60, r: 0.60, g: 0.50, b: 0.35 },  // brown
    { t: 0.75, r: 0.70, g: 0.65, b: 0.55 },  // light brown / rock
    { t: 0.88, r: 0.82, g: 0.80, b: 0.78 },  // grey rock
    { t: 1.0,  r: 1.00, g: 0.98, b: 0.96 },  // snow
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

// --- Scene setup ---
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a0f);
scene.fog = new THREE.FogExp2(0x0a0a0f, 0.035);

const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(5, 4, 7);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.minDistance = 2;
controls.maxDistance = 30;
controls.maxPolarAngle = Math.PI / 2 + 0.3;

// --- Lighting ---
const ambientLight = new THREE.AmbientLight(0x334455, 0.6);
scene.add(ambientLight);

const dirLight = new THREE.DirectionalLight(0xffeedd, 1.5);
dirLight.position.set(5, 8, 3);
scene.add(dirLight);

const backLight = new THREE.DirectionalLight(0x4488cc, 0.4);
backLight.position.set(-3, 4, -5);
scene.add(backLight);

// --- State ---
let currentSeed = Math.floor(Math.random() * 100000);
let terrainMesh = null;
let wireframeMesh = null;
let showWireframe = false;
let flatShading = true;
let animating = false;
let animTime = 0;

// --- Build terrain mesh ---
function buildTerrain() {
  const iterations = parseInt(document.getElementById('iterations').value);
  const roughness = parseFloat(document.getElementById('roughness').value);
  const displacementVal = parseFloat(document.getElementById('displacement').value);
  const scaleVal = parseFloat(document.getElementById('scale').value);
  const colormap = document.getElementById('colormap').value;

  const t0 = performance.now();
  const terrain = generateTerrain({
    iterations,
    roughness,
    displacement: displacementVal,
    scale: scaleVal,
    seed: currentSeed,
    baseShape: 'diamond',
  });
  const genTime = (performance.now() - t0).toFixed(1);

  // Remove old meshes
  if (terrainMesh) {
    scene.remove(terrainMesh);
    terrainMesh.geometry.dispose();
    terrainMesh.material.dispose();
  }
  if (wireframeMesh) {
    scene.remove(wireframeMesh);
    wireframeMesh.geometry.dispose();
    wireframeMesh.material.dispose();
  }

  // Geometry
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(terrain.positions, 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(terrain.normals, 3));
  geometry.setIndex(new THREE.BufferAttribute(terrain.indices, 1));

  // Height-based vertex colors
  let minH = Infinity, maxH = -Infinity;
  for (let i = 0; i < terrain.heights.length; i++) {
    minH = Math.min(minH, terrain.heights[i]);
    maxH = Math.max(maxH, terrain.heights[i]);
  }
  const range = maxH - minH || 1;

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
    // For flat shading, we need non-indexed geometry
    const flatGeo = geometry.toNonIndexed();
    flatGeo.computeVertexNormals();

    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      flatShading: true,
      roughness: 0.8,
      metalness: 0.1,
      side: THREE.DoubleSide,
    });

    terrainMesh = new THREE.Mesh(flatGeo, material);
    geometry.dispose();
  } else {
    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      flatShading: false,
      roughness: 0.8,
      metalness: 0.1,
      side: THREE.DoubleSide,
    });

    terrainMesh = new THREE.Mesh(geometry, material);
  }

  scene.add(terrainMesh);

  // Wireframe overlay
  const wireGeo = new THREE.BufferGeometry();
  wireGeo.setAttribute('position', new THREE.BufferAttribute(terrain.positions.slice(), 3));
  wireGeo.setIndex(new THREE.BufferAttribute(terrain.indices.slice(), 1));
  const wireMat = new THREE.MeshBasicMaterial({
    color: 0x4fc3f7,
    wireframe: true,
    transparent: true,
    opacity: 0.15,
  });
  wireframeMesh = new THREE.Mesh(wireGeo, wireMat);
  wireframeMesh.visible = showWireframe;
  scene.add(wireframeMesh);

  // Stats
  document.getElementById('stats').textContent =
    `${terrain.vertexCount.toLocaleString()} vertices  ·  ${terrain.faceCount.toLocaleString()} faces  ·  ${genTime}ms`;
  document.getElementById('seed-display').textContent = `seed: ${currentSeed}`;
}

// --- UI bindings ---
function bindSlider(id) {
  const el = document.getElementById(id);
  const valEl = document.getElementById(`val-${id}`);
  el.addEventListener('input', () => {
    valEl.textContent = parseFloat(el.value).toFixed(
      id === 'iterations' ? 0 : 2
    );
    buildTerrain();
  });
}

['iterations', 'roughness', 'displacement', 'scale'].forEach(bindSlider);

document.getElementById('colormap').addEventListener('change', buildTerrain);

document.getElementById('btn-wireframe').addEventListener('click', (e) => {
  showWireframe = !showWireframe;
  e.target.classList.toggle('active', showWireframe);
  if (wireframeMesh) wireframeMesh.visible = showWireframe;
});

document.getElementById('btn-flat').addEventListener('click', (e) => {
  flatShading = !flatShading;
  e.target.classList.toggle('active', flatShading);
  buildTerrain();
});
// Start with flat shading active
document.getElementById('btn-flat').classList.add('active');

document.getElementById('btn-animate').addEventListener('click', (e) => {
  animating = !animating;
  e.target.classList.toggle('active', animating);
});

document.getElementById('btn-regenerate').addEventListener('click', () => {
  currentSeed = Math.floor(Math.random() * 100000);
  buildTerrain();
});

// --- Resize ---
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// --- Animation loop ---
function animate(time) {
  requestAnimationFrame(animate);

  if (animating && terrainMesh) {
    animTime += 0.005;
    terrainMesh.rotation.y = Math.sin(animTime * 0.5) * 0.3;
    if (wireframeMesh) wireframeMesh.rotation.y = terrainMesh.rotation.y;
  }

  controls.update();
  renderer.render(scene, camera);
}

// --- Init ---
buildTerrain();
animate(0);
