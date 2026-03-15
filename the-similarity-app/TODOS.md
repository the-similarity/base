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

### Matplotlib backtest report visualization
- **What:** Add `BacktestReport.plot()` that produces a 4-panel matplotlib figure: (1) calibration curve, (2) rolling hit rate, (3) P50 error distribution histogram, (4) CRPS by trial.
- **Why:** Researchers want to see, not just read, their backtest results. Visual validation is much faster than parsing numbers.
- **Effort:** S (~30 min)
- **Priority:** P2
- **Depends on:** Backtester (core/backtester.py) being built.

### Method ablation framework
- **What:** Add `backtest_ablation(history, ...)` that runs N+1 backtests: one with all methods, then one with each method removed. Produces a table showing delta hit_rate and delta CRPS for each ablation.
- **Why:** Tells you which methods actually improve predictions vs adding noise. Data-driven method selection.
- **Effort:** M
- **Priority:** P2
- **Depends on:** Backtester being correct and trusted.

### Auto-weight-tuning from calibration feedback
- **What:** Add `tune_weights(backtest_report)` that adjusts `Config.weights` to minimize calibration error using `scipy.optimize.minimize`.
- **Why:** Current weights are hand-tuned guesses. This makes them empirical.
- **Effort:** L
- **Priority:** P3
- **Depends on:** Backtester + method ablation identifying which methods matter.

### Wire time range selector to search API
- **What:** Map range selector (1D/1W/1M/3M/1Y/ALL) to query window size parameter when calling searchApi. Currently ranges only switch mock dashboard views.
- **Why:** Range selection should re-run the search with a different window size, not just swap pre-computed mock views.
- **Effort:** S
- **Priority:** P2
- **Depends on:** Real API data wiring (this PR must land first).

### Align search workstation rendering with shared types
- **What:** The search workstation rendering code still references old field names from its inline types. Update template references to use shared MatchResult fields (confidenceScore, matchedSeries, etc.).
- **Why:** DRY — imports were fixed but some rendering code may still drift from shared types.
- **Effort:** S
- **Priority:** P3
- **Depends on:** Nothing.

### Add component render tests for ChartPanel and SearchInput
- **What:** Add vitest render tests for ChartPanel (with real search data, trajectory overlay) and SearchInput (validation, error states).
- **Why:** Reducer tests cover state logic but not rendering. SearchInput validation is a good candidate for render tests.
- **Effort:** S
- **Priority:** P3
- **Depends on:** Real API data wiring.
