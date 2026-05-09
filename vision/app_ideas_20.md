# 20 App Ideas Powered by the Engine — Path to $10M ARR

## The atomic primitive we sell

> **Given any time series (or 2D field), find the closest historical analogues and project the present forward with a calibrated forecast cone — backed by 9 methods (DTW, MASS/Matrix Profile, SAX, Wavelet Leaders, Koopman, EMD, TDA, Transfer Entropy, Bempedelis) ensembled with conformal calibration.**

Everything below is a wrapper around that primitive plus the supporting capabilities we already have: walk-forward backtester, synthetic data (block-bootstrap + fidelity/privacy/utility scorecards), 2D pattern matching, strategy/portfolio/alerts, Pine Script mirror, fractal terrain, registry/artifacts/scorecards platform spine.

## ARR math reality check

To hit $10M ARR you need roughly **one** of these to land:
- **B2C prosumer**: 30k subs × $30/mo  (≈ Fractal, Cone, Crypto Radar, Vital Mirror)
- **B2B SMB**: 1k teams × $850/mo  (≈ Creator Pulse, Incident Twin, SaaS Twin)
- **B2B mid-market**: 200 customers × $4,200/mo  (≈ Macro Terminal, Demand Twin)
- **Enterprise**: 25 logos × $33k/mo  (≈ Grid Forecast, MachineWatch)

Diversifying across one B2C hit + two B2B niches is the safest portfolio. Below I rank the **Top 3 bets** at the end.

---

## Finance / Trading (engine's home turf — fastest to revenue)

### 1. Fractal — analogue chart for retail traders  *(web)*
- **User**: active retail traders, swing/options crowd
- **Engine**: full 9-method match on every visible chart; live forecast cone; alerts on new analogues
- **Differentiator vs TradingView/TrendSpider**: they show indicators; we show *what actually happened next every other time this pattern appeared*. No competitor has DTW+Koopman+conformal in a chart UI.
- **Pricing**: $29 / $79 / $199 tiers
- **$10M path**: 30k subs blended ~$30 → $10.8M ARR. TradingView cracked $200M+, even 5% capture works.

### 2. Cone — "where is my stock going?"  *(iOS)*
- **User**: casual investors, Robinhood/Public crowd
- **Engine**: tap a ticker → P10/P50/P90 cone for next 5/20/60 days from analogue ensemble; push notification when a watchlist ticker hits a high-confidence analogue cluster
- **Differentiator**: Robinhood/Public have no forecasting. We're the only consumer iOS app with a calibrated cone.
- **Pricing**: free tier (2 tickers) + $9.99/mo Pro
- **$10M path**: 100k subs × $10 = $12M. App Store distribution does the heavy lifting.

### 3. Macro Analogue Terminal  *(web, B2B)*
- **User**: hedge funds, family offices, macro PMs, sell-side strategists
- **Engine**: cross-asset analogue search across 70 years of macro series; "this regime looks like 1994/2007/2018"; transfer-entropy-driven causal panel
- **Differentiator vs Bloomberg/Macrobond**: data terminals tell you *what is*; we tell you *what comes next based on the closest priors*.
- **Pricing**: $3k/mo seat, $15k/mo team
- **$10M path**: 250 teams × $3.5k = $10.5M. Plausible — Macrobond has thousands of seats at higher ASP.

### 4. Crypto Radar  *(web)*
- **User**: crypto retail, CT degens
- **Engine**: continuous analogue scan across 5,000 tokens; surfaces "BTC at this RSI/funding/realized-vol combo has only happened 11 times — here's what came next"
- **Differentiator**: Glassnode/CoinMetrics show *current* on-chain state; we show *historical analogue cone*.
- **Pricing**: $19 / $49 / $149
- **$10M path**: 35k subs blended $25 → $10.5M. Crypto's volatility means engagement is high.

### 5. Backtest Studio  *(Mac Electron + cloud)*
- **User**: aspiring quants, prop traders, factor researchers
- **Engine**: drag-drop strategy builder over our walk-forward backtester; analogue-driven entries; CRPS/calibration scorecards
- **Differentiator**: QuantConnect/Backtrader require code; ours is GUI + analogue-native (no other backtester treats *historical analogues* as a first-class signal source).
- **Pricing**: $99/mo or $999/yr; data add-ons
- **$10M path**: 9k subs × $99 = $10.7M

### 6. Portfolio Co-Pilot  *(Mac Electron menubar)*
- **User**: RIAs, sophisticated PA managers, $1M+ self-directed
- **Engine**: always-on regime monitor; "your portfolio's drawdown profile matches Q1 2018 — here's what worked and what didn't"
- **Differentiator**: this is the OpenClaw/Raycast-style ambient experience for portfolio risk. Nothing comparable exists.
- **Pricing**: $49/mo personal, $499/mo for advisors per book
- **$10M path**: 5k advisors × $200 = $12M

### 7. Pine Lab — strategy generator for TradingView  *(web)*
- **User**: 60M TradingView users who want auto-generated Pine strategies
- **Engine**: we already have the Pine Script mirror; productize it as "describe a strategy in English, we generate Pine + backtest + analogue-validated cone"
- **Pricing**: $19/mo, one-time $199 lifetime
- **$10M path**: 50k × $19 monthly cohort cycling = ~$11M with churn

---

## Health / Biometrics (massive iOS TAM, recurring use)

### 8. Vital Mirror  *(iOS)*
- **User**: Apple Health / Whoop / Oura users (~30M between platforms)
- **Engine**: HRV / RHR / sleep / strain time-series analogue across the user's own history *and* an anonymized cohort; "every other time your HRV trended down 4 days like this, you got sick within 6 days"
- **Differentiator**: Whoop / Oura tell you "today's score"; we tell you "your trajectory matches X past episode — here's what came next."
- **Pricing**: $9.99/mo
- **$10M path**: 100k subs × $10 = $12M. Apple Health gives huge top-of-funnel.

### 9. Gluco Twin  *(iOS, CGM-tethered)*
- **User**: 4M+ CGM wearers (T1D, T2D, biohackers via Levels/Stelo/Lingo)
- **Engine**: glucose curve analogue with 2D wavelet on (glucose, food/exercise) joint surface; predicts next-2h excursion
- **Differentiator**: Levels/Lingo show data; nobody projects forward with calibrated cones from your own analogue history.
- **Pricing**: $14.99/mo (clinical-adjacent crowd will pay)
- **$10M path**: 60k × $15 = $10.8M

### 10. Sleep Twin  *(iOS)*
- **User**: AutoSleep / Sleep Cycle / Apple Health power users
- **Engine**: stage-time-series + HRV analogue; "your last week looks like the run-up to your worst sleep month — here are the levers that helped historically"
- **Pricing**: $5.99/mo
- **$10M path**: bundle with Vital Mirror

---

## Industrial / Energy / Climate (high ACV)

### 11. Grid Forecast  *(web, B2B enterprise)*
- **User**: utilities, ISO/RTO traders, virtual power plants, BESS operators
- **Engine**: load + price + weather analogue forecasting; conformal P10/P90 for day-ahead and intraday
- **Differentiator vs Genscape/Yes Energy**: data vendors; we're the only analogue-native forecaster with calibrated tails (which is what risk teams actually need).
- **Pricing**: $50k–$250k/yr
- **$10M path**: 80 utilities × $125k = $10M. Long sales cycle but defensible.

### 12. MachineWatch  *(Electron + web, B2B)*
- **User**: factory ops, wind turbines, fleet operators
- **Engine**: vibration / temp / current time-series analogue → flags pre-failure signatures; 2D wavelet on spectrograms
- **Differentiator vs Augury/Uptake**: those need labeled failure data; analogue search works zero-shot — every past trace is implicit training.
- **Pricing**: $200/sensor/mo
- **$10M path**: 4,200 sensors total = 60 mid-size plants. Achievable.

### 13. StormMatch  *(web + iOS)*
- **User**: insurance underwriters, ag coops, emergency mgmt, weather geeks
- **Engine**: 2D wavelet leaders on satellite imagery + wind-field time series; "Hurricane X track/intensity matches 1989 Hugo + 2017 Maria; here's the cone of historical landfall outcomes"
- **Differentiator**: NHC publishes a single deterministic + ensemble cone; we publish a *historical-analogue* cone with named priors that underwriters can trust.
- **Pricing**: $99/mo retail, $5k–50k/yr enterprise
- **$10M path**: 50 insurers × $100k + 20k retail × $99 ≈ $10M

### 14. Climate Scenario Bench  *(web, B2B)*
- **User**: climate-risk teams at banks, asset managers (TCFD/ISSB-driven spend)
- **Engine**: synthetic data pipeline (block-bootstrap with regime conditioning) + analogue search across reanalysis datasets; produces auditable scenario fan-charts
- **Pricing**: $30k–150k/yr
- **$10M path**: 100 customers × $100k = $10M. Regulatory tailwind is real.

---

## SaaS / B2B Operational

### 15. Incident Twin  *(web + Mac menubar Electron)*
- **User**: SRE/DevOps teams (Datadog/PagerDuty buyers)
- **Engine**: live metric streams (latency, error rate, queue depth) → analogue lookup against past incidents; "this curve matches the Mar 14 Redis OOM at 87% confidence"
- **Differentiator vs Datadog Watchdog/AIOps**: their anomaly detection says *something is weird*; we say *which past incident this resembles*, which is what on-callers actually need at 3am.
- **Pricing**: $20/host/mo or $2k–10k/mo team
- **$10M path**: 1,500 teams × $600 = $10.8M. Sells naturally bottom-up.

### 16. Demand Twin  *(web, B2B)*
- **User**: DTC, CPG, retail planners
- **Engine**: SKU-level demand analogue (with promo / seasonality / weather covariates); calibrated stockout cones
- **Differentiator vs o9/Blue Yonder**: they take 18 months to deploy; we ship in a week because analogue search is zero-shot.
- **Pricing**: $2k–20k/mo
- **$10M path**: 200 brands × $4.2k = $10M

### 17. SaaS Twin  *(web)*
- **User**: founders, VC investors, RevOps
- **Engine**: MRR / churn / NPS / activation curve analogue against an anonymized cohort of public + opt-in private SaaS data; "your week-12 retention looks like Notion at the same stage"
- **Differentiator**: ChartMogul/Mosaic show *your* metrics; we show *which past company you most resemble and what came next*.
- **Pricing**: $99/mo founder, $500–2k/mo VC firm
- **$10M path**: 6k founders × $99 + 200 funds × $1k = $9.5M

### 18. Creator Pulse  *(web)*
- **User**: YouTubers, TikTok creators, MCNs, talent agencies
- **Engine**: view-curve analogue; "this video's hour-1 / day-1 trajectory matches viral hits at 73%; here's the projected 30-day cone"
- **Differentiator vs Tubular/VidIQ**: those score tags/SEO; we forecast the *trajectory shape* which is what monetization desks care about.
- **Pricing**: $29 creator, $499 agency, $5k MCN
- **$10M path**: 20k creators × $29 + 800 agencies × $499 = $11.7M

---

## Data / Synthetic / Platform

### 19. Synth Studio  *(web + CLI/SDK)*
- **User**: data scientists, ML platform teams, fintech compliance, healthcare analytics
- **Engine**: our existing `the_similarity/synthetic/` (block-bootstrap, regime-conditional, fidelity/privacy/utility scorecards) productized as Gretel/Mostly-AI competitor *for time series specifically* — a niche they underserve
- **Differentiator**: Gretel is tabular-first; we're time-series-native with conformal utility validation built in.
- **Pricing**: $499/mo team, $5k/mo enterprise
- **$10M path**: 1.5k teams blended $550 = $10M

### 20. Terra Studio  *(Mac Electron)*
- **User**: indie game devs, archviz, film VFX
- **Engine**: our fractal terrain + 2D analogue search ("make this terrain look more like the Dolomites")
- **Differentiator vs World Machine/Gaea**: they're parametric; we're *retrieval-based* — point at a real-world DEM tile and we synthesize coherent analogues.
- **Pricing**: $99 perpetual + $19/mo cloud render
- **$10M path**: this is the long-tail bet — likely $1–3M ARR ceiling. Include for brand/halo, not as a $10M lever.

---

## Top 3 bets I'd actually fund first

| Rank | App | Why this one |
|------|-----|--------------|
| **1** | **Fractal (web)** | Engine is already 90% there (Pine mirror, backtester, alerts, Next.js frontend). Fastest time-to-revenue. Retail trader TAM is proven by TradingView/TrendSpider. |
| **2** | **Macro Analogue Terminal (web, B2B)** | Highest ACV per logo; only ~250 customers needed for $10M; engine's analogue + transfer-entropy story sells itself to macro PMs. Also creates the pricing umbrella under which Fractal looks like a steal. |
| **3** | **Vital Mirror (iOS)** *or* **Incident Twin (B2B SRE)** | Pick based on team comfort with consumer vs B2B GTM. Vital Mirror has bigger ceiling and Apple Health distribution; Incident Twin has shorter sales cycle and lands inside existing Datadog budgets. |

**Portfolio rationale**: 1 + 2 are highly correlated (both ride financial-markets engagement). Adding 3 from a different vertical (health or devops) de-risks against a market downturn that could deflate both finance bets simultaneously.

## What's missing from the engine to ship these

- **Real-time streaming ingest** (currently batch-oriented) — needed for Fractal, Cone, Incident Twin
- **Multi-tenant registry isolation** — platform spine is single-tenant today
- **iOS SDK / on-device inference** — for Cone, Vital Mirror, Gluco Twin (privacy-sensitive, needs local match)
- **Domain-specific analogue universes** — pre-built corpora per app (macro series for #3, vibration spectra for #12, glucose curves for #9)
- **Semantic enrichment of analogues** — every match needs a one-liner explanation ("this is the 2018 vol-mageddon analogue") which means a metadata layer over the registry

These are 1–3 month investments each, not greenfield rebuilds. The engine is already most of the way there.
