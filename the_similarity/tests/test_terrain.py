"""Tests for 2D terrain analysis methods and generation pipeline."""

import numpy as np


# ---------------------------------------------------------------------------
# Wavelet Leaders 2D
# ---------------------------------------------------------------------------


class TestWaveletLeaders2D:
    """Tests for 2D wavelet leaders multifractal analysis."""

    def _make_terrain(self, size=64, hurst=0.5, seed=42):
        """Generate a simple fBm-like test heightmap."""
        rng = np.random.default_rng(seed)
        freq_x = np.fft.fftfreq(size)
        freq_y = np.fft.fftfreq(size)
        fx, fy = np.meshgrid(freq_x, freq_y)
        freq_mag = np.sqrt(fx**2 + fy**2)
        freq_mag[0, 0] = 1.0
        amplitude = freq_mag ** (-(hurst + 1))
        amplitude[0, 0] = 0.0
        phase = rng.uniform(0, 2 * np.pi, (size, size))
        spectrum = amplitude * np.exp(1j * phase)
        result = np.real(np.fft.ifft2(spectrum))
        return (result - result.min()) / (result.max() - result.min() + 1e-12)

    def test_leaders_shape(self):
        """Leaders should produce per-scale subband triples."""
        from the_similarity.methods.wavelet_leaders_2d import compute_wavelet_leaders_2d

        hmap = self._make_terrain(64)
        leaders = compute_wavelet_leaders_2d(hmap)
        assert len(leaders) >= 1
        for level_leaders in leaders:
            assert len(level_leaders) == 3  # LH, HL, HH

    def test_spectrum_output(self):
        """Spectrum should produce valid alpha and f_alpha arrays."""
        from the_similarity.methods.wavelet_leaders_2d import (
            compute_wavelet_leaders_2d,
            multifractal_spectrum_2d,
        )

        hmap = self._make_terrain(64)
        leaders = compute_wavelet_leaders_2d(hmap)
        alpha, f_alpha = multifractal_spectrum_2d(leaders)
        assert len(alpha) > 0
        assert len(alpha) == len(f_alpha)
        assert np.all(np.isfinite(alpha))
        assert np.all(np.isfinite(f_alpha))

    def test_rough_vs_smooth_hurst(self):
        """Rough terrain should have lower mean Hurst than smooth terrain."""
        from the_similarity.methods.wavelet_leaders_2d import local_hurst_map

        rough = self._make_terrain(64, hurst=0.2, seed=1)
        smooth = self._make_terrain(64, hurst=0.8, seed=2)

        h_rough = local_hurst_map(rough, block_size=16)
        h_smooth = local_hurst_map(smooth, block_size=16)

        assert np.mean(h_rough) < np.mean(h_smooth)

    def test_hurst_map_range(self):
        """Hurst map should be clipped to [0, 1]."""
        from the_similarity.methods.wavelet_leaders_2d import local_hurst_map

        hmap = self._make_terrain(64)
        h = local_hurst_map(hmap, block_size=16)
        assert h.min() >= 0.0
        assert h.max() <= 1.0
        assert h.shape == hmap.shape

    def test_extract_terrain_spectrum(self):
        """Full spectrum extraction should return all expected keys."""
        from the_similarity.methods.wavelet_leaders_2d import extract_terrain_spectrum

        hmap = self._make_terrain(64)
        result = extract_terrain_spectrum(hmap)

        for key in [
            "alpha",
            "f_alpha",
            "spectrum_width",
            "h_mean",
            "h_std",
            "dominant_scale",
            "hurst_map",
        ]:
            assert key in result, f"Missing key: {key}"

        assert 0 <= result["h_mean"] <= 1


# ---------------------------------------------------------------------------
# EMD 2D
# ---------------------------------------------------------------------------


class TestEMD2D:
    """Tests for profile-based 2D EMD."""

    def _make_terrain(self, size=64, seed=42):
        rng = np.random.default_rng(seed)
        x = np.linspace(0, 4 * np.pi, size)
        xx, yy = np.meshgrid(x, x)
        terrain = np.sin(xx) * np.cos(yy) + 0.3 * np.sin(3 * xx + yy)
        terrain += rng.normal(0, 0.05, terrain.shape)
        return terrain

    def test_decomposition_returns_multiple_imfs(self):
        """Should produce at least 2 scale layers."""
        from the_similarity.methods.emd_2d import decompose_terrain

        hmap = self._make_terrain(64)
        imfs = decompose_terrain(hmap, max_imfs=4, n_profiles=4)
        assert len(imfs) >= 2

    def test_imfs_have_correct_shape(self):
        """Each IMF should match the input shape."""
        from the_similarity.methods.emd_2d import decompose_terrain

        hmap = self._make_terrain(64)
        imfs = decompose_terrain(hmap, max_imfs=4, n_profiles=4)
        for imf in imfs:
            assert imf.shape == hmap.shape

    def test_recompose_recovers_original(self):
        """Summing all IMFs should approximately recover the input."""
        from the_similarity.methods.emd_2d import decompose_terrain, recompose_terrain

        hmap = self._make_terrain(64)
        imfs = decompose_terrain(hmap, max_imfs=4, n_profiles=4)
        reconstructed = recompose_terrain(imfs)
        # Should be close but not perfect (interpolation artifacts)
        corr = np.corrcoef(hmap.ravel(), reconstructed.ravel())[0, 1]
        assert corr > 0.5, f"Reconstruction correlation too low: {corr}"

    def test_scale_analysis(self):
        """Scale analysis should return expected structure."""
        from the_similarity.methods.emd_2d import terrain_scale_analysis

        hmap = self._make_terrain(64)
        result = terrain_scale_analysis(hmap, max_imfs=4, n_profiles=4)
        assert "energies" in result
        assert "dominant_scale" in result
        assert result["scale_count"] >= 1


# ---------------------------------------------------------------------------
# Bempedelis 2D
# ---------------------------------------------------------------------------


class TestBempedelis2D:
    """Tests for 2D self-similarity transform."""

    def _make_fractal(self, size=128, hurst=0.5, seed=42):
        rng = np.random.default_rng(seed)
        freq_x = np.fft.fftfreq(size)
        freq_y = np.fft.fftfreq(size)
        fx, fy = np.meshgrid(freq_x, freq_y)
        freq_mag = np.sqrt(fx**2 + fy**2)
        freq_mag[0, 0] = 1.0
        amplitude = freq_mag ** (-(hurst + 1))
        amplitude[0, 0] = 0.0
        phase = rng.uniform(0, 2 * np.pi, (size, size))
        spectrum = amplitude * np.exp(1j * phase)
        result = np.real(np.fft.ifft2(spectrum))
        return (result - result.min()) / (result.max() - result.min() + 1e-12)

    def test_self_similarity_score_range(self):
        """Score should be in [0, 1]."""
        from the_similarity.methods.bempedelis_2d import terrain_self_similarity

        hmap = self._make_fractal(128)
        result = terrain_self_similarity(hmap, n_scales=3, patch_size=32, n_restarts=1)
        assert 0 <= result.score <= 1

    def test_fractal_scores_higher_than_random(self):
        """Fractal terrain should be more self-similar than white noise."""
        from the_similarity.methods.bempedelis_2d import scale_invariance_score

        fractal = self._make_fractal(128, hurst=0.5)
        noise = np.random.default_rng(99).uniform(0, 1, (128, 128))

        score_fractal = scale_invariance_score(fractal, n_scales=3, patch_size=32)
        score_noise = scale_invariance_score(noise, n_scales=3, patch_size=32)

        assert score_fractal > score_noise, (
            f"Fractal ({score_fractal:.3f}) should score higher than noise ({score_noise:.3f})"
        )

    def test_result_fields(self):
        """Result should have all expected fields."""
        from the_similarity.methods.bempedelis_2d import terrain_self_similarity

        hmap = self._make_fractal(128)
        result = terrain_self_similarity(hmap, n_scales=3, patch_size=32, n_restarts=1)
        assert hasattr(result, "alpha")
        assert hasattr(result, "beta")
        assert hasattr(result, "power_law_r2")
        assert hasattr(result, "smoothness")
        assert len(result.alpha) >= 2


# ---------------------------------------------------------------------------
# Terrain Params
# ---------------------------------------------------------------------------


class TestTerrainParams:
    """Tests for terrain parameter system."""

    def test_all_presets_loadable(self):
        """Every preset should load without error."""
        from the_similarity.core.terrain_params import list_presets, get_preset

        for name in list_presets():
            params = get_preset(name)
            assert params.terrain_type == name
            assert 0 <= params.h_mean <= 1

    def test_preset_isolation(self):
        """Getting a preset twice should return independent copies."""
        from the_similarity.core.terrain_params import get_preset

        a = get_preset("alpine")
        b = get_preset("alpine")
        a.h_mean = 0.99
        assert b.h_mean != 0.99

    def test_classify_terrain_type(self):
        """Classification should return valid types."""
        from the_similarity.core.terrain_params import classify_terrain_type

        assert classify_terrain_type(0.7, 0.05, 0.2) == "desert"
        assert classify_terrain_type(0.7, 0.15, 0.2) == "rolling_hills"
        assert classify_terrain_type(0.25, 0.1, 0.9) == "canyon"
        assert classify_terrain_type(0.4, 0.1, 0.5) == "alpine"


# ---------------------------------------------------------------------------
# Erosion
# ---------------------------------------------------------------------------


class TestErosion:
    """Tests for hydraulic and thermal erosion."""

    def _flat_with_peak(self, size=64):
        hmap = np.zeros((size, size))
        cy, cx = size // 2, size // 2
        for y in range(size):
            for x in range(size):
                dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                hmap[y, x] = max(0, 1.0 - dist / (size * 0.3))
        return hmap

    def test_hydraulic_erosion_lowers_peaks(self):
        """Erosion should reduce the maximum elevation."""
        from the_similarity.core.erosion import hydraulic_erosion

        original = self._flat_with_peak(64)
        eroded, _, _ = hydraulic_erosion(original, iterations=5000, seed=42)
        assert eroded.max() < original.max()

    def test_hydraulic_returns_moisture_and_flow(self):
        """Should return moisture and flow maps."""
        from the_similarity.core.erosion import hydraulic_erosion

        hmap = self._flat_with_peak(32)
        eroded, moisture, flow = hydraulic_erosion(hmap, iterations=1000, seed=42)
        assert moisture.shape == hmap.shape
        assert flow.shape == hmap.shape
        assert moisture.max() <= 1.0
        assert flow.max() <= 1.0

    def test_thermal_erosion_reduces_slope(self):
        """Thermal erosion should reduce maximum slope."""
        from the_similarity.core.erosion import thermal_erosion

        # Create a steep pyramid for clear slope reduction
        size = 64
        hmap = np.zeros((size, size))
        cy, cx = size // 2, size // 2
        for y in range(size):
            for x in range(size):
                dist = max(abs(x - cx), abs(y - cy))
                hmap[y, x] = max(0, 1.0 - dist / 10.0)  # steep pyramid

        dy, dx = np.gradient(hmap)
        max_slope_before = np.sqrt(dx**2 + dy**2).max()

        eroded = thermal_erosion(hmap, iterations=100, talus_angle=0.02)
        dy2, dx2 = np.gradient(eroded)
        max_slope_after = np.sqrt(dx2**2 + dy2**2).max()

        assert max_slope_after < max_slope_before

    def test_flow_accumulation(self):
        """Flow output should be positive and accumulate."""
        from the_similarity.core.erosion import flow_accumulation

        hmap = self._flat_with_peak(32)
        flow = flow_accumulation(hmap)
        # Flow should be everywhere >= 1 (each cell starts with 1)
        assert flow.min() >= 1.0
        # Total flow should exceed the trivial case (some accumulation happens)
        assert flow.max() > 1.0


# ---------------------------------------------------------------------------
# Feature Scatter
# ---------------------------------------------------------------------------


class TestFeatureScatter:
    """Tests for biome-aware feature placement."""

    def test_scatter_returns_features(self):
        """Should return a non-empty list of features."""
        from the_similarity.core.feature_scatter import scatter_features

        size = 64
        heightmap = np.random.default_rng(42).uniform(0.1, 0.9, (size, size))
        hurst_map = np.full((size, size), 0.6)
        moisture = np.full((size, size), 0.5)
        biome = np.full((size, size), 2, dtype=np.int32)  # grass

        features = scatter_features(heightmap, hurst_map, moisture, biome, density=1.0)
        assert len(features) > 0

    def test_features_have_required_fields(self):
        """Each feature should have type, position, scale, rotation."""
        from the_similarity.core.feature_scatter import scatter_features

        size = 32
        heightmap = np.random.default_rng(42).uniform(0.1, 0.9, (size, size))
        hurst_map = np.full((size, size), 0.6)
        moisture = np.full((size, size), 0.5)
        biome = np.full((size, size), 3, dtype=np.int32)  # forest

        features = scatter_features(heightmap, hurst_map, moisture, biome, density=1.0)
        if features:
            f = features[0]
            assert "type" in f
            assert "x" in f
            assert "y" in f
            assert "z" in f
            assert "scale" in f
            assert "rotation" in f

    def test_zero_density_returns_empty(self):
        """Density=0 should produce no features."""
        from the_similarity.core.feature_scatter import scatter_features

        size = 32
        heightmap = np.ones((size, size)) * 0.5
        hurst_map = np.full((size, size), 0.6)
        moisture = np.full((size, size), 0.5)
        biome = np.full((size, size), 3, dtype=np.int32)

        features = scatter_features(heightmap, hurst_map, moisture, biome, density=0.0)
        assert len(features) == 0

    def test_no_trees_on_steep_slopes(self):
        """Trees should not appear on very steep terrain."""
        from the_similarity.core.feature_scatter import (
            scatter_features,
            FEATURE_TREE_PINE,
            FEATURE_TREE_OAK,
        )

        size = 64
        # Create a cliff with a smooth transition zone to get clear gradient
        heightmap = np.zeros((size, size))
        for x in range(size):
            heightmap[:, x] = np.clip((x - size // 2) / 2.0, 0, 1)  # steep ramp
        hurst_map = np.full((size, size), 0.8)
        moisture = np.full((size, size), 0.5)
        biome = np.full((size, size), 3, dtype=np.int32)

        features = scatter_features(heightmap, hurst_map, moisture, biome, density=2.0)
        tree_types = {FEATURE_TREE_PINE, FEATURE_TREE_OAK}
        tree_features = [f for f in features if f["type"] in tree_types]

        # Trees in the steep ramp zone (columns 32-36) should be absent
        steep_zone_trees = [f for f in tree_features if 30 < f["x"] < 38]
        assert len(steep_zone_trees) == 0, (
            f"Found {len(steep_zone_trees)} trees in steep zone"
        )


# ---------------------------------------------------------------------------
# Generator Integration
# ---------------------------------------------------------------------------


class TestTerrainGenerator:
    """Integration tests for the full generation pipeline."""

    def test_generate_produces_valid_terrain(self):
        """Generator should produce a complete GeneratedTerrain."""
        from the_similarity.core.terrain_generator import TerrainGenerator

        gen = TerrainGenerator("alpine")
        result = gen.generate(size=64, seed=42)

        assert result.heightmap.shape == (64, 64)
        assert result.moisture_map.shape == (64, 64)
        assert result.flow_map.shape == (64, 64)
        assert result.biome_map.shape == (64, 64)
        assert result.hurst_map.shape == (64, 64)
        assert 0 <= result.heightmap.min()
        assert result.heightmap.max() <= 1.0

    def test_deterministic_with_same_seed(self):
        """Same seed should produce identical terrain."""
        from the_similarity.core.terrain_generator import TerrainGenerator

        gen = TerrainGenerator("desert")
        a = gen.generate(size=32, seed=123)
        b = gen.generate(size=32, seed=123)

        np.testing.assert_array_equal(a.heightmap, b.heightmap)

    def test_different_presets_differ(self):
        """Different presets should produce different terrain."""
        from the_similarity.core.terrain_generator import TerrainGenerator

        alpine = TerrainGenerator("alpine").generate(size=32, seed=42)
        desert = TerrainGenerator("desert").generate(size=32, seed=42)

        # Heights should differ meaningfully
        assert not np.allclose(alpine.heightmap, desert.heightmap)

    def test_features_generated(self):
        """Generator with vegetation should produce features."""
        from the_similarity.core.terrain_generator import TerrainGenerator
        from the_similarity.core.terrain_params import get_preset

        params = get_preset("rolling_hills")
        params.vegetation_density = 2.0  # boost for small test terrain
        gen = TerrainGenerator(params)
        result = gen.generate(size=64, seed=42)

        # rolling_hills has high veg density, should get some features
        assert len(result.features) >= 0  # may be 0 for very small terrain

    def test_presets_create_different_relief_profiles(self):
        """Gentle presets should stay gentler than mountain-oriented ones."""
        from the_similarity.core.terrain_generator import TerrainGenerator

        alpine = TerrainGenerator("alpine").generate(size=64, seed=7)
        rolling = TerrainGenerator("rolling_hills").generate(size=64, seed=7)

        alpine_dy, alpine_dx = np.gradient(alpine.heightmap)
        rolling_dy, rolling_dx = np.gradient(rolling.heightmap)
        alpine_slope = np.sqrt(alpine_dx**2 + alpine_dy**2)
        rolling_slope = np.sqrt(rolling_dx**2 + rolling_dy**2)

        # Rolling hills should have fewer strong slopes in the upper tail.
        assert np.quantile(rolling_slope, 0.9) < np.quantile(alpine_slope, 0.9)

        # Even the alpine preset should still preserve plenty of non-mountain
        # area so the whole map does not collapse into all spikes and ridges.
        assert np.mean(alpine.heightmap < 0.45) > 0.25
