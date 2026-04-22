# Analog detail drawer — click to inspect what you're pinning

**Context:** PR #228 wired pinning to drive the forecast, but users had no way to see WHAT they were pinning beyond a short note and a 110-pixel sparkline. "July 2020 · top match" isn't enough for a quant who needs to trust the curation.

## What shipped

Right-side slide-in drawer on the Retrieve workstation that opens when the user clicks an analog card body. Contains:

1. Header — rank badge (colored per analog palette slot), date range, composite score, pin toggle, close button.
2. Context strip — one sentence labeling the historical window. Hand-curated regime table (`KNOWN_REGIMES` in `the-similarity-app/components/workstation/analog-detail-drawer.tsx`) covering 1998 LTCM through 2023 regional-bank stress; off-list dates fall back to `Q{n} YYYY`.
3. Per-lens score bars — 9 rows (one per `LENS_DEFS` entry). Top-3 lenses colored in the analog's rank palette, the other 6 muted grey.
4. Expanded sparkline — match window + forward window in one 380x80 SVG with dashed split marker.
5. Action row — Pin/Unpin, "Find similar analogs", Close.

## Click-affordance split

Before PR #K, clicking anywhere on an analog card toggled pin. Now:

- **Card body click** → opens the detail drawer (new).
- **Pin icon click** (top-right corner of card) → toggles pin (existing behavior, scoped to the icon).
- **Hover** → still highlights the analog path on the chart (PR #231 behavior preserved).

The pin icon is an inline SVG pushpin. `stopPropagation()` on its `onClick` prevents the card's click handler from also firing — this is what keeps the two affordances independent.

## Keyboard

- `1`..`6` → open the drawer for analog #N (when focus isn't in an input, no modifiers).
- `Esc` → close the drawer.
- Drawer uses `analogsRef` so the listener installed once on mount sees the latest analog list across re-searches.

## "Find similar analogs" flow

Clicking the action button in the drawer:

1. Calls `setWindowState({ start: analog.startIdx, len: analog.priceWindow.length })` — moves the query window to the analog's range.
2. Flips `isDirty` (windowState diff already triggers it — see `isDirty` derivation in `workstation.tsx`).
3. Closes the drawer.
4. Shows a floating toast (`UseAsQueryBanner`) telling the user what just happened. Self-dismisses after 8s or on manual click.
5. Dispatches a `ts:use-analog-as-query` CustomEvent on `window` for future analytics listeners.
6. Does **not** auto-fire search — the user must click Search so the new window is visible first.

## Files

- `the-similarity-app/components/workstation/analog-detail-drawer.tsx` — new component.
- `the-similarity-app/components/workstation/workstation.tsx` — state (`detailAnalogId`, `useAsQueryBanner`), keyboard shortcuts, card JSX (pin-icon button), drawer render, `UseAsQueryBanner` subcomponent.
- `the-similarity-app/app/globals.css` — `.adrawer*`, `.analog-card__pin-btn`, `.ws-use-as-query-banner` rules appended at bottom.
- `the-similarity-app/tests/analog-detail-drawer.test.tsx` — 11 tests covering `regimeLabelFor` + drawer render + click handlers.

## Related

- [[Analog forecasting]]
- PR #228 (pinning drives forecast)
- PR #231 (multi-analog palette + hover preview + rank badges)
