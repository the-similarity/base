# Finance Pilot v1 — Spec

Status: draft, 2026-04-14
Owner: strategy track (1C)
Scope: single end-to-end user workflow on top of The Similarity engine,
deliberately narrow.

## 1. Target user

**Who.** One-to-three discretionary or systematic traders at a small
single-manager equity hedge fund, a prop desk, or a family-office
treasury desk. Team size 1-5, AUM anywhere from $5M to $500M. Not
Two-Sigma-scale quant shops (they build this themselves) and not
zero-experience retail (they lack the judgement to act on probabilistic
cones).

**What they trade.** Liquid US equities and ETFs (SPY, QQQ, single-name
mega-caps), daily bars, holding period 2-10 trading days. They already
have execution and risk tooling; they do NOT have a rigorous analog
database.

**What pains them today.**
1. Their current "pattern recognition" is a chart print-out + 20 years
   of muscle memory. They can describe the setup but cannot cite a
   distribution of past outcomes.
2. Every sizing decision is anecdotal. They cannot answer "when I was
   wrong on this setup in the past, how wrong was I?" in under 5
   minutes.
3. They over-fit to regime. In a grindy range market they keep using
   trending-day rules because they haven't updated their mental
   anchor.
4. Their backtests are point estimates (expected return, win rate).
   They do not have calibrated uncertainty, so position size is by
   gut.

## 2. Input / output of the workflow

Single-user workflow, Python package + thin CLI. No hosted service in
v1. (Hosted is v2.)

### Inputs
- A historical daily price series for one ticker (CSV, parquet, or
  pandas DataFrame).
- An *optional* current query window (defaults to the trailing 30-60
  bars).
- Config for horizon (forward bars), coverage level, min confidence.
- *Optional* trust filter overrides (min_matches, max_calibration_mae,
  min_score). Defaults are conservative.

### Outputs (per query)
- `SearchResults` — ranked analogue windows with score breakdown.
- `Forecast` or `EnsembleForecast` — projection cone P10/P25/P50/P75/P90.
- `TrustDecision` — is the cone trustworthy, score, reasons.
- `CalibrationAwareSignal[]` — direction + position size + threshold
  outcome + review notes. Empty or FLAT when distrust fires.
- `ReviewSummary` — plain-text audit block suitable for a ticket or a
  Slack message. This is the handoff between model and trader.
- Backtest report — calibration, hit rate, coverage, CRPS on a rolling
  window. Used to rebind the trust filter.

Everything is local, deterministic given seeds, and replayable.

## 3. Success metrics

### What would make a design partner sign

A tier-1 prop trader or small-fund PM signs for a 3-month paid pilot
($5k-$25k) if we can show, on *their own ticker universe, their own
historical playbook trades*:

1. **Better calibration than their gut.** At 90% stated coverage, the
   empirical coverage on their 6-month walk-forward is within 5pp of
   90% (e.g. 85-95%), AND the P50 directional hit rate is >= 55% on
   trades where trust=True.
2. **Meaningful veto rate.** The trust filter vetoes 20-40% of
   signals. Too low: the filter is cosmetic. Too high: the engine is
   not useful.
3. **Delta vs naive.** On the same underlying signals, calibration-aware
   sizing produces Sharpe lift >= 0.3 over the naive fixed-size
   baseline in the pilot window. This is the punchline: "you make more
   money on fewer trades."
4. **Workflow fit.** The partner runs the CLI every morning before
   open, takes < 3 minutes per ticker, and actually READS the
   `ReviewSummary` before pulling a trigger. If they skip to the
   number, we failed to build a review artifact worth reading.

### Quant metrics (always reported)
- hit rate, MAE, CRPS — already computed.
- Conformal empirical coverage vs target — already computed.
- Veto rate (% of decision points with trust=False).
- Position-size-weighted P&L delta vs naive threshold.

### Qualitative metrics (pilot call after 30 days)
- Did the trader change their size on >= 3 trades because of the trust
  score? (Target: yes.)
- Did the ReviewSummary catch at least one trade they would have taken
  naively and shouldn't have? (Target: 1+.)
- Would they pay to keep it? (Binary.)

## 4. Scope boundaries

### This pilot explicitly IS NOT

- **Not an execution engine.** We do not route orders. We emit a
  signal and a size; the trader executes through their existing OMS.
- **Not a portfolio optimiser.** Single-ticker in, single-signal out.
  Portfolio roll-up is v2 (the `portfolio.py` scanner exists but is
  out of pilot scope).
- **Not intraday.** Daily bars only. Intraday requires different
  regime math (see `the_similarity/core/regime.py` — vol
  annualisation assumes √252 daily).
- **Not a crypto product.** Crypto is on the roadmap but needs a
  different data pipeline and typically 24/7 bars which break the
  calendar assumptions in the backtester.
- **Not alternative data.** Price and volume only. News / earnings /
  sentiment integrations are v3.
- **Not a replacement for a PM's judgement.** This is a decision
  SUPPORT tool. The trust filter deliberately vetoes more trades than
  it approves; the trader's job is to take the trusted ones AND
  sometimes ignore FLATs when they have external information.
- **Not a SaaS dashboard (v1).** We ship a Python package + CLI +
  markdown-report generator. A hosted UI is v2 if and only if the
  workflow clicks.

### Explicit non-goals for trust filter math
- No online learning. Calibration is point-in-time, recomputed by
  running a fresh `api.backtest(...)`. No drift detection, no
  streaming updates.
- No ML on trust signals. The four signals are hand-engineered and
  stay that way for the pilot. We need to explain every veto.

## 5. End-to-end workflow reference

The workflow script at [`examples/finance_workflow_v1.py`](../../examples/finance_workflow_v1.py)
implements the canonical user journey:

1. **Load** — read a daily price series.
2. **Backtest** — run a walk-forward `api.backtest(...)` on a warm-up
   window; extract calibration.
3. **Search** — find top-K analogue windows for the current query.
4. **Project** — generate the forecast cone.
5. **Decide** — run `CalibrationAwareStrategy.evaluate(...)` with the
   calibration report as the trust anchor.
6. **Review** — print the `ReviewSummary`, including trust reasons,
   threshold outcomes, and position size.

Run as:
```bash
python examples/finance_workflow_v1.py
```

## 6. Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Trust filter is too conservative → no trades | `min_matches` / `min_score` are knobs; document default behavior and how to relax. |
| Calibration drifts between refreshes | Ship with a "backtest staleness" warning if the report is > N days old. v1: log-only. |
| Partner refuses to read text review | v1.1: render ReviewSummary as a markdown card consumable in their tool of choice. |
| Engine finds spurious analogues | Trust filter's *agreement* signal is the designed defence. Backtest coverage is the empirical defence. |
| Over-fitting to the pilot window | Separate calibration set (pre-window) from evaluation set (pilot window); never tune on the eval set. |

## 7. Open questions for the first partner call

1. Universe size? (1 ticker? 10? 100?) — affects whether v1 is
   single-ticker or batch.
2. How do they actually want the ReviewSummary rendered? (CLI, Slack
   webhook, markdown file, PDF?)
3. What is their current benchmark? (Buy-and-hold? Existing systematic
   rule? Discretionary baseline?)
4. What is the honest veto rate ceiling before they turn it off?
