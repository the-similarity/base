# Copy Data & World Models — UI Design Reference

**Status:** reference design adopted 2026-04-16.
**Scope:** dashboard UI for the synthetic copy-data and world-models product surfaces
(see `vision/synthetic_copies_worlds_eval_mvp.md`, `vision/synthetic_data_platform.md`,
`vision/synthetic_worlds_eval.md`).

This is a **dark-theme** reference (working name: *"Orbit"*) distinct from the
light Bloomberg-lite language in `DESIGN_LANGUAGE.md`. Use Orbit for the
copy-data / world-models product pages; keep the light language for the
similarity analytics dashboard.

---

## Overall impression

- Dark, near-black canvas with soft edge glow around the app frame.
- Two-pane layout: fixed left sidebar (nav + favorites) and a main content area.
- One strong accent color (warm orange) used sparingly: brand mark, the
  single highlighted bar in charts, and hover dots.
- Generous whitespace, large page header typography, subtle card separation.

---

## Layout

```
┌─────────────────────────────────────────────────────────────┐
│  [Logo] Orbit              [panel]                          │
│  ─────────────                                              │
│  [ ⌘K  Search        ]      Dashboard   14 Live Projects    │
│                                                             │
│  NAVIGATION                 Good morning, Aman              │
│   ■ Dashboard       ←active                                 │
│     Workspace         v    ┌──────────┐ ┌──────────┐ ┌───── │
│     Business Hub      v    │ Active   │ │ Pending  │ │ …    │
│     Clients           v    │ Contracts│ │          │ │      │
│     Companies         v    │   25     │ │   09     │ │      │
│     Growth Report          │ +5 mo    │ │ +6 last  │ │      │
│                            └──────────┘ └──────────┘ └───── │
│  FAVORITES                                                  │
│     Apple      COMPANY     ┌──────────────────────────────┐ │
│     Google     COMPANY     │ Revenue   $10,985.56         │ │
│     Figma      COMPANY     │           2.5% ↓ vs last wk  │ │
│     Aman       DESIGNER    │        [bar chart — orange]  │ │
│                            │   Mon Tue Wed Thu  Fr …      │ │
│                            └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

Dimensions (observed from reference):

| Region | Notes |
|---|---|
| Sidebar width | ~280–300px, full height |
| Main content padding | ~32–40px |
| Section gap | ~24px between KPI row and chart card |
| Corner radius (cards) | 14–16px |
| Corner radius (pills/nav items) | 10–12px |

---

## Color

Flat, dark palette. One orange accent. Text is near-white with a muted gray for
secondary copy.

| Token | Value (target) | Usage |
|---|---|---|
| `--bg` | `#0E0F11` | App canvas |
| `--surface-1` | `#141518` | Sidebar, top-level surface |
| `--surface-2` | `#1A1C20` | Cards, raised panels |
| `--surface-3` | `#22252A` | Hover/active states, pill bg |
| `--border` | `#26292F` | Card and divider lines (very subtle) |
| `--text-primary` | `#F5F6F7` | Headings, KPI values |
| `--text-secondary` | `#9AA0A6` | Labels, nav items, axis text |
| `--text-tertiary` | `#6B7077` | Disclosures, placeholder |
| `--accent` | `#F07A1A` | Brand mark, highlighted bar, active dot |
| `--accent-glow` | `rgba(240,122,26,0.35)` | Soft glow on highlighted chart bar |
| `--positive` | `#2BD97B` | "+5 vs last month" |
| `--negative` | `#F05454` | "2.5% ↓ vs last week" |

The ambient panel glow around the frame in the reference is a large, soft
outer shadow on the app container:
`box-shadow: 0 24px 80px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.03) inset;`

---

## Typography

Same system stack as the light language (SF Pro Display → system sans). Size
and weight shift heavier for the dark theme because perceived weight drops on
dark backgrounds.

| Role | Size | Weight | Color | Notes |
|---|---|---|---|---|
| Page greeting ("Good morning, Aman") | 40–44px | 700 | `--text-primary` | Letter-spacing `-0.02em` |
| Brand wordmark ("Orbit") | 22px | 700 | `--text-primary` | Paired with 28px logo |
| Section label ("NAVIGATION", "FAVORITES") | 11px | 600 | `--text-secondary` | Uppercase, `letter-spacing: 0.08em` |
| Nav item | 15px | 500 | `--text-secondary` (700 + primary when active) | |
| KPI label ("Active Contracts") | 13px | 500 | `--text-secondary` | |
| KPI value ("25", "09") | 56px | 700 | `--text-primary` | Tabular numbers |
| Delta line ("+5 vs last month") | 12px | 500 | `--positive` / `--negative` | Tabular numbers |
| Chart axis (Mon, Tue, …) | 12px | 500 | `--text-secondary` | |
| Chart hover label ("$9,340") | 12px | 600 | `--text-primary` on `--surface-3` pill | Rounded pill, 4px radius |

---

## Sidebar

- Sticky, full-height, `--surface-1` background, 1px right border in `--border`.
- Top: logo tile (28px rounded square, orange fill, white eye icon) + wordmark.
- Below: search input, pill-shaped, `--surface-2`, with a sparkle icon on the
  left and `⌘K` shortcut label on the right.
- **Navigation section**: 11px uppercase label, then a vertical list of items.
  Each item is 44px tall, 12px horizontal padding, 12px radius.
  - Active state: filled `--surface-3`, primary text, leading icon in white.
  - Items with sub-menus show a chevron-down on the right.
- **Favorites section** sits below a soft divider. Each row is
  `[avatar/icon] [name] ......... [role/type label]` where the right label is
  11px `--text-tertiary` uppercase.

---

## KPI cards (top row)

Horizontally scrollable row of equal-width cards.

- Background `--surface-2`, 1px `--border`, 16px radius.
- Padding `24px 28px`.
- Layout:
  - Top: small label ("Active Contracts") in `--text-secondary`.
  - Center-left: very large numeric value.
  - Bottom-left: delta in green/red with direction glyph.
  - Right: small illustrative mark (stacked-cards glyph in reference). Keep
    these as optional decorative SVGs at ~40% opacity — they must never
    compete with the number.

Numbers use leading zeros for small integers ("09" not "9") — this is a
deliberate stylistic choice in the reference and should be applied consistently
for single- and double-digit KPI values that belong in the same row.

---

## Chart card (Revenue)

- Same surface as KPI cards but taller and full-width.
- Header stack: label ("Revenue"), then big value ("$10,985.56"), then delta
  line. Delta uses `↓`/`↑` glyph plus `vs last <period>`.
- Chart: vertical bar chart, one bar per weekday.
  - Bars default to `--surface-3` with very subtle vertical gradient
    (top slightly brighter) and ~12px rounded top corners.
  - **One highlighted bar** uses `--accent` with a soft glow
    (`filter: drop-shadow(0 0 24px var(--accent-glow))`).
  - Hovered/selected bar shows a tiny white dot and a floating rounded pill
    with the exact value ("$9,340"). Pill bg = `--surface-3`, text = primary.
  - Dashed guide line from the pill to the bar top, 1px, `--text-tertiary`
    at 40% alpha.
  - X-axis labels sit below with a small gap, no axis line.
  - No Y gridlines — keep the chart chromeless.

---

## Motion & interaction

- All transitions short: 120–180ms, `ease-out`.
- Hover on cards: border shifts to `--text-tertiary`, no scale.
- Hover on bars: glow expands slightly (accent-glow goes from 35% → 50% alpha);
  value pill fades in.
- No long-running loops, no parallax, no decorative background animation.

---

## Do / don't

**Do**
- Use the orange accent on exactly one element per screen region.
- Keep KPI values oversized. The number is the hero.
- Keep surfaces within two steps of the canvas brightness (`surface-1`, `-2`).
- Use tabular numbers everywhere — KPIs, deltas, axis labels, hover pills.

**Don't**
- Don't introduce secondary accent colors. Positive/negative greens/reds are
  semantic only — never decorative.
- Don't gradient the card backgrounds; gradients are reserved for the single
  highlighted bar and the app-frame ambient glow.
- Don't use drop shadows on cards — the `--border` line is the separator.
- Don't mix this dark language with the light `DESIGN_LANGUAGE.md` on the
  same screen.

---

## Cross-links

- Product surfaces this applies to: `vision/synthetic_copies_worlds_eval_mvp.md`,
  `vision/synthetic_data_platform.md`, `vision/synthetic_worlds_eval.md`.
- Light-theme counterpart (similarity analytics): `docs/design/DESIGN_LANGUAGE.md`.
- Frontend codebase that will implement this: `the-similarity-app/`.

---

## Source

Reference screenshot supplied in-session 2026-04-16. The image itself was not
checked in; specs above are transcribed from it. If we later add the PNG,
store it under `docs/design/images/orbit_dashboard_ref.png` and link from this
doc.
