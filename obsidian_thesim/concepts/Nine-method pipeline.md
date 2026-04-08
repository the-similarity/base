# Nine-method pipeline

End-state shape of the matcher: **fast screen → strong baseline → rich enrichment** so cost stays under control.

## Tiers (conceptual)

1. **Prefilter:** SAX representation + MASS / matrix-profile style screening — cheap, high recall-ish filter.
2. **Core similarity:** DTW and Pearson — tighter scoring on survivors.
3. **Tier 2:** Seven additional methods (wavelet leaders, Koopman, EMD, TDA, transfer entropy, Bempedelis, etc. — see `the_similarity/methods/`) add orthogonal evidence for ranking and confidence.

Koopman specifically feeds **forward dynamics** used in the projector (eigenvalue clamping). The forecast **cone** blends statistical quantiles with that evolution; decay knocks down confidence with horizon.

## When you learn more

Add child notes (e.g. one file per method) and link them here. Mirror or extend `research/methods/` in the repo where long-form writeups already exist.

## Related

- [[Engine map]]
- [[Repo research and docs]]
