# Batch 6: World Event Prediction v1

**Date**: 2026-04-18
**Status**: Shipped
**Agents**: 5 parallel worktree agents

## Decision

Ship the world-event prediction pillar v1 as a 5-agent batch:
1. **Agent 1**: Event contracts + benchmark dataset (20-30 historical events)
2. **Agent 2**: ForecastQuestion + MarketHistory + benchmark questions (10-15 resolved)
3. **Agent 3**: Event graph + feature extraction + analogue retrieval
4. **Agent 4**: Event scorecard (Brier, calibration, log score)
5. **Agent 5**: End-to-end demo + docs + integration tests

## Alternatives considered

### Ship as a single large PR
Rejected. A single agent doing all five deliverables would take 5x longer and produce a harder-to-review PR. The 5-agent parallel approach ships in one session with granular PRs that can be reviewed independently.

### Use a real forecasting model for v1
Rejected. The goal of v1 is the **eval scaffold**, not prediction quality. A naive base-rate estimator is honest, testable, and establishes the scoring baseline that all future models will be compared against. Shipping a half-baked LLM forecaster would conflate two problems (model quality + infrastructure correctness) and make debugging harder.

### Build a custom graph module for events
Rejected. Events reuse `the_similarity/core/state_graph.py` (KNN graphs, `StateVector`). Building a separate graph module would duplicate code and miss the cross-pillar value of the shared state space.

### Use `ScorecardKind.BACKTEST` for event scorecards
Rejected. Event prediction scoring is closer to calibration than backtesting. Using `ScorecardKind.CALIBRATION` aligns with the platform's taxonomy and lets the UI group event scorecards with other calibration metrics.

## What shipped

- `examples/event_prediction_demo.py` — full pipeline demo (10 events, 10 questions, graph, predict, score, register)
- `the_similarity/tests/test_event_prediction_e2e.py` — 7 integration tests
- `vision/world_event_prediction.md` — pillar vision doc
- `obsidian_thesim/concepts/event_contracts.md` — schema documentation
- `obsidian_thesim/concepts/event_scorecard.md` — scoring metrics documentation
- `scripts/smoke_event_prediction.sh` — smoke test script

## What's next

- v2: LLM-based prediction, richer embeddings, market signal integration
- v3: ensemble prediction, continuous calibration tracking, live market ingestion
- Long-term: cross-pillar fusion, conditional forecasting, forecast tournaments

## Related

- [[event_contracts]] — data model
- [[event_scorecard]] — scoring metrics
- `vision/world_event_prediction.md` — full vision doc
