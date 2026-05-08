# The Similarity Design Language

Clean, data-dense dashboard UI in the style of TradingView/Bloomberg Lite.
Every pixel serves a purpose. No decorative elements.

## Scope

This base doc covers editorial pages (home, case studies, demos, marketing surfaces) and the shared component primitives. Per-surface guidelines for `/workstation`, `/workstation/lumen`, `/cadence`, and `/prudent` live in `design_guideline/` at the repo root and override or extend the rules below where the surface's audience or density requires it. See `design_guideline/README.md` for the index.

---

## Layout

Editorial pages (home, case studies, demos) follow the 1100px container below. Terminal-grade surfaces (`/workstation`, `/workstation/lumen`, `/cadence`) are full-viewport and use their own grids; see `design_guideline/<surface>.md`.

- Card-based grid with horizontal scroll for overflow sections.
- Max-width container: `1100px`, centered.
- Generous padding: `32-40px` on container edges.
- Sections stacked vertically with clear hierarchy.
- Bold section headers with a `>` chevron link indicator.

```css
.container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 40px;
}

.section-header {
  font-size: 14px;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: #1a1a1a;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
}

.section-header::after {
  content: "\203A"; /* > chevron */
  font-size: 18px;
  color: #8a8a8a;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.card-row {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.card-row::-webkit-scrollbar {
  display: none;
}
```

---

## Cards

Light, compact containers for individual data points.

| Property | Value |
|---|---|
| Background | `#fafafa` |
| Border | `1px solid #f0f0f0` |
| Border radius | `12px` |
| Padding | `16px 20px` |
| Hover shadow | `0 2px 12px rgba(0,0,0,0.06)` |

Each card contains:
1. **Icon/logo** (16-20px, top-left)
2. **Label** (11px, `#8a8a8a`, uppercase tracking)
3. **Value** (18px, weight 600, tabular numbers)
4. **Unit tag** (11px, `#8a8a8a`, inline after value)
5. **Delta indicator** (12px, colored green/red, with arrow)

```css
.card {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 12px;
  padding: 16px 20px;
  cursor: pointer;
  transition: box-shadow 0.2s ease;
}

.card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.card-label {
  font-size: 11px;
  color: #8a8a8a;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}

.card-value {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a1a;
  font-feature-settings: 'tnum';
}

.card-unit {
  font-size: 11px;
  color: #8a8a8a;
  margin-left: 3px;
}

.card-delta {
  font-size: 12px;
  font-weight: 500;
  font-feature-settings: 'tnum';
  margin-top: 4px;
}

.card-delta.positive { color: #22a06b; }
.card-delta.negative { color: #e34935; }
```

---

## Typography

System font stack for editorial pages. Heavy headers, tabular numbers, tight spacing. Surface-specific font stacks live in their respective `design_guideline/*.md` files and override the SF Pro fallback chain below.

**Actual ship.** Workstation uses Newsreader (display serif), Inter, and JetBrains Mono. Lumen and Cadence use TradingView's Lightweight Charts default stack (`-apple-system, BlinkMacSystemFont, 'Trebuchet MS', Roboto, Ubuntu, sans-serif`) plus JetBrains Mono. Prudent uses Newsreader (composer 19px) with Inter. The SF Pro chain stays as the system fallback for editorial surfaces.

```css
:root {
  --font-family: 'SF Pro Display', -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}

body {
  font-family: var(--font-family);
  color: #1a1a1a;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

| Role | Size | Weight | Color | Extra |
|---|---|---|---|---|
| Page header | 22px | 800 | `#1a1a1a` | `letter-spacing: -0.03em` |
| Section header | 14px | 800 | `#1a1a1a` | `letter-spacing: -0.03em` |
| Card label | 11px | 400 | `#8a8a8a` | `text-transform: uppercase; letter-spacing: 0.04em` |
| Card value | 18px | 600 | `#1a1a1a` | `font-feature-settings: 'tnum'` |
| Secondary text | 11px | 400 | `#8a8a8a` | |
| Delta value | 12px | 500 | green/red | `font-feature-settings: 'tnum'` |
| Axis label | 10px | 400 | `#8a8a8a` | `font-feature-settings: 'tnum'` |

---

## Color

No gradients on UI chrome. Flat, high-contrast palette.

Lumen and Cadence ship painterly multi-stop gradient backgrounds. Those gradients are background art behind the cards, not chrome on the cards themselves. Cards stay flat. See `design_guideline/lumen.md` and `design_guideline/cadence.md` for the gradient compositions.

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#ffffff` | Page background |
| `--card-bg` | `#fafafa` | Card background |
| `--text-primary` | `#1a1a1a` | Headings, values |
| `--text-secondary` | `#8a8a8a` | Labels, secondary info |
| `--border` | `#f0f0f0` | Card borders |
| `--border-strong` | `#e8e8e8` | Dividers, tab underlines |
| `--positive` | `#22a06b` | Positive deltas, up trends |
| `--negative` | `#e34935` | Negative deltas, down trends |
| `--active` | `#1a1a1a` | Active tabs, selected pills |
| `--active-text` | `#ffffff` | Text on active backgrounds |
| `--pill-bg` | `#f5f5f5` | Time range selector background |

```css
:root {
  --bg: #ffffff;
  --card-bg: #fafafa;
  --text-primary: #1a1a1a;
  --text-secondary: #8a8a8a;
  --border: #f0f0f0;
  --border-strong: #e8e8e8;
  --positive: #22a06b;
  --negative: #e34935;
  --active: #1a1a1a;
  --active-text: #ffffff;
  --pill-bg: #f5f5f5;
}
```

---

## Navigation Tabs

Horizontal row, pill-shaped with rounded top corners. Sits on a thin divider.

```css
.tab-nav {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-strong);
  padding-bottom: 0;
}

.tab {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: 8px 8px 0 0;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.tab:hover {
  color: var(--text-primary);
}

.tab.active {
  background: var(--active);
  color: var(--active-text);
}
```

---

## Time Range Selector

Compact pill group for switching chart ranges (1D, 1W, 1M, 3M, 1Y, ALL).

```css
.time-range {
  display: inline-flex;
  background: var(--pill-bg);
  border-radius: 8px;
  padding: 2px;
  gap: 2px;
}

.time-range-item {
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-feature-settings: 'tnum';
  transition: color 0.15s ease, background 0.15s ease;
}

.time-range-item:hover {
  color: var(--text-primary);
}

.time-range-item.active {
  background: var(--active);
  color: var(--active-text);
}
```

---

## Charts

SVG area charts with smooth curves. Gradient fills, minimal grid.

### Line + Area

```css
.chart-line {
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.chart-area {
  /* Gradient from line color at 8% opacity to transparent */
}

.chart-grid-line {
  stroke: var(--border);
  stroke-width: 1;
  stroke-dasharray: none;
}

.chart-axis-label {
  font-family: var(--font-family);
  font-size: 10px;
  font-weight: 400;
  fill: var(--text-secondary);
  font-feature-settings: 'tnum';
}
```

### SVG Gradient Template

```html
<defs>
  <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="currentColor" stop-opacity="0.08" />
    <stop offset="100%" stop-color="currentColor" stop-opacity="0" />
  </linearGradient>
</defs>
```

### Current Value Marker

Small dot at the latest data point with a dark rounded label.

```css
.chart-dot {
  r: 3;
  fill: var(--text-primary);
}

.chart-value-label {
  background: var(--active);
  color: var(--active-text);
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  font-feature-settings: 'tnum';
}
```

---

## Interactions

Fast and responsive. No heavy animations.

```css
/* Global transition defaults */
* {
  transition-timing-function: ease;
}

/* Cards: shadow on hover */
.card { transition: box-shadow 0.2s ease; }
.card:hover { box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06); }

/* Buttons: border color on hover */
.btn {
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  background: var(--bg);
  color: var(--text-primary);
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.btn:hover {
  border-color: var(--text-secondary);
}

/* All interactive elements */
[role="button"],
button,
a,
.card,
.tab,
.time-range-item {
  cursor: pointer;
}
```

---

## Spacing Scale

Consistent spacing based on a 4px grid.

| Token | Value | Usage |
|---|---|---|
| `--space-xs` | `4px` | Inline gaps, icon-to-text |
| `--space-sm` | `8px` | Compact internal padding |
| `--space-md` | `12px` | Card grid gap, card internal |
| `--space-lg` | `16px` | Card padding, section gaps |
| `--space-xl` | `24px` | Between sections |
| `--space-2xl` | `32px` | Container padding |
| `--space-3xl` | `40px` | Page-level padding |

---

## Summary

| Principle | Rule |
|---|---|
| Density | Information-dense but not cluttered. Compact cards, small labels, large values. |
| Contrast | High contrast between values (`#1a1a1a`, 18px, 600) and labels (`#8a8a8a`, 11px, 400). |
| Precision | Swiss/editorial. Tabular numbers everywhere. Tight letter-spacing on headers. |
| Restraint | No decorative elements, no gradients on chrome, no heavy animations. |
| Color | Semantic only: green = positive, red = negative. Everything else is grayscale. |

---

## Per-surface guidelines

The base doc above is the editorial baseline. Each terminal surface has its own guideline that overrides or extends these rules where the audience and information density demand it. Start at `design_guideline/README.md` for the index.

- `design_guideline/workstation.md`: flagship Bloomberg-Lite analog finder
- `design_guideline/lumen.md`: `<Workstation>` reskinned via CSS-variable cascade for demos
- `design_guideline/cadence.md`: nine-screen personal-health workstation
- `design_guideline/prudent.md`: conversational NL-to-time-series journal
