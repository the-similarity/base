# Multi-Analog Palette & Hover Preview

Shipped 2026-04-20 (Agent G). Fixes the "is it only showing top 1?"
bug — prior to this, 3..6 analog overlays all rendered in the same
`--c-analog` tone at near-identical opacity, visually collapsing into
one line.

## Files
- `the-similarity-app/app/globals.css` — palette tokens + card borders + badge styles + legend dot styles (bottom section)
- `the-similarity-app/components/workstation/line-chart.tsx` — SVG "Fast" view: palette + opacity ramp + hover preview + rank badges
- `the-similarity-app/components/workstation/line-chart-lw.tsx` — Pro lightweight-charts view: palette + alpha ramp + hover preview (no badges)
- `the-similarity-app/components/workstation/workstation.tsx` — passes `hoveredAnalogId` to both charts, adds `data-rank` to cards, per-rank legend dots
- `the-similarity-app/tests/line-chart-palette.test.tsx` — regression guard for the 5 rendering invariants

## Palette tokens
Added in `:root` and `[data-theme="dark"]`:
```
--c-analog-1  oxblood  (reuses --accent for rank 1)
--c-analog-2  muted amber
--c-analog-3  muted green
--c-analog-4  muted navy
--c-analog-5  muted plum
--c-analog-6  muted sienna
```
Dark-mode variants brighten each hue to keep contrast on the ink background.

## Interaction hierarchy
Four-state matrix in both renderers:

| pins?       | hover?            | rendering                                            |
|-------------|-------------------|------------------------------------------------------|
| none        | none              | palette per rank + opacity ramp .95→.45              |
| none        | hover match       | palette + opacity 1.0 + stroke-width 2.0 + brighter  |
| some pinned | hover match pinned| `.strong` + stroke-width 2.2                         |
| some pinned | hover match un-pin| `.context` un-faded to opacity .7 (pre-pin preview)  |

Rule: **pin > hover > default**. Palette is the *default* look; pin mode replaces it wholesale so the curated subset dominates.

## Rank badges (Fast only)
At each analog's forward terminal we draw a 14px circle in the rank's
palette color + white numeral 1..6. Overlap avoidance: any badge within
(20px x, 12px y) of a previously-placed badge is nudged down 14px,
iterated up to 8 times.

**Suppressed when any pin is active** — pinned analogs don't need the
badge; the pin state is the emphasis.

**Pro view skips badges entirely.** lightweight-charts v5 has no native
annotation primitive; implementing a DOM overlay would require a full
timeScale/priceScale coordinate sync loop for every analog. Deferred.
Per-rank color + width ramp alone is enough to differentiate lines in Pro.

## Legend dots
The "Analogs (N)" text is now followed by N colored dots, one per
analog, each colored to match its chart line and card border. Clicking
a dot toggles the pin on that analog (same as clicking the card).
Pinned dots gain an accent-colored 1.5px ring. This creates a
three-way correspondence: **card left-border ↔ chart line ↔ legend dot**
all share the same rank palette color.

## Why inline styles in SVG
The palette decision is keyed by rank 0..5. Using six separate CSS
classes (.analog-rank-0 ... .analog-rank-5) would be noisier than a
single `style={{ stroke: var(--c-analog-N), ... }}` payload colocated
with the rank decision in the render pass. The CSS class still handles
variant selection (`.analog.strong`, `.analog.context`) for pin mode.

## Why `lineWidth: 3` caps the Pro hover
lightweight-charts' `LineSeries.lineWidth` accepts only `1 | 2 | 3 | 4`
integers — no float widths. Hover bumps any variant to 3; the default
rank-0 line renders at 2, and rank 1..5 at 1. The visual "pop" from 1 → 3
is large enough that users read the hovered line as the focused one,
even without the brightness filter the SVG view uses.

## Test insight
`ResizeObserver` is not provided by jsdom. The LineChart's mount-time
observer throws in vitest unless stubbed. The palette test file installs
a no-op stub in `beforeAll` — the observer never needs to actually fire
because we assert on attributes, not computed layout.

See also: [[workstation_chart_modes]], [[pinning_drives_forecast]].
