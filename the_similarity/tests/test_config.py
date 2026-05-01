"""Tests for the_similarity.config — Config dataclass and feature flags.

Covers:
- Default construction backward compatibility
- Experimental feature flag defaults and introspection
- __post_init__ validation (weight bounds, path requirement, fail-safe)
"""

import pytest

from the_similarity.config import Config


class TestConfigDefaults:
    """Verify that default Config() is backward-compatible."""

    def test_default_config_creates_successfully(self):
        """Config() with no args must not raise."""
        cfg = Config()
        assert cfg is not None

    def test_default_jepa_disabled(self):
        """JEPA must be off by default so existing behavior is unchanged."""
        cfg = Config()
        assert cfg.jepa_enabled is False

    def test_default_jepa_weight_zero(self):
        cfg = Config()
        assert cfg.jepa_weight == 0.0

    def test_default_jepa_embedding_path_none(self):
        cfg = Config()
        assert cfg.jepa_embedding_path is None

    def test_default_active_methods_unchanged(self):
        """The 9 production methods must still be active by default."""
        cfg = Config()
        expected = {
            "bempedelis_r2",
            "bempedelis_smoothness",
            "koopman",
            "wavelet_spectrum",
            "emd",
            "tda",
            "dtw",
            "pearson_warped",
            "transfer_entropy",
        }
        assert set(cfg.active_methods) == expected


class TestFeatureFlags:
    """Test the feature_flags() introspection method."""

    def test_feature_flags_returns_dict(self):
        cfg = Config()
        flags = cfg.feature_flags()
        assert isinstance(flags, dict)

    def test_feature_flags_keys(self):
        cfg = Config()
        flags = cfg.feature_flags()
        assert set(flags.keys()) == {
            "jepa_enabled",
            "jepa_weight",
            "jepa_embedding_path",
            "latent_regime_enabled",
            "latent_regime_weight",
            "robust_ambiguity_enabled",
            "robust_ambiguity_radius",
            "robust_ambiguity_weight",
        }

    def test_feature_flags_default_values(self):
        cfg = Config()
        flags = cfg.feature_flags()
        assert flags["jepa_enabled"] is False
        assert flags["jepa_weight"] == 0.0
        assert flags["jepa_embedding_path"] is None
        assert flags["latent_regime_enabled"] is False
        assert flags["latent_regime_weight"] == 0.15
        assert flags["robust_ambiguity_enabled"] is False
        assert flags["robust_ambiguity_radius"] == 1.5
        assert flags["robust_ambiguity_weight"] == 0.0

    def test_feature_flags_enabled_values(self):
        cfg = Config(
            jepa_enabled=True,
            jepa_weight=0.15,
            jepa_embedding_path="/tmp/jepa.h5",
            latent_regime_enabled=True,
            latent_regime_weight=0.25,
            robust_ambiguity_enabled=True,
            robust_ambiguity_radius=2.0,
            robust_ambiguity_weight=0.2,
        )
        flags = cfg.feature_flags()
        assert flags["jepa_enabled"] is True
        assert flags["jepa_weight"] == 0.15
        assert flags["jepa_embedding_path"] == "/tmp/jepa.h5"
        assert flags["latent_regime_enabled"] is True
        assert flags["latent_regime_weight"] == 0.25
        assert flags["robust_ambiguity_enabled"] is True
        assert flags["robust_ambiguity_radius"] == 2.0
        assert flags["robust_ambiguity_weight"] == 0.2


class TestJepaValidation:
    """Test __post_init__ validation rules for JEPA flags."""

    def test_weight_below_zero_raises(self):
        with pytest.raises(ValueError, match="jepa_weight must be in"):
            Config(jepa_weight=-0.1)

    def test_weight_above_one_raises(self):
        with pytest.raises(ValueError, match="jepa_weight must be in"):
            Config(jepa_weight=1.5)

    def test_weight_boundary_zero_ok(self):
        cfg = Config(jepa_weight=0.0)
        assert cfg.jepa_weight == 0.0

    def test_weight_boundary_one_ok(self):
        """Weight=1.0 is valid (requires enabled + path to be meaningful)."""
        cfg = Config(jepa_enabled=True, jepa_weight=1.0, jepa_embedding_path="/tmp/x")
        assert cfg.jepa_weight == 1.0

    def test_enabled_without_path_raises(self):
        with pytest.raises(ValueError, match="jepa_embedding_path must be set"):
            Config(jepa_enabled=True, jepa_weight=0.1)

    def test_enabled_with_empty_path_raises(self):
        with pytest.raises(ValueError, match="jepa_embedding_path must be set"):
            Config(jepa_enabled=True, jepa_weight=0.1, jepa_embedding_path="")

    def test_enabled_with_path_ok(self):
        cfg = Config(
            jepa_enabled=True,
            jepa_weight=0.2,
            jepa_embedding_path="/data/jepa_embeddings.h5",
        )
        assert cfg.jepa_enabled is True
        assert cfg.jepa_weight == 0.2

    def test_disabled_forces_weight_to_zero(self):
        """Fail-safe: even if caller passes weight > 0, disabled clamps it."""
        cfg = Config(jepa_enabled=False, jepa_weight=0.5)
        assert cfg.jepa_weight == 0.0

    def test_disabled_with_path_is_ok(self):
        """Having a stale path while disabled is harmless — no error."""
        cfg = Config(
            jepa_enabled=False,
            jepa_weight=0.3,
            jepa_embedding_path="/old/path.h5",
        )
        # Weight forced to 0.0, path kept for informational purposes
        assert cfg.jepa_weight == 0.0
        assert cfg.jepa_embedding_path == "/old/path.h5"
