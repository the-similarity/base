# Cadence Design Guideline

Cadence lives at `/cadence`. It is the personal-health workstation: nine screens of self-similarity over the user's own 365-day biomarker history. The product question is "your body has rhymed before — here's what came next." Mock data only at this stage; no cohort acquisition, no HIPAA scope.

Cadence borrows the Lumen scaffold (sidebar + main card + Cmd+K + painterly background + tweaks) and replaces the palette with a sage-clinical green. It is NOT a trading UI; the visual language signals calm-clinical, not Bloomberg-pit.

Code anchors:
- Page: `the-similarity-app/app/cadence/page.tsx`
- Engine (rhyme finder, baselines): `the-similarity-app/app/cadence/engine.ts`
- Scoped stylesheet: `the-similarity-app/app/cadence/_components/styles.tsx` (the `CADENCE_CSS` template literal)
- Screens (one file per): `the-similarity-app/app/cadence/_components/screens/today.tsx`, `flow.tsx`, `rhymes.tsx`, `cycles.tsx`, `log.tsx`, `targets.tsx`, `goals.tsx`, `sources.tsx`, `labs.tsx`
- Sidebar / cmdk / tweaks / shared / charts / icons / data: same `_components/` folder

## Purpose and audience

User: a quantified-self enthusiast on a wearable (Whoop, Oura) plus a CGM, occasionally adding lab uploads. They want to know which past day or week structurally rhymes with the current one, and what came next on the rhyming day's tail.

The screens, by spec (`_components/screen-types.ts` lines 12 to 22):
- `today` — KPI column + DayTrajectory + RhymeHeatmap + TagDonut + ThreadRibbon
- `flow` — multi-channel vitals (HRV, HR, glucose, activity)
- `rhymes` — hero analogue cards + forecast cone
- `cycles` — recurring patterns weekly/monthly/training
- `log` — chronological event ledger + composer
- `targets` — active sleep/HRV/recovery targets with progress
- `goals` — long-horizon goals with projected completion
- `sources` — connected wearables + lab uploads
- `labs` — long-term biomarker tracking with optimal ranges

"Good" looks like: the screen reads as a calm clinical report, the rhyme overlay on a chart actually shows the rhyme (not just states it), and the painterly green-and-coral background does not overpower the white panels.

## Relationship to DESIGN_LANGUAGE.md

Cadence inherits very little from `docs/design/DESIGN_LANGUAGE.md` because the base document is tuned for finance UI. It keeps:

- Tabular numbers (`.cadence-num` with `font-variant-numeric: tabular-nums`).
- Compact dense KPI grid.
- Restraint on motion.
- Semantic split between pos/neg, but the palette differs.

It overrides almost everything else:

1. **Background.** Painterly multi-stop gradient with fractal-noise overlay (`.cadence-painterly` in `styles.tsx` line 98). The default preset is sage-and-coral: `linear-gradient(160deg, #4a7a5a, #6b9a72, #c4b896, #8a6a4a, #3d2f1f)`. Three other presets `dusk`, `paper`, `charcoal` are exposed via the tweaks panel.
2. **Display serif.** Instrument Serif for KPI values, hero numbers, and section eyebrows. Loaded via `<link>` in `cadence/page.tsx` line 173, same mechanism as Lumen.
3. **Accent.** Sage green `#5b8a72`. Mapped to `--accent`, `--accent-2`, `--pos`. The "color of being well" — green that reads clinical-biological, not finance-bullish.
4. **Card model.** Two floating cards: a glass sidebar (`.cadence-sidebar`) and a solid white main panel (`.cadence-main`). 14px gutter, 14px border-radius. Same scaffold as Lumen but the screens inside are different.
5. **Width.** No 1100px container. Cadence runs `100vw × 100vh` and the main card fills the column.
6. **Negative color.** `#c2655c` warm coral instead of the workstation's `#8a2a2a` brick. "Negative" in a health context is a body signal, not a market signal; the warmer hue is intentional.

## Voice and tone

Calm-clinical with a coach undertone. Short sentences. Numbers carry units. The product asks "is your body primed today" rather than "trade this signal".

Real strings from the UI:

- Screen `today` hero pill (`screens/today.tsx` line 122):
  - `Primed to train` (recovery >= 70)
  - `Moderate` (recovery 50 to 69)
  - `Take it easy` (recovery < 50)
- Hero rhyme pill (`screens/today.tsx` line 127): `Rhymes with Apr 3 · 87% match`
- Hero subline (`screens/today.tsx` line 131): `HRV 64ms · RHR 52 · Sleep 7.4h`
- Topbar crumbs (`screens/today.tsx` line 96): `["Workspace", "Today"]`
- KPI metric labels (`screens/today.tsx` lines 152 to 207): `HRV`, `Resting HR`, `Recovery`, `Sleep score`, `Energy`, `Glucose (am)`
- Buttons: `Share`, `Log`, `+ Log` (primary CTA, see line 103)

Rules:
- Never use trading language: no "edge", "P&L", "outperform", "alpha".
- Always carry the unit: `64ms`, `52 bpm`, `92 mg/dL`, `7.4h`.
- Deltas read as `+3 ms` or `-2 bpm`, never as `+5%` for absolute units.
- Absolute dates are `Mar 14` for chart labels (`FMT.shortDate`) or `Mon, Mar 14` for prose (`FMT.longDate`). Both helpers live in `_components/data.ts`.

## Typography

Three families, loaded via `<link>` at `page.tsx` line 173:

- `Instrument Serif` (display) — KPI values, hero numbers, eyebrow rows when serif.
- `Inter` (sans) — body, controls, sidebar nav. Default `font-size: 14px`, `line-height: 1.45`.
- `JetBrains Mono` — kbd chips, mono labels, command palette.

Font-feature-settings on `.cadence-app` (line 82): `'cv11', 'ss01', 'ss03'`. Same rationale as Lumen.

Sizes worth memorizing (from `styles.tsx`):

| Element | Class | Size |
|---|---|---|
| Hero recovery number | inline 56px | Instrument Serif |
| Hero unit suffix `%` | inline 28px | Instrument Serif |
| KPI value | `.cadence-kpi .cadence-value` | 30px Instrument Serif `letter-spacing: -0.015em` |
| Metric row value | `.cadence-metric-row .cadence-val` | 22px Instrument Serif tabular |
| Eyebrow | `.cadence-h-eyebrow` | 11px uppercase, `letter-spacing: 0.1em`, weight 550 |
| Display | `.cadence-h-display` | Instrument Serif, weight 400, `letter-spacing: -0.02em`, `line-height: 1` |
| Section title | `.cadence-section-head .cadence-title` | 13px Inter 600 |
| Brand wordmark | `.cadence-brand-name` | 18px Instrument Serif `letter-spacing: -0.01em` |
| Body default | `.cadence-app` | 14px Inter 1.45 |

`.cadence-num` and `.cadence-mono` are the two utility classes for tabular alignment. Use `.cadence-num` whenever a number sits next to another number in a column. Use `.cadence-mono` for kbd labels and source-of-truth identifiers.

## Color

Cadence tokens are defined on `.cadence-app` in `styles.tsx` lines 47 to 88. The palette is sage-clinical and warm-coral, very deliberately distinct from Lumen's earthy forest.

Light theme:

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#f4f1ea` | Paper beige, behind the painterly art |
| `--surface` | `#ffffff` | Main card, KPI tiles |
| `--surface-2` | `#faf9f6` | Tinted card variant |
| `--surface-3` | `#f4f3ef` | Hover background |
| `--ink` | `#161614` | Primary text |
| `--ink-3` | `#7a7a75` | Muted labels |
| `--ink-4` | `#a8a8a3` | Faint labels (eyebrow) |
| `--accent` / `--accent-2` | `#5b8a72` | Sage green, the Cadence color |
| `--accent-soft` | `#e8efe9` | Pos pill background |
| `--accent-ink` | `#3d6650` | Pos pill text |
| `--pos` | `#5b8a72` | Up trends, "Primed" pill |
| `--neg` | `#c2655c` | Down trends, warm coral |
| `--warn` | `#c89a4a` | Yellow caution |
| `--info` | `#5a7d9c` | Slate blue (rhyme pill) |
| `--coral` | `#d4a3a3` | Avatar gradient stop |
| `--bloom` | `#e8c4b0` | Decorative accent |

Painterly presets (from `cadence/page.tsx` lines 63 to 69, identical to Lumen so the two routes feel like siblings):
- `painterly` — sage and coral sunrise.
- `dusk` — indigo to coral.
- `paper` — flat `#f4f1ea`.
- `charcoal` — dark mode bias.

Dark mode is opt-in via the tweaks panel (toggles `.dark` on `.cadence-app`). The dark token block is set up as a parallel to the light block.

The full palette is undocumented inside `globals.css`. All Cadence colors are scoped to `.cadence-app` in `_components/styles.tsx`. If you need a new biomarker-specific color, add it to the same scope and reference it via a CSS variable; do not put a Cadence color in `globals.css`.

## Layout and density

Page shell (`styles.tsx` lines 47 to 88, plus 121 to 135):
- `.cadence-app` is `100vw × 100vh`, `position: relative`, `overflow: hidden`. The cascade root.
- `.cadence-painterly` is `position: absolute; inset: 0; z-index: 0`.
- `.cadence-app-shell` is the grid container: `padding: 14px; grid-template-columns: 220px 1fr; grid-template-rows: 1fr; gap: 14px`.

Note from the page docstring (`page.tsx` lines 36 to 39): the `.cadence-app-shell` rename is THE bugfix for the empty-main-panel problem. `.app` in `globals.css` sets `grid-template-rows: 44px 1fr 26px`, which would combine with our `220px 1fr` columns and squeeze the main panel into a 44px row. Never reuse `.app` here.

Card discipline:
- `.cadence-sidebar` is a glass card: `rgba(255,255,255,0.72)` with `backdrop-filter: blur(20px) saturate(120%)`. Rounded `var(--radius-lg)` = 14px.
- `.cadence-main` is a solid white card: `border-radius: var(--radius-lg); border: 1px solid rgba(255,255,255,0.5); box-shadow: var(--shadow-card)`. Owns its own scroll via `.cadence-scroll`.
- `.cadence-topbar` is a 46px row inside `.cadence-main` with crumbs left and a `.cadence-top-actions` cluster right.

Density rules:
- Inside the main card, `.cadence-scroll-pad` is `padding: 22px 28px 80px 28px`. The 80px bottom pad is intentional so the scroll never bottoms-out flush with the card edge.
- KPI grid is four columns: `grid-template-columns: repeat(4, 1fr); gap: 12px`. Each KPI tile is `min-height: 108px`.
- Metric rows are 4-column grids `18px 1fr auto auto` with 10px gap (`.cadence-metric-row` line 412).
- Section heads are `padding: 6px 0 12px 0`. Tight rhythm.

## Component patterns

By file. Read the source before forking a pattern.

- **Sidebar.** `_components/sidebar.tsx`. Brand cluster (`.cadence-brand`) at top, nav groups (`.cadence-nav-group`) with item rows (`.cadence-nav-item`), foot cluster (`.cadence-sidebar-foot`) at bottom with avatar and plan label.
- **Topbar.** `_components/shared.tsx` exports `Topbar`. 46px row with `.cadence-crumbs` and `.cadence-top-actions`.
- **KPI tile.** `.cadence-kpi` with `.cadence-label` row, `.cadence-value` Instrument Serif 30px, optional `.cadence-delta` at bottom. Use the `.cadence-kpi-grid` four-col grid.
- **Metric row.** `.cadence-metric-row` for the Today screen's vertical key-metrics column. 18px icon | 1fr label | auto value | auto delta. Deltas use `.cadence-delta.cadence-pos`, `.cadence-neg`, `.cadence-flat` pill variants.
- **Pill.** `.cadence-pill` family: `.cadence-pill-pos`, `.cadence-pill-neg`, `.cadence-pill-warn`, `.cadence-pill-info`, `.cadence-pill-outline`. 22px tall, fully rounded.
- **Card.** `.cadence-card` plain. `.cadence-card-tinted` for the surface-2 variant. `.cadence-card-pad` (16px) and `.cadence-card-pad-lg` (22px).
- **Charts.** `_components/charts.tsx` exports `DayTrajectory`, `RhymeHeatmap`, `TagDonut`, `ThreadRibbon`, `Ring`. Charts are SVG, sized via `.cadence-chart-wrap`.
- **Cmd+K palette.** `.cadence-cmdk-back` backdrop, `.cadence-cmdk` 580px modal, `.cadence-cmdk-input`, `.cadence-cmdk-list`, `.cadence-cmdk-group`, `.cadence-cmdk-item`. Same shape as Lumen.
- **Tweaks panel.** `_components/tweaks.tsx`. Mutates accent / background / dark on `.cadence-app` via the `rootRef`. Exposes the four painterly presets.
- **Buttons.** `.cadence-btn` (default), `.cadence-btn-primary` (ink fill), `.cadence-btn-accent` (sage fill), `.cadence-btn-ghost` (transparent border). Height 28px, padding `0 11px`.
- **Icon button.** `.cadence-icon-btn` 28×28, optionally `.cadence-outline` for a bordered variant.

## Motion

- `100ms` for sidebar nav background transitions (`.cadence-nav-item` line 198).
- `120ms` for icon button and primary button color/background transitions.
- The painterly background is static. Do not animate it.

The screen-fade animation (referenced as `.cadence-screen-fade` on the screen root `<div>` in each screen file) is the only intra-page transition. It runs once on mount because each screen is a fresh component subtree thanks to the `switch (screen)` block in `page.tsx` lines 129 to 159.

## States

Empty:
- Each screen owns its own empty state. The Today screen does not have a real empty state because the demo data ships preloaded; if you build a real ingest pipeline, add an empty state per screen and link from it to the Sources screen ("connect a wearable").
- Cmd+K palette empty state: handled in `_components/cmdk.tsx`.

Loading:
- No global loading skeleton at this stage. Charts compute synchronously off the demo data.

Error:
- Error surfaces are not yet defined. When you add them, do not reuse the `.ws-banner--warn` from the workstation; use `.cadence-pill-warn` or a card with a coral left border to keep the surface consistent.

Stale:
- A wearable that has not synced in N hours should surface a `.cadence-pill-warn` on the Sources screen. As of 2026-04-27 this state is not implemented in the screen files; flag it as a TODO if you ship the live ingest path.

Disclaimer:
- Cadence runs on mock data. The hero number and rhyme percentage are computed on a fictional Buba's 365-day history, not real biometrics. Any real-data integration must add an explicit "your data" badge somewhere on the topbar so the user understands what they are looking at.

## Don'ts

- Do not import Cadence colors or classes from `globals.css`. Cadence's full palette is scoped to `.cadence-app` and that is on purpose.
- Do not use trading semantics. A red number in Cadence does not mean "loss"; it means "below baseline" or "needs attention." Copy must reflect that.
- Do not skip the `cadence-` prefix on a class. The header docstring at `styles.tsx` lines 5 to 26 documents the bug from the previous revision: generic class names like `.app`, `.main`, `.card`, `.btn` collided with `globals.css` and squeezed the main panel into a 44px row.
- Do not reuse the workstation's nine-lens radar. Cadence does not need it; the rhyme finder is the trust signal.
- Do not animate biomarker numbers. Show them stable. A heart rate that ticks counts noise as visible signal.
- Do not put a `position: fixed` element inside `.cadence-app` for chrome. The cmdk modal is the only legal fixed element here.
- Do not exceed Instrument Serif 56px for the hero. That is the load-bearing scale. Going to 72px breaks the "calm clinical report" feel.
- Do not depend on the global `body { overflow: hidden }` rule. The `.cadence-app` is its own viewport with its own scroll inside `.cadence-scroll`.
