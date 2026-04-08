# Code — method modules table

Python package: **`the_similarity/methods/`** (each file is a candidate touchpoint when debugging a score).

| Area | Module | Notes |
|------|--------|--------|
| Power-law / Bempedelis | `bempedelis.py`, `bempedelis_2d.py` | Two score fields in `ScoreBreakdown` |
| DTW + Pearson | `dtw_matcher.py` | Tier-1 cheap path + alignment for warped Pearson |
| SAX | `sax_filter.py` | Prefilter / symbolic distances |
| Matrix profile | `matrix_profile_filter.py` | STUMPY when available (`HAS_STUMPY`) |
| Koopman | `koopman.py` | Spectrum match + projector-side evolution |
| Wavelet leaders | `wavelet_leaders.py`, `wavelet_leaders_2d.py` | Multifractal spectrum distance |
| EMD | `emd_matcher.py`, `emd_2d.py` | IMF alignment scoring |
| TDA | `tda_matcher.py` | Persistence diagram comparison |
| Transfer entropy | `transfer_entropy.py` | Directional predictive information |

Matcher **imports** the 1D matchers by default; see **`matcher.py`** for actual call graph.

## Related

- [[topics/Code — matcher tiers and modules]]
- [[topics/Methods index]] — plain-language method pages
