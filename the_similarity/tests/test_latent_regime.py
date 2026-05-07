import numpy as np

from the_similarity.config import Config
from the_similarity.core.latent_regime import (
    infer_latent_regime,
    regime_probability_similarity,
)
from the_similarity.core.matcher import find_matches


def test_latent_regime_probabilities_sum_to_one():
    rng = np.random.default_rng(7)
    series = 100.0 * np.exp(np.cumsum(0.001 + 0.01 * rng.standard_normal(80)))

    state = infer_latent_regime(series)

    assert abs(sum(state.probabilities.values()) - 1.0) < 1e-10
    assert state.dominant_regime in state.probabilities
    assert abs(sum(state.transition_probabilities.values()) - 1.0) < 1e-10


def test_regime_similarity_prefers_same_state():
    up = 100.0 + np.linspace(0, 10, 80) + 0.05 * np.sin(np.linspace(0, 8, 80))
    down = 100.0 - np.linspace(0, 10, 80) + 0.05 * np.sin(np.linspace(0, 8, 80))

    up_state = infer_latent_regime(up)
    down_state = infer_latent_regime(down)

    assert regime_probability_similarity(
        up_state, up_state
    ) >= regime_probability_similarity(up_state, down_state)


def test_matcher_attaches_latent_regime_metadata_when_enabled():
    rng = np.random.default_rng(11)
    history = 100.0 + np.cumsum(rng.normal(0, 0.03, size=220))
    pattern = 100.0 + np.linspace(0, 5, 40)
    history[40:80] = pattern
    history[140:180] = pattern
    query = history[140:180].copy()

    matches = find_matches(
        query=query,
        history=history,
        top_k=3,
        config=Config(
            active_methods=["dtw", "pearson_warped"],
            tier1_candidates=30,
            latent_regime_enabled=True,
        ),
        exclude_query_region=(140, 180),
    )

    assert matches
    assert matches[0].latent_regime_probabilities is not None
    assert matches[0].latent_regime_similarity is not None
    assert 0.0 <= matches[0].latent_regime_similarity <= 1.0
