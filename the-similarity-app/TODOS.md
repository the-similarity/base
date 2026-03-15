# The Similarity App — TODOs

## Deferred from Plan Review (2026-03-14)

### Docker Compose for full stack
- **What:** Dockerfile for the-similarity-app (Next.js) + docker-compose.yml at project root with both frontend and API services.
- **Why:** Single `docker compose up` to run the full stack. Reproducible environment, easy to share.
- **Effort:** S
- **Priority:** P2
- **Depends on:** Nothing — can be done anytime.

### Remove frontend mock-data.ts, consolidate on API-only mocks
- **What:** Delete `lib/mock-data.ts` (224 lines). Show a clear "API unavailable" state instead of silently falling back to mock data. All mock generation lives in the API repo (`services.py`).
- **Why:** DRY violation — identical mock data in two repos will drift. Silent mock fallback masks real API issues.
- **Effort:** S
- **Priority:** P2
- **Depends on:** Docker Compose (so API is always available), ErrorBoundary (to handle no-API gracefully).

### Keyboard shortcuts
- **What:** `1`-`6` to switch time ranges, `j`/`k` to cycle matches, `/` to focus search input, `Esc` to close panels.
- **Why:** Power users (researchers) live on the keyboard. Transforms the tool from click-around to instrument-grade.
- **Effort:** S (~30 min)
- **Priority:** P3
- **Depends on:** Search UI being stable.

## Backtester Improvements

### Plot backtester equity curve
- **What:** Add a chart (e.g., Recharts line chart) that plots the backtester's cumulative return / equity curve over time.
- **Why:** Visual feedback is essential for evaluating strategy performance at a glance.
- **Effort:** S
- **Priority:** P2
- **Depends on:** Backtester API returning time-series data.

### Ablation study support
- **What:** Allow running the backtester with individual features toggled off to measure each signal's marginal contribution.
- **Why:** Identifies which similarity signals actually drive returns vs. add noise.
- **Effort:** M
- **Priority:** P2
- **Depends on:** Backtester core being stable.

### Auto-tune backtester parameters
- **What:** Add a grid-search or Bayesian optimization pass that sweeps backtester hyperparameters (lookback, threshold, rebalance frequency) and reports the best config.
- **Why:** Manual tuning is tedious and leaves alpha on the table.
- **Effort:** M
- **Priority:** P3
- **Depends on:** Ablation study (to know which params matter).
