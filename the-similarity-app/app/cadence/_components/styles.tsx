/**
 * Cadence health workstation scoped stylesheet.
 *
 * The design's CSS uses generic class names (.card, .pill, .kpi, .btn,
 * .merch, .scroll, etc.) that would collide with any other route in this
 * app. To keep the styling page-local, every selector is prefixed with
 * `.cadence-app`. The only top-level rule is the `.cadence-app` block
 * itself, which sets the CSS custom properties (design tokens) that the
 * rest of the rules consume.
 *
 * Background note: the painterly background is rendered by a sibling
 * element with class `.cadence-painterly`. It is absolutely positioned
 * (NOT fixed) so it stays inside this route's wrapper and doesn't bleed
 * into other pages. Its background-image is mutated at runtime by the
 * tweaks panel to swap between Bloom/Dawn/Paper/Slate presets.
 *
 * Palette rationale (different from Lumen's earthy forest/sienna):
 *   - Default accent: #5b8a72 (sage green) — calm clinical biological feel
 *   - Bloom default: warm coral → sage gradient (sunrise + plant)
 *   - Dawn alt: deeper sunrise → indigo (early-morning feel)
 *   - Paper: clinical white (chart-of-the-day mode)
 *   - Slate: dark mode bias (night reading / sleep tracking)
 *
 * IMPORTANT: NEVER add un-prefixed selectors here. Anything without a
 * `.cadence-app` ancestor will leak into the rest of the app.
 */
"use client";

export const CADENCE_CSS = `
.cadence-app {
  --bg: #f4f1ea;
  --surface: #ffffff;
  --surface-2: #faf9f6;
  --surface-3: #f4f3ef;
  --border: #ececea;
  --border-strong: #dcdbd7;
  --ink: #161614;
  --ink-2: #3d3d3a;
  --ink-3: #7a7a75;
  --ink-4: #a8a8a3;
  --ink-5: #d2d2cd;
  --accent: #5b8a72;
  --accent-2: #5b8a72;
  --accent-soft: #e8efe9;
  --accent-ink: #3d6650;
  --pos: #5b8a72;
  --neg: #c2655c;
  --warn: #c89a4a;
  --info: #5a7d9c;
  --coral: #d4a3a3;
  --bloom: #e8c4b0;
  --shadow-card: 0 1px 0 rgba(20,20,20,0.03), 0 8px 24px -14px rgba(20,20,20,0.10);
  --shadow-pop: 0 12px 36px -10px rgba(20,20,20,0.22), 0 2px 6px rgba(20,20,20,0.06);
  --radius: 10px;
  --radius-lg: 14px;
  --radius-sm: 6px;
  --radius-pill: 999px;

  position: relative;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  color: var(--ink);
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-feature-settings: 'cv11', 'ss01', 'ss03';
  font-size: 14px;
  line-height: 1.45;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}
.cadence-app *, .cadence-app *::before, .cadence-app *::after { box-sizing: border-box; }
.cadence-app button { font-family: inherit; cursor: pointer; }
.cadence-app input,
.cadence-app textarea,
.cadence-app select { font-family: inherit; }

/* ============ painterly background — absolutely positioned inside the
   page, not fixed, so it's contained to this route only. The default
   Bloom preset is a warm coral → sage sunrise gradient. */
.cadence-app .cadence-painterly {
  position: absolute; inset: 0; z-index: 0;
  overflow: hidden;
  background: linear-gradient(160deg, #d4a3a3 0%, #e8c4b0 30%, #b8c9a8 60%, #5b8a72 100%);
  pointer-events: none;
}
.cadence-app .cadence-painterly::before {
  content: ''; position: absolute; inset: -10%;
  background:
    radial-gradient(ellipse 60% 40% at 20% 30%, rgba(220,180,170,0.55), transparent 60%),
    radial-gradient(ellipse 50% 35% at 75% 60%, rgba(140,180,150,0.45), transparent 60%),
    radial-gradient(ellipse 40% 30% at 50% 85%, rgba(60,90,75,0.35), transparent 60%),
    radial-gradient(ellipse 70% 50% at 90% 15%, rgba(200,150,140,0.45), transparent 70%);
  filter: blur(40px);
}
.cadence-app .cadence-painterly::after {
  content: ''; position: absolute; inset: 0;
  background-image:
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.4 0 0 0 0 0.35 0 0 0 0 0.30 0 0 0 0.6 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.30'/></svg>");
  mix-blend-mode: overlay;
  opacity: 0.5;
}

/* ============ app shell ============ */
.cadence-app .app {
  position: relative; z-index: 1;
  height: 100vh;
  padding: 14px;
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 14px;
}

/* ============ sidebar ============ */
.cadence-app .sidebar {
  background: rgba(255,255,255,0.72);
  backdrop-filter: blur(20px) saturate(120%);
  -webkit-backdrop-filter: blur(20px) saturate(120%);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: var(--radius-lg);
  padding: 14px 10px;
  display: flex; flex-direction: column;
  box-shadow: var(--shadow-card);
}
.cadence-app .brand {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px 18px 8px;
}
.cadence-app .brand-mark {
  width: 22px; height: 22px;
  border-radius: 6px;
  background: var(--ink);
  display: grid; place-items: center;
  color: #f4f1ea;
  font-family: 'Instrument Serif', serif;
  font-size: 16px; font-style: italic;
  line-height: 1;
}
.cadence-app .brand-name {
  font-family: 'Instrument Serif', serif;
  font-size: 18px;
  letter-spacing: -0.01em;
}
.cadence-app .brand-sub {
  margin-left: auto;
  font-size: 10px;
  color: var(--ink-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.cadence-app .nav-group { display: flex; flex-direction: column; gap: 1px; }
.cadence-app .nav-label {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-4);
  padding: 14px 10px 6px 10px;
  font-weight: 550;
}
.cadence-app .nav-item {
  display: flex; align-items: center; gap: 9px;
  padding: 6px 10px;
  border-radius: 7px;
  color: var(--ink-2);
  font-weight: 450;
  font-size: 13px;
  cursor: pointer;
  border: none; background: none;
  width: 100%;
  text-align: left;
  transition: background 100ms;
}
.cadence-app .nav-item:hover { background: rgba(0,0,0,0.04); color: var(--ink); }
.cadence-app .nav-item.active {
  background: rgba(0,0,0,0.06);
  color: var(--ink);
  font-weight: 550;
}
.cadence-app .nav-item .ico { width: 15px; height: 15px; flex: 0 0 15px; opacity: 0.75; }
.cadence-app .nav-item.active .ico { opacity: 1; }
.cadence-app .nav-item .badge {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--ink-3);
  background: rgba(0,0,0,0.05);
  padding: 1px 6px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}
.cadence-app .nav-item .badge.dot {
  width: 6px; height: 6px;
  padding: 0;
  background: var(--accent);
}

.cadence-app .sidebar-foot {
  margin-top: auto;
  padding: 10px 8px 4px 8px;
  border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 9px;
}
.cadence-app .avatar {
  width: 26px; height: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, #d4a3a3, #5b8a72);
  color: #fff;
  display: grid; place-items: center;
  font-size: 11px; font-weight: 600;
  flex: 0 0 26px;
}
.cadence-app .sidebar-foot .who { font-size: 12.5px; font-weight: 550; line-height: 1.1; }
.cadence-app .sidebar-foot .plan { font-size: 11px; color: var(--ink-3); line-height: 1.1; }

/* ============ main panel ============ */
.cadence-app .main {
  background: var(--surface);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255,255,255,0.5);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  display: flex; flex-direction: column;
  min-width: 0;
}

.cadence-app .topbar {
  height: 46px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 16px;
  gap: 10px;
  flex: 0 0 46px;
}
.cadence-app .crumbs {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px;
  color: var(--ink-3);
}
.cadence-app .crumbs .sep { color: var(--ink-4); }
.cadence-app .crumbs .here { color: var(--ink); font-weight: 500; }
.cadence-app .top-actions { margin-left: auto; display: flex; align-items: center; gap: 6px; }

.cadence-app .icon-btn {
  width: 28px; height: 28px;
  display: grid; place-items: center;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink-2);
  transition: all 120ms;
}
.cadence-app .icon-btn:hover { background: rgba(0,0,0,0.05); color: var(--ink); }
.cadence-app .icon-btn.outline { border-color: var(--border-strong); }
.cadence-app .icon-btn svg { width: 15px; height: 15px; }

.cadence-app .btn {
  display: inline-flex; align-items: center; gap: 6px;
  height: 28px;
  padding: 0 11px;
  border-radius: 7px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--ink);
  font-size: 12.5px;
  font-weight: 500;
  transition: all 120ms;
}
.cadence-app .btn:hover { background: var(--surface-2); }
.cadence-app .btn.primary {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.cadence-app .btn.primary:hover { background: #000; }
.cadence-app .btn.accent {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.cadence-app .btn.ghost { border-color: transparent; }
.cadence-app .btn.ghost:hover { background: rgba(0,0,0,0.05); }
.cadence-app .btn .ico { width: 13px; height: 13px; }

.cadence-app .scroll {
  flex: 1; min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.cadence-app .scroll::-webkit-scrollbar { width: 10px; }
.cadence-app .scroll::-webkit-scrollbar-thumb { background: var(--ink-5); border-radius: 999px; border: 3px solid var(--surface); background-clip: padding-box; }
.cadence-app .scroll::-webkit-scrollbar-thumb:hover { background: var(--ink-4); border: 3px solid var(--surface); background-clip: padding-box; }

/* ============ typography ============ */
.cadence-app .h-eyebrow {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--ink-3); font-weight: 550;
}
.cadence-app .h-display {
  font-family: 'Instrument Serif', serif;
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1;
}
.cadence-app .num { font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; }
.cadence-app .mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.cadence-app .pos { color: var(--pos); }
.cadence-app .neg { color: var(--neg); }

/* ============ pills / chips ============ */
.cadence-app .pill {
  display: inline-flex; align-items: center; gap: 5px;
  height: 22px; padding: 0 8px;
  border-radius: 999px;
  background: rgba(0,0,0,0.04);
  color: var(--ink-2);
  font-size: 11.5px;
  font-weight: 500;
}
.cadence-app .pill .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.cadence-app .pill.pos { background: var(--accent-soft); color: var(--accent-ink); }
.cadence-app .pill.neg { background: #f5e4e0; color: #7a2f24; }
.cadence-app .pill.warn { background: #f6ecd6; color: #6b4f0f; }
.cadence-app .pill.info { background: #e3ecf5; color: #1f4569; }
.cadence-app .pill.outline { background: transparent; border: 1px solid var(--border-strong); }

/* ============ section title ============ */
.cadence-app .section-head {
  display: flex; align-items: baseline; gap: 12px;
  padding: 6px 0 12px 0;
}
.cadence-app .section-head .title {
  font-size: 13px; font-weight: 600; color: var(--ink);
}
.cadence-app .section-head .sub { font-size: 12.5px; color: var(--ink-3); }
.cadence-app .section-head .actions { margin-left: auto; display: flex; gap: 4px; align-items: center; }

/* ============ card ============ */
.cadence-app .card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.cadence-app .card.tinted { background: var(--surface-2); }
.cadence-app .card-pad { padding: 16px; }
.cadence-app .card-pad-lg { padding: 22px; }

/* ============ KPI ============ */
.cadence-app .kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.cadence-app .kpi {
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex; flex-direction: column;
  min-height: 108px;
}
.cadence-app .kpi .label {
  font-size: 11.5px; color: var(--ink-3); font-weight: 500;
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 8px;
}
.cadence-app .kpi .label .ico { width: 13px; height: 13px; opacity: 0.7; }
.cadence-app .kpi .value {
  font-family: 'Instrument Serif', serif;
  font-size: 30px; line-height: 1;
  letter-spacing: -0.015em;
  color: var(--ink);
}
.cadence-app .kpi .delta {
  margin-top: auto; padding-top: 10px;
  font-size: 11.5px; color: var(--ink-3);
  display: flex; align-items: center; gap: 4px;
}
.cadence-app .kpi .delta .arrow { font-weight: 600; }

/* ============ metrics column (Today screen) — 6 vertical key metrics ============ */
.cadence-app .metric-col { display: flex; flex-direction: column; gap: 8px; }
.cadence-app .metric-row {
  display: grid;
  grid-template-columns: 18px 1fr auto auto;
  gap: 10px;
  align-items: center;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.cadence-app .metric-row .ico { width: 16px; height: 16px; color: var(--ink-3); }
.cadence-app .metric-row .lab { font-size: 12px; color: var(--ink-3); font-weight: 500; }
.cadence-app .metric-row .val {
  font-family: 'Instrument Serif', serif;
  font-size: 22px; line-height: 1;
  letter-spacing: -0.015em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.cadence-app .metric-row .unit { font-size: 11px; color: var(--ink-3); margin-left: 2px; }
.cadence-app .metric-row .delta {
  font-size: 11px; font-variant-numeric: tabular-nums;
  padding: 1px 6px; border-radius: 999px;
}
.cadence-app .metric-row .delta.pos { background: var(--accent-soft); color: var(--accent-ink); }
.cadence-app .metric-row .delta.neg { background: #f5e4e0; color: #7a2f24; }
.cadence-app .metric-row .delta.flat { background: rgba(0,0,0,0.04); color: var(--ink-3); }

/* ============ progress ============ */
.cadence-app .progress {
  height: 6px; background: rgba(0,0,0,0.06); border-radius: 999px; overflow: hidden;
  position: relative;
}
.cadence-app .progress > .fill { height: 100%; background: var(--ink); border-radius: 999px; }
.cadence-app .progress.thin { height: 4px; }
.cadence-app .progress > .fill.accent { background: var(--accent); }
.cadence-app .progress > .fill.warn { background: var(--warn); }
.cadence-app .progress > .fill.neg { background: var(--neg); }

/* ============ chart helpers ============ */
.cadence-app .chart-wrap { position: relative; }
.cadence-app .chart-wrap svg { display: block; width: 100%; height: 100%; }

/* ============ split layout ============ */
.cadence-app .split {
  display: flex;
  flex: 1;
  min-height: 0;
}
.cadence-app .content-col { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.cadence-app .scroll-pad { padding: 22px 28px 80px 28px; }

/* ============ command palette — fixed because it's a modal overlay ============ */
.cadence-app .cmdk-back {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(20,20,20,0.35);
  backdrop-filter: blur(4px);
  display: grid; place-items: start center;
  padding-top: 14vh;
}
.cadence-app .cmdk {
  width: 580px;
  max-width: 92vw;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  box-shadow: var(--shadow-pop);
  overflow: hidden;
}
.cadence-app .cmdk-input {
  width: 100%; height: 48px; border: none; outline: none;
  padding: 0 18px; font-size: 14px;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--ink);
}
.cadence-app .cmdk-list { max-height: 380px; overflow-y: auto; padding: 6px; }
.cadence-app .cmdk-group { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-4); padding: 10px 12px 4px 12px; font-weight: 550; }
.cadence-app .cmdk-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 7px; font-size: 13px; cursor: pointer; color: var(--ink); }
.cadence-app .cmdk-item:hover, .cadence-app .cmdk-item.active { background: rgba(0,0,0,0.05); }
.cadence-app .cmdk-item .ico { width: 14px; height: 14px; color: var(--ink-3); }
.cadence-app .cmdk-item .kbd { margin-left: auto; font-size: 10.5px; color: var(--ink-4); }

/* ============ kbd ============ */
.cadence-app .kbd {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  padding: 1px 5px;
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  background: var(--surface);
  color: var(--ink-3);
  line-height: 1.4;
}

/* ============ assistant / insight bubble ============ */
.cadence-app .ai-bubble {
  background: linear-gradient(180deg, #fafaf6, #f4f1ea);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  font-size: 13px;
  color: var(--ink);
  line-height: 1.55;
}
.cadence-app .ai-bubble .ai-head {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--ink-3); font-weight: 550;
  margin-bottom: 8px;
}
.cadence-app .ai-bubble .ai-head .pulse {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent); box-shadow: 0 0 0 0 var(--accent);
  animation: cadence-pulse 2s infinite;
}
@keyframes cadence-pulse {
  0% { box-shadow: 0 0 0 0 rgba(91,138,114,0.5); }
  70% { box-shadow: 0 0 0 6px rgba(91,138,114,0); }
  100% { box-shadow: 0 0 0 0 rgba(91,138,114,0); }
}

/* ============ utility ============ */
.cadence-app .row { display: flex; align-items: center; }
.cadence-app .col { display: flex; flex-direction: column; }
.cadence-app .gap-4 { gap: 4px; }
.cadence-app .gap-6 { gap: 6px; }
.cadence-app .gap-8 { gap: 8px; }
.cadence-app .gap-12 { gap: 12px; }
.cadence-app .gap-16 { gap: 16px; }
.cadence-app .gap-20 { gap: 20px; }
.cadence-app .gap-24 { gap: 24px; }
.cadence-app .grow { flex: 1; min-width: 0; }
.cadence-app .right { margin-left: auto; }
.cadence-app .mt-4 { margin-top: 4px; }
.cadence-app .mt-8 { margin-top: 8px; }
.cadence-app .mt-12 { margin-top: 12px; }
.cadence-app .mt-16 { margin-top: 16px; }
.cadence-app .mt-20 { margin-top: 20px; }
.cadence-app .mt-24 { margin-top: 24px; }
.cadence-app .mt-32 { margin-top: 32px; }
.cadence-app .mb-4 { margin-bottom: 4px; }
.cadence-app .mb-8 { margin-bottom: 8px; }
.cadence-app .mb-12 { margin-bottom: 12px; }
.cadence-app .mb-16 { margin-bottom: 16px; }
.cadence-app .mb-20 { margin-bottom: 20px; }
.cadence-app .mb-24 { margin-bottom: 24px; }
.cadence-app .text-3 { color: var(--ink-3); }
.cadence-app .text-2 { color: var(--ink-2); }
.cadence-app .fz-11 { font-size: 11px; }
.cadence-app .fz-12 { font-size: 12px; }
.cadence-app .fz-13 { font-size: 13px; }
.cadence-app .fz-14 { font-size: 14px; }
.cadence-app .fw-5 { font-weight: 500; }
.cadence-app .fw-6 { font-weight: 600; }

/* ============ donut legend ============ */
.cadence-app .legend-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0;
  font-size: 12.5px;
  border-bottom: 1px dashed var(--border);
}
.cadence-app .legend-row:last-child { border-bottom: none; }
.cadence-app .legend-row .sw { width: 8px; height: 8px; border-radius: 2px; flex: 0 0 8px; }
.cadence-app .legend-row .lab { color: var(--ink-2); }
.cadence-app .legend-row .pct { margin-left: auto; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.cadence-app .legend-row .amt { width: 80px; text-align: right; color: var(--ink); font-weight: 500; font-variant-numeric: tabular-nums; }

/* ============ rhyme card ============ */
.cadence-app .rhyme-card {
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  display: flex; flex-direction: column; gap: 12px;
  cursor: pointer;
  transition: all 120ms;
}
.cadence-app .rhyme-card:hover { border-color: var(--border-strong); transform: translateY(-1px); box-shadow: var(--shadow-card); }
.cadence-app .rhyme-card.featured {
  border-color: var(--accent);
  background: linear-gradient(180deg, var(--accent-soft), var(--surface));
}
.cadence-app .rhyme-card .rh-head { display: flex; align-items: baseline; gap: 12px; }
.cadence-app .rhyme-card .rh-date { font-size: 13px; font-weight: 600; color: var(--ink); }
.cadence-app .rhyme-card .rh-score {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; padding: 2px 7px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent-ink); font-weight: 600;
}
.cadence-app .rhyme-card .rh-outcome { font-size: 12.5px; color: var(--ink-2); }

/* ============ ring ============ */
.cadence-app .ring-wrap { position: relative; width: 84px; height: 84px; }
.cadence-app .ring-wrap .ring-text {
  position: absolute; inset: 0; display: grid; place-items: center;
  font-family: 'Instrument Serif', serif;
  font-size: 22px; line-height: 1;
}

/* ============ log entry ============ */
.cadence-app .log-row {
  display: grid;
  grid-template-columns: 60px 24px 1fr 100px 24px;
  gap: 10px;
  align-items: center;
  padding: 9px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  cursor: pointer;
  transition: background 80ms;
}
.cadence-app .log-row:hover { background: var(--surface-2); }
.cadence-app .log-row .tm { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--ink-3); }
.cadence-app .log-row .ic {
  width: 24px; height: 24px;
  border-radius: 6px;
  display: grid; place-items: center;
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--ink-3);
}
.cadence-app .log-row .ic svg { width: 12px; height: 12px; }
.cadence-app .log-row .body { min-width: 0; }
.cadence-app .log-row .body .ttl { font-weight: 500; color: var(--ink); }
.cadence-app .log-row .body .sub { font-size: 11.5px; color: var(--ink-3); }
.cadence-app .log-row .meta { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--ink-2); text-align: right; }

/* composer */
.cadence-app .composer {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 14px;
}
.cadence-app .composer input {
  flex: 1; height: 32px;
  border: none; background: transparent;
  font-size: 13.5px;
  outline: none;
  color: var(--ink);
}
.cadence-app .composer input::placeholder { color: var(--ink-4); }

/* ============ source card ============ */
.cadence-app .source-card {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  display: flex; align-items: center; gap: 14px;
}
.cadence-app .source-logo {
  width: 36px; height: 36px;
  border-radius: 8px;
  display: grid; place-items: center;
  color: #fff;
  font-size: 13px; font-weight: 600;
  flex: 0 0 36px;
}

/* ============ lab row ============ */
.cadence-app .lab-row {
  display: grid;
  grid-template-columns: 1fr 100px 130px 100px 120px;
  gap: 14px;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.cadence-app .lab-row.head {
  background: var(--surface-2);
  color: var(--ink-3);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 550;
  padding: 8px 16px;
}
.cadence-app .lab-row .nm { font-weight: 500; }
.cadence-app .lab-row .vl { font-family: 'Instrument Serif', serif; font-size: 18px; }

/* ============ filter bar ============ */
.cadence-app .filter-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.cadence-app .chip {
  display: inline-flex; align-items: center; gap: 5px;
  height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px dashed var(--border-strong);
  color: var(--ink-3);
  font-size: 12px;
  background: transparent;
}
.cadence-app .chip.active {
  border-style: solid;
  background: var(--surface-2);
  color: var(--ink);
}
.cadence-app .chip:hover { color: var(--ink); border-color: var(--ink-3); }

/* ============ search input ============ */
.cadence-app .search-input {
  height: 28px;
  padding: 0 10px 0 30px;
  border-radius: 7px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  width: 220px;
  font-size: 12.5px;
  outline: none;
  color: var(--ink);
  transition: border 120ms;
}
.cadence-app .search-input:focus { border-color: var(--ink-3); }
.cadence-app .search-wrap { position: relative; }
.cadence-app .search-wrap svg { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); width: 13px; height: 13px; color: var(--ink-4); }

/* ============ donut ============ */
.cadence-app .donut-c { width: 200px; height: 200px; position: relative; }
.cadence-app .donut-c .center {
  position: absolute; inset: 0; display: grid; place-items: center; text-align: center;
}

/* ============ tweaks panel custom ============ */
.cadence-app .tweak-swatch-row { display: flex; gap: 6px; flex-wrap: wrap; }
.cadence-app .tweak-swatch {
  width: 26px; height: 26px;
  border-radius: 6px;
  border: 2px solid transparent;
  cursor: pointer;
  position: relative;
}
.cadence-app .tweak-swatch.active {
  border-color: var(--ink);
  box-shadow: 0 0 0 2px var(--surface) inset;
}

/* mini segmented */
.cadence-app .seg {
  display: inline-flex;
  background: rgba(0,0,0,0.05);
  border-radius: 7px;
  padding: 2px;
}
.cadence-app .seg button {
  border: none; background: transparent;
  padding: 4px 10px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--ink-3);
  font-weight: 500;
}
.cadence-app .seg button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}

/* sparkline color helpers */
.cadence-app .spark-pos path.line { stroke: var(--pos); }
.cadence-app .spark-pos path.fill { fill: var(--pos); fill-opacity: 0.10; }
.cadence-app .spark-neg path.line { stroke: var(--neg); }
.cadence-app .spark-neg path.fill { fill: var(--neg); fill-opacity: 0.10; }

/* fade-in for screens */
.cadence-app .screen-fade {
  animation: cadence-fadeIn 220ms ease-out;
}
@keyframes cadence-fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
}

/* selection */
.cadence-app ::selection { background: var(--accent-soft); color: var(--accent-ink); }

/* ============ dark mode (toggled via .dark on .cadence-app root) ============ */
.cadence-app.dark {
  --bg: #1f2326;
  --surface: #2a3030;
  --surface-2: #25292c;
  --surface-3: #2f3535;
  --border: #3a4041;
  --border-strong: #4a5052;
  --ink: #ececea;
  --ink-2: #c4c5c2;
  --ink-3: #8a8c89;
  --ink-4: #6a6c69;
  --ink-5: #4a4d4a;
  --accent-soft: #2a3f33;
  --accent-ink: #c8e2d4;
}
.cadence-app.dark .cadence-painterly {
  background: linear-gradient(160deg, #1f2326 0%, #2a3030 50%, #1f2326 100%);
}
.cadence-app.dark .sidebar {
  background: rgba(36,40,42,0.7);
  border-color: rgba(255,255,255,0.06);
}
.cadence-app.dark .ai-bubble {
  background: linear-gradient(180deg, #2a3030, #25292c);
}

/* ============ tweaks panel (collapsed tab + expanded panel) ============
   These are page-scoped so they can't leak. The expanded panel is fixed
   to the bottom-right corner with a glass backdrop matching the design. */
.cadence-app .cadence-tweaks-tab {
  position: fixed; right: 16px; bottom: 16px; z-index: 90;
  height: 28px; padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.6);
  background: rgba(255,255,255,0.78);
  -webkit-backdrop-filter: blur(20px) saturate(160%);
  backdrop-filter: blur(20px) saturate(160%);
  color: var(--ink);
  font-size: 11.5px; font-weight: 500;
  box-shadow: 0 8px 24px -10px rgba(20,20,20,0.18);
}
.cadence-app .cadence-tweaks-panel {
  position: fixed; right: 16px; bottom: 16px; z-index: 90;
  width: 260px;
  background: rgba(250,249,247,0.82);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: 14px;
  box-shadow: 0 1px 0 rgba(255,255,255,0.5) inset, 0 12px 40px rgba(0,0,0,0.18);
  -webkit-backdrop-filter: blur(24px) saturate(160%);
  backdrop-filter: blur(24px) saturate(160%);
  color: #29261b;
  font-size: 11.5px;
  overflow: hidden;
}
.cadence-app.dark .cadence-tweaks-panel { background: rgba(42,48,48,0.82); color: var(--ink); }
.cadence-app.dark .cadence-tweaks-tab { background: rgba(42,48,48,0.78); color: var(--ink); border-color: rgba(255,255,255,0.08); }
.cadence-app .cadence-tweaks-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 8px 10px 14px;
}
.cadence-app .cadence-tweaks-head b { font-size: 12px; font-weight: 600; }
.cadence-app .cadence-tweaks-x {
  width: 22px; height: 22px;
  border: 0; background: transparent;
  border-radius: 6px;
  font-size: 16px; line-height: 1;
  color: rgba(41,38,27,0.55);
  cursor: pointer;
}
.cadence-app .cadence-tweaks-x:hover { background: rgba(0,0,0,0.06); color: #29261b; }
.cadence-app .cadence-tweaks-body { padding: 2px 14px 14px; display: flex; flex-direction: column; gap: 10px; }
.cadence-app .cadence-tweaks-sect {
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.06em; text-transform: uppercase;
  color: rgba(41,38,27,0.45);
  padding: 6px 0 0;
}
.cadence-app.dark .cadence-tweaks-sect { color: var(--ink-3); }
.cadence-app .cadence-tweaks-radio {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px;
  background: rgba(0,0,0,0.06);
  border-radius: 8px;
  padding: 2px;
}
.cadence-app .cadence-tweaks-radio button {
  border: 0; background: transparent;
  border-radius: 6px;
  padding: 5px 6px;
  font-size: 11px; font-weight: 500;
  color: inherit;
  cursor: pointer;
}
.cadence-app .cadence-tweaks-radio button.active {
  background: rgba(255,255,255,0.9);
  box-shadow: 0 1px 2px rgba(0,0,0,0.12);
}
.cadence-app.dark .cadence-tweaks-radio button.active { background: rgba(255,255,255,0.12); }
.cadence-app .cadence-tweaks-toggle-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 2px 0;
}
.cadence-app .cadence-tweaks-toggle {
  position: relative; width: 32px; height: 18px;
  border: 0; border-radius: 999px;
  background: rgba(0,0,0,0.15);
  transition: background 0.15s;
  cursor: pointer; padding: 0;
}
.cadence-app .cadence-tweaks-toggle[data-on="1"] { background: var(--accent); }
.cadence-app .cadence-tweaks-toggle i {
  position: absolute; top: 2px; left: 2px;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0,0,0,0.25);
  transition: transform 0.15s;
}
.cadence-app .cadence-tweaks-toggle[data-on="1"] i { transform: translateX(14px); }
`;
