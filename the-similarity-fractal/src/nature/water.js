/**
 * Realistic water rendering system with self-similar Gerstner waves.
 *
 * Replaces the flat transparent plane from terrain-renderer.js with a
 * physically-motivated ocean surface. The system layers three wave scales
 * (ocean swell, medium chop, ripples) to produce self-similar structure,
 * matching the fractal terrain aesthetic of the project.
 *
 * Architecture overview:
 *   Water
 *     |- PlaneGeometry (128x128 segments for vertex displacement)
 *     |- Custom ShaderMaterial (vertex: Gerstner displacement, fragment: PBR water)
 *     |- Reflection render target (half-res, mirrored camera)
 *     |- Refraction render target (half-res, underwater view)
 *
 * Lifecycle:
 *   1. constructor(scene, options) -- creates geometry, material, render targets
 *   2. update(time, renderer, camera) -- called each frame; animates waves, renders reflection/refraction
 *   3. dispose() -- releases GPU resources; safe to call multiple times
 *
 * The reflection system mirrors the main camera across the water plane and renders
 * to a half-resolution WebGLRenderTarget. During this render pass the water mesh
 * itself is hidden (visible=false) to avoid recursion. A clipping plane excludes
 * geometry below the water surface from the reflection.
 *
 * Immutability: wave parameters (WAVE_SCALES) are frozen at construction. The only
 * mutable state is the time uniform and the render targets, which are updated each
 * frame via update(). setWaterLevel() mutates the mesh position and uniforms.
 *
 * Performance budget: the reflection/refraction renders are half-res (width/2, height/2).
 * The 128x128 plane has ~16k vertices, which is modest for modern GPUs. The vertex
 * shader does all wave math analytically (no texture lookups), keeping it bandwidth-friendly.
 */

import * as THREE from 'three';

// ─────────────────────────────────────────────────────────────────────────────
// Wave scale definitions (self-similar, 3 octaves)
// ─────────────────────────────────────────────────────────────────────────────
// Each scale is defined by:
//   amplitude   (A) -- vertical displacement in world units
//   wavelength  (λ) -- spatial period; wave number k = 2π/λ
//   speed       (S) -- phase velocity in world units/sec
//   direction   (D) -- 2D unit vector [dx, dz] in the XZ plane
//   steepness   (Q) -- Gerstner "Q" factor in [0, 1/(k*A)] controlling horizontal pinch;
//                       higher values produce sharper crests approaching the breaking limit
//
// The three scales mimic real ocean spectra at vastly different energy levels:
//   Scale 1 (swell):  long-period energy from distant storms, dominates visual shape
//   Scale 2 (chop):   local wind waves, adds medium-frequency detail
//   Scale 3 (ripples): capillary-gravity waves, highest frequency, lowest energy
//
// Self-similarity: each successive scale has roughly λ/3 and A/3 of the previous,
// producing a 1/f-like power spectrum consistent with the Pierson-Moskowitz model.
const WAVE_SCALES = Object.freeze([
  { amplitude: 0.03,  wavelength: 4.0, speed: 0.8, direction: [1.0, 0.6],  steepness: 0.4 },
  { amplitude: 0.01,  wavelength: 1.5, speed: 1.2, direction: [-0.7, 1.0], steepness: 0.5 },
  { amplitude: 0.003, wavelength: 0.3, speed: 2.0, direction: [0.4, -0.8], steepness: 0.6 },
]);

// ─────────────────────────────────────────────────────────────────────────────
// Default configuration
// ─────────────────────────────────────────────────────────────────────────────
const DEFAULTS = Object.freeze({
  size: 10,                            // XZ extent of water plane (world units)
  waterLevel: 0.42,                    // Y position of the undisplaced water surface
  segments: 128,                       // subdivision count per axis; 128^2 = 16384 verts
  rtResolutionScale: 0.5,              // fraction of renderer size for reflection/refraction RTs
  shallowColor: [0.1, 0.6, 0.7],      // bright teal (RGB, linear)
  deepColor: [0.02, 0.05, 0.15],      // dark navy (RGB, linear)
  foamColor: [0.9, 0.95, 1.0],        // near-white with slight blue tint
  absorptionCoeff: 3.0,               // exponential depth-absorption rate
  foamDepthThreshold: 0.15,           // shallow-water foam trigger depth
  foamCrestThreshold: 0.6,            // wave-crest foam trigger (fraction of max amplitude)
  chromaticOffset: 0.003,             // RGB channel offset for refraction dispersion
});

// ─────────────────────────────────────────────────────────────────────────────
// GLSL — Vertex shader
// ─────────────────────────────────────────────────────────────────────────────
// The vertex shader displaces each vertex according to the Gerstner wave model.
//
// Gerstner waves displace vertices both vertically (Y) and horizontally (XZ),
// producing the characteristic trochoid shape of ocean waves: flat troughs and
// peaked crests. The standard formulation for a single Gerstner wave is:
//
//   x' = x - Q * A * Dx * sin(dot(k*D, p) - w*t)
//   z' = z - Q * A * Dz * sin(dot(k*D, p) - w*t)
//   y' = A * cos(dot(k*D, p) - w*t)
//
// where:
//   (x, z)  = undisplaced vertex position
//   k       = 2π / wavelength  (wave number)
//   w       = speed * k         (angular frequency; deep-water dispersion would use sqrt(g*k))
//   D       = (Dx, Dz) normalized wave direction
//   A       = amplitude
//   Q       = steepness factor (0 = pure sine, 1/(k*A) = cusp limit)
//   t       = time
//
// Multiple waves are summed. The analytic normal is computed from the partial
// derivatives of the displaced surface, avoiding a costly finite-difference pass.
const VERTEX_SHADER = /* glsl */ `
  precision highp float;

  // Per-wave parameters packed into vec4s to reduce uniform call overhead.
  // waveParams[i] = vec4(amplitude, wavenumber_k, angular_freq_w, steepness_Q)
  // waveDir[i]    = vec2(normalized direction Dx, Dz)
  uniform vec4 waveParams[3];
  uniform vec2 waveDir[3];
  uniform float uTime;
  uniform float uWaterLevel;

  varying vec3 vWorldPosition;
  varying vec3 vNormal;
  varying vec2 vUv;

  /**
   * Sum Gerstner displacement and compute analytic normal.
   *
   * Returns displaced position in xyz; also writes the surface normal into
   * the out-parameter 'norm'. Computing both in one pass avoids redundant
   * trig evaluations.
   *
   * The analytic normal comes from the Jacobian of the Gerstner mapping:
   *   dP/du and dP/dv give tangent vectors on the displaced surface;
   *   their cross product is the (unnormalized) normal.
   *
   * For the sum of N waves, the partial derivatives sum linearly (the
   * Gerstner mapping is a linear combination of per-wave displacements).
   * We accumulate the tangent/binormal perturbations and reconstruct
   * the normal at the end.
   */
  vec3 gerstnerDisplace(vec3 pos, out vec3 norm) {
    vec3 displaced = pos;

    // Analytic normal accumulator (GPU Gems 1, Ch. 1 — Finch).
    // The simplified normal formula avoids full Jacobian reconstruction:
    //   N = (sum(Dx * WA * sin(phase)),
    //        1 - sum(Q * WA * cos(phase)),
    //        sum(Dz * WA * sin(phase)))
    // This can produce N.y < 0 if steepness Q is too high; the normalize()
    // at the end handles that gracefully.
    vec3 N = vec3(0.0, 1.0, 0.0);

    for (int i = 0; i < 3; i++) {
      float A = waveParams[i].x;   // amplitude
      float k = waveParams[i].y;   // wave number 2pi/lambda
      float w = waveParams[i].z;   // angular frequency
      float Q = waveParams[i].w;   // steepness

      vec2 D = waveDir[i];         // normalized direction

      // Phase: dot product of wave vector with undisplaced XZ position, minus time term.
      // Using the original (undisplaced) position for the phase avoids the implicit
      // equation that full Gerstner requires, which would need iteration to solve.
      // This approximation is standard in real-time rendering (GPU Gems, Tessendorf).
      float phase = k * dot(D, pos.xz) - w * uTime;
      float S = sin(phase);
      float C = cos(phase);

      // Horizontal displacement (the hallmark of Gerstner vs. simple sine waves).
      // Q controls how much the surface "pinches" toward wave crests.
      displaced.x -= Q * A * D.x * S;
      displaced.z -= Q * A * D.y * S;  // D.y is the Z-component of the 2D direction

      // Vertical displacement.
      displaced.y += A * C;

      // Accumulate analytic normal from partial derivatives of the displaced surface.
      float WA = k * A;
      N.x += D.x * WA * S;
      N.y -= Q * WA * C;
      N.z += D.y * WA * S;
    }

    norm = normalize(N);
    return displaced;
  }

  void main() {
    vec3 norm;
    vec3 displaced = gerstnerDisplace(position, norm);

    // Offset by the global water level.
    displaced.y += uWaterLevel;

    vWorldPosition = (modelMatrix * vec4(displaced, 1.0)).xyz;
    vNormal = normalize((modelMatrix * vec4(norm, 0.0)).xyz);
    vUv = uv;

    gl_Position = projectionMatrix * viewMatrix * vec4(vWorldPosition, 1.0);
  }
`;

// ─────────────────────────────────────────────────────────────────────────────
// GLSL — Fragment shader
// ─────────────────────────────────────────────────────────────────────────────
// Combines:
//   1. Planar reflection (mirrored scene rendered to texture)
//   2. Refraction with chromatic dispersion (underwater scene, RGB-offset sampling)
//   3. Fresnel blend (Schlick approximation)
//   4. Depth-based absorption (shallow teal -> deep navy, exponential)
//   5. Foam (shoreline proximity + wave-crest detection, noise-modulated)
const FRAGMENT_SHADER = /* glsl */ `
  precision highp float;

  uniform sampler2D uReflectionMap;
  uniform sampler2D uRefractionMap;
  uniform vec2 uResolution;
  uniform float uTime;
  uniform vec3 uCameraPosition;

  // Water appearance
  uniform vec3 uShallowColor;
  uniform vec3 uDeepColor;
  uniform vec3 uFoamColor;
  uniform float uAbsorptionCoeff;
  uniform float uFoamDepthThreshold;
  uniform float uFoamCrestThreshold;
  uniform float uChromaticOffset;
  uniform float uWaterLevel;

  // Wave params (reused for foam crest detection in fragment)
  uniform vec4 waveParams[3];
  uniform vec2 waveDir[3];

  varying vec3 vWorldPosition;
  varying vec3 vNormal;
  varying vec2 vUv;

  // ── Noise function for foam organic edges ──────────────────────────────────
  // Simple 2D hash-based value noise. We do NOT need Perlin/simplex quality here;
  // the foam is additive and brief, so banding artifacts are invisible.
  float hash(vec2 p) {
    // Robust hash: large prime dot product -> fract of sine.
    // The magic numbers are standard (iq/Shadertoy community).
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    // Hermite smoothstep for C1 continuity (avoids grid artifacts).
    vec2 u = f * f * (3.0 - 2.0 * f);

    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));

    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }

  // Fractal Brownian Motion -- 3 octaves, matching the 3 wave scales for thematic
  // consistency with the self-similar wave structure.
  float fbm(vec2 p) {
    float val = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 3; i++) {
      val += amp * noise(p);
      p *= 2.17;    // frequency multiplier (non-integer to avoid aliasing patterns)
      amp *= 0.5;   // standard 1/f decay
    }
    return val;
  }

  void main() {
    vec3 normal = normalize(vNormal);
    vec3 viewDir = normalize(uCameraPosition - vWorldPosition);

    // ── Screen-space UV for reflection/refraction texture lookups ───────────
    // Project world position to clip space, then to [0,1] UV range.
    // The reflection map was rendered from a mirrored camera, so we flip V.
    vec2 screenUV = gl_FragCoord.xy / uResolution;

    // Distort the texture coordinates by the wave normal to simulate
    // the light-bending effect of the wavy surface. The distortion magnitude
    // is tuned to be subtle but visible.
    vec2 distortion = normal.xz * 0.03;

    // ── Reflection ─────────────────────────────────────────────────────────
    // Sample the mirrored-camera render target. The V coordinate is flipped
    // because the reflection camera is upside-down relative to the main camera.
    vec2 reflUV = vec2(screenUV.x, 1.0 - screenUV.y) + distortion;
    reflUV = clamp(reflUV, 0.001, 0.999);   // prevent edge bleeding
    vec3 reflectionColor = texture2D(uReflectionMap, reflUV).rgb;

    // ── Refraction with chromatic dispersion ───────────────────────────────
    // Sample the underwater scene three times with slight UV offsets per
    // channel, simulating how water disperses light by wavelength (red
    // refracts less than blue). The offset is small to avoid cartoon effects.
    vec2 refrUV = screenUV + distortion * 0.5;
    refrUV = clamp(refrUV, 0.001, 0.999);
    float refrR = texture2D(uRefractionMap, refrUV + vec2(uChromaticOffset, 0.0)).r;
    float refrG = texture2D(uRefractionMap, refrUV).g;
    float refrB = texture2D(uRefractionMap, refrUV - vec2(uChromaticOffset, 0.0)).b;
    vec3 refractionColor = vec3(refrR, refrG, refrB);

    // ── Depth-based absorption ─────────────────────────────────────────────
    // Approximate water depth as the distance from the water surface to the
    // terrain below. Since we don't have a proper depth buffer from the
    // refraction pass in this setup, we use the vertical distance of the
    // fragment from the water level as a proxy. Near the shore (shallow),
    // the water is bright teal; in deep open water, it darkens to navy.
    //
    // The exponential model: color = shallow * exp(-absorption * depth) + deep * (1 - exp(...))
    // is physically motivated by Beer-Lambert absorption.
    float depth = max(0.0, uWaterLevel - (vWorldPosition.y - uWaterLevel));
    float absorption = 1.0 - exp(-uAbsorptionCoeff * depth);
    vec3 waterBodyColor = mix(uShallowColor, uDeepColor, absorption);

    // Tint the refraction by the water body color (light passing through water picks up color).
    refractionColor *= mix(vec3(1.0), waterBodyColor, 0.6);

    // ── Fresnel effect (Schlick approximation) ─────────────────────────────
    // At grazing angles (viewDir nearly perpendicular to normal), the surface
    // is highly reflective. Looking straight down, it becomes transparent.
    //
    // Schlick: F = F0 + (1 - F0) * (1 - cos(theta))^5
    // F0 for water-air interface is ~0.02 (n_water = 1.33).
    float F0 = 0.02;
    float cosTheta = max(dot(viewDir, normal), 0.0);
    float fresnel = F0 + (1.0 - F0) * pow(1.0 - cosTheta, 5.0);

    // Blend reflection and refraction based on Fresnel.
    vec3 color = mix(refractionColor, reflectionColor, fresnel);

    // ── Foam ───────────────────────────────────────────────────────────────
    // Two foam sources:
    //   1. Shoreline foam: where water is shallow (depth < threshold)
    //   2. Crest foam: where the wave height exceeds a threshold
    //
    // Both are modulated by fractal noise for organic, patchy edges.

    // Shoreline foam (based on depth proximity).
    float shorelineFoam = smoothstep(uFoamDepthThreshold, 0.0, depth);

    // Crest foam: recompute the wave-crest height in the fragment shader.
    // This is the sum of the vertical (Y) displacement from all wave scales.
    // When the summed height exceeds a threshold fraction of the maximum
    // possible displacement, we trigger foam.
    float waveHeight = 0.0;
    float maxHeight = 0.0;
    for (int i = 0; i < 3; i++) {
      float A = waveParams[i].x;
      float k = waveParams[i].y;
      float w = waveParams[i].z;
      vec2 D = waveDir[i];
      float phase = k * dot(D, vWorldPosition.xz) - w * uTime;
      waveHeight += A * cos(phase);
      maxHeight += A;
    }
    float crestFoam = smoothstep(uFoamCrestThreshold * maxHeight, maxHeight, waveHeight);

    // Combine foam sources and modulate with noise.
    float foamNoise = fbm(vWorldPosition.xz * 8.0 + uTime * 0.3);
    float foam = max(shorelineFoam, crestFoam) * foamNoise;
    foam = smoothstep(0.2, 0.8, foam);   // sharpen edges

    color = mix(color, uFoamColor, foam);

    // ── Subtle specular highlight (sun direction hardcoded for simplicity) ──
    vec3 sunDir = normalize(vec3(0.5, 0.8, 0.3));
    vec3 halfVec = normalize(sunDir + viewDir);
    float spec = pow(max(dot(normal, halfVec), 0.0), 256.0);
    color += vec3(1.0, 0.95, 0.9) * spec * 0.5;

    // Final output with slight transparency for the deepest parts.
    float alpha = mix(0.85, 0.95, fresnel);
    gl_FragColor = vec4(color, alpha);
  }
`;

// ─────────────────────────────────────────────────────────────────────────────
// Water class
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Realistic water rendering system with self-similar Gerstner waves,
 * planar reflections, refraction with chromatic dispersion, Fresnel blending,
 * depth-based absorption, and foam.
 *
 * Usage:
 *   const water = new Water(scene, { size: 10, waterLevel: 0.42 });
 *   // in animation loop:
 *   water.update(elapsedTime, renderer, camera);
 *   // cleanup:
 *   water.dispose();
 *
 * State:
 *   - this.mesh: the THREE.Mesh added to the scene (mutable position via setWaterLevel)
 *   - this._reflectionRT / this._refractionRT: WebGLRenderTargets (recreated if renderer resizes)
 *   - this._reflectionCamera: PerspectiveCamera mirrored across the water plane
 *   - this._disposed: guard flag preventing double-dispose
 *
 * Thread safety: N/A (single-threaded JS). However, update() temporarily mutates
 * scene state (water.visible, camera clipping planes) and restores it before returning.
 * Do NOT call update() from within another render pass.
 */
export class Water {
  /**
   * @param {THREE.Scene} scene - The scene to add the water mesh to.
   * @param {Object} [options={}] - Configuration overrides (see DEFAULTS).
   * @param {number} [options.size] - XZ extent of the water plane.
   * @param {number} [options.waterLevel] - Y position of the undisplaced surface.
   * @param {number[]} [options.shallowColor] - RGB array for shallow water.
   * @param {number[]} [options.deepColor] - RGB array for deep water.
   */
  constructor(scene, options = {}) {
    const cfg = { ...DEFAULTS, ...options };
    this._scene = scene;
    this._disposed = false;

    // ── Geometry ────────────────────────────────────────────────────────────
    // 128x128 segments = 16,384 vertices. Each vertex gets displaced by the
    // Gerstner shader, so we need enough resolution for the shortest wavelength
    // (0.3 world units) to be represented by multiple vertices. At size=10,
    // vertex spacing = 10/128 ~ 0.078, giving ~4 vertices per shortest wavelength.
    // Nyquist is satisfied (need >= 2 per wavelength).
    const geometry = new THREE.PlaneGeometry(
      cfg.size, cfg.size,
      cfg.segments, cfg.segments
    );
    // Rotate from XY to XZ plane (Three.js PlaneGeometry defaults to XY).
    geometry.rotateX(-Math.PI / 2);

    // ── Pack wave parameters into uniform-friendly arrays ──────────────────
    // Pre-normalize wave directions and compute derived quantities (k, w)
    // so the shader doesn't have to.
    const waveParamsArray = [];
    const waveDirArray = [];

    for (const wave of WAVE_SCALES) {
      const k = (2.0 * Math.PI) / wave.wavelength;  // wave number
      const w = wave.speed * k;                       // angular frequency
      // Normalize direction vector.
      const len = Math.sqrt(wave.direction[0] ** 2 + wave.direction[1] ** 2);
      const dx = wave.direction[0] / len;
      const dz = wave.direction[1] / len;

      waveParamsArray.push(new THREE.Vector4(wave.amplitude, k, w, wave.steepness));
      waveDirArray.push(new THREE.Vector2(dx, dz));
    }

    // ── Render targets for reflection & refraction ─────────────────────────
    // Half-resolution is a standard real-time water optimization. The slight
    // blur from upscaling actually helps sell the water surface distortion.
    // We use 512x512 as initial size; update() resizes if the renderer changes.
    const rtOptions = {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      format: THREE.RGBAFormat,
      // No depth texture needed -- we use a clipping plane approach instead.
    };
    this._reflectionRT = new THREE.WebGLRenderTarget(512, 512, rtOptions);
    this._refractionRT = new THREE.WebGLRenderTarget(512, 512, rtOptions);

    // ── Reflection camera ──────────────────────────────────────────────────
    // A PerspectiveCamera whose position and orientation are mirrored across
    // the water plane (Y = waterLevel). Updated each frame in update().
    this._reflectionCamera = new THREE.PerspectiveCamera();

    // ── Clipping planes ────────────────────────────────────────────────────
    // During reflection render: clip everything BELOW the water (only render above-water geometry).
    // During refraction render: clip everything ABOVE the water (only render underwater geometry).
    // The planes are updated in setWaterLevel() and update().
    this._reflectionClipPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -cfg.waterLevel);
    this._refractionClipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), cfg.waterLevel);

    // ── Shader material ────────────────────────────────────────────────────
    const material = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      transparent: true,
      // Side: render both faces so the water is visible from below (e.g., underwater camera).
      side: THREE.DoubleSide,
      uniforms: {
        waveParams: { value: waveParamsArray },
        waveDir: { value: waveDirArray },
        uTime: { value: 0.0 },
        uWaterLevel: { value: cfg.waterLevel },
        uReflectionMap: { value: this._reflectionRT.texture },
        uRefractionMap: { value: this._refractionRT.texture },
        uResolution: { value: new THREE.Vector2(512, 512) },
        uCameraPosition: { value: new THREE.Vector3() },
        uShallowColor: { value: new THREE.Vector3(...cfg.shallowColor) },
        uDeepColor: { value: new THREE.Vector3(...cfg.deepColor) },
        uFoamColor: { value: new THREE.Vector3(...cfg.foamColor) },
        uAbsorptionCoeff: { value: cfg.absorptionCoeff },
        uFoamDepthThreshold: { value: cfg.foamDepthThreshold },
        uFoamCrestThreshold: { value: cfg.foamCrestThreshold },
        uChromaticOffset: { value: cfg.chromaticOffset },
      },
    });

    // ── Mesh ───────────────────────────────────────────────────────────────
    this.mesh = new THREE.Mesh(geometry, material);
    // The mesh sits at Y=0 in world space; the vertex shader adds uWaterLevel
    // to each vertex. This keeps the geometry centered for LOD/frustum purposes.
    this.mesh.frustumCulled = false;  // water is always visible if in the scene
    scene.add(this.mesh);

    // Store config for later use.
    this._waterLevel = cfg.waterLevel;
    this._rtResolutionScale = cfg.rtResolutionScale;

    // Pre-allocate reusable temporaries to avoid per-frame GC pressure.
    // These are mutated in update() and _updateReflectionCamera() -- never
    // expose them outside this instance.
    this._tmpSize = new THREE.Vector2();
    this._tmpLookDir = new THREE.Vector3();
    this._tmpTarget = new THREE.Vector3();
  }

  /**
   * Per-frame update: animate waves, render reflection/refraction, update uniforms.
   *
   * This method temporarily modifies scene state (clipping planes, water visibility)
   * and restores it before returning. It is NOT safe to call from within another
   * render pass (e.g., from within a custom render callback).
   *
   * @param {number} time - Elapsed time in seconds (monotonically increasing).
   * @param {THREE.WebGLRenderer} renderer - The active WebGL renderer.
   * @param {THREE.PerspectiveCamera} camera - The main scene camera.
   */
  update(time, renderer, camera) {
    if (this._disposed) return;

    const uniforms = this.mesh.material.uniforms;

    // ── Update time uniform ──────────────────────────────────────────────
    uniforms.uTime.value = time;
    uniforms.uCameraPosition.value.copy(camera.position);

    // ── Resize render targets if renderer size changed ───────────────────
    // Check against the current renderer size and resize RTs if needed.
    // This handles window resizes without requiring an explicit resize callback.
    // Reuse this._tmpSize to avoid per-frame allocation.
    const rendererSize = renderer.getSize(this._tmpSize);
    const rtWidth = Math.floor(rendererSize.x * this._rtResolutionScale);
    const rtHeight = Math.floor(rendererSize.y * this._rtResolutionScale);

    if (this._reflectionRT.width !== rtWidth || this._reflectionRT.height !== rtHeight) {
      this._reflectionRT.setSize(rtWidth, rtHeight);
      this._refractionRT.setSize(rtWidth, rtHeight);
      uniforms.uResolution.value.set(rendererSize.x, rendererSize.y);
    }

    // ── Save renderer state we're about to mutate ────────────────────────
    const originalRenderTarget = renderer.getRenderTarget();
    const originalClippingPlanes = renderer.clippingPlanes;
    const originalWaterVisible = this.mesh.visible;

    // ── Render reflection pass ───────────────────────────────────────────
    // Mirror the main camera across the water plane Y = waterLevel.
    this._updateReflectionCamera(camera);

    // Hide the water mesh to prevent self-reflection (infinite recursion).
    this.mesh.visible = false;

    // Enable clipping: only render geometry ABOVE the water plane.
    renderer.clippingPlanes = [this._reflectionClipPlane];
    renderer.setRenderTarget(this._reflectionRT);
    renderer.clear();
    renderer.render(this._scene, this._reflectionCamera);

    // ── Render refraction pass ───────────────────────────────────────────
    // Render the scene from the normal camera but clip everything above water,
    // showing only the underwater terrain.
    renderer.clippingPlanes = [this._refractionClipPlane];
    renderer.setRenderTarget(this._refractionRT);
    renderer.clear();
    renderer.render(this._scene, camera);

    // ── Restore renderer state ───────────────────────────────────────────
    this.mesh.visible = originalWaterVisible;
    renderer.clippingPlanes = originalClippingPlanes || [];
    renderer.setRenderTarget(originalRenderTarget);
  }

  /**
   * Mirror the main camera across the water plane for planar reflections.
   *
   * The reflection camera copies the main camera's projection and mirrors
   * its position and look direction across Y = waterLevel. This produces
   * a view as if standing on the other side of the water surface looking back.
   *
   * Math:
   *   reflected_y = 2 * waterLevel - camera_y
   *   The up vector's Y component is negated.
   *   The look target's Y component is similarly mirrored.
   *
   * @param {THREE.PerspectiveCamera} camera - The main scene camera.
   * @private
   */
  _updateReflectionCamera(camera) {
    const reflCam = this._reflectionCamera;

    // Copy projection parameters (fov, aspect, near, far).
    reflCam.projectionMatrix.copy(camera.projectionMatrix);
    reflCam.projectionMatrixInverse.copy(camera.projectionMatrixInverse);

    // Mirror position across the water plane.
    reflCam.position.copy(camera.position);
    reflCam.position.y = 2.0 * this._waterLevel - camera.position.y;

    // Mirror rotation: extract the camera's look-at target, mirror it, and look at it.
    // Reuse cached vectors to avoid per-frame allocations on this hot path.
    camera.getWorldDirection(this._tmpLookDir);

    // Mirror the look direction's Y component.
    this._tmpLookDir.y = -this._tmpLookDir.y;

    this._tmpTarget.addVectors(reflCam.position, this._tmpLookDir);
    reflCam.lookAt(this._tmpTarget);

    // Copy near/far for consistent depth behavior.
    reflCam.near = camera.near;
    reflCam.far = camera.far;
    reflCam.aspect = camera.aspect;
    reflCam.updateProjectionMatrix();
  }

  /**
   * Update the water level (Y position of the undisplaced surface).
   *
   * This adjusts:
   *   - The shader uniform (vertex displacement offset)
   *   - The clipping planes (for reflection/refraction)
   *
   * @param {number} level - New water level in world-space Y units.
   */
  setWaterLevel(level) {
    this._waterLevel = level;
    this.mesh.material.uniforms.uWaterLevel.value = level;

    // Update clipping planes to match new water level.
    // Reflection plane: clip below water -> normal (0,1,0), constant = -level
    //   meaning: dot((0,1,0), point) + (-level) >= 0 -> y >= level
    this._reflectionClipPlane.set(new THREE.Vector3(0, 1, 0), -level);
    // Refraction plane: clip above water -> normal (0,-1,0), constant = level
    //   meaning: dot((0,-1,0), point) + level >= 0 -> -y + level >= 0 -> y <= level
    this._refractionClipPlane.set(new THREE.Vector3(0, -1, 0), level);
  }

  /**
   * Release all GPU resources. Safe to call multiple times (idempotent).
   *
   * After dispose(), the mesh is removed from the scene and all WebGL resources
   * (geometry, material, render targets) are freed. The Water instance should not
   * be used after dispose().
   */
  dispose() {
    if (this._disposed) return;
    this._disposed = true;

    // Remove from scene.
    this._scene.remove(this.mesh);

    // Free GPU resources.
    this.mesh.geometry.dispose();
    this.mesh.material.dispose();
    this._reflectionRT.dispose();
    this._refractionRT.dispose();

    // Null out references to aid garbage collection.
    this.mesh = null;
    this._reflectionCamera = null;
    this._reflectionRT = null;
    this._refractionRT = null;
    this._tmpSize = null;
    this._tmpLookDir = null;
    this._tmpTarget = null;
  }
}
