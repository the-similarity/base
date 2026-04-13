/**
 * Procedural terrain shader material for the fractal nature engine.
 *
 * Replaces flat per-vertex biome colors with rich, noise-based procedural textures
 * using a custom `onBeforeCompile` hook on `MeshStandardMaterial`. Every visual
 * detail derives from the SAME simplex noise function evaluated at different scales
 * — this is self-similarity in action: the large-scale color variation, medium
 * detail, micro texture, and fine grain are all octaves of the same fractal process.
 *
 * Architecture:
 *   1. Vertex shader injects world-space position and normal as varyings.
 *   2. Fragment shader injects 3D simplex noise (Ashima Arts, MIT license).
 *   3. Triplanar mapping eliminates stretching on cliffs by projecting noise
 *      from three orthogonal planes and blending by surface normal.
 *   4. fBm (fractal Brownian motion) layers four octaves at scales 0.5, 2.0,
 *      8.0, and 20.0 — each with half the amplitude of the previous one.
 *   5. Biome blending reads vertex color as a classification hint and applies
 *      slope-dependent rock, height-based snow/sand, and noise-driven detail.
 *   6. Normal perturbation from noise derivatives creates apparent micro-roughness
 *      without additional geometry.
 *
 * Lifecycle:
 *   - Call `createTerrainMaterial(options)` once per terrain mesh.
 *   - The returned material is a standard `MeshStandardMaterial` that Three.js
 *     manages normally — no extra dispose() or update() calls needed.
 *   - The `onBeforeCompile` callback fires once when Three.js first compiles the
 *     shader program; after that, the GPU program is cached.
 *
 * Immutability:
 *   - The GLSL source strings are frozen at material creation time.
 *   - The material's uniform values (noiseScale, detailLevel) can be changed at
 *     runtime via `material.userData.uniforms` if dynamic LOD is desired.
 *   - The noise function itself is pure (no state, no side effects).
 *
 * Compatibility:
 *   - Three.js 0.160.0+ (onBeforeCompile API).
 *   - Requires `vertexColors: true` on the geometry (biome hints via vertex color).
 *   - Expects geometry with position displaced by a heightmap (PlaneGeometry).
 *
 * @module nature/terrain-material
 */

import * as THREE from 'three';

// ─── GLSL: Ashima Arts 3D Simplex Noise ───────────────────────────────────────
// MIT License. Original: https://github.com/ashima/webgl-noise
// This is the foundational noise primitive. ALL procedural detail in the terrain
// derives from this single function at different input scales. The self-similar
// principle: snoise(p * 0.5) gives continent-scale variation; snoise(p * 20.0)
// gives sand grain texture — same algorithm, different frequency.
//
// ~60 lines of GLSL. Inlined as a template literal to avoid external file I/O
// and keep the module self-contained for bundlers.
const SIMPLEX_NOISE_GLSL = /* glsl */ `
  //
  // Description : Array and textureless GLSL 2D/3D/4D simplex noise functions.
  //      Author : Ian McEwan, Ashima Arts.
  //  Maintainer : stegu
  //     Lastmod : 20201014 (stegu)
  //     License : Copyright (C) 2011 Ashima Arts. All rights reserved.
  //               Distributed under the MIT License. See LICENSE file.
  //               https://github.com/ashima/webgl-noise
  //               https://github.com/stegu/webgl-noise
  //

  vec3 mod289(vec3 x) {
    return x - floor(x * (1.0 / 289.0)) * 289.0;
  }

  vec4 mod289(vec4 x) {
    return x - floor(x * (1.0 / 289.0)) * 289.0;
  }

  vec4 permute(vec4 x) {
    // Permutation polynomial: (34x^2 + 6x) mod 289.
    // This is the hash function that gives simplex noise its pseudo-random
    // gradient selection. The constants 34 and 6 were chosen by McEwan
    // to minimize visible periodicity artifacts.
    return mod289(((x * 34.0) + 6.0) * x);
  }

  vec4 taylorInvSqrt(vec4 r) {
    // Fast approximate inverse square root using a first-order Taylor expansion.
    // Accuracy is sufficient for noise normalization — we don't need IEEE precision.
    return 1.79284291400159 - 0.85373472095314 * r;
  }

  float snoise(vec3 v) {
    // 3D simplex noise. Returns a value in approximately [-1, 1].
    //
    // The simplex grid is a skewed cube lattice where each cube is divided
    // into 6 tetrahedra. For any input point, we identify which tetrahedron
    // it falls in, compute contributions from the 4 corners, and sum them.
    //
    // Why simplex over Perlin: fewer multiplications (4 corners vs 8),
    // no directional artifacts, and better visual isotropy.

    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

    // First corner — skew input space to find the simplex cell origin.
    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);

    // Determine which simplex (tetrahedron) we are in by sorting the
    // fractional offsets. The comparison cascade identifies the traversal
    // order through the 3 axes.
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);

    // Offsets for the remaining 3 corners of the tetrahedron.
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;       // 2.0 * C.x = 1/3
    vec3 x3 = x0 - D.yyy;             // -1.0 + 3.0 * C.x = -0.5

    // Permutation: hash the integer lattice coordinates to select
    // pseudo-random gradient directions at each corner.
    i = mod289(i);
    vec4 p = permute(permute(permute(
              i.z + vec4(0.0, i1.z, i2.z, 1.0))
            + i.y + vec4(0.0, i1.y, i2.y, 1.0))
            + i.x + vec4(0.0, i1.x, i2.x, 1.0));

    // Gradient selection: map the hash to a point on a unit sphere surface
    // using a method that avoids trigonometry.
    float n_ = 0.142857142857;   // 1.0 / 7.0
    vec3 ns = n_ * D.wyz - D.xzx;

    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);

    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);

    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);

    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);

    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));

    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;

    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);

    // Normalize gradients to avoid brightness variation across the lattice.
    vec4 norm = taylorInvSqrt(vec4(
      dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)
    ));
    p0 *= norm.x;
    p1 *= norm.y;
    p2 *= norm.z;
    p3 *= norm.w;

    // Radial falloff: each corner's contribution falls off with a quartic
    // kernel (0.5 - |x|^2)^4. The 0.5 radius ensures smooth C2 continuity
    // at simplex boundaries.
    vec4 m = max(0.5 - vec4(
      dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)
    ), 0.0);
    m = m * m;

    // Final weighted sum of gradient dot products.
    // The 105.0 scaling constant normalizes the output to approximately [-1, 1].
    return 105.0 * dot(m * m, vec4(
      dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)
    ));
  }
`;

// ─── GLSL: Triplanar Mapping + fBm + Biome Blending ──────────────────────────
// This is the core fragment shader logic injected after the noise function.
// It combines all six visual features: triplanar projection, fBm octaves,
// biome classification, slope-dependent rock, height-based blending, and
// normal perturbation.
const TERRAIN_FRAGMENT_GLSL = /* glsl */ `
  // ── Triplanar noise sampling ──────────────────────────────────────────
  // Projects noise from 3 orthogonal planes (XY, XZ, YZ) and blends by
  // the surface normal. This eliminates the stretching artifacts that
  // single-plane UV projection would produce on steep cliffs.
  //
  // The blend weights are |normal| components, normalized to sum to 1.
  // A surface facing +Y (flat ground) gets mostly XZ noise; a vertical
  // cliff face gets mostly XY or YZ noise depending on orientation.
  float triplanarNoise(vec3 pos, float scale) {
    // Blend weights from world-space normal.
    vec3 blendWeights = abs(vWorldNormal);
    // Normalize so weights sum to 1 — prevents brightness shifts on
    // surfaces where all three components are similar (45-degree slopes).
    blendWeights /= (blendWeights.x + blendWeights.y + blendWeights.z + 1e-6);

    // Sample noise from each projection plane.
    // Each plane uses two of the three world coordinates as the "UV" axes,
    // with the third coordinate providing depth variation.
    float noiseXY = snoise(vec3(pos.xy * scale, pos.z * scale * 0.5));
    float noiseXZ = snoise(vec3(pos.xz * scale, pos.y * scale * 0.5));
    float noiseYZ = snoise(vec3(pos.yz * scale, pos.x * scale * 0.5));

    // Weighted blend: each projection contributes proportional to how
    // much the surface faces that projection's normal axis.
    return noiseXY * blendWeights.z + noiseXZ * blendWeights.y + noiseYZ * blendWeights.x;
  }

  // ── Fractal Brownian Motion (fBm) ────────────────────────────────────
  // Layers triplanar noise at 4 octaves. This IS the self-similarity:
  //
  //   Octave 1 (scale * 1.0):  continent-scale color variation — same pattern
  //   Octave 2 (scale * 4.0):  medium terrain detail — same pattern, 4x smaller
  //   Octave 3 (scale * 16.0): micro detail (grass blades, rock cracks) — 16x smaller
  //   Octave 4 (scale * 40.0): fine grain (sand ripples, snow crystals) — 40x smaller
  //
  // Each octave has half the amplitude of the previous (persistence = 0.5).
  // This produces the classic "fractal" falloff: 1/f noise, where amplitude
  // is inversely proportional to frequency.
  //
  // The base scales (0.5, 2.0, 8.0, 20.0) come from multiplying the user's
  // noiseScale uniform by the octave multipliers [1, 4, 16, 40].
  float fbm(vec3 pos, float baseScale) {
    float value = 0.0;
    float amplitude = 0.5;    // Starting amplitude — largest octave dominates.
    float totalAmplitude = 0.0;

    // Octave 1: large-scale terrain color variation.
    // This determines whether a patch of grass is light-green or dark-green
    // at the broadest level — the "continental" pattern.
    value += triplanarNoise(pos, baseScale * 1.0) * amplitude;
    totalAmplitude += amplitude;
    amplitude *= 0.5;  // Persistence: each octave is half the previous.

    // Octave 2: medium detail.
    // Adds visible texture at ~5m scale: moss patches, soil color shifts,
    // individual rock face variation.
    value += triplanarNoise(pos, baseScale * 4.0) * amplitude;
    totalAmplitude += amplitude;
    amplitude *= 0.5;

    // Octave 3: micro detail — grass blades, rock cracks, bark texture.
    // At ~1m scale, this octave provides the "up close" visual richness.
    value += triplanarNoise(pos, baseScale * 16.0) * amplitude;
    totalAmplitude += amplitude;
    amplitude *= 0.5;

    // Octave 4: fine grain — sand ripples, snow crystal sparkle.
    // Visible only at close range. The highest frequency, lowest amplitude.
    value += triplanarNoise(pos, baseScale * 40.0) * amplitude;
    totalAmplitude += amplitude;

    // Normalize to [-1, 1] range regardless of how many octaves contribute.
    return value / totalAmplitude;
  }

  // ── Biome color palettes ──────────────────────────────────────────────
  // Each biome has a base color and a detail color. The fBm noise blends
  // between them to produce the final surface color. The detail color
  // represents the visual "character" of each biome at close range.

  // Grass: bright green base with darker variation in low areas.
  vec3 grassColor(vec3 pos, float noise, float detailNoise) {
    vec3 base = vec3(0.28, 0.52, 0.18);      // Mid green — typical grassland.
    vec3 detail = vec3(0.18, 0.40, 0.10);     // Darker green — shaded grass blades.
    vec3 dry = vec3(0.45, 0.48, 0.20);        // Yellow-green — dry patches.
    // Mix base toward detail using medium-frequency noise for blade-level variation.
    vec3 color = mix(base, detail, detailNoise * 0.5 + 0.5);
    // Large-scale noise creates dry patches where the "continental" pattern dips.
    color = mix(color, dry, smoothstep(-0.2, 0.4, noise) * 0.3);
    return color;
  }

  // Rock: gray-brown with high-contrast cracks from the micro-detail octave.
  vec3 rockColor(vec3 pos, float noise, float detailNoise) {
    vec3 base = vec3(0.45, 0.42, 0.40);       // Warm gray.
    vec3 dark = vec3(0.25, 0.22, 0.20);        // Deep crevice shadow.
    vec3 light = vec3(0.60, 0.58, 0.55);       // Exposed face highlight.
    // High-contrast noise → crack patterns. The abs() creates sharp ridges
    // that read as fracture lines in the rock surface.
    float crackPattern = abs(detailNoise);
    vec3 color = mix(dark, light, crackPattern);
    // Large-scale variation shifts the overall rock tone (iron staining, lichen).
    color = mix(color, base, noise * 0.3 + 0.5);
    return color;
  }

  // Snow: mostly white with subtle blue shadows in concavities.
  vec3 snowColor(vec3 pos, float noise, float detailNoise) {
    vec3 base = vec3(0.95, 0.96, 0.98);       // Near-white with cool bias.
    vec3 shadow = vec3(0.75, 0.80, 0.92);      // Blue shadow in dips.
    vec3 sparkle = vec3(1.0, 1.0, 1.0);        // Pure white highlight.
    // Subtle undulation — snow drifts and wind patterns.
    vec3 color = mix(base, shadow, noise * 0.15 + 0.15);
    // Fine-grain sparkle simulates individual crystal facets catching light.
    color = mix(color, sparkle, max(0.0, detailNoise) * 0.1);
    return color;
  }

  // Sand: warm tan with fine ripple texture from the highest octave.
  vec3 sandColor(vec3 pos, float noise, float detailNoise) {
    vec3 base = vec3(0.82, 0.74, 0.55);       // Warm beach sand.
    vec3 wet = vec3(0.65, 0.55, 0.38);         // Darker wet sand.
    vec3 ripple = vec3(0.88, 0.80, 0.62);      // Lighter ripple crests.
    // Ripple pattern: high-frequency noise creates wind-formed ridges.
    vec3 color = mix(base, ripple, detailNoise * 0.3 + 0.5);
    // Moisture-driven darkening near the waterline.
    color = mix(color, wet, smoothstep(0.1, -0.3, noise) * 0.4);
    return color;
  }

  // Forest: dark green base with noise-driven moss and undergrowth patches.
  vec3 forestColor(vec3 pos, float noise, float detailNoise) {
    vec3 base = vec3(0.15, 0.38, 0.12);       // Deep forest green.
    vec3 moss = vec3(0.22, 0.48, 0.18);        // Bright moss patches.
    vec3 earth = vec3(0.30, 0.25, 0.15);       // Exposed forest floor.
    // Moss spots driven by medium-scale noise — creates patches of bright
    // green on an otherwise dark canopy / floor.
    vec3 color = mix(base, moss, smoothstep(-0.1, 0.5, detailNoise) * 0.5);
    // Earth showing through where large-scale noise dips (clearings, paths).
    color = mix(color, earth, smoothstep(0.2, 0.6, noise) * 0.25);
    return color;
  }

  // Water floor: dark blue-green visible through shallow water.
  vec3 waterFloorColor(vec3 pos, float noise, float detailNoise) {
    vec3 base = vec3(0.12, 0.30, 0.50);       // Deep water blue.
    vec3 shallow = vec3(0.15, 0.38, 0.42);     // Shallower teal.
    vec3 sediment = vec3(0.20, 0.28, 0.25);    // Muddy patches.
    vec3 color = mix(base, shallow, noise * 0.2 + 0.5);
    color = mix(color, sediment, smoothstep(-0.3, 0.2, detailNoise) * 0.2);
    return color;
  }
`;

// ─── GLSL: Normal Perturbation ────────────────────────────────────────────────
// Adds micro-normal variation to create apparent surface roughness.
// Instead of computing analytical derivatives of the noise function (expensive),
// we use finite differences: sample noise at slight offsets from the fragment
// position and compute the gradient numerically.
const NORMAL_PERTURBATION_GLSL = /* glsl */ `
  // Perturb the fragment normal using noise-derived gradients.
  // This creates visible surface roughness (bumps, dimples) without
  // additional geometry. The perturbation strength controls how "rough"
  // the surface appears — higher values for rock, lower for snow.
  //
  // Mathematical formulation:
  //   gradient.x = (noise(p + dx) - noise(p - dx)) / (2 * eps)
  //   gradient.y = (noise(p + dy) - noise(p - dy)) / (2 * eps)
  //   perturbedNormal = normalize(normal + tangentSpaceGradient * strength)
  //
  // The epsilon (eps) controls the "wavelength" of the perturbation.
  // Smaller eps = finer bumps. We use 0.02 world units, which produces
  // visible texture at typical viewing distances.
  vec3 perturbNormal(vec3 normal, vec3 pos, float strength, float noiseScale) {
    float eps = 0.02;
    // Central differences along X and Z (the terrain's primary plane).
    // We skip Y because the terrain is predominantly horizontal and
    // Y-axis perturbation would fight the heightmap displacement.
    float nx = snoise(pos * noiseScale + vec3(eps, 0.0, 0.0))
             - snoise(pos * noiseScale - vec3(eps, 0.0, 0.0));
    float nz = snoise(pos * noiseScale + vec3(0.0, 0.0, eps))
             - snoise(pos * noiseScale - vec3(0.0, 0.0, eps));

    // Build the perturbation in world space. We need two tangent vectors
    // spanning the plane perpendicular to the normal. Using cross products
    // with cardinal axes works, but degenerates when the normal is parallel
    // to the chosen axis (cross product → zero → NaN from normalize).
    //
    // Guard: if |dot(normal, axis)| > 0.99, the normal is nearly parallel
    // to that axis, so we pick the other cardinal axis instead. This
    // guarantees a non-degenerate cross product on any surface orientation.
    vec3 refAxisX = abs(dot(normal, vec3(0.0, 0.0, 1.0))) > 0.99
                  ? vec3(0.0, 1.0, 0.0)
                  : vec3(0.0, 0.0, 1.0);
    vec3 refAxisZ = abs(dot(normal, vec3(1.0, 0.0, 0.0))) > 0.99
                  ? vec3(0.0, 1.0, 0.0)
                  : vec3(1.0, 0.0, 0.0);
    vec3 tangentX = normalize(cross(normal, refAxisX));
    vec3 tangentZ = normalize(cross(normal, refAxisZ));

    // Apply the gradient as a displacement along the tangent plane.
    vec3 perturbation = tangentX * nx + tangentZ * nz;
    return normalize(normal + perturbation * strength);
  }
`;

// ─── Vertex Shader Injection ──────────────────────────────────────────────────
// We need world-space position and normal in the fragment shader for:
//   1. Triplanar mapping (world position as UV source)
//   2. Slope detection (world normal dot product with up vector)
//   3. Height-based blending (world position Y coordinate)
//   4. Normal perturbation (world position for noise sampling)
//
// Three.js MeshStandardMaterial already computes modelMatrix transforms
// internally, but doesn't expose world-space varyings. We inject them.
const VERTEX_DECLARATIONS = /* glsl */ `
  varying vec3 vWorldPosition;
  varying vec3 vWorldNormal;
`;

const VERTEX_MAIN_INJECTION = /* glsl */ `
  // Compute world-space position by applying the full model matrix.
  // This accounts for any translation, rotation, or scale on the mesh.
  vWorldPosition = (modelMatrix * vec4(position, 1.0)).xyz;

  // Transform normal to world space. normalMatrix is the inverse-transpose
  // of modelViewMatrix's upper-left 3x3, which correctly handles non-uniform
  // scale. However, we want world-space (not view-space) normals, so we use
  // the model matrix's upper-left 3x3 instead. For uniformly-scaled meshes
  // (which terrain typically is), this is equivalent and cheaper.
  vWorldNormal = normalize(mat3(modelMatrix) * normal);
`;

// ─── Fragment Shader Injection ────────────────────────────────────────────────
// The main fragment logic: classifies the surface into a biome, computes
// noise-based detail, blends by slope and height, and applies normal perturbation.
const FRAGMENT_DECLARATIONS = /* glsl */ `
  varying vec3 vWorldPosition;
  varying vec3 vWorldNormal;

  // User-configurable uniforms for runtime tuning.
  uniform float uNoiseScale;      // Base frequency multiplier for all noise.
  uniform float uDetailLevel;     // 0 = flat color only, 1 = full procedural detail.
  uniform float uHeightMax;       // Maximum terrain height for snow/sand normalization.
`;

/**
 * Build the main fragment shader body that replaces the color_fragment chunk.
 *
 * This function returns a GLSL string that:
 *   1. Reads the vertex color (biome classification hint).
 *   2. Computes slope from the world normal.
 *   3. Computes normalized height from world position Y.
 *   4. Evaluates fBm noise at multiple octaves.
 *   5. Selects and blends biome colors based on vertex color, slope, and height.
 *   6. Applies normal perturbation for micro-roughness.
 *   7. Writes the final diffuseColor.
 *
 * @returns {string} GLSL fragment shader code.
 */
function buildColorFragmentGLSL() {
  return /* glsl */ `
    // ── Read biome hint from vertex color ───────────────────────────────
    // The terrain mesh has vertex colors set by the biome classifier in
    // terrain-renderer.js. We use these as soft hints, not hard assignments,
    // because we want slope and height to override classification at edges.
    vec3 biomeHint = vColor;

    // ── Compute slope and height ────────────────────────────────────────
    // Slope = angle between surface normal and the up vector.
    // dot(N, up) = cos(angle). Flat ground → 1.0, vertical cliff → 0.0.
    float slopeAngle = dot(normalize(vWorldNormal), vec3(0.0, 1.0, 0.0));

    // slope01: 0.0 = flat, 1.0 = vertical. Inverted from slopeAngle for
    // intuitive use: "more slope = more rock".
    float slope01 = 1.0 - slopeAngle;

    // Normalized height: map world Y into [0, 1] range for height-based
    // biome transitions. uHeightMax should match the terrain's vertical
    // extent (heightScale * max heightmap value).
    float heightNorm = clamp(vWorldPosition.y / max(uHeightMax, 0.01), 0.0, 1.0);

    // ── Evaluate noise at multiple scales ───────────────────────────────
    // Large-scale noise (octave 1 dominant) — drives biome-level variation.
    float noiseLarge = fbm(vWorldPosition, uNoiseScale * 0.5);
    // Detail noise (octaves 2-4 dominant) — drives texture-level variation.
    float noiseDetail = fbm(vWorldPosition, uNoiseScale * 2.0);
    // Micro noise for the finest detail (sand ripples, snow crystals).
    float noiseMicro = triplanarNoise(vWorldPosition, uNoiseScale * 20.0);

    // ── Biome identification from vertex color ──────────────────────────
    // Rather than passing biome IDs as a separate attribute, we decode
    // the biome from the vertex color's hue/value. This is approximate
    // but avoids adding a custom attribute to the geometry.
    //
    // Strategy: compute distance from each biome's reference color and
    // pick the closest match. This is O(6) per fragment — negligible.

    // Reference colors match BIOME_COLORS from terrain-renderer.js.
    vec3 refWater  = vec3(0.12, 0.30, 0.50);
    vec3 refSand   = vec3(0.82, 0.74, 0.55);
    vec3 refGrass  = vec3(0.28, 0.52, 0.18);
    vec3 refForest = vec3(0.15, 0.38, 0.12);
    vec3 refRock   = vec3(0.45, 0.42, 0.40);
    vec3 refSnow   = vec3(0.95, 0.96, 0.98);

    // Distance to each reference — smaller = closer match.
    float dWater  = distance(biomeHint, refWater);
    float dSand   = distance(biomeHint, refSand);
    float dGrass  = distance(biomeHint, refGrass);
    float dForest = distance(biomeHint, refForest);
    float dRock   = distance(biomeHint, refRock);
    float dSnow   = distance(biomeHint, refSnow);

    // Convert distances to soft weights using an inverse-distance scheme.
    // The exponent (8.0) controls sharpness: higher = harder boundaries.
    // 8.0 gives smooth ~10% terrain-unit transitions between biomes.
    float sharpness = 8.0;
    float wWater  = 1.0 / (pow(dWater  + 0.001, sharpness) + 0.0001);
    float wSand   = 1.0 / (pow(dSand   + 0.001, sharpness) + 0.0001);
    float wGrass  = 1.0 / (pow(dGrass  + 0.001, sharpness) + 0.0001);
    float wForest = 1.0 / (pow(dForest + 0.001, sharpness) + 0.0001);
    float wRock   = 1.0 / (pow(dRock   + 0.001, sharpness) + 0.0001);
    float wSnow   = 1.0 / (pow(dSnow   + 0.001, sharpness) + 0.0001);

    // Normalize weights to sum to 1.
    float wTotal = wWater + wSand + wGrass + wForest + wRock + wSnow;
    wWater  /= wTotal;
    wSand   /= wTotal;
    wGrass  /= wTotal;
    wForest /= wTotal;
    wRock   /= wTotal;
    wSnow   /= wTotal;

    // ── Compute per-biome procedural color ──────────────────────────────
    vec3 cWater  = waterFloorColor(vWorldPosition, noiseLarge, noiseDetail);
    vec3 cSand   = sandColor(vWorldPosition, noiseLarge, noiseMicro);
    vec3 cGrass  = grassColor(vWorldPosition, noiseLarge, noiseDetail);
    vec3 cForest = forestColor(vWorldPosition, noiseLarge, noiseDetail);
    vec3 cRock   = rockColor(vWorldPosition, noiseLarge, noiseDetail);
    vec3 cSnow   = snowColor(vWorldPosition, noiseLarge, noiseMicro);

    // ── Blend biome colors by vertex-color weights ──────────────────────
    vec3 proceduralColor = cWater  * wWater
                         + cSand   * wSand
                         + cGrass  * wGrass
                         + cForest * wForest
                         + cRock   * wRock
                         + cSnow   * wSnow;

    // ── Slope-dependent rock override ───────────────────────────────────
    // Steep cliffs automatically show rock material regardless of biome.
    // This is physically motivated: soil can't accumulate on steep slopes,
    // so bedrock is exposed.
    //
    // Threshold: slope01 > 0.5 corresponds to ~60 degrees from horizontal.
    // The smoothstep gives a gradual transition over the 0.4-0.7 range.
    float rockBlend = smoothstep(0.4, 0.7, slope01);
    proceduralColor = mix(proceduralColor, cRock, rockBlend);

    // ── Height-based snow override ──────────────────────────────────────
    // Snow appears at high elevations AND low slope (can't stick to cliffs).
    // The height threshold is at 70% of max terrain height.
    // Noise adds irregular snow line for visual interest.
    float snowLine = 0.7 + noiseLarge * 0.08;
    float snowBlend = smoothstep(snowLine, snowLine + 0.1, heightNorm)
                    * smoothstep(0.5, 0.2, slope01);   // Less snow on steep slopes.
    proceduralColor = mix(proceduralColor, cSnow, snowBlend);

    // ── Height-based sand near sea level ────────────────────────────────
    // Sand appears near sea level (bottom 15% of height range) on gentle slopes.
    // This simulates beach / river bank deposits.
    float sandLine = 0.15 + noiseLarge * 0.05;
    float sandBlend = smoothstep(sandLine, sandLine - 0.1, heightNorm)
                    * smoothstep(0.4, 0.15, slope01);  // Only on gentle slopes.
    proceduralColor = mix(proceduralColor, cSand, sandBlend);

    // ── Valley darkening ────────────────────────────────────────────────
    // Low areas are slightly darker — simulates ambient occlusion from
    // surrounding terrain blocking sky light. Simple height-based fade.
    float valleyDarken = smoothstep(0.0, 0.3, heightNorm);
    proceduralColor *= mix(0.8, 1.0, valleyDarken);

    // ── Blend with original vertex color based on detail level ──────────
    // uDetailLevel = 0 → pure vertex color (original flat biome look).
    // uDetailLevel = 1 → full procedural detail.
    // This allows graceful LOD fallback at distance.
    vec3 finalColor = mix(biomeHint, proceduralColor, uDetailLevel);

    // ── Normal perturbation for micro-roughness ─────────────────────────
    // Different biomes get different perturbation strengths:
    // Rock = strongest (0.4), Grass/Forest = moderate (0.15), Snow = subtle (0.05).
    float perturbStrength = 0.15;
    perturbStrength = mix(perturbStrength, 0.4, rockBlend);     // Rocky surfaces are rougher.
    perturbStrength = mix(perturbStrength, 0.05, snowBlend);    // Snow is smooth.
    perturbStrength *= uDetailLevel;                            // Scale with detail level.

    // Apply normal perturbation to the fragment normal.
    // This modifies how light interacts with the surface, creating the
    // appearance of bumps and crevices without additional geometry.
    vec3 perturbedNormal = perturbNormal(
      normalize(vWorldNormal),
      vWorldPosition,
      perturbStrength,
      uNoiseScale * 8.0     // Perturbation noise scale — medium-high frequency.
    );

    // Write perturbed normal back for lighting calculations.
    // In Three.js MeshStandardMaterial, the normal is used by the PBR
    // lighting model in subsequent shader chunks.
    normal = perturbedNormal;

    // Write final diffuse color.
    diffuseColor.rgb = finalColor;
  `;
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Create a procedural terrain material with noise-based textures.
 *
 * Returns a `MeshStandardMaterial` with `onBeforeCompile` configured to inject
 * simplex noise, triplanar mapping, fBm, biome blending, and normal perturbation
 * into the shader pipeline.
 *
 * The material reads vertex colors (`vColor`) as biome classification hints and
 * uses world-space position and normals for all procedural effects. It is
 * designed as a drop-in replacement for the plain `MeshStandardMaterial` in
 * `terrain-renderer.js`.
 *
 * @param {Object} [options={}] - Configuration options.
 * @param {number} [options.roughness=0.85] - PBR roughness (0 = mirror, 1 = matte).
 *   Terrain is almost always matte, so the default is high.
 * @param {number} [options.metalness=0.05] - PBR metalness (0 = dielectric, 1 = metal).
 *   Natural terrain has near-zero metalness.
 * @param {number} [options.noiseScale=1.0] - Base frequency multiplier for all noise
 *   octaves. Higher values = more repetitions per world unit = smaller features.
 *   The four fBm octaves evaluate at noiseScale * [0.5, 2.0, 8.0, 20.0].
 * @param {number} [options.detailLevel=1.0] - Procedural detail blend factor (0-1).
 *   0 = original flat vertex colors, 1 = full procedural texturing.
 *   Useful for LOD: reduce detail for distant terrain chunks.
 * @param {number} [options.heightMax=2.1] - Maximum terrain height in world units.
 *   Used to normalize height for snow/sand blending. Should match
 *   `heightScale` from `buildTerrainMesh()`.
 * @returns {THREE.MeshStandardMaterial} Material with procedural shader injection.
 *
 * @example
 * ```js
 * import { createTerrainMaterial } from './nature/terrain-material.js';
 *
 * const material = createTerrainMaterial({ noiseScale: 1.2, detailLevel: 0.8 });
 * const mesh = new THREE.Mesh(terrainGeometry, material);
 * ```
 */
export function createTerrainMaterial(options = {}) {
  const {
    roughness = 0.85,
    metalness = 0.05,
    noiseScale = 1.0,
    detailLevel = 1.0,
    heightMax = 2.1,
  } = options;

  const material = new THREE.MeshStandardMaterial({
    vertexColors: true,
    flatShading: false,
    roughness,
    metalness,
    side: THREE.DoubleSide,
  });

  // Store uniform references so they can be updated at runtime for LOD,
  // animation, or debug tuning without recompiling the shader.
  const customUniforms = {
    uNoiseScale: { value: noiseScale },
    uDetailLevel: { value: detailLevel },
    uHeightMax: { value: heightMax },
  };

  // Expose uniforms on userData for external access:
  //   material.userData.uniforms.uDetailLevel.value = 0.5;
  material.userData.uniforms = customUniforms;

  /**
   * onBeforeCompile is called by Three.js exactly once, just before the shader
   * program is compiled and linked on the GPU. We use it to:
   *   1. Merge our custom uniforms into the shader's uniform map.
   *   2. Inject world-space varyings into the vertex shader.
   *   3. Inject noise functions, biome palettes, and blending logic into the
   *      fragment shader.
   *
   * After this callback, the compiled program is cached by Three.js. Changing
   * uniform VALUES (not structure) still works via the uniform objects; changing
   * the shader SOURCE requires calling material.needsUpdate = true to force
   * recompilation.
   */
  material.onBeforeCompile = (shader) => {
    // ── Merge custom uniforms ──────────────────────────────────────────
    // Three.js provides its own uniforms (lights, matrices, etc.) in
    // shader.uniforms. We add ours alongside them.
    Object.assign(shader.uniforms, customUniforms);

    // ── Vertex shader modifications ────────────────────────────────────
    // Inject varying declarations before the main() function.
    // We target `#include <common>` which appears early in every Three.js
    // vertex shader and is a safe injection point.
    shader.vertexShader = shader.vertexShader.replace(
      '#include <common>',
      `#include <common>\n${VERTEX_DECLARATIONS}`
    );

    // Inject world-space computation at the end of the vertex main().
    // We target `#include <worldpos_vertex>` which is the standard
    // Three.js injection point for world-position-related code.
    // If the chunk isn't found (some material variants omit it),
    // fall back to appending before the closing brace.
    if (shader.vertexShader.includes('#include <worldpos_vertex>')) {
      shader.vertexShader = shader.vertexShader.replace(
        '#include <worldpos_vertex>',
        `#include <worldpos_vertex>\n${VERTEX_MAIN_INJECTION}`
      );
    } else {
      // Fallback: insert before the last closing brace of main().
      shader.vertexShader = shader.vertexShader.replace(
        /}\s*$/,
        `${VERTEX_MAIN_INJECTION}\n}`
      );
    }

    // ── Fragment shader modifications ──────────────────────────────────
    // Step 1: Inject varying declarations and uniform declarations.
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <common>',
      [
        '#include <common>',
        FRAGMENT_DECLARATIONS,
        SIMPLEX_NOISE_GLSL,
        TERRAIN_FRAGMENT_GLSL,
        NORMAL_PERTURBATION_GLSL,
      ].join('\n')
    );

    // Step 2: Replace the color_fragment chunk with our procedural logic.
    // The `#include <color_fragment>` chunk in MeshStandardMaterial is where
    // `diffuseColor` gets set from the base color / vertex color. We replace
    // it entirely with our biome + noise blending code.
    //
    // The replacement reads `vColor` (set by Three.js when vertexColors: true),
    // computes procedural color, and writes back to `diffuseColor.rgb`.
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <color_fragment>',
      buildColorFragmentGLSL()
    );
  };

  // Mark the material key as unique so Three.js doesn't share the compiled
  // program with other MeshStandardMaterials that lack our injections.
  // Without this, Three.js's program cache might serve the wrong shader.
  material.customProgramCacheKey = () => 'terrain-procedural-v1';

  return material;
}
