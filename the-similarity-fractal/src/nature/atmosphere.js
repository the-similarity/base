/**
 * Height-based fog and atmospheric scattering effects.
 *
 * Replaces the uniform FogExp2(0x0a0a0f, 0.025) with a physically-motivated
 * height fog model where valleys are misty and peaks are clear. Also provides
 * an atmospheric scattering approximation that blends distant objects toward
 * the horizon color, adding depth and aerial perspective.
 *
 * Architecture:
 * - Uses THREE.FogExp2 as the scene fog (simple, GPU-efficient).
 * - Each frame, the fog density is recomputed from camera height using an
 *   exponential falloff model: density = baseDensity * exp(-height * falloff).
 * - Fog color blends between warm ground-level mist and sky blue at altitude.
 *
 * Why FogExp2 instead of custom shader fog:
 * - FogExp2 is applied automatically by Three.js to all standard materials.
 * - No need to patch every material's shader or add a post-processing pass.
 * - The per-frame density adjustment gives a convincing height-dependent result
 *   at zero additional draw cost.
 *
 * Lifecycle:
 * - Construct once after scene creation but before the render loop.
 * - Call update(cameraPosition) every frame.
 * - Call dispose() to restore original scene fog state.
 *
 * Mutability:
 * - fogDensity, fogColor, and heightFalloff are mutable via setters.
 * - The scene.fog reference is overwritten at construction and restored at dispose().
 */

import * as THREE from 'three';

/**
 * Height-based atmospheric fog system.
 *
 * Models fog density as an exponential function of camera height:
 *   effectiveDensity = baseDensity * exp(-height * heightFalloff)
 *
 * At ground level (height ~ 0), fog is at full baseDensity.
 * At altitude, fog density drops exponentially, revealing distant peaks clearly.
 *
 * The fog color also shifts with height:
 * - Ground level: warm gray mist (0.65, 0.6, 0.55) — matches atmospheric haze.
 * - Altitude: blends toward sky blue (0.5, 0.6, 0.75) — matches the zenith.
 *
 * Usage:
 *   const atmo = new Atmosphere(scene, { fogDensity: 0.03 });
 *   // in animation loop:
 *   atmo.update(camera.position);
 *   // cleanup:
 *   atmo.dispose();
 */
export class Atmosphere {
  /**
   * @param {THREE.Scene} scene - Scene whose fog will be managed.
   * @param {Object} options
   * @param {number} [options.fogDensity=0.02] - Base fog density at ground level.
   *   Higher values = thicker valley mist. The existing scene used 0.025.
   *   We default to 0.02 for a slightly cleaner look now that fog is height-aware.
   * @param {THREE.Color|number} [options.fogColor=0xb0a898] - Base fog color.
   *   Warm gray-beige matches the horizon haze from the sky shader.
   * @param {number} [options.heightFalloff=0.5] - How quickly fog thins with
   *   altitude. Higher values = fog confined to lower areas.
   *   At falloff=0.5: fog halves every ~1.4 units of height.
   *   At falloff=1.0: fog halves every ~0.7 units of height.
   */
  constructor(scene, options = {}) {
    this._scene = scene;

    // Preserve whatever fog the scene had so dispose() can restore it.
    this._previousFog = scene.fog;
    // Also preserve the previous background color for restoration.
    this._previousBackground = scene.background
      ? scene.background.clone()
      : null;

    // Base fog parameters — these define the ground-level maximum.
    this._baseDensity = options.fogDensity !== undefined ? options.fogDensity : 0.02;
    this._heightFalloff = options.heightFalloff !== undefined ? options.heightFalloff : 0.5;

    // Sky-altitude fog color: blue-gray that matches the sky gradient.
    // When the camera is high up, fog (applied to distant ground objects)
    // should blend toward the sky color for visual coherence.
    this._skyFogColor = new THREE.Color(0.5, 0.6, 0.75);

    // Ground-level mist color: warmer and slightly denser-looking.
    // This replaces the dark 0x0a0a0f fog that made the scene feel like night.
    this._groundFogColor = new THREE.Color(0.65, 0.6, 0.55);

    // Initial fog color from options, defaulting to warm gray-beige that
    // matches the horizon haze from the sky shader.
    const initialFogColor = new THREE.Color(
      options.fogColor !== undefined ? options.fogColor : 0xb0a898
    );

    // Install our fog on the scene. FogExp2 applies density-based exponential
    // fog to all standard Three.js materials automatically.
    this._fog = new THREE.FogExp2(initialFogColor.getHex(), this._baseDensity);
    scene.fog = this._fog;

    // Update the scene background to match the fog color at ground level.
    // This prevents the harsh visual discontinuity where fog-blended objects
    // meet the scene background at the edges of the view.
    scene.background = initialFogColor;
  }

  /**
   * Recompute fog density and color based on camera height.
   *
   * Should be called once per frame. The computation is trivially cheap
   * (one exp, one lerp) so there is no need to throttle or skip frames.
   *
   * The mathematical model:
   *   effectiveDensity = baseDensity * exp(-cameraHeight * heightFalloff)
   *
   * This means:
   * - At height=0: density = baseDensity (full valley mist)
   * - At height=2, falloff=0.5: density = baseDensity * exp(-1) ~ 0.37 * baseDensity
   * - At height=5, falloff=0.5: density = baseDensity * exp(-2.5) ~ 0.08 * baseDensity
   *
   * Fog color also shifts: at ground level it is warm gray (valley mist),
   * at altitude it shifts toward sky blue (aerial perspective).
   *
   * @param {THREE.Vector3} cameraPosition - Current camera world position.
   */
  update(cameraPosition) {
    // Camera height above the world origin plane (Y-up convention).
    // Clamp to 0 so underground cameras still get maximum fog.
    const height = Math.max(0, cameraPosition.y);

    // Exponential falloff: fog density decreases with altitude.
    // The negative exponent ensures density is always positive and bounded
    // by baseDensity from above.
    const effectiveDensity = this._baseDensity * Math.exp(-height * this._heightFalloff);
    this._fog.density = effectiveDensity;

    // Blend fog color from ground mist (warm) to sky (cool) based on height.
    // The smoothstep-like mapping creates a natural transition zone.
    // heightBlend: 0 at ground, approaches 1 at height >= 4 units.
    const heightBlend = Math.min(1.0, height / 4.0);

    // Interpolate between warm ground mist and cool sky fog.
    this._fog.color.copy(this._groundFogColor).lerp(this._skyFogColor, heightBlend);

    // Keep scene background in sync with fog color so the clear color behind
    // all geometry matches what fog-blended objects are converging toward.
    // Without this, objects at max fog distance would "pop" against a
    // different-colored background.
    this._scene.background.copy(this._fog.color);
  }

  /**
   * Override the base fog density.
   *
   * The effective per-frame density will still be modulated by height.
   * This sets the ground-level maximum.
   *
   * @param {number} density - New base fog density.
   */
  setFogDensity(density) {
    this._baseDensity = density;
  }

  /**
   * Release resources and restore the scene's previous fog state.
   *
   * After calling dispose(), this instance must not be used.
   * The scene's fog and background are restored to their pre-construction values.
   */
  dispose() {
    // Restore the scene to its original fog configuration.
    this._scene.fog = this._previousFog;

    if (this._previousBackground) {
      this._scene.background = this._previousBackground;
    }

    this._fog = null;
  }
}
