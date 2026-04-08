# Code — matcher tiers and modules

File: **`the_similarity/core/matcher.py`**.

## Lifecycle (from module docstring)

Orchestrator **`find_matches()`** — one full search. **`history`** is treated as immutable; candidates are windowed views.

**Tiers (implementation names in `ProgressEvent.stage`):**

- **Prefilter** — SAX + MASS-style distance profile to drop most windows.
- **Tier 1** — cheap scores: DTW + Pearson (warped).
- **Tier 2** — expensive enrichment (Koopman, wavelet spectrum, EMD, TDA, transfer entropy; Bempedelis fields filled as part of the pipeline).

Threading: Tier 2 uses a **`ThreadPoolExecutor`**; NumPy/SciPy release the GIL — see docstring for why nested pools are a bad idea. **`progress_fn`** emits **`ProgressEvent`** for UI / WebSocket streaming.

## Score field groupings (constants)

```python
CHEAP_SCORE_FIELDS = {"dtw", "pearson_warped"}
BEMPEDELIS_SCORE_FIELDS = {"bempedelis_r2", "bempedelis_smoothness"}
TIER2_SCORE_FIELDS = {
    "koopman", "wavelet_spectrum", "emd", "tda", "transfer_entropy",
}
```

Full Cartesian product for schema/sync lives in **`ALL_SCORE_FIELDS`**.

## Representative imports (wiring map)

```python
from the_similarity.methods.bempedelis import bempedelis_match
from the_similarity.methods.dtw_matcher import batch_dtw_scores, dtw_distance, dtw_score
from the_similarity.methods.emd_matcher import emd_score
from the_similarity.methods.koopman import koopman_match
from the_similarity.methods.matrix_profile_filter import mp_score_profile, query_profile, HAS_STUMPY
from the_similarity.methods.sax_filter import sax_mindist, sax_score, sax_transform
from the_similarity.methods.tda_matcher import compare as tda_compare
from the_similarity.methods.transfer_entropy import te_score
from the_similarity.methods.wavelet_leaders import wavelet_spectrum_score
```

## Related

- [[topics/Code — method modules table]]
- [[topics/Code — Config and ScoreBreakdown]]
- [[Nine-method pipeline]]
