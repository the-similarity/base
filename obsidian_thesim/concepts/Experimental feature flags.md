# Experimental feature flags

Feature flags in `the_similarity/config.py` that gate experimental integrations. All default to **OFF** so that `Config()` produces identical behavior to the pre-flag codebase.

## Current flags

| Flag | Type | Default | Purpose |
|------|------|---------|---------|
| `jepa_enabled` | `bool` | `False` | Master switch for JEPA embedding similarity scoring |
| `jepa_weight` | `float` | `0.0` | Relative importance in composite confidence score (0.0 -- 1.0) |
| `jepa_embedding_path` | `str \| None` | `None` | Path to pre-computed JEPA embedding store |

## Validation rules (`__post_init__`)

- `jepa_weight` must be in [0.0, 1.0] -- raises `ValueError` otherwise.
- If `jepa_enabled` is `True`, `jepa_embedding_path` must be a non-empty string -- fail-fast.
- If `jepa_enabled` is `False`, `jepa_weight` is forced to `0.0` -- fail-safe default-off.

## Introspection

`Config.feature_flags()` returns a dict of all experimental flags and their post-validation values. Designed for experiment ledger entries and reproducibility metadata.

```python
cfg = Config(jepa_enabled=True, jepa_weight=0.15, jepa_embedding_path="/data/jepa.h5")
cfg.feature_flags()
# {'jepa_enabled': True, 'jepa_weight': 0.15, 'jepa_embedding_path': '/data/jepa.h5'}
```

## Design rationale

Autoresearch loops and JEPA integration experiments need reversible switches that do not require invasive code edits. Feature flags keep the production pipeline stable while allowing controlled experiments on feature branches.

## Related

- [[Nine-method pipeline]] -- the tiered matcher these flags extend
- [[Engine map]] -- where `config.py` sits in the architecture
- Code: `the_similarity/config.py`
- Tests: `the_similarity/tests/test_config.py`
