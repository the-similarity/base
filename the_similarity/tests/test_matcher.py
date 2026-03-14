import numpy as np

from the_similarity.config import Config
from the_similarity.core.matcher import find_matches


def _make_history_with_repeated_pattern():
    rng = np.random.default_rng(42)
    history = 100 + np.cumsum(rng.normal(0, 0.05, size=420))
    pattern = 100 + np.cumsum(np.sin(np.linspace(0, 4 * np.pi, 40)) * 0.4 + 0.2)
    history[60:100] = pattern
    history[260:300] = pattern
    query = history[260:300].copy()
    return history, query


def test_tier1_pruning_keeps_obvious_match():
    history, query = _make_history_with_repeated_pattern()
    config = Config(
        tier1_candidates=25,
        active_methods=["dtw", "pearson_warped"],
    )
    matches = find_matches(
        query=query,
        history=history,
        top_k=5,
        config=config,
        exclude_query_region=(260, 300),
    )
    assert matches
    assert matches[0].start_idx == 60


def test_bempedelis_reranking_populates_transform_details():
    history, query = _make_history_with_repeated_pattern()
    config = Config(
        tier1_candidates=50,
        tier2_candidates=10,
        active_methods=[
            "dtw",
            "pearson_warped",
            "bempedelis_r2",
            "bempedelis_smoothness",
        ],
    )
    matches = find_matches(
        query=query,
        history=history,
        top_k=3,
        config=config,
        exclude_query_region=(260, 300),
    )
    assert matches
    best = matches[0]
    assert best.score_breakdown.bempedelis_r2 >= 0
    assert best.score_breakdown.bempedelis_smoothness >= 0
    assert best.transform_alpha is not None
    assert best.transform_beta is not None
