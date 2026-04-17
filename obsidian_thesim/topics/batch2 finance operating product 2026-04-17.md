# Batch 2: Finance Operating Product — Decision Record

**Date**: 2026-04-17
**Status**: In progress
**Authors**: Batch 2 agent swarm (5 parallel agents)

## Decision: Why finance first?

Finance is the first pillar to become fully operational on the platform because:

1. **Most mature engine code.** The 9-method pipeline, backtester, and projector have been shipping since Phase 1. Every other pillar (synthetic copies, worlds, events, NL-to-TS) was built later and has less test coverage.

2. **Clearest feedback loop.** Market data has a ground truth (what actually happened). This makes calibration, trust scoring, and review workflows testable with real outcomes. Synthetic worlds and copies have fidelity scores, but no "actual" to compare against in the same direct way.

3. **Smallest integration surface.** Finance runs are fully in-process — no Node runner, no GPU, no external service. The adapter writes directly to the SQLite registry. This means the operational layer (trust, calibration, review, benchmark) can ship without infrastructure changes.

4. **Investor-legible.** A finance demo with trust scores, calibration grades, and a review workflow is immediately understandable to investors and enterprise prospects. "We forecast SPY with 62% directional accuracy, grade-B calibration, and a trust score of 0.72" lands better than "our synthetic data has a fidelity score of 0.87."

## What shipped in Batch 2

| Component | Owner | What it does |
|-----------|-------|-------------|
| Enriched finance adapter | Agent 1 | Adds trust_score + calibration_grade to registered runs |
| ReviewArtifact + API | Agent 2 | Review workflow with risk flags, signal summary, status transitions |
| Finance runs browser | Agent 3 | Next.js UI: list/detail/compare pages for finance runs |
| Benchmark CLI | Agent 4 | Single-run + multi-symbol sweep + registration |
| Integration tests + docs | Agent 5 | End-to-end tests, workflow doc, obsidian notes, smoke script |

## Success metrics

| Metric | Target | How to measure |
|--------|--------|---------------|
| Tests pass | 100% green | `python -m pytest the_similarity/tests/ -v` |
| Smoke script | Exit 0 | `bash scripts/smoke_finance_operating.sh` |
| Registry round-trip | Backtest -> register -> list -> show works | Integration test |
| Trust score present | Every registered run has trust_score in summary | Integration test (optional assertion) |
| Review workflow | pending -> approved/flagged/rejected transitions work | Agent 2 tests |
| Benchmark sweep | Multi-symbol sweep registers N independent runs | Agent 4 tests |

## What's next after Batch 2

- **Benchmark harness for customer models**: bring-your-own-forecast, compare against our baseline
- **Live monitoring**: auto-run on new bars, register results, alert on drift
- **Realized outcome tracking**: auto-compare forecast vs actual after the window closes
- **Cross-asset portfolio view**: aggregate trust scores and signals across multiple symbols

## Related

- [[batch1 platform spine 2026-04-17]] — the platform spine that Batch 2 builds on
- [[finance_pilot]] — earlier scoping of the finance pillar
- [[trust_artifact]] — trust scoring details
- [[calibration_artifact]] — calibration grading details
- [[finance_review]] — review workflow details
- [[finance_benchmark]] — benchmark CLI details
