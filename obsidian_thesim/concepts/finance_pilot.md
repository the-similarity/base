# Finance pilot (v1)

Track 1C deliverable. Canonical end-to-end workflow for a design
partner — single-ticker, daily bars, 2-10 day holding period. Full spec
at `docs/planning/finance_pilot_v1.md`.

## Target user

Small fund / prop / family-office trader, team 1-5, AUM $5M-$500M.
Trades liquid US equities and ETFs on daily bars. Has execution, lacks
rigorous analogue + calibration tooling.

## Workflow

Implemented in `examples/finance_workflow_v1.py`:

1. Load daily price series.
2. Walk-forward `api.backtest(...)` → `BacktestReport.calibration`.
3. `search(...)` → analogue pool.
4. `project(...)` → percentile cone.
5. `CalibrationAwareStrategy.evaluate(...)` with the backtest as the
   trust anchor → [[trust_filter]] gate + percentile-threshold entry +
   scaled position size.
6. `summarise_review(...)` → plain-text audit block for the trader.

## Decision layer

`CalibrationAwareStrategy` wraps any existing [[Strategy]]. Enforces:

- Hard veto on low samples or catastrophic calibration error.
- Entry requires `P{entry_percentile}` (default 25) past the
  `entry_threshold` in the signal direction.
- Position size = `min + (max-min) * trust.score *
  (confidence/100)`, clamped.
- `veto_on_distrust=True` collapses a vetoed signal to FLAT; False
  preserves direction with size=0.

## Success criteria to sign a pilot

- Empirical coverage within 5pp of stated (e.g. 85-95% for 90%).
- P50 directional hit rate ≥ 55% on trust=True trades.
- Veto rate 20-40%.
- Sharpe lift ≥ 0.3 vs naive fixed-size baseline.
- Trader reads the `ReviewSummary` daily.

## Non-goals (v1)

- No execution / OMS routing.
- No portfolio optimisation (single-ticker only).
- No intraday.
- No SaaS dashboard.
- No alt-data, no ML on trust signals, no online learning.

## Related

- [[trust_filter]] — the gating math.
- `docs/planning/finance_pilot_v1.md` — full spec.
- `examples/finance_workflow_v1.py` — reference script.
- `the_similarity/core/decision_rules.py` — the decision layer.
- `the_similarity/core/backtester.py` — calibration anchor.
