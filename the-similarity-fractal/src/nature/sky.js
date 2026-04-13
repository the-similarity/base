/**
 * Procedural sky dome with sun disc, glow halo, gradient atmosphere, and
 * animated fractal clouds. Everything is generated from noise in a single
 * ShaderMaterial — no textures are loaded.
 *
 * Architecture:
 * - A large inverted sphere (BackSide) wraps the entire scene.
 * - The fragment shader computes sky color per-pixel from view direction.
 * - Clouds use 2D simplex noise at 3 self-similar octaves, scrolled by time.
 * - The sun is a sharp bright disc + soft glow halo.
 *
 * Lifecycle:
 * - Construct once, add to scene BEFORE terrain so it renders as background.
 * - Call update(time) every frame to animate cloud scrolling.
 * - Call setSunPosition() to move the sun (affects gradient + lighting).
 * - Call dispose() to clean up GPU resources.
 *
 * Performance notes:
 * - Radius 500 keeps the dome well outside any terrain geometry (scale ~10)
 *   but is small enough to stay within default camera far plane (~1000).
 * - Fragment shader is the bottleneck: 3-octave noise + sun disc + gradient.
 *   At typical resolutions this is well within budget for a background pass.
 */

import * as THREE from 'three';

// ── GLSL simplex noise ──────────────────────────────────────────────────────
// Classic Ashima 2D simplex noise, inlined so every nature module can embed
// the same function without runtime dependencies. ~60 lines of pure math.
// This is the standard implementation used across all nature shaders.
const SIMPLEX_NOISE_GLSL = /* glsl */ `
  // Modulo 289 without a division (only multiplications and subtractions).
  // Works because 289 = 17*17, and the bit pattern of 1/289 in float has
  // enough precision for values < 289^2.
  vec3 mod289_3(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec2 mod289_2(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }

  // Permutation polynomial: ((x * 34.0) + 10.0) * x mod 289.
  // This is a hash function that distributes values pseudo-randomly.
  vec3 permute(vec3 x) { return mod289_3(((x * 34.0) + 10.0) * x); }

  // 2D simplex noise: returns a value in approximately [-1, 1].
  //
  // The simplex grid tiles the plane with equilateral triangles (2 per
  // square in the skewed coordinate system). Each evaluation:
  // 1. Skews the input point into simplex space to find which triangle.
  // 2. Computes distances to the triangle's 3 corners.
  // 3. Hashes each corner to get a pseudo-random gradient.
  // 4. Sums radially-attenuated dot products of gradients and offsets.
  float snoise(vec2 v) {
    // Skew constants for 2D simplex:
    // F = (sqrt(3) - 1) / 2 = 0.3660...  (skew into simplex space)
    // G = (3 - sqrt(3)) / 6 = 0.2113...  (unskew back to Cartesian)
    const vec4 C = vec4(
      0.211324865405187,   // (3.0 - sqrt(3.0)) / 6.0
      0.366025403784439,   // 0.5 * (sqrt(3.0) - 1.0)
     -0.577350269189626,   // -1.0 + 2.0 * C.x
      0.024390243902439    // 1.0 / 41.0
    );

    // Skew the input point and find which simplex cell we are in.
    vec2 i = floor(v + dot(v, C.yy));
    // Unskew the cell origin back to Cartesian space.
    vec2 x0 = v - i + dot(i, C.xx);

    // Determine which simplex triangle (lower or upper) the point falls in.
    // In 2D, the simplex is a triangle. The two possible triangles within
    // the skewed unit square are distinguished by comparing x0.x vs x0.y.
    vec2 i1;
    i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);

    // Offsets for the other two corners of the simplex triangle.
    // x1 = x0 - i1 + C.xx  (offset from second corner)
    // x2 = x0 - 1.0 + 2.0 * C.xx = x0 + C.zz  (offset from third corner)
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;

    // Wrap cell coordinates to [0, 289) for the permutation hash.
    i = mod289_2(i);

    // Compute hash values for the 3 simplex corners.
    vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));

    // Map hashed values to 2D gradients using a ring of radius sqrt(0.5).
    // The fract/floor trick gives us 7 uniformly-spaced gradient directions.
    vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
    m = m * m;
    m = m * m;

    // Extract gradient directions from hash.
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;

    // Normalize gradients implicitly by scaling (approximation that avoids
    // a true normalize per corner — good enough for noise quality).
    m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);

    // Compute the dot product of each gradient with its offset vector.
    vec3 g;
    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;

    // Scale output to approximately [-1, 1].
    return 130.0 * dot(m, g);
  }
`;

// ── Sky vertex shader ───────────────────────────────────────────────────────
// Passes world-space position to the fragment shader for direction-based
// coloring. The sky sphere is centered at the camera (no parallax), so
// we only need direction, not distance.
const SKY_VERTEX_SHADER = /* glsl */ `
  varying vec3 vWorldPosition;

  void main() {
    // Transform vertex to world space for direction computation in fragment.
    vec4 worldPos = modelMatrix * vec4(position, 1.0);
    vWorldPosition = worldPos.xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

// ── Sky fragment shader ─────────────────────────────────────────────────────
// Computes the final sky color from:
// 1. Vertical gradient (zenith to horizon to below-horizon)
// 2. Sun disc and glow halo
// 3. Animated fractal clouds (3-octave simplex noise)
const SKY_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uSunDirection;
  uniform float uTime;
  uniform float uCloudDensity;

  varying vec3 vWorldPosition;

  ${SIMPLEX_NOISE_GLSL}

  /**
   * Fractal Brownian Motion with 3 self-similar octaves.
   *
   * Each octave doubles the frequency (lacunarity = 2.0) and halves the
   * amplitude (gain = 0.5). This produces clouds with large billowy shapes
   * from octave 1, medium detail from octave 2, and fine wisps from octave 3.
   *
   * The 3-octave choice balances visual quality against fragment cost.
   */
  float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    // Each octave uses the same snoise function at increasing scale.
    // This self-similarity is what makes the result look "natural."
    for (int i = 0; i < 3; i++) {
      value += amplitude * snoise(p);
      p *= 2.0;          // lacunarity: double the frequency
      amplitude *= 0.5;  // gain: halve the contribution
    }
    return value;
  }

  void main() {
    // Normalize the world position to get a pure direction vector.
    // All sky coloring is direction-based — distance is irrelevant.
    vec3 viewDir = normalize(vWorldPosition);

    // ── 1. Sky gradient ──────────────────────────────────────────────────
    // Vertical blend factor: 0 at horizon, 1 at zenith, negative below.
    float elevation = dot(viewDir, vec3(0.0, 1.0, 0.0));

    // Smoothstep creates a gradual transition from horizon haze to zenith blue.
    // The 0.0..0.4 range means the transition occupies the lower ~40% of the sky.
    float skyBlend = smoothstep(0.0, 0.4, elevation);

    // Zenith: deep blue sky.
    vec3 zenithColor = vec3(0.15, 0.3, 0.7);
    // Horizon: warm haze (atmospheric scattering makes horizons warm/bright).
    vec3 horizonColor = vec3(0.7, 0.6, 0.5);
    // Below horizon: fade to a terrain-matching earth tone.
    vec3 groundColor = vec3(0.25, 0.22, 0.18);

    // Compose the gradient: ground below, haze at horizon, blue at zenith.
    vec3 skyColor;
    if (elevation < 0.0) {
      // Below horizon: blend from horizon haze to ground color.
      float groundBlend = smoothstep(0.0, -0.3, elevation);
      skyColor = mix(horizonColor, groundColor, groundBlend);
    } else {
      skyColor = mix(horizonColor, zenithColor, skyBlend);
    }

    // ── 2. Sun disc + glow ───────────────────────────────────────────────
    // The sun is rendered as two additive components:
    // - A sharp bright disc (exponent 256 = very tight falloff)
    // - A soft atmospheric glow halo (exponent 8 = wide falloff)
    vec3 sunDir = normalize(uSunDirection);
    float sunDot = max(dot(viewDir, sunDir), 0.0);

    // Sharp disc: pow(x, 256) creates an extremely tight bright spot.
    // Only pixels very close to the sun direction get any contribution.
    float sunDisc = pow(sunDot, 256.0);

    // Soft glow: pow(x, 8) creates a wide warm halo around the sun.
    // This simulates forward-scattering in the atmosphere (Mie scattering).
    float sunGlow = pow(sunDot, 8.0);

    // Sun color: warm white, slightly yellow. The glow is dimmer and warmer.
    vec3 sunColor = vec3(1.0, 0.95, 0.8);
    skyColor += sunDisc * sunColor * 2.0;
    skyColor += sunGlow * sunColor * 0.3;

    // ── 3. Clouds ────────────────────────────────────────────────────────
    // Clouds are only rendered in the upper hemisphere (elevation > 0).
    // We project the view direction onto a flat plane at a fixed virtual
    // altitude to get 2D UV coordinates for the noise lookup.
    if (elevation > 0.0) {
      // Project onto a virtual cloud plane. The division by max(elevation, 0.1)
      // maps near-zenith views to the cloud center and near-horizon views to
      // the cloud edges, creating a natural dome-like perspective.
      vec2 cloudUV = viewDir.xz / max(elevation, 0.1);

      // Scale controls the apparent size of cloud formations.
      // Smaller scale = larger, more billowy clouds.
      cloudUV *= 0.3;

      // Animate: scroll clouds slowly eastward by adding time offset.
      // The 0.01 rate gives gentle drift that is visible but not distracting.
      cloudUV.x += uTime * 0.01;

      // Evaluate fractal noise to get raw cloud density.
      float noise = fbm(cloudUV);

      // Map noise to cloud density with defined edges.
      // smoothstep(0.4, 0.6, ...) clips low noise to zero (clear sky) and
      // creates soft edges around the 0.4..0.6 transition band.
      // The uCloudDensity uniform shifts the threshold: higher = more clouds.
      float cloudThreshold = 0.4 - (uCloudDensity - 0.5) * 0.3;
      float cloud = smoothstep(cloudThreshold, cloudThreshold + 0.2, noise);

      // Cloud color: white on top (sun-lit side), slightly darker underneath.
      // The fake lighting darkens clouds more near the horizon where we are
      // viewing them from below, and keeps them bright near zenith.
      vec3 cloudColorBright = vec3(1.0, 1.0, 1.0);
      vec3 cloudColorDark = vec3(0.7, 0.7, 0.75);
      float lightFactor = smoothstep(0.0, 0.5, elevation);
      vec3 cloudCol = mix(cloudColorDark, cloudColorBright, lightFactor);

      // Blend clouds into sky. Clouds near the horizon fade out to avoid
      // a hard cutoff line.
      float horizonFade = smoothstep(0.0, 0.15, elevation);
      skyColor = mix(skyColor, cloudCol, cloud * horizonFade);
    }

    gl_FragColor = vec4(skyColor, 1.0);
  }
`;


/**
 * Procedural sky dome.
 *
 * Creates an inverted sphere with a custom ShaderMaterial that renders a
 * gradient sky, sun disc, glow halo, and animated fractal clouds entirely
 * in the fragment shader.
 *
 * Usage:
 *   const sky = new ProceduralSky(scene);
 *   // in animation loop:
 *   sky.update(elapsedTime);
 *   // cleanup:
 *   sky.dispose();
 *
 * Mutability:
 * - Sun position is mutable via setSunPosition().
 * - Cloud density is mutable via options at construction and internally.
 * - The mesh itself (geometry, material) is immutable after construction.
 *
 * Scene integration:
 * - The sky sphere must be added BEFORE terrain so it renders as background.
 * - depthWrite is disabled so terrain always renders on top.
 * - side: BackSide means the camera is inside the sphere looking outward.
 */
export class ProceduralSky {
  /**
   * @param {THREE.Scene} scene - The scene to add the sky dome to.
   * @param {Object} options
   * @param {THREE.Vector3} [options.sunPosition] - Initial sun direction vector.
   *   Defaults to upper-right: (1, 0.6, 0.5). Does not need to be normalized.
   * @param {number} [options.cloudDensity=0.5] - Cloud coverage 0..1.
   *   0 = clear sky, 1 = overcast.
   * @param {number} [options.radius=500] - Sky sphere radius. Must be large
   *   enough to enclose all scene geometry but smaller than camera far plane.
   */
  constructor(scene, options = {}) {
    this._scene = scene;

    // Default sun position: upper right, roughly 35 degrees above horizon.
    // Not normalized here — the shader normalizes it.
    const sunPos = options.sunPosition || new THREE.Vector3(1, 0.6, 0.5);
    const cloudDensity = options.cloudDensity !== undefined ? options.cloudDensity : 0.5;

    // Sky sphere radius. 500 is a safe default:
    // - terrain world scale is ~10, so 500 is well outside all geometry.
    // - default camera far plane is typically 1000, so 500 stays visible.
    const radius = options.radius || 500;

    // Shader uniforms bridge JS state into GLSL.
    // These are the only mutable connection points between CPU and GPU.
    this._uniforms = {
      uSunDirection: { value: sunPos.clone() },
      uTime: { value: 0.0 },
      uCloudDensity: { value: cloudDensity },
    };

    // Geometry: sphere with inverted normals (BackSide rendering).
    // 32 segments is enough for a smooth dome at this radius — the visual
    // detail comes from the shader, not the geometry.
    const geometry = new THREE.SphereGeometry(radius, 32, 32);

    const material = new THREE.ShaderMaterial({
      vertexShader: SKY_VERTEX_SHADER,
      fragmentShader: SKY_FRAGMENT_SHADER,
      uniforms: this._uniforms,
      side: THREE.BackSide,    // Camera is inside the sphere.
      depthWrite: false,       // Sky never occludes other geometry.
    });

    this._mesh = new THREE.Mesh(geometry, material);

    // renderOrder -1 ensures the sky draws before all other scene objects,
    // functioning as a true background pass.
    this._mesh.renderOrder = -1;

    // The camera is always inside the sky sphere, so it always passes the
    // frustum test. Disabling the check skips one bounding-sphere computation
    // per frame — trivial but free.
    this._mesh.frustumCulled = false;

    scene.add(this._mesh);
  }

  /**
   * Advance cloud animation.
   *
   * Call once per frame with the elapsed time (in seconds) since the scene
   * started. Cloud positions scroll linearly with time.
   *
   * @param {number} time - Elapsed seconds since scene start.
   */
  update(time) {
    this._uniforms.uTime.value = time;
  }

  /**
   * Reposition the sun.
   *
   * The vector does not need to be normalized — the shader normalizes it.
   * Moving the sun changes the gradient tint (via the glow halo) and the
   * bright disc position.
   *
   * @param {number} x
   * @param {number} y
   * @param {number} z
   */
  setSunPosition(x, y, z) {
    this._uniforms.uSunDirection.value.set(x, y, z);
  }

  /**
   * Release GPU resources.
   *
   * Removes the mesh from the scene and disposes geometry + material.
   * After calling dispose(), this instance must not be used.
   */
  dispose() {
    this._scene.remove(this._mesh);
    this._mesh.geometry.dispose();
    this._mesh.material.dispose();
    this._mesh = null;
  }
}
