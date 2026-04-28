# Workstation Design Guideline

The default Workstation at `/workstation`. This is the flagship surface: an analog finder for time series. A researcher pulls up SPY, drags a query window over a six-month region, and gets back the top-K historically similar windows plus a P10 to P90 forecast cone derived from what came next. Everything here is tuned for that single workflow.

Code anchors:
- Page shell: `the-similarity-app/app/workstation/page.tsx`
- The workstation itself: `the-similarity-app/components/workstation/workstation.tsx`
- Charts: `the-similarity-app/components/workstation/line-chart.tsx`, `line-chart-lw.tsx`
- Styles: the `:root` palette and the `.workstation`, `.side`, `.main`, `.ws-*`, `.chart-card`, `.chart-stack` blocks in `the-similarity-app/app/globals.css`

## Purpose and audience

Buyside researcher, sellside quant, PM, founder running their own portfolio. They have a Bloomberg or TradingView open in another window. They are evaluating one of two questions:

1. "Is the current setup like anything I have seen before, and if so what came next?"
2. "Did this analog actually hit when I traded it last quarter?"

"Good" looks like: every pixel earns its keep, numbers are tabular, dates are unambiguous, charts are draggable with no lag, and nothing on screen is decorative theatre. A frozen ticker price would destroy credibility instantly. See the marquee comment block in `app/workstation/page.tsx` line 386 onward for the literal rule: "Hardcoded ticker prices were removed: frozen numbers that never update destroy credibility instantly with a quant or PM."

## Relationship to DESIGN_LANGUAGE.md

Workstation is the most direct expression of the base document. It inherits:

- Tabular numbers everywhere via `font-feature-settings: 'tnum'` on `.mono` and `.num`.
- Flat semantic color: `var(--positive)` `#1c5b3d`, `var(--negative)` `#8a2a2a`. No gradients on chrome.
- Compact dense card grid for analog cards.
- Restraint on motion: hover transitions are 120 to 200ms.

It deviates in three places:

1. **Width.** `1100px` is not a constraint here. The workstation is a fixed three-column grid (`260px 1fr 320px`, see `.workstation` in `globals.css`) and fills the viewport. The 1100px container in the base doc applies to editorial pages like the home view and the case studies, not to the terminal.
2. **Typography stack.** Base says SF Pro. Workstation runs Newsreader (display serif) plus Inter (sans) plus JetBrains Mono (labels). See `:root --serif --sans --mono` in `globals.css` lines 46 to 48. The serif shows up in card titles and notebook prose; numbers stay in mono.
3. **Surface tone.** Base background is `#ffffff`. Workstation runs a warm paper `#faf9f6` (`--bg`) with elevated cards at `#ffffff` (`--bg-elevated`). The warm tone is intentional and editorial, not Bloomberg-clinical.

## Voice and tone

Quant-newsroom voice. Short, factual, slightly editorial. Never marketing.

Real strings from the UI:

- Marquee tagline: `Structural intelligence for time, state & simulation`
- Marquee tagline: `Find what rhymes · model what evolves · simulate what comes next`
- Notebook prose example (workstation.tsx line 1952): `Nine lenses agree that late-'18 Q4 and now share a regime.`
- Status bar: `engine v4.14 · nine lenses` and `feed live` or `feed demo`
- Empty catalog headline: `No datasets registered yet`
- Pin banner: `Forecast computed from your N pinned analogs only.`

Rules:
- No exclamation points.
- No emoji except the load-bearing `🔶` and `ℹ` in `.ws-banner__icon`.
- Absolute units always carry the unit (`60 d`, `7,500 bars`, `+3.2%`).
- Dates are `MMM D, YYYY` for prose and `YYYY-MM-DD` inside cards (see `formatShortDate` in `workstation.tsx`).
- Time is wall-clock SF, format `Apr 20, 2026 · 09:47 SF` (see `nyClock` block in `app/workstation/page.tsx`).

## Typography

Three families, defined as CSS custom properties at `:root` in `globals.css`:

- `--serif` Newsreader for display titles and the notebook narrative.
- `--sans` Inter for body, controls, navigation. Default `body { font-family: var(--sans); font-size: 13px; line-height: 1.55 }`.
- `--mono` JetBrains Mono for labels, numbers, kbd chips, status bar.

Utility classes that combine them, defined at `globals.css` lines 121 to 129:
- `.serif` 500 weight, `letter-spacing: -0.01em`. Use for chart card titles like `SPX · daily`.
- `.label` 10px mono, uppercase, `letter-spacing: 0.14em`, color `var(--ink-3)`. Use for every micro caps label.
- `.mono` JetBrains Mono with `tnum` and `zero` feature flags on. Use for any number that lives next to other numbers.
- `.num` mono with only `tnum`. Use when you want tabular alignment but not the slashed zero.
- `.kbd` for keyboard chips: `<span class="kbd">/</span>`.

Sizes that recur and should not be invented anew:

| Element | Size | Family |
|---|---|---|
| Page header (e.g. dataset name in chart card) | 15px | serif 500 |
| Section header inside sidebar | 10px mono uppercase via `.label` | mono |
| Card label | 10px mono uppercase via `.label` | mono |
| Card value (ticker, count) | 18px serif 500 or 11.5px mono | mono or serif |
| Status bar | 10.5px mono `letter-spacing: 0.04em` | mono |
| Kbd chip | 10px mono | mono |

## Color

Light theme tokens are at `globals.css` lines 7 to 57. Dark theme overrides at lines 60 to 91. Both are scoped to `:root` (with `[data-theme="dark"]` selector) so any descendant of the workstation route resolves them.

Workstation-specific tokens worth memorizing:

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--bg` | `#faf9f6` | `#0e0d0b` | Body / page background |
| `--bg-elevated` | `#ffffff` | `#15140f` | Sidebar, status bar, drawers |
| `--bg-card` | `#ffffff` | `#181712` | Chart card, dataset cards |
| `--bg-inset` | `#f2f0ea` | `#1f1d18` | Marquee strip, kbd chip background |
| `--ink` / `--ink-2` / `--ink-3` / `--ink-4` | `#14130f` to `#9a978d` | `#ecead9` to `#5a564a` | Four-step ink ramp |
| `--rule` / `--rule-strong` | `#e6e2d6` / `#cec9b8` | `#2a2721` / `#3a362d` | Hairlines vs dividers |
| `--positive` | `#1c5b3d` | `#6fb88e` | Up trends, hit forecasts |
| `--negative` | `#8a2a2a` | `#c77272` | Down trends, missed forecasts |
| `--accent` | `#5a2b2b` | `#c88a8a` | Oxblood. Selection, query line, pin banner |
| `--c-query` | `#14130f` | `#ecead9` | Query-window line on chart |
| `--c-analog` / `--c-analog-strong` | `#9a978d` / `#6f6c62` | `#7b7868` / `#b8b4a2` | Analog overlay lines |
| `--c-cone-fill` / `--c-cone-line` | green soft / `#1c5b3d` | green soft / `#6fb88e` | P10 to P90 forecast cone |
| `--c-grid` | `#eae6d8` | `#22201a` | Chart gridlines |

Theme is toggled by setting `data-theme="dark"` on `document.documentElement` (see `app/workstation/page.tsx` line 213). Never write a colour literal in a component if a token exists.

## Layout and density

The shell is three CSS rows (`44px 1fr 26px`, see `.app` in `globals.css`):

1. Marquee at 44px (`.marquee`)
2. Page content at 1fr (`.page`, `.workstation`)
3. Status bar at 26px (`.statusbar`)

The workstation itself is three CSS columns (`260px 1fr 320px`, see `.workstation`):

- `.side` left rail: dataset selector, query window definition, pinned analogs, notebook.
- `.main` center: `.ws-search-row` over `.chart-stack` over the analog strip.
- `.right`: nine-lens radar plus narrative.

Breakpoint discipline lives in `globals.css` lines 745 to 805:

- `>= 1280px` three columns docked.
- `1024px to 1279px` right panel becomes a slide-in drawer behind a backdrop. `.ws-drawer-toggle--right` becomes visible.
- `768px to 1023px` left rail also becomes a drawer. Right panel hidden entirely.
- `< 768px` everything stacks. `.ws-mobile-notice` shows a "best viewed on desktop" banner.

Density rules:
- Sidebar section padding `var(--s-5) var(--s-5)` which is 20px on both axes.
- Chart card padding `var(--s-3) var(--s-4) var(--s-4)` (`.chart-card__body`).
- Chip row gap 4px (`.chip-row`). Chips `font-size: 10.5px` and `padding: 3px 7px`.
- Dotted border between sidebar key/value rows: `.side__row { border-bottom: 1px dotted var(--rule) }`.

## Component patterns

Cite by file. If you reuse one of these in a new screen, read the source first; do not invent a parallel pattern.

- **Marquee strip.** `.marquee` in `globals.css` line 155. Houses the brand wordmark (`.brand`), the rolling tagline (`.marquee__track`), and the search/tweaks/account cluster (`.nav__right`). Auto-scrolls via `@keyframes marquee` 90s linear infinite.
- **Status bar.** `.statusbar` in `globals.css` line 303. Mono 10.5px, `letter-spacing: 0.04em`. Items separated by `│` glyph in `.statusbar__sep`. Right-aligned cluster via `.statusbar__right`.
- **Sidebar section.** `.side__section` with a `.side__header` row (label plus optional context value) and either `.side__row` key/value pairs, a `.chip-row` for choices, or a `.saved-list` for pinned items.
- **Search row.** `.ws-search-row` over the chart stack. Contains the Top-K segmented selector (`.ws-topk`), horizon segmented selector (`.ws-horizon`), and the primary `.ws-search-btn` with a `.ws-search-btn__dot` dirty indicator and `.ws-search-btn__spinner` in-flight indicator.
- **Chart card.** `.chart-card` with `.chart-card__head` (title plus legend), `.chart-card__body` for the chart, `.chart-card__legend` for the colored dot legend.
- **Chip.** `.chip` for window length and view range pickers. Active state via `data-active="true"` attribute, not a class.
- **Banners.** `.ws-banner` family for offline / empty-catalog warnings. `.ws-pin-banner` for the curated-forecast confirmation. Both use a 3px left border in the surface accent color.
- **Empty state.** `.ws-empty-state__card` for the "no datasets registered yet" callout. Serif 22px headline plus body plus two CTAs.
- **Drawer toggles.** `.ws-drawer-toggle--left`, `.ws-drawer-toggle--right`, `.ws-drawer-close`, `.ws-drawer-backdrop` for the sub-1280px layout.

## Motion

Two transition timings, no more:

- `120ms ease` for color / border-color / background changes on buttons and chips. Example: `.ws-empty-state__cta`, `.ws-pin-banner__clear`.
- `200ms ease` for transform and slide-in drawers. Example: drawer `transform: translateX(100%)` to `0`.

The marquee is the single ambient animation: `@keyframes marquee 90s linear infinite`. Running 90 seconds end-to-end means it is barely perceptible, which is the point.

Do not animate:
- Numeric values (use `tnum` for stable alignment, jump to new values).
- Chart redraws (lightweight-charts handles its own pan/zoom).
- Layout grid changes when the user resizes the viewport.

Spinner: `.ws-search-btn__spinner` is a simple CSS rotation, used only while a search is in flight.

## States

Empty:
- Catalog empty: `.ws-empty-state__card` with headline "No datasets registered yet".
- Window empty (no bars in the dragged region): `.ws-micro-empty` with title "No data in this window".
- Analogs strip empty: `.ws-micro-empty--strip` variant, smaller padding.

Loading:
- Inline mono "Searching..." 12px next to the chart while a search is in flight.
- `.ws-search-btn__spinner` on the primary CTA.

Error / offline:
- `.ws-banner--warn` with the orange diamond icon. Example body: synthetic fallback notice. The banner has a dismiss button (`.ws-banner__dismiss`).
- `.ws-banner--info` with the i icon for empty-catalog hints.
- Status bar reads `feed demo` instead of `feed live` (see `DATA_MODE` in `app/workstation/page.tsx`).

Stale:
- `.dataset-card__stale-dot` red dot inside the dataset selector card when `lastUpdatedAt` is older than 48h on a daily-or-faster timeframe. See `isStale` helper in `workstation.tsx`.

Pinned:
- `.ws-pin-banner` shows above the metrics row when `pinned.size > 0`, with copy "Forecast computed from your N pinned analogs only." and a `.ws-pin-banner__clear` button.

## Don'ts

- Do not introduce a third typeface. Newsreader, Inter, JetBrains Mono. That is the set.
- Do not add gradients to chrome. The cone fill (`--c-cone-fill`) is the only legal gradient and it is on the chart, not the UI.
- Do not invent a fourth ink step beyond `--ink-4`. If you reach for 5 you are over-decorating.
- Do not put a hard-coded number in the marquee. The frozen-ticker rule is in the page docstring; a stale price reads as a mock instantly.
- Do not put theme-toggling logic anywhere except `app/workstation/page.tsx`. The keyboard shortcut `t` and the tweaks panel both write through `setSettings`.
- Do not let the workstation's grid columns reshuffle on a hover or click. The shell is fixed; only drawers slide.
- Do not use the home page's `.home__cta--primary` style for workstation buttons. Inside the workstation use `.ws-empty-state__cta--primary` and `.ws-search-btn` patterns.
- Do not skip `tnum` on a number column. Misaligned digits in a stack of analog scores is the single ugliest thing this surface can do.
