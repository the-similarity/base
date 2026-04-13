# JEPA integration surface

Where JEPA (Joint Embedding Predictive Architecture) slots into the production engine.

> Full spec: `docs/planning/JEPA_INTEGRATION_SPEC.md`

## Summary

JEPA adds a **10th scoring method** (`jepa_similarity`) to the existing 9-method tiered pipeline. It lives in **Tier 2 enrichment** alongside Koopman, Wavelet, TDA, EMD, and Transfer Entropy — running on only the top ~20 candidates after DTW+Pearson ranking.

## Where it touches

| Component | Change |
|-----------|--------|
| [[Engine map\|Config]] | `jepa_enabled: bool`, `jepa_weight: float`, `jepa_embedding_path: str` |
| [[Nine-method pipeline\|ScoreBreakdown]] | `jepa_similarity: float` field (range [0, 1], default 0.0) |
| Matcher Tier 2 | New block in `_enrich_tier2()`, added to `TIER2_SCORE_FIELDS` |
| FeatureStore | Cache key: `(ds_hash, start, len, "jepa_similarity", checkpoint_hash)` |
| Methods | New file: `the_similarity/methods/jepa_matcher.py` |
| Dependencies | PyTorch as optional: `pip install the-similarity[jepa]` |

## Backward compatibility

`jepa_enabled=False` (default) produces **byte-identical results** to the current engine. No torch import, no score pollution, no weight distortion.

## Migration phases

1. **Research** (current) — train encoder in `research/autoresearch/`
2. **Method stub** — `jepa_matcher.py` with lazy torch import
3. **Config + scorer wiring** — 3 config fields, 1 score field, matcher block
4. **FeatureStore caching** — same pattern as Koopman
5. **Backtester validation** — compare hit_rate/CRPS with JEPA on vs off
6. **Frontend** — toggle + score display

## Related

- [[Nine-method pipeline]] — current Tier 0/1/2 architecture
- [[Vision pillars]] — where JEPA fits in the product roadmap
- [[Research hub]] — JEPA research notes
- `research/autoresearch/` — active JEPA experiments
