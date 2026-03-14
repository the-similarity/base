import numpy as np

from the_similarity.methods.transfer_entropy import compute_transfer_entropy, te_score


def test_te_deterministic():
    """Source that determines target should yield high TE."""
    rng = np.random.default_rng(42)
    # Build a target that is a noisy function of the source's past
    source = np.cumsum(rng.standard_normal(500))
    # target_t = source_{t-1} + small noise => source strongly predicts target
    target = np.concatenate([[0.0], source[:-1]]) + rng.standard_normal(500) * 0.1
    te = compute_transfer_entropy(source, target, lag=1, bins=6)
    assert te > 0.3, f"Expected TE > 0.3 for deterministic relationship, got {te}"


def test_te_independent():
    """Two independent random series should have near-zero TE."""
    rng = np.random.default_rng(123)
    source = rng.standard_normal(1000)
    target = rng.standard_normal(1000)
    te = compute_transfer_entropy(source, target, lag=1, bins=4)
    assert te < 0.1, f"Expected TE < 0.1 for independent series, got {te}"


def test_te_normalized_range():
    """Output should always be in [0, 1] for a variety of inputs."""
    rng = np.random.default_rng(7)
    for _ in range(30):
        source = rng.standard_normal(100)
        target = rng.standard_normal(100)
        te = te_score(source, target, lag=1, bins=8)
        assert 0.0 <= te <= 1.0, f"TE {te} out of [0, 1]"


def test_te_constant_series():
    """Constant input should return 0.0."""
    source = np.ones(50)
    target = np.ones(50)
    assert compute_transfer_entropy(source, target) == 0.0

    # One constant, one varying
    rng = np.random.default_rng(0)
    target_var = rng.standard_normal(50)
    assert compute_transfer_entropy(source, target_var) == 0.0
    assert compute_transfer_entropy(target_var, source) == 0.0


def test_te_short_series():
    """Series shorter than lag + 1 should return 0.0."""
    source = np.array([1.0])
    target = np.array([2.0])
    assert compute_transfer_entropy(source, target, lag=1) == 0.0

    source = np.array([1.0, 2.0, 3.0, 4.0])
    target = np.array([1.0, 2.0, 3.0, 4.0])
    assert compute_transfer_entropy(source, target, lag=5) == 0.0
