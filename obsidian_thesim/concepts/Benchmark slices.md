# Benchmark slices

Canonical dataset slices used by the autoresearch framework to evaluate retrieval quality, projector calibration, and downstream walk-forward accuracy. Defined in YAML benchmark files under `research/autoresearch/benchmarks/`.

## Why fixed slices?

Reproducibility requires that every experiment runs against the **same symbols, date ranges, and trial parameters**. Without explicit membership, "equities-daily-core" is ambiguous -- different agents or scripts might pick different symbols. Pinning the slice contents to the data catalog (`the-similarity-data/manifests/catalog.json`) eliminates that drift.

## Slice definitions

### equities-daily-core

| Field | Value |
|-------|-------|
| Timeframe | 1d |
| Source | Stooq |
| Symbols | aapl, amzn, dia, goog, iwm, meta, msft, nvda, qqq, spy, tsla |
| Date range | Varies per symbol (earliest: 1984-09-07, latest end: 2026-03-20) |
| Total rows | ~76,776 across 11 symbols |

**Purpose.** Liquid US large-cap equities and major ETFs. Covers secular bull markets, corrections, sideways regimes, and sector rotations across 15-40 years of daily data. This is the primary slice for both the JEPA retrieval lane and the projector calibration lane.

### crypto-daily-core

| Field | Value |
|-------|-------|
| Timeframe | 1d |
| Source | CCXT |
| Symbols | btc_usdt, eth_usdt, sol_usdt, xrp_usdt |
| Date range | 2019-09-23 to 2026-03-23 (sol starts 2020-09-18) |
| Total rows | ~8,225 across 4 symbols |

**Purpose.** Higher volatility than equities with fat-tailed return distributions. Tests whether the matcher retrieves meaningful analogues under extreme moves and whether the projector's uncertainty cone widens appropriately.

### stress-regimes-core

Date sub-ranges carved from the equities and crypto slices above. The benchmark runner filters each parquet to `[stress_start, stress_end]` before sampling trials.

| Label | Symbol | Window | Rationale |
|-------|--------|--------|-----------|
| covid-crash-equities | spy | 2020-02-19 to 2020-04-30 | Fastest 30% drawdown in S&P history |
| covid-crash-tech | qqq | 2020-02-19 to 2020-04-30 | Tech-concentrated drawdown and V-recovery |
| crypto-winter-2022-btc | btc_usdt | 2021-11-01 to 2022-07-31 | Prolonged drawdown with LUNA/3AC capitulation |
| crypto-winter-2022-eth | eth_usdt | 2021-11-01 to 2022-07-31 | Parallel crypto winter with merge-narrative divergence |
| rate-hike-bear-2022 | spy | 2022-01-03 to 2022-10-14 | Grinding bear from Fed tightening (slow, persistent) |
| growth-crash-2022-tsla | tsla | 2021-11-01 to 2022-12-31 | Extreme single-name mega-cap drawdown |
| oil-price-war-2020 | spy | 2020-03-01 to 2020-05-15 | Commodity dislocation reflected in broad-market stress |

**Purpose.** Verify that retrieval and projection stay calibrated under tail events. Crisis windows have different volatility signatures (sharp V-shaped vs. grinding, equity vs. crypto) to catch overfitting to a single stress archetype.

## Which benchmarks use which slices

| Benchmark | equities-daily-core | crypto-daily-core | stress-regimes-core |
|-----------|:---:|:---:|:---:|
| [[jepa-retrieval-core-v1]] | yes | yes | yes |
| [[projector-calibration-core-v1]] | yes | yes | -- |

The projector lane omits stress-regimes-core because its primary concern is cone shaping under normal and high-vol regimes, not novelty detection.

## Related

- [[Nine-method pipeline]] -- the matcher whose output these benchmarks evaluate
- [[Engine map]] -- where `backtester.py`, `projector.py`, and `matcher.py` live
- `research/autoresearch/benchmarks/` -- YAML source of truth
- `the-similarity-data/manifests/catalog.json` -- full 52-dataset catalog
