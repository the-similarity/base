/**
 * PostProcessing — EffectComposer-based post-processing pipeline for the nature engine.
 *
 * Layered effects chain:
 *   RenderPass -> SSAO -> UnrealBloom -> ColorGrade -> Vignette -> FXAA -> OutputPass
 *
 * Three quality tiers control which passes are active:
 *   - low:    RenderPass + ColorGrade + FXAA
 *   - medium: RenderPass + SSAO (half-res) + Bloom + ColorGrade + FXAA
 *   - high:   RenderPass + SSAO (full)     + Bloom + ColorGrade + Vignette + FXAA
 *
 * Usage:
 *   const pp = new PostProcessing(renderer, scene, camera, { quality: 'high' });
 *   // in animation loop:
 *   pp.render();
 *   // on resize:
 *   pp.resize(window.innerWidth, window.innerHeight);
 *   // cleanup:
 *   pp.dispose();
 */

import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { SSAOPass } from 'three/addons/postprocessing/SSAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { FXAAShader } from 'three/addons/shaders/FXAAShader.js';

// ---------------------------------------------------------------------------
// Custom shader: Color Grading
// ---------------------------------------------------------------------------
// Applies four corrections in a single fragment pass:
//   1. Warm highlights — slight yellow shift on bright pixels
//   2. Cool shadows  — slight blue shift on dark pixels
//   3. Saturation boost (+10%)
//   4. Gentle S-curve contrast in luminance space
// All tuning knobs are compile-time constants so the GPU branch-predicts
// them away; no uniforms needed beyond the source texture and resolution.
// ---------------------------------------------------------------------------
const ColorGradeShader = {
  name: 'ColorGradeShader',
  uniforms: {
    tDiffuse: { value: null },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    varying vec2 vUv;

    // ---- tuning constants ----
    // Warm highlight tint: small yellow push on bright pixels.
    const vec3 WARM_TINT  = vec3(0.03, 0.02, -0.01);
    // Cool shadow tint: small blue push on dark pixels.
    const vec3 COOL_TINT  = vec3(-0.01, -0.005, 0.03);
    // Saturation multiplier — 1.1 = 10 % boost.
    const float SAT_BOOST = 1.1;
    // S-curve contrast strength. Higher = steeper mid-tone contrast.
    const float CONTRAST  = 1.05;

    // Smooth S-curve via a shifted smoothstep: f(x) = 3x^2 - 2x^3
    // mapped so 0 stays 0, 1 stays 1, mid-tones get compressed/expanded.
    float sCurve(float x) {
      // Bias toward 0.5 then apply smoothstep, then scale back.
      float shifted = clamp((x - 0.5) * CONTRAST + 0.5, 0.0, 1.0);
      return smoothstep(0.0, 1.0, shifted);
    }

    void main() {
      vec3 color = texture2D(tDiffuse, vUv).rgb;

      // 1. Compute perceptual luminance (Rec. 709 coefficients).
      float lum = dot(color, vec3(0.2126, 0.7152, 0.0722));

      // 2. Warm highlights / cool shadows — mix by luminance weight.
      //    Bright pixels (lum > 0.5) get warmed; dark pixels get cooled.
      color += WARM_TINT * smoothstep(0.4, 0.9, lum);
      color += COOL_TINT * (1.0 - smoothstep(0.1, 0.5, lum));

      // 3. Saturation boost — lerp toward/away from grey.
      vec3 grey = vec3(lum);
      color = mix(grey, color, SAT_BOOST);

      // 4. S-curve contrast per channel.
      color = vec3(sCurve(color.r), sCurve(color.g), sCurve(color.b));

      gl_FragColor = vec4(clamp(color, 0.0, 1.0), 1.0);
    }
  `,
};

// ---------------------------------------------------------------------------
// Custom shader: Vignette
// ---------------------------------------------------------------------------
// Darkens edges of the screen by 20-30 % with a smooth radial falloff.
// Uses a simple quadratic-ish curve: mix factor = 1 - smoothstep(inner, outer, dist).
// ---------------------------------------------------------------------------
const VignetteShader = {
  name: 'VignetteShader',
  uniforms: {
    tDiffuse: { value: null },
    // Darkness controls how much the edges dim (0 = none, 1 = full black).
    darkness: { value: 0.25 },
    // Offset controls how far from center the effect begins (0 = center, 1 = edge).
    offset: { value: 1.0 },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse;
    uniform float darkness;
    uniform float offset;
    varying vec2 vUv;

    void main() {
      vec3 color = texture2D(tDiffuse, vUv).rgb;

      // Distance from centre in UV space (0..~0.707 for corners).
      vec2 centred = vUv - 0.5;
      float dist = length(centred) * 2.0; // normalise so corners ~ 1.414

      // Smooth radial falloff: starts dimming at 'offset' radius,
      // reaches full darkness at ~1.4 (corner).
      float vignette = 1.0 - smoothstep(offset * 0.5, offset * 1.3, dist) * darkness;

      gl_FragColor = vec4(color * vignette, 1.0);
    }
  `,
};

// Reusable scratch vector to avoid allocating in hot paths (getSize, etc.).
const _scratchVec2 = new THREE.Vector2();

// ---------------------------------------------------------------------------
// Quality preset definitions
// ---------------------------------------------------------------------------
const QUALITY_PRESETS = {
  low: { ssao: false, bloom: false, colorGrade: true, vignette: false, fxaa: true },
  medium: { ssao: true, bloom: true, colorGrade: true, vignette: false, fxaa: true },
  high: { ssao: true, bloom: true, colorGrade: true, vignette: true, fxaa: true },
};

/**
 * PostProcessing — manages a full EffectComposer chain for the nature scene.
 *
 * Lifecycle:
 *   1. Construct with renderer, scene, camera.
 *   2. Call render() every frame (replaces renderer.render()).
 *   3. Call resize() on window resize.
 *   4. Call dispose() when tearing down the scene.
 *
 * Immutability notes:
 *   - The composer is rebuilt from scratch on setQuality() because
 *     EffectComposer does not support pass reordering after init.
 *   - Individual pass uniforms (bloom strength, SSAO radius, etc.)
 *     can be tweaked at runtime without rebuilding.
 */
export class PostProcessing {
  /**
   * @param {THREE.WebGLRenderer} renderer - The renderer whose output we wrap.
   * @param {THREE.Scene} scene - The scene graph to render.
   * @param {THREE.Camera} camera - The active camera.
   * @param {Object} [options={}] - Per-effect toggles and quality level.
   * @param {string} [options.quality='high'] - 'low' | 'medium' | 'high'.
   * @param {boolean} [options.ssao] - Override SSAO toggle (else from quality preset).
   * @param {boolean} [options.bloom] - Override bloom toggle.
   * @param {boolean} [options.colorGrade] - Override color grading toggle.
   * @param {boolean} [options.vignette] - Override vignette toggle.
   * @param {boolean} [options.fxaa] - Override FXAA toggle.
   */
  constructor(renderer, scene, camera, options = {}) {
    this._renderer = renderer;
    this._scene = scene;
    this._camera = camera;

    // Merge explicit boolean overrides on top of the quality preset.
    // Only keys present in the preset are considered; undefined options are ignored.
    this._quality = options.quality || 'high';
    const preset = QUALITY_PRESETS[this._quality];
    this._options = { ...preset };
    for (const key of Object.keys(preset)) {
      if (options[key] !== undefined) this._options[key] = options[key];
    }

    // Individual pass references for runtime tweaking and disposal.
    this._composer = null;
    this._ssaoPass = null;
    this._bloomPass = null;
    this._colorGradePass = null;
    this._vignettePass = null;
    this._fxaaPass = null;

    this._buildComposer();
  }

  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  /** Render one frame through the post-processing chain. */
  render() {
    this._composer.render();
  }

  /**
   * Handle viewport resize. Updates internal render targets and
   * resolution-dependent uniforms (FXAA pixel size, SSAO resolution).
   *
   * @param {number} width  - New viewport width in CSS pixels.
   * @param {number} height - New viewport height in CSS pixels.
   */
  resize(width, height) {
    // The pixel ratio matters — render targets must match the physical size.
    const pixelRatio = this._renderer.getPixelRatio();
    const w = Math.floor(width * pixelRatio);
    const h = Math.floor(height * pixelRatio);

    // EffectComposer.setSize() propagates to all passes (including SSAO and Bloom),
    // so we only need to manually update FXAA's resolution uniform afterward.
    this._composer.setSize(w, h);

    // FXAA needs 1/resolution for its kernel offsets.
    if (this._fxaaPass) {
      this._fxaaPass.material.uniforms['resolution'].value.set(1 / w, 1 / h);
    }
  }

  /**
   * Switch the quality tier at runtime. Tears down and rebuilds the
   * entire composer because EffectComposer does not support dynamic
   * pass insertion/removal.
   *
   * @param {'low'|'medium'|'high'} level
   */
  setQuality(level) {
    if (!QUALITY_PRESETS[level]) {
      console.warn(`PostProcessing: unknown quality level "${level}", ignoring.`);
      return;
    }
    this._quality = level;
    this._options = { ...QUALITY_PRESETS[level] };
    this._disposeComposer();
    this._buildComposer();
  }

  /** Release all GPU resources held by the composer and its passes. */
  dispose() {
    this._disposeComposer();
  }

  // -----------------------------------------------------------------------
  // Internal: composer construction
  // -----------------------------------------------------------------------

  /**
   * Build the EffectComposer and append passes according to this._options.
   *
   * Pass order matters for visual correctness:
   *   1. RenderPass   — rasterise the scene into the composer's write buffer.
   *   2. SSAOPass     — needs depth/normal from (1); writes darkened AO.
   *   3. UnrealBloom  — operates on bright fragments; must come before colour
   *                     grading so the grade does not artificially brighten.
   *   4. ColorGrade   — tint, saturation, contrast adjustments.
   *   5. Vignette     — screen-space effect, after grading so it dims the
   *                     final colour, not an intermediate.
   *   6. FXAA         — anti-aliasing on the final image before output.
   *   7. OutputPass   — gamma / tone-mapping blit to canvas.
   */
  _buildComposer() {
    const size = this._renderer.getSize(_scratchVec2);
    const pixelRatio = this._renderer.getPixelRatio();
    const w = Math.floor(size.x * pixelRatio);
    const h = Math.floor(size.y * pixelRatio);

    this._composer = new EffectComposer(this._renderer);

    // -- 1. Render pass (always present) --
    const renderPass = new RenderPass(this._scene, this._camera);
    this._composer.addPass(renderPass);

    // -- 2. SSAO --
    if (this._options.ssao) {
      // SSAOPass constructor: (scene, camera, width, height)
      // For "medium" quality we halve the internal resolution to save fill-rate.
      const ssaoScale = this._quality === 'medium' ? 0.5 : 1.0;
      const ssaoW = Math.floor(w * ssaoScale);
      const ssaoH = Math.floor(h * ssaoScale);

      this._ssaoPass = new SSAOPass(this._scene, this._camera, ssaoW, ssaoH);
      // Radius in world units — 0.5 gives subtle contact shadows under trees,
      // between rocks, in terrain crevices without halos.
      this._ssaoPass.kernelRadius = 0.5;
      // Min/max distance clamp to avoid self-occlusion on flat surfaces
      // and to ignore far-away geometry that cannot contribute AO.
      this._ssaoPass.minDistance = 0.001;
      this._ssaoPass.maxDistance = 0.1;
      this._ssaoPass.output = SSAOPass.OUTPUT.Default;
      this._composer.addPass(this._ssaoPass);
    }

    // -- 3. Bloom --
    if (this._options.bloom) {
      // UnrealBloomPass(resolution, strength, radius, threshold)
      // Strength 0.3 keeps the glow subtle — sun reflections on water and
      // snow highlights pop without the "everything glows" problem.
      this._bloomPass = new UnrealBloomPass(
        new THREE.Vector2(w, h),
        0.3,  // strength — intentionally low
        0.4,  // radius — how far bloom spreads
        0.85  // threshold — only the brightest fragments bloom
      );
      this._composer.addPass(this._bloomPass);
    }

    // -- 4. Color grading --
    if (this._options.colorGrade) {
      this._colorGradePass = new ShaderPass(ColorGradeShader);
      this._composer.addPass(this._colorGradePass);
    }

    // -- 5. Vignette --
    if (this._options.vignette) {
      this._vignettePass = new ShaderPass(VignetteShader);
      this._composer.addPass(this._vignettePass);
    }

    // -- 6. FXAA --
    if (this._options.fxaa) {
      this._fxaaPass = new ShaderPass(FXAAShader);
      this._fxaaPass.material.uniforms['resolution'].value.set(1 / w, 1 / h);
      this._composer.addPass(this._fxaaPass);
    }

    // -- 7. Output pass (tone mapping + gamma) --
    const outputPass = new OutputPass();
    this._composer.addPass(outputPass);
  }

  /** Dispose the composer and null out pass references. */
  _disposeComposer() {
    if (this._composer) {
      // EffectComposer.dispose() releases its internal render targets.
      // Individual passes that own resources (SSAO, Bloom) also get disposed
      // because the composer iterates its pass list.
      this._composer.dispose();
    }
    this._composer = null;
    this._ssaoPass = null;
    this._bloomPass = null;
    this._colorGradePass = null;
    this._vignettePass = null;
    this._fxaaPass = null;
  }
}
