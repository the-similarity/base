# TradingView Pine Scripts — The Similarity

This folder contains a Pine-native approximation of the repo's pattern engine for TradingView:

- `similarity_indicator.pine` — overlay indicator that finds the best analogue, rescales it to the current chart price, and projects forward percentile paths.
- `similarity_strategy.pine` — TradingView strategy that reuses the same analogue search and enters/exits trades from the projected path.

## How this maps to the repo engine

The Python engine in this repo is richer than Pine can support directly:

- `the_similarity/core/matcher.py` uses a multi-stage search pipeline with DTW, Pearson, Koopman, wavelets, TDA, EMD, and transfer-entropy enrichment.
- `the_similarity/core/projector.py` builds weighted percentile cones from post-match forward returns.
- `the_similarity/core/strategy.py` turns confidence + percentile outputs into momentum / mean-reversion / breakout rules.

The Pine implementation keeps the same high-level workflow:

1. use the latest `Pattern Length` bars as the query;
2. scan older windows over several scale factors;
3. compare normalized return paths;
4. rank analogues by confidence;
5. convert matched future paths into return projections;
6. rescale the selected analogue and forecast to the current chart anchor.

## Pine-specific simplifications

Because TradingView Pine runs inside a bounded chart runtime, the scripts intentionally simplify the search engine:

- full Tier 2 methods are replaced by a Pine-safe composite score:
  - normalized-return correlation
  - normalized-return distance penalty
  - direction agreement
  - volatility similarity
- scale search uses a curated list of four inputs rather than arbitrary continuous search;
- forecast percentiles are computed from the retained top-K matches with a simple weighted discrete percentile;
- regime detection is heuristic (`trending_up`, `trending_down`, `mean_reverting`, `high_vol`) instead of using the full Python research stack.

## Recommended defaults

- Pattern Length: `40`
- Forecast Bars: `20`
- Search Lookback: `600–1200` (default `600` in Pine sources)
- **Search Stride**: `3` on the **indicator** (default), `4` on the **strategy** (each bar replays the scan — stride matters more there)
- Top Matches: `3–5`
- Scales: `0.75 / 1.00 / 1.25 / 1.50`

### Runtime error RE10110 (“script takes too long — 20 seconds”)

TradingView caps script time per run (stricter on free plans). Mitigations:

1. **Indicator** (`similarity_indicator.pine`): the expensive analogue scan runs **only on `barstate.islast`** (one pass when the chart finishes updating), not on every historical bar. That was the main fix for timeouts.
2. **Raise `Search Stride`** (e.g. `4–8`) — fewer `endOffset` steps; slightly coarser search.
3. **Lower `Search Lookback`** or **Pattern Length**.
4. Use **fewer distinct scales** (set two scales to the same value in settings to effectively disable one, or we can add toggles later).
5. **Strategy**: still evaluates every bar — keep stride ≥ `4`, lookback modest, or test on shorter date ranges.

If the script feels slow on a low timeframe, reduce:

- `Search Lookback`
- `Pattern Length`
- number of enabled / distinct scales
- `Top Matches`

## Indicator behavior

The indicator:

- overlays the best historical match over the current query window;
- extends the best match's forward path from the current price anchor;
- optionally draws a `P10 / P50 / P90` projection cone from the top matches;
- shows a diagnostics table with confidence, scale, regime, offset, and cone width.

## Strategy behavior

The strategy supports three rule modes inspired by `the_similarity/core/strategy.py`:

- `momentum`
- `mean_reversion`
- `breakout`

Entries require the confidence threshold to pass first. Exits use projected percentiles:

- long stop ≈ `P10`
- long target ≈ `P75`
- short stop ≈ `P90`
- short target ≈ `P25`

## Install in TradingView

1. Open TradingView Pine Editor.
2. Paste either script into a new editor tab.
3. Save, then add it to a chart.
4. Start with defaults and tune `Search Lookback`, `Pattern Length`, and the scale set for your market/timeframe.

## Verification status

These scripts were grounded against the repo's matcher / projector / strategy modules and written to Pine v6 syntax patterns, but Pine cannot be compiled in this local environment. Repo-local validation therefore focuses on source review and unaffected local project checks rather than TradingView compilation.
