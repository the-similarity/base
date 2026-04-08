# Code — public API quickstart

Entry: `the_similarity/api.py`.

## Minimal search

```python
import numpy as np
from the_similarity.api import load, search
from the_similarity.config import Config

history = load("path/to/prices.csv", column="close")
query = history.values[-60:]  # last 60 bars as pattern

cfg = Config(tier1_candidates=500)  # optional knobs
results = search(query, history, top_k=10, config=cfg)
results.summary()  # prints ScoreBreakdown columns for top matches
```

`search()` builds a **`Config`** if you pass `None`, merges optional **`weights`** and `**kwargs` into config fields, then calls **`find_matches`** in `core/matcher.py`.

## Useful types

- **`SearchResults`** — `.matches: list[MatchResult]`, `.best`
- **`MatchResult`** — indices, dates, `score_breakdown: ScoreBreakdown`, `confidence_score` (0–100 scale for display)

## Projection / forecasting

Use **`project()`** from the same module (see `api.py` after `search` — signature includes match list, horizon, config). The projector lives in `the_similarity/core/projector.py` and composes weighted quantile paths; Koopman blend is config-driven.

## Related

- [[topics/Code — matcher tiers and modules]]
- [[topics/Code — Config and ScoreBreakdown]]
- [[Engine map]]
