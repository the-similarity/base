# Terminal forward windows

The terminal search UI sends only pre-query history to `/search` so retrieval
does not rank candidates using bars after the selected query. That is correct
for search, but it means the backend may not populate long `forward_window`
arrays for custom/past query ranges.

For display, `the-similarity-app/lib/api.ts` uses
`withForwardWindowsFromSeries()` to rebuild each ranked match's continuation
from the full chart series after the backend returns. The rebuilt values keep
the backend unit contract: centered cumulative returns relative to
`match.endIdx - 1`.

This lets the `Fwd` control in
`the-similarity-app/components/terminal/match-list.tsx` show longer continuations
such as 90 or 120 bars when those bars exist in the loaded dataset, without
changing which analogs were selected by the search.

The Lumen route (`the-similarity-app/app/workstation/lumen/page.tsx`) embeds
the shared `Workstation` component. Its chart path now uses
`analogsAtCurrentHorizon` in
`the-similarity-app/components/workstation/workstation.tsx` so both the cone
and per-analog overlay lines rebuild from `loadedSeries` when Horizon grows.

Related: [[retrieval_bench]], [[Analog forecasting]]
