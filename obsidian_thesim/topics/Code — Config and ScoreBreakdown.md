# Code — Config and ScoreBreakdown

## `Config`

**File:** `the_similarity/config.py`

Single dataclass for knobs: **`weights`**, **`active_methods`**, DTW Sakoe–Chiba radius, **`tier1_candidates`**, projector / Koopman blend / decay flags, etc.

Default **weights** (relative — scorer renormalizes over **`active_methods` only**):

```python
weights: dict[str, float] = field(default_factory=lambda: {
    "bempedelis_r2": 0.20,
    "bempedelis_smoothness": 0.10,
    "koopman": 0.20,
    "wavelet_spectrum": 0.15,
    "emd": 0.10,
    "tda": 0.08,
    "dtw": 0.07,
    "pearson_warped": 0.05,
    "transfer_entropy": 0.05,
})
```

**Invariant:** keys must stay aligned with **`ScoreBreakdown`** fields and API contract types.

## `ScoreBreakdown`

**File:** `the_similarity/core/scorer.py`

Per-method similarities in **\[0, 1]** before the weighted composite; composite is scaled to **0–100** for display/API.

Fields include: `bempedelis_r2`, `bempedelis_smoothness`, `koopman`, `wavelet_spectrum`, `emd`, `tda`, `dtw`, `pearson_warped`, `transfer_entropy`.

**`compute_confidence()`** renormalizes weights so toggling methods in the UI does not deflate the total arbitrarily.

## Related

- [[topics/Code — matcher tiers and modules]]
- [[Why nine lenses]] (conceptual counterpart)
