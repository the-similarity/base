# Workstation Chart Modes — Fast (SVG) vs Pro (lightweight-charts)

The Retrieve workstation ships two alternate chart renderers. Users toggle
between them via a segmented control above the chart card.

## Files
- `the-similarity-app/components/workstation/line-chart.tsx` — Fast view
- `the-similarity-app/components/workstation/line-chart-lw.tsx` — Pro view
- `the-similarity-app/components/workstation/workstation.tsx` — mode toggle + conditional render
- `the-similarity-app/app/globals.css` — `.ws-chartmode*` and `.lw-chart*` rules

## Fast — SVG LineChart (default)
- Hand-rolled SVG paths for price, cone, analog overlays.
- Draggable query window with left/right handle + body drag.
- Crosshair + annotation on hover.
- Best when the user is actively **editing** the query range.

## Pro — lightweight-charts LineChartLW
- Uses `lightweight-charts` v5 (`createChart`, `addSeries(LineSeries|AreaSeries)`).
- Price line, P50 median line, P10–P90 + P25–P75 cone bands.
  - Bands implemented as two stacked AreaSeries per band (top = upper
    quantile filled to baseline, bottom = lower quantile painted with the
    page background to "erase" the sub-region). Lightweight-charts has no
    native band primitive.
- Analog overlays as individual `LineSeries`, scaled by
  `qAnchorP / analogEnd` to align the terminal bar with the query's
  terminal (identical to the SVG chart's `line-chart.tsx` scale calc).
- Query window is **read-only** — rendered as a DOM overlay synced via
  `chart.timeScale().timeToCoordinate(...)`. Corner note tells the user
  "Window editing is in Fast view." Editing in Pro was dropped for scope.
- Theme-aware: reads CSS tokens (`--bg`, `--ink`, `--c-cone-fill`, etc.)
  via `getComputedStyle(documentElement)` on mount; a `MutationObserver`
  on `data-theme` re-applies layout tokens when the theme flips.
- Lifecycle: `chart.remove()` on unmount. All series held in refs,
  mutated via `setData(...)` — never reconstructed except for analogs,
  where set identity changes when the top-K list reorders.

## Why two views?
Fast view stays as the interactive editing surface — SVG gives us cheap,
precise control of the handle drag UX. Pro view is for high-fidelity
inspection (pan/zoom, crosshair with magnet mode, canvas perf on long
series). A `WorkstationSettings.chartMode` field (optional, defaults to
`"fast"`) persists the choice.

See also: [[Nine-method pipeline]], [[Projector calibration lane]].
