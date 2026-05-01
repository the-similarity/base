# Correia (2015) — An Analog Model for Global Macro Investing

**Source**: Gonçalo Guimarães Correia, *An Analog Model for Global Macro Investing*. Directed Research Project (MS Finance), Nova School of Business and Economics, January 2015. Supervisor: Pedro Lameira.

## Why this matters for [[the_similarity]]

This is the closest published academic precedent to the engine's core thesis: **find historical analogs of the current regime, vote over what worked next, allocate accordingly**. It validates the approach for global-macro asset allocation, *and* — more usefully — documents where the approach breaks. Reading it as a strict subset of what the engine already does:

| Correia (2015) | the_similarity engine |
|---|---|
| 1 method (Pearson correlation k-NN) | 9 methods (DTW, SAX+MASS, Matrix Profile, Wavelet Leaders, Koopman, EMD, TDA, Transfer Entropy, Pearson) |
| Fixed top-5 neighbours | Weighted top-K with confidence decay + Koopman blend |
| Majority-vote / best-Sharpe pick | Ensemble forecasting (Monte Carlo, regime-conditional, conformal) |
| 1-month horizon, monthly rebalance | Cross-timeframe search, walk-forward backtester with hit_rate / calibration / CRPS |
| 6 hand-picked features | Generic feature interface — but useful as a curated *preset* |

So Correia's paper is not a method we need to implement. It's a **citation**, a **feature preset**, and a **honest scope boundary** we should bake into our messaging.

## Method (compact)

- Each "regime" = one month = a 20-day × N-variable matrix of standardised daily changes.
- Distance between two months: Pearson correlation between flattened matrices (not Euclidean — the paper argues correlation is robust to amplitude differences).
- For an unknown month *A*, compute correlation to every prior month *B_i*. Take the top-5 most-correlated months. For each analog, look at its subsequent month and identify the asset/portfolio with the highest info-Sharpe (`r_p / σ`). Allocate to the **mode** across the 5 analogs ("majority vote").
- Walk-forward: trained on 1985–1990, tested 1991–2014.

## Feature set ("primary case")

The paper tests two feature sets and abandons the second. Useful set:

| Code | Variable | Description |
|---|---|---|
| `FED` | 3-month constant maturity yield | Short-rate / monetary policy proxy |
| `STY` | 2-year constant maturity yield | Mid-curve |
| `LTY` | 10-year constant maturity yield | Long-rate / growth & inflation expectations |
| `TERM` | 10Y – 3M spread | Yield curve slope (recession indicator, Estrella & Mishkin 1996) |
| `MRP` | S&P 500 daily return rate | Market risk premium / sentiment |
| `FX` | EUR/USD rate of change | Cross-currency macro signal |

Mirrored in code as `the_similarity/finance/presets.py::MACRO_US_CORREIA_2015`.

## Results — three test cases

### 1. Asset Allocation (Equity / Bond / Cash)

**Dynamic version** (variable Equity/Bond weights, no Cash) — the paper's headline:

| Metric | Dynamic Analog | Global 60/40 |
|---|---|---|
| Annualised return | **10.6%** | 8.3% |
| Annualised vol | 8.4% | 11.4% |
| Sharpe | **1.27** | 0.74 |
| Max drawdown | **−16.7%** | −41.1% |
| Market beta | 0.21 | −0.05 |

→ Strong evidence that analog matching adds value to broad asset allocation.

### 2. Style investing (Value / Size / Momentum)

| Metric | Analog | Equal-weight |
|---|---|---|
| Sharpe | 0.99 | **1.97** |
| Max drawdown | **−73.5%** | −22.7% |

→ **Failure case.** The model degenerates into a Momentum-tilt and inherits Momentum's 73% drawdown. Equal-weight crushes it.

### 3. Industry sectors

→ Also fails. Max drawdown −74.9% vs equal-weight −58%.

## The honest finding (cite this)

> *"The variables that we find reliable indicators to find analogous periods are certainly not the same that allow investors to extract the likelihood of Equity and Style allocations."*

Translated for [[the_similarity]]: **the analog approach has a signal-to-noise floor**. It works when the target decision is broad (asset class) and the regime features are macro-load-bearing. It fails when the target is fine-grained (style, sector) because the noise component dominates.

This should inform our defaults:
1. Recommend the engine for asset-allocation / regime-rotation tasks first.
2. Warn / lower confidence when target hit_rate ≈ baseline despite high analog correlation.
3. The conformal cone in `the_similarity/core/projector_adaptive_conformal.py` already captures this — it widens when the regime is uncertain. Correia had no analog of this, which is part of why his style/sector tests blew up.

## Macro-regime evaluation framework (Table 7)

Correia evaluates performance across four regime axes — useful as a backtest slicing dimension:

| Regime axis | Indicator | Threshold |
|---|---|---|
| **Growth** | Quarterly real GDP growth | vs. 2-year average → Up/Down |
| **Inflation** | CPI YoY | vs. 5-year average → Up/Down |
| **Volatility** | CBOE VIX | vs. 1-year average → Bullish/Bearish |
| **Liquidity** | FED Funds rate Δ | Hike → Down, Cut → Up |

Mirrored in code as `the_similarity/finance/regime_slice.py` — accepts a returns Series + macro regime label series and reports per-regime info-Sharpe. Lets us claim "robust in bearish + tightening regimes" with evidence (Correia's own Tables 8–10 show the analog model excels exactly there).

## Method primer references (cited in paper)

- Estrella & Mishkin (1996, 1998) — yield curve as recession predictor.
- Estrella & Trubin (2006) — practical issues using yield curve slopes.
- Fama & French (1989) — business conditions and expected returns.
- Ilmanen, Maloney & Ross (2014) — *Exploring Macroeconomic Sensitivities* (JPM) — closest analytical framework.
- Ramli, Ismail & Wooi (2013) — k-NN for currency crisis prediction (the closest k-NN-in-finance citation).

## What we should NOT take from this paper

- The single-method (Pearson) approach. Our 9-method ensemble strictly dominates.
- Fixed top-5. Our weighted top-K with decay handles regime ambiguity better.
- The integer-percentile "best Sharpe" allocation rule — too brittle; our [[forecast cone]] is the proper generalisation.
- The 1-month rigid window — our cross-timeframe search relaxes this.

## Cross-links

- [[concepts]] — engine method explainers that supersede Correia's single-distance approach.
- `the_similarity/finance/presets.py` — `MACRO_US_CORREIA_2015` feature pack.
- `the_similarity/finance/regime_slice.py` — Correia Table-7 regime slicing for backtest reports.
- `obsidian_thesim/research/full-text/methods/05-pattern-forecasting-backtesting.md` — broader analog-forecasting survey.
