# The Similarity — March Architecture Snapshot

This document is a historical architecture snapshot from an earlier stage of the
project. It is useful for understanding how the system evolved, but it is not
the canonical description of the current repository layout.

For the current architecture, see:

- [ARCHITECTURE_OVERVIEW.md](/Users/buyantogtokh/.codex/worktrees/b679/14/docs/architecture/ARCHITECTURE_OVERVIEW.md)

## Historical System Overview

A research-grade time series pattern matching platform. You give it a price pattern (e.g., last 60 bars of XAUUSD 1H), and it finds the most similar historical patterns across 9 mathematical methods, then projects what happened next.

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js)                        │
│  SearchSidebar → ChartPanel → MatchList → DetailPanel       │
└────────────────────────┬────────────────────────────────────┘
                         │  JSON (REST / WebSocket)
┌────────────────────────▼────────────────────────────────────┐
│                    BACKEND (FastAPI)                          │
│  /search, /catalog, /datasets, /ws/search                    │
└────────────────────────┬────────────────────────────────────┘
                         │  numpy arrays / dataclasses
┌────────────────────────▼────────────────────────────────────┐
│                 CORE ENGINE (Python)                          │
│  Tier 0 → Tier 1 → Tier 2 → Projector                       │
└────────────────────────┬────────────────────────────────────┘
                         │  parquet reads
┌────────────────────────▼────────────────────────────────────┐
│              DATA WAREHOUSE (Parquet + DuckDB)               │
│  crypto / stocks / forex / commodities                       │
└─────────────────────────────────────────────────────────────┘
```

---

## The Search Pipeline

When you click "Run Search", here's what happens:

### Tier 0 — Prefilter (milliseconds, eliminates ~95% of candidates)
- SAX (symbolic approximation) + MASS (matrix profile via FFT) + Pearson
- Scans all sliding windows in history, scores cheaply
- Keeps top 1,000 candidates

### Tier 1 — Cheap scoring (seconds)
- DTW (Dynamic Time Warping) with Sakoe-Chiba band
- Pearson correlation post-warp
- Ranks all 1,000 survivors, keeps top 20

### Tier 2 — Expensive enrichment (seconds, parallel threads)
7 methods on just 20 candidates:
- **Bempedelis** — power-law self-similarity (R² + smoothness)
- **Koopman EDMD** — dynamical system eigenvalue matching
- **Wavelet Leaders** — multifractal spectrum distance
- **EMD** — empirical mode decomposition (IMF matching)
- **TDA** — persistent homology (topological structure)
- **Transfer Entropy** — predictive information flow
- **Regime Tagger** — market state classification

**Final score** = weighted combination of all 9 methods, renormalized to [0, 100].

### Projection
For each match, extracts what happened *after* that pattern in history, converts to cumulative returns, builds weighted percentile curves (p10, p25, p50, p75, p90) with confidence decay.

---

## Frontend Flow

```
User selects dataset (e.g., commodities/gold/1h)
  → fetchSeries() + fetchOhlc() load data
  → User sets query window (last N bars)
  → Click "Run Search"
  → POST /search with queryValues + historyValues
  → Results arrive: 20 matches + forecast cone
  → ChartPanel renders: candles + purple match overlay + continuation
  → MatchList shows ranked cards with sparklines
  → Click/hover a match → purple overlay swaps, detail panel opens
  → FWD slider extends continuation line into the future
```

**State management**: single `useReducer` in `terminal-context.tsx` — all components read/dispatch from one place.

**Chart**: lightweight-charts (TradingView library). Three effects:
1. Data effect — sets candles/lines, calls `fitContent()` once
2. Overlay effect — updates purple match + continuation on hover/select/FWD change, never resets zoom

---

## Historical Markdown File Layout

| File | Purpose |
|------|---------|
| **`CLAUDE.md`** (root) | Git workflow, worktree coordination, test commands, architecture summary. The "how to work in this repo" guide. |
| **`docs/planning/plan.md`** | Phase-by-phase roadmap from this earlier implementation stage. |
| **`docs/planning/TODOS.md`** | Deferred work items with rationale for *why* they're deferred. |
| **`docs/architecture/ARCHITECTURE.md`** | Design principles, module responsibilities, data flow, scaling path. |
| **`docs/theory/THEORY.md`** | Math foundations and method theory notes. |
| **`docs/reference/API_REFERENCE.md`** | User-facing Python API docs. |
| **`docs/design/DESIGN_LANGUAGE.md`** | UI/UX spec — colors, typography, spacing, card styles, interactions. |
| **`research/methods/01-dtw-*.md`** | Deep dive: DTW algorithm, constraints, library comparison. |
| **`research/methods/02-fractal-*.md`** | Hurst exponent, DFA, multifractal analysis, MMAR. |
| **`research/methods/03-koopman-*.md`** | Koopman operator theory, EDMD, eigenvalue comparison methods. |
| **`research/methods/04-tda-emd-*.md`** | TDA, EMD, wavelets, SAX, matrix profile, transfer entropy. |
| **`research/methods/05-pattern-*.md`** | Analog forecasting, forecast cones, walk-forward backtesting. |
| **`research/notes/presenting_idea.md`** | Competitive landscape analysis — why 9 methods, why tiered, what's the gap in the market. |
| **`progress/progress3_9.md`** | Sprint report from March 9 — 56 new tests in one session, phases 2c-3f completed. |
| **`the-similarity-app/TODOS.md`** | Frontend-specific improvements: Docker, keyboard shortcuts, mock cleanup. |
| **`.cursor/agents/boyo.md`** | Cursor agent config — a "critic" persona for code review. |
| **`.gstack/qa-reports/qa-report-*.md`** | QA health report (72/100) from March 14 with specific issues. |

---

## Key Files by Component

| What | Where |
|------|-------|
| Search pipeline | `the_similarity/core/matcher.py` |
| 9-method scoring | `the_similarity/core/scorer.py` |
| Forward projection | `the_similarity/core/projector.py` |
| All config/weights | `the_similarity/config.py` |
| Public Python API | `the_similarity/api.py` |
| Each method | `the_similarity/methods/{dtw,koopman,bempedelis,wavelet_leaders,emd,tda,transfer_entropy}.py` |
| FastAPI routes | `the-similarity-api/app/main.py` |
| Search orchestration | `the-similarity-api/app/services.py` |
| Data loading | `the-similarity-api/app/data_service.py` |
| Frontend state | `the-similarity-app/lib/terminal-context.tsx` |
| Chart rendering | `the-similarity-app/components/terminal/chart-panel.tsx` |
| Search UI | `the-similarity-app/components/terminal/search-input.tsx` |
| API client | `the-similarity-app/lib/api.ts` |
| Dataset catalog | `the-similarity-data/manifests/catalog.json` |
| Price data | `the-similarity-data/data/{asset_class}/{symbol}/{timeframe}.parquet` |

---

## Why It Works This Way

- **9 methods, not 1**: DTW alone is brittle. Each method captures something different — shape, dynamics, fractals, topology, predictive power. Weighted combination is robust.
- **3 tiers, not flat**: Running all 9 methods on 100k+ windows would take minutes. Tiering: SAX/MASS eliminates 95% in milliseconds, DTW ranks cheaply, expensive methods only touch top 20.
- **Per-window normalization**: Prevents high-volatility periods from dominating. Two windows with identical shape but different amplitude should match.
- **Forward window on each match**: Shows what *actually happened* after that pattern historically — the continuation line you see on the chart.
- **Stateless API**: Backend has no sessions. Frontend owns all state. Makes caching, scaling, and offline fallback trivial.
