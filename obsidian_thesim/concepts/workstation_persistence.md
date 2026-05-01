---
type: concept
tags: [workstation, ux, persistence, frontend]
---

# Workstation persistence

The `/workstation` and `/workstation/lumen` routes share one component: `the-similarity-app/components/workstation/workstation.tsx`. Lumen is just a CSS-variable re-skin via the cascade — feature work in the shared component flows into both for free.

The workstation used to be amnesiac: every reopen reset to default SPY 1d, and the left-rail "Notebook" section was a hardcoded prose paragraph that always read "Nine lenses agree…". Saved goodruns were fire-and-forget — POSTed to `/goodruns` and then invisible inside the workstation. Result: nothing about the surface remembered the user, so it felt like a calculator, not a workstation.

This concept covers what now persists, where, and why.

## What persists

| Slice | Storage key | Lifetime | Notes |
|---|---|---|---|
| Last dataset + window + view-range | `ts-last-query` (localStorage) | Single user, persists across sessions | URL params still win; lastQuery only fills gaps. Window/view indices only restore when the dataset matches the saved dataset (mismatched indices on a different series produce gibberish). |
| Settings (theme, kAnalogs, horizon, chartMode, showAnalogs, showCone, showWindow, showMedian) | `ts-settings` | Across sessions | Pre-existing — see `app/workstation/page.tsx`. |
| Pinned analogs | `ts-pinned:<dataset>:<windowStart>:<windowLen>` | Per-query | Per-query isolation deliberate — pins are meaningful only against the query that produced them. Rehydrates after first search completes for the key. |
| Notebook entries | `ts-notebook` (single bucket, JSON array) | Across sessions | Cap 200 entries, oldest dropped on overflow. Each entry: `{id, ts, text, dataset, windowStart, windowEnd}` — the dataset+window triple is the **restore key** that lets click-to-restore work. |
| Saved-runs local mirror | `ts-goodruns-local` | Across sessions | Cap 50 records. Mirror of `GoodrunRecord` shape returned by `/goodruns`. API records win on id collisions when both are present; offline-only saves preserved. |

## Hydration order

1. URL state (parsed via `parseUrlState` from `lib/url-state.ts`).
2. localStorage last-query (via `readLastQuery()` in `workstation.tsx`).
3. Hardcoded defaults.

URL is the share-link contract — must restore exactly. localStorage is the personal continuity layer — fills gaps. Defaults are the floor.

The hydration is implemented in the three `useState(() => …)` initializers for `activeDataset`, `windowState`, `viewRange`. Both URL and lastQuery are read once via lazy refs so subsequent renders don't re-trigger reads.

## Persistence triggers

- `ts-last-query`: 400ms debounced effect on (dataset, windowStart, windowLen, viewStart, viewEnd). Same cadence as the URL writer; matches drag/click granularity.
- `ts-notebook`: synchronously on every `addNotebookEntry` / `removeNotebookEntry`. Bounded list, write is cheap.
- `ts-goodruns-local`: synchronously on `saveLocalGoodrun` / `removeLocalGoodrun`. Also back-filled from the API in the saved-runs hydration effect — the first time `isApiAvailable` resolves true, we fetch `listGoodruns()` and merge into the mirror so subsequent opens have remote records cached for offline.

## Why this matters

A workstation isn't features. It's persistent state + always-on signal + closed action loops. This batch covers persistence and the action-loop close (notebook + saved-runs are both round-trippable artifacts now). Always-on signal — watchlist rotator, time scrubbing, lens deep-dive — is separate, follow-up work.

## Related

- [[goodruns]] — the durable artifact this layer mirrors.
- `the-similarity-app/lib/url-state.ts` — share-link parser/serializer.
- `the-similarity-app/lib/notebook.ts` — notebook persistence helpers.
- `the-similarity-app/lib/goodruns.ts` — API client + local mirror.
- `the-similarity-app/components/workstation/notebook-panel.tsx` / `saved-runs-panel.tsx` — left-rail panels that consume this state.
