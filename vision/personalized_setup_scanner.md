# Personalized Setup Scanner — v1 Plan

> CEO plan + v1 design + worktree split for parallel execution.
> Generated 2026-05-07 via `/plan-ceo-review` (SCOPE EXPANSION mode).
> Status: **ACTIVE**, ready to dispatch to worktrees.

## TL;DR

A personalized cross-instrument scanner for active retail traders. User defines their setup (drag a region on any chart). Engine scans 36 instruments (crypto + forex/gold) for analogs of that setup. On signup, user instantly sees 20 historical analogs and what happened next. When the setup appears live anywhere in the universe, alerts fire to email + Discord. Every alert and analog has thumbs-up/down feedback that feeds the goodrun filter.

5 alpha buyers committed at $29/mo (conditional on "if it works") via phone calls on 2026-05-07. Build target: ~10 days human / ~3-4 days CC.

---

## Vision

### 10x check

Turn the product from "Buba's pattern matcher" into a **marketplace of trading setups**. Top traders publish setups; subscribers pay to follow them. Every alert and goodrun outcome compounds into a shared learning filter no competitor can replicate. Substack-for-traders with verified track records baked in. Network-effects flywheel: more setups → more subscribers → more goodrun signal → sharper filter → better alerts → higher retention → more data.

This is the trajectory that makes the $100M raise math work, because marketplace + compounding-data has network effects retail-only does not. v1 builds the engine and the data hooks; v3 turns it into the marketplace.

### Year-3 felt experience

Trader sits down Sunday night, opens the app:

- "Your setups are active on 12 instruments right now." Top 3 by historical edge with confidence scores.
- "3 traders you follow had setups fire this week." Two played out, one didn't. Journal attached.
- "Market regime shifted Tuesday." Setups similar to current conditions historically have 64% upward bias over 5 sessions. 41 historical analogs.

No more "what should I trade?" anxiety. The system has scanned everything, knows what the trader cares about, surfaces only what matters with receipts attached. Trading shifts from anxious search to evidence-backed selection.

---

## v1 Product Spec

### Problem

Active retail traders have setups they trust but watch one chart at a time. They miss when those setups appear on other instruments. Existing scanners (TradingView, Trendspider, Trade Ideas) detect generic patterns, not the user's specific setup. There is no tool that watches every liquid instrument for a user's idiosyncratic setup, returns historical analogs with continuations, and learns from the user's own win-loss feedback.

### Demand evidence

- **Founder use:** existing similarity engine used on XAUUSD, recently informed a long that made $700. Counterfactual: regular technical analysis on a single chart.
- **Phone calls 2026-05-07:** 5 traders in personal network said yes-pending-proof at $19/mo. All 5 said $19 felt cheap if the product proves itself. Final price set to $29/mo.
- **Segments:** 2 crypto traders, 1 day trader (equities, deferred to v2), 2 forex/gold traders.
- **Setup-articulation premise:** founder reports buyers can articulate setups via chart-region selection in <60 seconds. Re-confirm with 2 buyers via screen-share before code.

### Target user and wedge

Active retail trader with a defined setup, trades crypto or forex/gold (equities v2), willing to pay $29/mo for personalized cross-instrument alerts grounded in historical analogs.

**Wedge:** alerts + cold-backtest onboarding. Sign up → define setup → see top-5 analogs (with "show 15 more" reveal) instantly → alerts fire when setup appears on any of the 36 covered instruments.

### Universe (v1)

- ~30 top crypto pairs on Binance (free public API)
- 6 FX majors: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD
- XAUUSD (gold)
- **Total: ~36 instruments**

Equities (top 50 S&P daily) deferred to v2. Day-trader buyer holds the founding-plan slot at $29 grandfathered.

### Pricing

- Alpha cohort: $29/mo, grandfathered
- Public launch: $49/mo (after goodrun calibration)
- Institutional / B2B: $1K-10K/mo (after forward win-rate proof)
- Money-back guarantee for month 1, no free trial

### Alert delivery

Email (SMTP) + Discord webhook for v1. Telegram conditional: ask each buyer their preferred channel; build only if at least one chooses Telegram.

### Goodrun feedback hook (the moat)

Every alert and every analog gets thumbs-up / thumbs-down + optional free-text. Persisted from day 1 even if filter logic does not yet compute on it. Without this hook, the goodrun filter has no input data when v2 begins; this is the moat, do not skip the data capture.

### Compliance posture

Research subscription, **not** investment advice. Marketing copy must avoid "guarantee," "make money," "signal," "investment advice." Disclaimer in BOTH places:

- Signup click-through with consent record ("Not financial advice. Past performance does not guarantee future results.")
- Footer of every email + Discord alert (same line)

---

## Premises (load-bearing, with confidence)

| # | Premise | Confidence | Test |
|---|---------|------------|------|
| 1 | Users articulate setups via chart-region in <60s | Provisional | Screen-share with 2 buyers before code |
| 2 | Personalized cross-instrument matching differentiates vs Trendspider/Trade Ideas | Plausible | Stranger pitch test before public launch |
| 3 | Engine signal is decision-relevant, not noise | Highest risk | Lead indicator: % of last 20 alerts marked thumbs-up after 1 week. <50% by month 2 = kill or rework |
| 4 | Research-tool framing avoids regulated-advisor line | Holds | Marketing copy review before public widget launch; consult counsel before public launch |
| 5 | 5 friends are representative of broader retail trader market | Lowest | v2 milestone: first stranger pays without founder phone call |

---

## Locked v1 Scope (with effort estimates)

### Core build (~10 days human / ~3-4 days CC)

| # | Item | Effort | Owner-able worktree |
|---|------|--------|---------------------|
| 1 | Multi-tenant `user_id` foreign key on setups + scopes | S | Backend |
| 2 | Setup definition: chart-region selector + "live capture" button | S | Frontend |
| 3 | Cold-backtest onboarding: top-5 analogs + "show 15 more" reveal | M | Frontend |
| 4 | Cross-instrument scanner over 36-instrument universe | M | Backend |
| 5 | Email delivery (SMTP) with retry + dead-letter | S | Delivery |
| 6 | Discord webhook delivery with retry + dead-letter | S | Delivery |
| 7 | Alert overlay component (analog over current price) | S | Frontend |
| 8 | Public widget at thesimilarity.tech/try (zero-signup demo) | S | Frontend |
| 9 | Stripe Checkout $29/mo + idempotent webhook + month-1 money-back | M | Delivery |
| 10 | Disclaimer click-through (signup) + footer (every alert) | XS | Frontend |
| 11 | Pine Script attribution + leadgen link in `tradingview/` | XS | Integrations |
| 12 | Thumbs-up/down feedback hook on every alert + analog | S | Frontend + Backend (shared schema) |

### Pre-launch checklist (manual, founder-owned)

- [ ] Day-trader holdover message: "v2 stocks coming, $29 grandfathered, founding-plan reserved"
- [ ] Channel survey to all 5 buyers (email/Discord/Telegram)
- [ ] Verbatim "what does 'works' mean to you?" answer from each of 5 buyers
- [ ] Screen-share with 2 buyers: confirm <60s setup articulation
- [ ] Stripe account setup: $29/mo product, Checkout link, webhook secret
- [ ] TradingView Pine content-policy check before publishing the leadgen link update
- [ ] `auth.py` row-level scoping audit before any signup goes live
- [ ] Marketing copy review: scan all visible text for forbidden phrasings ("guarantee," "make money," "signal," "investment advice")

---

## Worktree split (parallel execution, minimal collision)

Four worktrees, file boundaries chosen so two agents do not edit the same file. Backend worktree ships schema first; others mock against the contract until it lands.

### Worktree A: Backend / engine surfaces

Owns the schema, the scanner orchestration, and reuse of the existing engine.

- Multi-tenant setups schema (`user_id` FK on every relevant table, migrations)
- Cross-instrument scanner orchestration over 36-instrument universe (crypto via Binance public API, FX + gold via OANDA or Yahoo)
- Wires existing `the_similarity/core/matcher.py` and `projector.py` into the scanner loop
- Persists thumbs-up/down feedback to existing goodrun infrastructure (#283/#284/#287)

**Files:** `the_similarity/core/scanner.py` (new), `the_similarity/platform/registry.py` (extend), migrations under `the_similarity/platform/`, schema definitions.

**Ships first.** Other worktrees mock against the schema contract until this lands.

### Worktree B: Delivery + billing

Owns the outbound channels and money flow.

- Email delivery (SMTP) with retry + dead-letter
- Discord webhook delivery with retry + dead-letter
- Stripe Checkout integration ($29/mo, month-1 money-back)
- Stripe webhook handler (idempotent, `idempotency_key`)
- Disclaimer footer template applied to every email + Discord alert

**Files:** `the-similarity-api/app/alerts.py` (new), `the-similarity-api/app/billing.py` (new), `the-similarity-api/app/main.py` (route registration only).

### Worktree C: Frontend / UX

Owns everything the user touches inside the app.

- Setup definition: chart-region selector + live-capture button on existing workstation window
- Cold-backtest onboarding view (top-5 by default + "show 15 more" reveal)
- Alert overlay component (analog superimposed on current price)
- Disclaimer click-through on signup with consent record
- Thumbs-up/down feedback hook UI
- Mobile-responsive cold-backtest, loading progress >1s, empty state for "zero alerts yet"

**Files:** `the-similarity-app/src/components/setup/` (new), `the-similarity-app/src/components/onboarding/` (new), `the-similarity-app/src/components/alerts/` (new). Reuses existing window selector from finance workstation.

### Worktree D: Public surfaces + audit

Owns the leadgen surfaces and the pre-launch hardening.

- Public widget at `thesimilarity.tech/try` (zero-signup, paste any chart URL, see analogs)
- Pine Script attribution + leadgen link in `tradingview/` (after content-policy check)
- Marketing copy review across landing pages, app surfaces, alert templates
- `auth.py` row-level scoping audit
- "Low-coverage setup" indicator when engine returns <X analogs

**Files:** `the-similarity-app/src/pages/try/` (new public widget), `tradingview/similarity_indicator.pine` and `tradingview/similarity_strategy.pine` (attribution edit), `the_similarity/core/auth.py` (audit-only, no edits unless gap found).

### Inter-worktree dependencies

```
A (schema + scanner)  ─────▶  B (delivery, consumes scanner events)
                       │
                       ▼
                       C (frontend, reads schema for setups + analogs)
                       │
                       ▼
                       D (public widget reuses cold-backtest endpoint from A+C)
```

A ships first. B + C run in parallel against A's schema (mock the schema if needed during overlap). D depends on A's cold-backtest endpoint and C's component patterns. Order is not strict; B and C can land before D.

### Shared-file conflict prevention

Per CLAUDE.md, only one worktree edits any of these:

- `obsidian_thesim/_MOC.md`: NONE. Orchestrator updates after merge.
- `.gitignore`: only worktree A may edit; others note in PR body what they need added.
- `pyproject.toml`, `CHANGELOG.md`: only worktree A or D, by prior coordination.
- `the_similarity/platform/registry.py`: ONLY worktree A.
- `the-similarity-api/app/main.py`: ONLY worktree B; others register routes via subroutes that B exposes.
- `the_similarity/core/auth.py`: ONLY worktree D, audit-only.

---

## Scope decisions (this session)

| # | Proposal | Decision | Reasoning |
|---|----------|----------|-----------|
| Marketplace of setups (10x bet) | DEFERRED to TODOS (v3+) | v1 retail must seed it; design v1 multi-tenant from day 1 so v3 is not blocked |
| "Why did this match?" overlay | ACCEPTED to v1 | Trust at minute 0 of every alert; directly answers "only if it works" |
| Daily digest email | DEFERRED to TODOS (v2) | Right tool, wrong phase; build at ~month 2 when retention is the question |
| Public landing-page widget | ACCEPTED to v1 | Reuses existing landing page; friends evangelize via shareable demo URL |
| Pine Script leadgen funnel | ACCEPTED to v1 | 30 min CC for permanent passive lead channel via existing infra |
| Multi-timeframe cross-confirmation | DEFERRED to TODOS (v2) | Most retail setups are TF-specific; build when buyers ask |
| Telegram bot | DEFERRED with survey | Build only if buyer-channel survey returns at least one Telegram preference |

### Compressed-review locked decisions

- **Multi-tenant schema from day 1** (architecture, prevents v3 marketplace migration)
- **Low-confidence analog handling: show all matches with confidence warning** (errors, transparency over silence or hiding)
- **Disclaimer in BOTH signup click-through and alert footer** (compliance, belt and suspenders)
- **Cold-backtest output: top 5 by default + "show 15 more" reveal** (UX, fast hit + deep proof on demand)

---

## Deferred to TODOS.md (do not lose these)

- **Marketplace of setups (v3+):** the 10x bet. Top traders publish, subscribers follow, revenue share, leaderboard, verified track records. v1 multi-tenant schema keeps this path open.
- **Daily digest email (v2):** end-of-day summary, hits, goodrun rank vs cohort. Build at month 2.
- **Multi-timeframe cross-confirmation (v2):** scan setup at 15m/1h/4h/1d. Build when buyers ask.
- **Telegram bot (conditional):** build if buyer-channel survey returns ≥1 Telegram preference.
- **Equities v2:** top 50 S&P daily, day-trader holdover converts.
- **Bench items, available on request:** Twitter share, copy-trade button, public setup library, cohort goodrun comparison, backtest replay, marketplace v0.5 leaderboard.

---

## Success criteria

- **Week 1 of v1 launch:** ≥3 of 5 alpha buyers convert from "excited" to paying ($29/mo).
- **Week 4:** ≥2 of those still active and giving thumbs feedback on alerts.
- **Week 8:** ≥1 referral to a non-network trader who pays without a founder phone call.
- **Lead indicator:** Cold-backtest at signup produces "huh, that's interesting" reaction in ≥4 of 5 alpha onboardings (observed during screen-share, not surveyed).
- **Kill criterion:** If <2 of 5 convert at week 1, the wedge is wrong, the engine is not yet useful, or the cohort was wrong. Stop, regroup, do not double-build.

---

## Cross-cutting strategic update

The `project_strategy_horizontal_primitive.md` thesis ("self-similarity primitive IS the product, do not lead with Finance") is **superseded** for this product. The personalized scanner IS leading with Finance, and the demand evidence (5 phone calls, founder $700 trade) supports it. That memory entry should be updated or marked superseded so future sessions do not re-litigate the framing.

The `project_general_prediction_modalities.md` framing ("World's first general prediction") still holds at the long-term level — finance is the first modality, the engine extends to others later. The shift is tactical, not strategic.
