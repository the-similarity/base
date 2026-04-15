# Slice catalogue v1 — 2026-04-14

**Status:** live on `main` via feat/canonical-slice-catalogue (PR #118).

**Source:** `research/autoresearch/slices/catalogue.yaml`. See [[benchmark_slices]] for structure + append-only rule.

## Per-regime slice counts

| Regime | Slices | Notes |
|---|---|---|
| `calm` | 5 | SPY 2013-15, SPY 2017, NVDA 2016 pre-breakout, AAPL 2019, BTC 2019 range |
| `crisis` | 9 | GFC 2008, Flash Crash 2010, Volmageddon 2018, COVID 2020 (SPY + NVDA), 2022 rate-hike (SPY + NVDA), crypto 2022 (BTC + ETH) |
| `trend` | 9 | 6 LEGACY 1A (spy-bull, spy/nvda/tsla/btc long-run) + NVDA/TSLA/SPY melt-ups + BTC parabolas |
| `mean_reverting` | 4 | SPY 2015-16 range, NVDA 2022-pre-AI, AAPL 2016, BTC 2019 range |
| **Total** | **27** | |

## Cross-asset pairs (3)

| pair_id | regime | legs | join_rule |
|---|---|---|---|
| `spy-vs-nvda-covid` | crisis | spy-covid-2020 + nvda-covid-2020 | intersection |
| `btc-vs-eth-crypto-winter-2022` | crisis | btc-collapse-2022 + eth-collapse-2022 | intersection |
| `spy-vs-btc-covid-rally` | trend | spy-post-covid-rally-2020-2021 + btc-parabola-2020-2021 | left_anchor |

## Slices marked `missing_data: true`

| id | Window | Why |
|---|---|---|
| `btc-parabola-2017` | 2017-01-01..2017-12-31 | Dataset catalog starts 2019-09-23 on `crypto/btc_usdt/1d.parquet`; runners synth-fallback. |

## Known gaps

- **No `forex` regime coverage yet.** Catalogue declares `forex` in `asset_classes` but no slice uses it. Add if/when we wire FX datasets.
- **No `commodity` slice.** Declared enum value, no coverage.
- **No intraday (`1h` / `15m`) slices.** All entries are `1d`. Intraday coverage is a Phase 3 item.
- **`spy-flash-crash-2010`** has `min_bars: 40` — well below the 200 default. Some Tier 2 methods may skip this slice; callers honor `min_bars` per-slice.
- **`btc-calm-2019-range`** starts at dataset availability boundary (`2019-09-23`); window is ~100 bars only.
- **Mean-reverting count is the smallest** (4). If a regime-conditional evaluation lane needs more mean_reverting data, add AAPL 2020-21 range, SPY 2011 debt-ceiling range, etc.

## How migrations landed

- `research/autoresearch/retrieval_bench/slices.yaml` — 6 slices migrated (all LEGACY 1A IDs preserved by append-only rule). `run_bench.load_spec` now dual-mode: inline (legacy) OR catalogue-id reference.
- `research/autoresearch/benchmarks/projector-v2-core-v1.yaml` — `canonical_slices` now use `catalogue_slice_ids` instead of inlined `symbols: [{path}]`.

## Verification

```bash
# Validator (all invariants):
python -m research.autoresearch.slices.validate

# Unit tests (33 total):
python -m pytest research/autoresearch/slices/ -v

# 1A bench still resolves its slice IDs via the catalogue:
python -c "from research.autoresearch.retrieval_bench.run_bench import load_spec; \
           print(len(load_spec().slices), 'slices resolved')"
```

## Next

- [ ] Backfill `forex` and `commodity` slices when FX / commodity datasets land.
- [ ] Intraday slices once 1h / 15m data is in the daily refresh.
- [ ] More `mean_reverting` entries if regime-conditional ensemble needs tighter per-regime CRPS estimates.
- [ ] Foundation-model bench + parameter-sweep lane should adopt the loader (currently not migrated).
