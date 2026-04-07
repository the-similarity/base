# The Similarity — Research-to-Product Analysis

## What We're Building

A system that answers: **"Has this market pattern happened before, and what happened next?"**

Given a window of recent price action, The Similarity searches historical data for structurally similar patterns using 9 independent mathematical methods, scores each match with a composite confidence score, and generates a probabilistic forecast cone from the matched outcomes.

No existing product does this at the depth we're targeting.

---

## What Exists Today (Competitive Landscape)

| Product | What It Does | What It Doesn't Do |
|---------|-------------|-------------------|
| **ThinkOrSwim** | Single-metric pattern search (Pearson correlation) | No multi-method scoring, no weighted projection, no confidence breakdown |
| **TrendSpider** | Predefined chart pattern detection (triangles, flags) | Template-only — can't search for arbitrary subsequences |
| **TradingView** | Community Pine Script indicators | No native similarity search at all |
| **Trade Ideas** | AI scanning for trade signals | Event-based, not pattern-based |
| **STUMPY (academic)** | Matrix profile motif/anomaly discovery | Distance computation only — no scoring, no forecasting layer |
| **tslearn (academic)** | DTW clustering and classification | No projection, no composite scoring |

**The gap**: Every existing tool either (a) only recognizes predefined chart patterns, or (b) uses a single distance metric with no forecasting layer. Nobody combines multiple mathematical similarity methods into a single confidence score and generates weighted probabilistic forecasts from the matches.

---

## Our 9 Methods — What Each Brings to the Table

### Currently Implemented (2/9)

| Method | Weight | What It Captures | Status |
|--------|--------|-----------------|--------|
| **DTW** | 0.07 | Shape similarity with temporal flexibility | Working |
| **Pearson (warped)** | 0.05 | Linear correlation after alignment | Working |

### Phase 2 — Core Differentiators (3/9)

| Method | Weight | What It Captures | Research Insight |
|--------|--------|-----------------|-----------------|
| **Bempedelis R²** | 0.20 | Whether both patterns obey the same power-law scaling — a deep structural test, not just surface shape | Coded but not wired in. The R² of the power-law collapse separates genuinely self-similar dynamics from coincidental shape matches. This is our most original method. |
| **Bempedelis Smoothness** | 0.10 | Whether the scaling transform is clean (not overfitted) | Acts as a regularizer. Jagged alpha/beta curves that achieve low residual are not genuinely self-similar. |
| **Wavelet Spectrum** | 0.15 | Multifractal fingerprint — how complexity distributes across time scales | Wavelet leaders produce a singularity spectrum f(α) that acts as a fractal fingerprint. Two patterns with similar f(α) share the same multi-scale dynamics. Width of spectrum = degree of complexity. Research shows markets become more multifractal during crises. |

### Phase 3 — Research Grade (4/9)

| Method | Weight | What It Captures | Research Insight |
|--------|--------|-----------------|-----------------|
| **Koopman** | 0.20 | Dynamical system equivalence — same underlying "engine" driving both patterns | The highest-weighted single method. Koopman eigenvalues encode oscillation frequencies and growth/decay rates. Two patterns with similar eigenvalue spectra are driven by similar dynamical processes, even if surface shapes differ. KoopSTD (ICML 2025) validates this approach for dynamical similarity. |
| **EMD** | 0.10 | Multi-scale oscillation matching — similarity at each frequency band independently | Decomposes into Intrinsic Mode Functions (IMFs), then matches corresponding IMFs. Catches matches that are similar at the trend level but different in noise, or vice versa. CEEMDAN variant eliminates mode mixing. |
| **TDA** | 0.08 | Topological similarity — same "shape of the shape" in phase space | Persistence diagrams capture loops and holes in the reconstructed attractor. Research shows L^p norms of persistence landscapes rise ~250 trading days before crashes (Gidea & Katz, 2018). Invariant to rescaling and warping. |
| **Transfer Entropy** | 0.05 | Predictive information — does this match actually predict what follows? | Unlike other methods that measure similarity, TE measures whether the matched period genuinely predicts its forward window. High TE = the match is not just similar, it's informative. Acts as a post-hoc quality filter. |

### Why This Combination Matters

Each method captures a fundamentally different aspect of similarity:

```
Surface Shape ←→ DTW, Pearson
Scaling Structure ←→ Bempedelis
Frequency Content ←→ Wavelet, EMD
Dynamical Fingerprint ←→ Koopman
Topological Structure ←→ TDA
Predictive Power ←→ Transfer Entropy
```

A match that scores high across all dimensions is not just "similar looking" — it's structurally, dynamically, and topologically equivalent. This is qualitatively different from any single-metric approach.

---

## The Tier Architecture — Why It's Smart

### Current Problem
Right now, `matcher.py` scores every single candidate window with DTW + Pearson. For a 5-year daily history (~1,250 bars) with a 60-bar query, that's ~1,190 candidates. Adding 7 more expensive methods would make this prohibitively slow.

### Research-Backed Solution

**Tier 1 — Fast Pre-Filters (eliminate ~80%)**

| Pre-Filter | Time Complexity | What It Does | Research Finding |
|------------|----------------|-------------|-----------------|
| **SAX** | O(n) per comparison | Converts to symbolic string, MINDIST distance | MINDIST lower-bounds Euclidean distance — guaranteed no false dismissals. Eliminates bottom 80% instantly. |
| **Matrix Profile** | O(n²) one-time | Computes nearest-neighbor for every subsequence | STUMPY: parameter-free, exact, no false positives. Already identifies the best candidates. |
| **Wavelet Leaders** | O(n log n) | Coarse spectral fingerprint | Fast spectrum distance as first-pass filter before full f(α) comparison. |

**Tier 1 Merger**: Ranked union with nomination scoring. A candidate nominated by all 3 methods ranks higher than one nominated by 1. Top N survivors pass to Tier 2.

**Tier 2 — Quality Scoring (the 9 methods)**
Only the ~200 surviving candidates (from 1,000+) get the full 9-method treatment. This makes the system feasible at scale.

**Net effect**: Search time goes from O(N × 9_methods) to O(N × 3_fast + K × 9_full), where K << N.

---

## The Forecast Cone — What Research Says We Should Improve

### Current Implementation
`projector.py` extracts forward windows from top matches, converts to cumulative returns, and computes weighted percentiles at each future bar.

### Research-Backed Enhancements

1. **Confidence Decay** (planned Phase 4b)
   - Pattern match predictive power decays with forecast horizon
   - Formula: `w_i(t) = w_i × exp(-λ × t)`
   - Effect: bands widen naturally even with few matches
   - Research: Bank of England, ECB Fan Charts 2.0 all use this

2. **Interpolated Weighted Quantiles**
   - Current: snaps to nearest path at threshold crossing
   - Better: linear interpolation between adjacent paths → smoother percentile curves
   - A 3-line change with significant visual improvement

3. **More Percentile Bands**
   - Current: 10th, 50th, 90th
   - Better: 10th, 25th, 50th, 75th, 90th (5 bands)
   - Provides finer uncertainty granularity

4. **Koopman Forward Evolution** (Phase 4a)
   - Use the Koopman operator K to evolve the query forward: x(t+dt) = K·x(t)
   - A completely separate forecast that can be compared against the pattern-based cone
   - Uncertainty from eigenvalue matching residuals

---

## Backtesting — The Ground Truth We Need

### Why It's Critical (Phase 4c)

Without backtesting, we can't answer: "Do these confidence scores actually mean anything?"

### Research-Backed Approach

**Walk-Forward Validation** (gold standard):
1. Pick random query window at time t
2. Search only in data before t (no lookahead)
3. Generate forecast cone
4. Compare to what actually happened
5. Repeat N times across different market regimes

**Key Metrics:**
- **Calibration**: Does the 90% band contain the actual outcome 90% of the time? If not, we're overconfident. Almost all systems are overconfident initially.
- **CRPS** (Continuous Ranked Probability Score): Gold standard for probabilistic forecasts. Better than hit rate because it evaluates the full distribution.
- **Directional accuracy**: Did the median forecast get the direction right?
- **Coverage probability**: What fraction of actuals fall within each band?

**Critical finding from research**: Historic prices alone are insufficient for reliable prediction. Our multi-method approach partially addresses this by capturing structural information beyond raw price, but rigorous backtesting will reveal the true edge (if any).

---

## What Makes This Product Unique — The Pitch

### For Traders / Analysts
"You draw a pattern. We find every time something structurally identical happened in history — not just similar looking, but mathematically equivalent across 9 dimensions — and show you what happened next, with honest confidence bands."

### For Quant Researchers
"A research-grade time series similarity system with the first composite scoring framework that combines DTW, power-law self-similarity, Koopman dynamical system matching, topological data analysis, and wavelet multifractal fingerprinting into a single calibrated confidence score."

### The Core Differentiator in One Sentence
**"Not just shape matching — structural matching."**

DTW says "these look similar." Bempedelis says "these scale the same way." Koopman says "these are driven by the same dynamical process." TDA says "these have the same topological structure." Transfer entropy says "and this match actually predicts what comes next."

No other product or open-source tool combines all of these.

---

## Immediate Priorities (Based on Research)

### High Impact, Low Effort
1. **Wire Bempedelis into matcher** — It's coded, just not called. Instantly makes confidence scores meaningful (30% weight unlocked).
2. **Interpolated weighted quantiles** — 3-line change in projector.py for smoother forecast cones.
3. **Add 25th/75th percentile bands** — Trivial config change, better uncertainty visualization.

### High Impact, Medium Effort
4. **SAX pre-filter** — The research is clear: MINDIST lower-bounds guarantee no false dismissals. Use pyts library. Eliminates 80% of candidates.
5. **Matrix Profile via STUMPY** — Parameter-free, exact nearest-neighbor ranking. One `pip install stumpy` away.
6. **Tier 1 merger** — Ranked union with nomination scoring. Straightforward algorithm.

### High Impact, High Effort (But Researched)
7. **Koopman EDMD** — Highest single weight (0.20). PyKoopman and PyDMD are mature. The pipeline is clear: Takens embed → EDMD → eigenvalues → Hungarian matching.
8. **Backtester** — Without this, we can't tune weights or validate calibration. Critical path for credibility.

### Deferred
9. **TDA, EMD, Transfer Entropy** — Important for completeness but lower weights. Implement after Koopman and backtester prove the core thesis.
10. **FeatureStore caching** — Performance optimization. Only matters at scale.
11. **Foundation model comparison** — Research shows generic foundation models (TimesFM, Chronos) underperform on financial data. Our domain-specific approach may have an edge, but we need the backtester to prove it.

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| **Pattern matching is fundamentally unreliable for prediction** | The multi-method scoring is designed to filter out coincidental matches. Transfer entropy specifically tests predictive power. Backtester will provide honest calibration. |
| **Computational cost of 9 methods per candidate** | Tier 1 pre-filtering eliminates 80%+ before expensive methods run. FeatureStore caches results. |
| **Overfitting weights to historical data** | Walk-forward validation with nested cross-validation. Regime-stratified backtesting. |
| **Market regime changes invalidate historical analogs** | Regime tagger (Phase 3f) labels each window. Koopman can filter by regime. Confidence decay reduces weight at longer horizons. |
| **Insufficient data for reliable statistics** | Multi-asset data bank (stocks, crypto, forex, commodities) expands the search space. Cross-timeframe search (Phase 5c) multiplies available analogs. |

---

## Summary

The research confirms three things:

1. **The architecture is sound.** Tiered search, multi-method composite scoring, and weighted percentile projection are all well-established patterns. The specific combination of methods is novel.

2. **The methods are real.** Every method in the 9-component score has published academic support, mature Python libraries, and demonstrated financial applications. This is not speculative.

3. **The gap in the market is real.** No existing product combines arbitrary subsequence similarity search with multi-method confidence scoring and probabilistic forecasting. ThinkOrSwim comes closest but uses only Pearson correlation.

The key question the backtester must answer: **Does structural similarity actually predict forward returns better than chance?** If yes, this is a genuinely useful tool. If no, it's still a powerful exploratory research platform — but the marketing changes.
