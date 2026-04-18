# Full Platform Buildout (2026-04-15 to 2026-04-18)

Four-day sprint that transformed The Similarity from a time-series retrieval engine into a seven-pillar synthetic environment platform. 134+ commits, 37+ PRs merged, 7 batches executed mostly by parallel worktree agents.

## The seven batches

### Batch 1: Platform Spine (2026-04-17)
The foundation everything else plugs into.
- Unified contracts: `RunRecord`, `ArtifactRecord`, `ScorecardSummary`, `DatasetSpec`, `ScenarioSpec`
- `RunKind` enum: COPIES, WORLDS, SWEEP, EVAL, FINANCE, EVENTS, NL_TS
- SQLite-backed `RunRegistry` with WAL mode, upsert semantics, cascade delete
- Adapters for finance and copies pillars
- FastAPI surface over registry (port 8787)
- CLI: `python -m the_similarity.platform list/show/compare`
- Platform smoke test + ci_local.sh throwaway-venv gate

See [[batch1 platform spine 2026-04-17]]

### Batch 2: Finance Operating Product (2026-04-17)
Made the original engine production-ready.
- Finance benchmark v2 with canonical slices (SPY regimes, sector rotation)
- Walk-forward backtester integration with platform registry
- Projector v2: adaptive conformal calibration with real-parquet confirmation

See [[batch2 finance operating product 2026-04-17]]

### Batch 3: Slop Audit + Synthetic Copies v2 (2026-04-17)
Quality pass on docstrings + synthetic pipeline hardening.
- Claude Code Documentation Standard enforcement across codebase
- Privacy scorecard: DCR, memorization, membership-inference proxy, attribute inference risk, tail exposure
- Utility scorecard: TRTS/TSTR Ridge forecasting
- Synthetic CLI with `--register` and `--strict` flags

See [[batch3 slop audit 2026-04-17]], [[batch3 synthetic copies v2 2026-04-17]]

### Batch 4: Synthetic Worlds v2 (2026-04-17)
Agent-based simulation with eval harness.
- Headless world runner with JSONL telemetry
- Sweep runner for parameter exploration
- Regime coverage + controllability evaluation (permutation p-values)
- Platform registry integration for world runs

See [[batch4 synthetic worlds v2 2026-04-17]]

### Batch 5: 3D Data Space (2026-04-18)
State-graph visualization infrastructure.
- StateVector + StateGraph contracts with KNN graph construction
- Fractal terrain engine with FPS controls
- 3D state space demo with regime embeddings

See [[batch5 3d data space 2026-04-18]]

### Batch 6: World Event Prediction v1 (2026-04-18)
Forecasting pipeline for world events.
- Event contracts: Event, ForecastQuestion with benchmark fixtures
- Event graph construction via KNN over state vectors
- Naive base-rate predictor from analogue resolution frequencies
- EventScorecard: Brier, log score, calibration error, letter grade
- Prediction market ingestion (ForecastQuestion loader)

See [[batch6 world event prediction v1 2026-04-18]]

### Batch 7: NL-to-Time-Series v1 (2026-04-18)
Natural-language to synthetic trajectory pipeline.
- Keyword parser: direction, magnitude, duration, volatility extraction
- NarrativeSchema intermediate representation
- Trajectory compiler: piecewise-linear drift + Gaussian noise
- E2E demo with 3 inline narratives
- Platform registry integration (RunKind.NL_TS)

See [[batch7 nl to timeseries v1 2026-04-18]]

## What the platform looks like now

```
The Similarity Platform
├── Engine (Phase 1-7)
│   ├── 9 methods + 2D variants
│   ├── Tiered pipeline: SAX+MASS → DTW+Pearson → Tier 2
│   ├── Ensemble forecasting: Monte Carlo, regime-conditional, conformal
│   └── Strategy builder, portfolio scanner, alerts, auth, explainability
│
├── Platform Spine
│   ├── Unified object model (7 RunKinds)
│   ├── SQLite registry (WAL mode)
│   ├── REST API + CLI
│   └── Adapters per pillar
│
├── Finance Pillar
│   ├── Canonical slice catalogue
│   ├── Walk-forward backtester
│   └── Projector v2 (adaptive conformal)
│
├── Synthetic Copies Pillar
│   ├── Block bootstrap + regime-aware generators
│   ├── Fidelity + privacy + utility scorecards
│   └── CLI pipeline with registry integration
│
├── Synthetic Worlds Pillar
│   ├── Headless agent-based runner
│   ├── Sweep + eval harness
│   └── Regime coverage + controllability metrics
│
├── 3D Data Space
│   ├── StateVector + StateGraph
│   ├── Fractal terrain engine
│   └── 3D visualization demos
│
├── World Events Pillar
│   ├── Event graph + KNN retrieval
│   ├── Forecast questions + prediction market ingestion
│   └── EventScorecard (Brier, calibration)
│
├── NL-to-Time-Series Pillar
│   ├── Keyword parser + NarrativeSchema
│   ├── Trajectory compiler
│   └── E2E demo with registry integration
│
├── Infrastructure
│   ├── CI: pr-gate, main-health, branch-reaper
│   ├── ci_local.sh (throwaway-venv gate)
│   ├── Orchestrator (auto-discovery + parallel worktree dispatch)
│   └── Daily data refresh (GitHub Actions)
│
└── Surfaces
    ├── TradingView Pine Script (indicator + strategy)
    ├── Next.js frontend (lightweight-charts)
    ├── FastAPI backend
    └── Obsidian knowledge base (50+ notes)
```

## Lessons learned

1. **Worktree isolation works.** 5 parallel agents editing different files in different branches produced zero merge conflicts when each agent stays in its lane. The key: no shared-file edits (MOC, .gitignore, pyproject.toml).

2. **Merge-as-you-go, not batch.** Batch merging 5 PRs creates cascading conflicts on shared files. Merging each PR immediately after its gate passes keeps main clean and gives later agents a fresh base.

3. **ci_local.sh saved hundreds of CI minutes.** Running the full test suite in a throwaway venv locally catches 95% of failures before push. Reserve CI for the final gate, not iterative debugging.

4. **Scaffolds beat polish.** Every pillar shipped a "v1 with honest limitations" rather than waiting for the ideal implementation. The eval harness, registry integration, and contract definitions are the durable value; the algorithms are replaceable.

5. **The platform spine unlocks everything.** Without unified contracts and a registry, each pillar would be an island. With them, every run from every pillar is queryable, comparable, and auditable through one CLI/API/UI.

6. **Cascade merge conflicts are the #1 parallel-agent failure mode.** Hot files (`_MOC.md`, `.gitignore`, `CHANGELOG.md`) must be touched by exactly one agent or post-merge by the orchestrator. This was learned the hard way in batch 3.

## Stats

- **Duration**: 4 days (2026-04-15 to 2026-04-18)
- **Commits**: 134+
- **PRs merged**: 37+
- **Test count**: 754+ (up from 347 at start)
- **Pillars**: 7 (finance, synthetic copies, worlds, 3D, events, NL-to-TS, eval)
- **Obsidian notes**: 50+ across concepts, topics, research
