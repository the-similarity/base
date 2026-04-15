from the_similarity.core.scorer import ScoreBreakdown, compute_confidence
from the_similarity.config import Config


def test_dtw_and_pearson_only():
    """With only DTW+Pearson active, perfect scores → 100."""
    breakdown = ScoreBreakdown(dtw=1.0, pearson_warped=1.0)
    config = Config(active_methods=["dtw", "pearson_warped"])
    score = compute_confidence(breakdown, config)
    assert abs(score - 100.0) < 0.01


def test_all_perfect():
    """All 9 methods at 1.0 → 100."""
    breakdown = ScoreBreakdown(
        bempedelis_r2=1.0,
        bempedelis_smoothness=1.0,
        koopman=1.0,
        wavelet_spectrum=1.0,
        emd=1.0,
        tda=1.0,
        dtw=1.0,
        pearson_warped=1.0,
        transfer_entropy=1.0,
    )
    score = compute_confidence(breakdown)
    assert abs(score - 100.0) < 0.01


def test_all_zero():
    breakdown = ScoreBreakdown()
    score = compute_confidence(breakdown)
    assert score == 0.0


def test_custom_weights():
    breakdown = ScoreBreakdown(dtw=1.0)
    config = Config(weights={"dtw": 1.0}, active_methods=["dtw"])
    score = compute_confidence(breakdown, config)
    assert abs(score - 100.0) < 0.01


def test_weights_sum_to_one():
    config = Config()
    total = sum(config.weights.values())
    assert abs(total - 1.0) < 1e-10


def test_single_method_renormalized():
    """With all methods active, setting only bempedelis_r2=1.0
    should yield its weight fraction * 100."""
    breakdown = ScoreBreakdown(bempedelis_r2=1.0)
    config = Config()
    score = compute_confidence(breakdown, config)
    expected = 100.0 * 0.20  # bempedelis_r2 weight / total (1.0)
    assert abs(score - expected) < 0.01


def test_koopman_renormalized():
    breakdown = ScoreBreakdown(koopman=1.0)
    config = Config()
    score = compute_confidence(breakdown, config)
    expected = 100.0 * 0.20
    assert abs(score - expected) < 0.01


def test_default_all_methods_active():
    """Default config now has all 9 methods active."""
    config = Config()
    assert len(config.active_methods) == 9


def test_renormalized_subset():
    """With a 2-method subset, weights renormalize correctly."""
    breakdown = ScoreBreakdown(dtw=1.0)
    config = Config(active_methods=["dtw", "pearson_warped"])
    score = compute_confidence(breakdown, config)
    expected = 100.0 * 0.07 / (0.07 + 0.05)
    assert abs(score - expected) < 0.01


def test_inactive_metrics_can_be_enabled_explicitly():
    breakdown = ScoreBreakdown(dtw=1.0, koopman=0.5)
    config = Config(active_methods=["dtw", "koopman"])
    score = compute_confidence(breakdown, config)
    expected = 100.0 * ((0.07 * 1.0) + (0.20 * 0.5)) / (0.07 + 0.20)
    assert abs(score - expected) < 0.01
