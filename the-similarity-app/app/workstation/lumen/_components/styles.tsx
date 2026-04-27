/**
 * Lumen Finance scoped stylesheet.
 *
 * The design's CSS uses generic class names (.card, .pill, .kpi, .btn,
 * .merch, .scroll, etc.) that would collide with any other route in this
 * app. To keep the styling page-local, every selector is prefixed with
 * `.lumen-app`. The only top-level rule is the `.lumen-app` block itself,
 * which sets the CSS custom properties (design tokens) that the rest of
 * the rules consume.
 *
 * Background note: the painterly background is rendered by a sibling
 * element with class `.lumen-painterly`. It is absolutely positioned
 * (NOT fixed) so it stays inside this route's wrapper and doesn't bleed
 * into other pages. Its background-image is mutated at runtime by the
 * tweaks panel to swap between Painterly/Dusk/Char/Paper presets.
 *
 * IMPORTANT: NEVER add un-prefixed selectors here. Anything without a
 * `.lumen-app` ancestor will leak into the rest of the app.
 */
"use client";

export const LUMEN_CSS = `
.lumen-app {
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
  --accent: #0a6b48;
  --accent-2: #0e8556;
  --accent-soft: #e7f0ea;
  --accent-ink: #064a32;
  --pos: #0a6b48;
  --neg: #b14a3a;
  --warn: #b07c1d;
  --info: #2e5d8c;
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
.lumen-app *, .lumen-app *::before, .lumen-app *::after { box-sizing: border-box; }
.lumen-app button { font-family: inherit; cursor: pointer; }
.lumen-app input,
.lumen-app textarea,
.lumen-app select { font-family: inherit; }

/* ============ painterly background — absolutely positioned inside the
   page, not fixed, so it's contained to this route only. */
.lumen-app .lumen-painterly {
  position: absolute; inset: 0; z-index: 0;
  overflow: hidden;
  background: linear-gradient(160deg, #4a7a5a 0%, #6b9a72 25%, #c4b896 55%, #8a6a4a 80%, #3d2f1f 100%);
  pointer-events: none;
}
.lumen-app .lumen-painterly::before {
  content: ''; position: absolute; inset: -10%;
  background:
    radial-gradient(ellipse 60% 40% at 20% 30%, rgba(120,160,140,0.6), transparent 60%),
    radial-gradient(ellipse 50% 35% at 75% 60%, rgba(180,150,100,0.5), transparent 60%),
    radial-gradient(ellipse 40% 30% at 50% 85%, rgba(60,40,25,0.4), transparent 60%),
    radial-gradient(ellipse 70% 50% at 90% 15%, rgba(90,130,110,0.5), transparent 70%);
  filter: blur(40px);
}
.lumen-app .lumen-painterly::after {
  content: ''; position: absolute; inset: 0;
  background-image:
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.4 0 0 0 0 0.35 0 0 0 0 0.25 0 0 0 0.6 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.35'/></svg>");
  mix-blend-mode: overlay;
  opacity: 0.5;
}

/* ============ app shell ============ */
.lumen-app .app {
  position: relative; z-index: 1;
  height: 100vh;
  padding: 14px;
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 14px;
}

/* ============ sidebar ============ */
.lumen-app .sidebar {
  background: rgba(255,255,255,0.72);
  backdrop-filter: blur(20px) saturate(120%);
  -webkit-backdrop-filter: blur(20px) saturate(120%);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: var(--radius-lg);
  padding: 14px 10px;
  display: flex; flex-direction: column;
  box-shadow: var(--shadow-card);
}
.lumen-app .brand {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px 18px 8px;
}
.lumen-app .brand-mark {
  width: 22px; height: 22px;
  border-radius: 6px;
  background: var(--ink);
  display: grid; place-items: center;
  color: #f4f1ea;
  font-family: 'Instrument Serif', serif;
  font-size: 16px; font-style: italic;
  line-height: 1;
}
.lumen-app .brand-name {
  font-family: 'Instrument Serif', serif;
  font-size: 18px;
  letter-spacing: -0.01em;
}
.lumen-app .brand-sub {
  margin-left: auto;
  font-size: 10px;
  color: var(--ink-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.lumen-app .nav-group { display: flex; flex-direction: column; gap: 1px; }
.lumen-app .nav-label {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-4);
  padding: 14px 10px 6px 10px;
  font-weight: 550;
}
.lumen-app .nav-item {
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
.lumen-app .nav-item:hover { background: rgba(0,0,0,0.04); color: var(--ink); }
.lumen-app .nav-item.active {
  background: rgba(0,0,0,0.06);
  color: var(--ink);
  font-weight: 550;
}
.lumen-app .nav-item .ico { width: 15px; height: 15px; flex: 0 0 15px; opacity: 0.75; }
.lumen-app .nav-item.active .ico { opacity: 1; }
.lumen-app .nav-item .badge {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--ink-3);
  background: rgba(0,0,0,0.05);
  padding: 1px 6px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}
.lumen-app .nav-item .badge.dot {
  width: 6px; height: 6px;
  padding: 0;
  background: var(--accent);
}

.lumen-app .sidebar-foot {
  margin-top: auto;
  padding: 10px 8px 4px 8px;
  border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 9px;
}
.lumen-app .avatar {
  width: 26px; height: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, #c8a878, #6b4a2a);
  color: #fff;
  display: grid; place-items: center;
  font-size: 11px; font-weight: 600;
  flex: 0 0 26px;
}
.lumen-app .sidebar-foot .who { font-size: 12.5px; font-weight: 550; line-height: 1.1; }
.lumen-app .sidebar-foot .plan { font-size: 11px; color: var(--ink-3); line-height: 1.1; }

/* ============ main panel ============ */
.lumen-app .main {
  background: var(--surface);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255,255,255,0.5);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  display: flex; flex-direction: column;
  min-width: 0;
}

.lumen-app .topbar {
  height: 46px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 16px;
  gap: 10px;
  flex: 0 0 46px;
}
.lumen-app .crumbs {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px;
  color: var(--ink-3);
}
.lumen-app .crumbs .sep { color: var(--ink-4); }
.lumen-app .crumbs .here { color: var(--ink); font-weight: 500; }
.lumen-app .top-actions { margin-left: auto; display: flex; align-items: center; gap: 6px; }

.lumen-app .icon-btn {
  width: 28px; height: 28px;
  display: grid; place-items: center;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink-2);
  transition: all 120ms;
}
.lumen-app .icon-btn:hover { background: rgba(0,0,0,0.05); color: var(--ink); }
.lumen-app .icon-btn.outline { border-color: var(--border-strong); }
.lumen-app .icon-btn svg { width: 15px; height: 15px; }

.lumen-app .btn {
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
.lumen-app .btn:hover { background: var(--surface-2); }
.lumen-app .btn.primary {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.lumen-app .btn.primary:hover { background: #000; }
.lumen-app .btn.accent {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.lumen-app .btn.ghost { border-color: transparent; }
.lumen-app .btn.ghost:hover { background: rgba(0,0,0,0.05); }
.lumen-app .btn .ico { width: 13px; height: 13px; }

.lumen-app .scroll {
  flex: 1; min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.lumen-app .scroll::-webkit-scrollbar { width: 10px; }
.lumen-app .scroll::-webkit-scrollbar-thumb { background: var(--ink-5); border-radius: 999px; border: 3px solid var(--surface); background-clip: padding-box; }
.lumen-app .scroll::-webkit-scrollbar-thumb:hover { background: var(--ink-4); border: 3px solid var(--surface); background-clip: padding-box; }

/* ============ typography ============ */
.lumen-app .h-eyebrow {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--ink-3); font-weight: 550;
}
.lumen-app .h-display {
  font-family: 'Instrument Serif', serif;
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1;
}
.lumen-app .num { font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; }
.lumen-app .mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.lumen-app .pos { color: var(--pos); }
.lumen-app .neg { color: var(--neg); }

/* ============ pills / chips ============ */
.lumen-app .pill {
  display: inline-flex; align-items: center; gap: 5px;
  height: 22px; padding: 0 8px;
  border-radius: 999px;
  background: rgba(0,0,0,0.04);
  color: var(--ink-2);
  font-size: 11.5px;
  font-weight: 500;
}
.lumen-app .pill .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.lumen-app .pill.pos { background: var(--accent-soft); color: var(--accent-ink); }
.lumen-app .pill.neg { background: #f5e4e0; color: #7a2f24; }
.lumen-app .pill.warn { background: #f6ecd6; color: #6b4f0f; }
.lumen-app .pill.info { background: #e3ecf5; color: #1f4569; }
.lumen-app .pill.outline { background: transparent; border: 1px solid var(--border-strong); }

/* ============ section title ============ */
.lumen-app .section-head {
  display: flex; align-items: baseline; gap: 12px;
  padding: 6px 0 12px 0;
}
.lumen-app .section-head .title {
  font-size: 13px; font-weight: 600; color: var(--ink);
}
.lumen-app .section-head .sub { font-size: 12.5px; color: var(--ink-3); }
.lumen-app .section-head .actions { margin-left: auto; display: flex; gap: 4px; align-items: center; }

/* ============ card ============ */
.lumen-app .card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.lumen-app .card.tinted { background: var(--surface-2); }
.lumen-app .card-pad { padding: 16px; }
.lumen-app .card-pad-lg { padding: 22px; }

/* ============ table ============ */
.lumen-app .tx-row {
  display: grid;
  grid-template-columns: 18px 1fr 130px 110px 110px 24px;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  cursor: pointer;
  transition: background 80ms;
}
.lumen-app .tx-row:hover { background: var(--surface-2); }
.lumen-app .tx-row.head {
  cursor: default;
  background: var(--surface-2);
  color: var(--ink-3);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 550;
  padding: 8px 16px;
  border-top: 1px solid var(--border);
}
.lumen-app .tx-row.head:hover { background: var(--surface-2); }
.lumen-app .tx-row.selected { background: var(--accent-soft); }
.lumen-app .tx-row.selected:hover { background: #dde8e1; }

.lumen-app .merch {
  width: 26px; height: 26px;
  border-radius: 7px;
  display: grid; place-items: center;
  color: #fff;
  font-size: 11px; font-weight: 600;
  flex: 0 0 26px;
}
.lumen-app .merch-cell { display: flex; align-items: center; gap: 10px; min-width: 0; }
.lumen-app .merch-name { font-weight: 500; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lumen-app .merch-sub { font-size: 11.5px; color: var(--ink-3); }

/* ============ KPI ============ */
.lumen-app .kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.lumen-app .kpi {
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex; flex-direction: column;
  min-height: 108px;
}
.lumen-app .kpi .label {
  font-size: 11.5px; color: var(--ink-3); font-weight: 500;
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 8px;
}
.lumen-app .kpi .label .ico { width: 13px; height: 13px; opacity: 0.7; }
.lumen-app .kpi .value {
  font-family: 'Instrument Serif', serif;
  font-size: 30px; line-height: 1;
  letter-spacing: -0.015em;
  color: var(--ink);
}
.lumen-app .kpi .delta {
  margin-top: auto; padding-top: 10px;
  font-size: 11.5px; color: var(--ink-3);
  display: flex; align-items: center; gap: 4px;
}
.lumen-app .kpi .delta .arrow { font-weight: 600; }

/* ============ progress ============ */
.lumen-app .progress {
  height: 6px; background: rgba(0,0,0,0.06); border-radius: 999px; overflow: hidden;
  position: relative;
}
.lumen-app .progress > .fill { height: 100%; background: var(--ink); border-radius: 999px; }
.lumen-app .progress.thin { height: 4px; }

/* ============ chart helpers ============ */
.lumen-app .chart-wrap { position: relative; }
.lumen-app .chart-wrap svg { display: block; width: 100%; height: 100%; }

/* ============ details panel (right rail) ============ */
.lumen-app .detail-panel {
  width: 360px;
  flex: 0 0 360px;
  border-left: 1px solid var(--border);
  background: var(--surface-2);
  display: flex; flex-direction: column;
  overflow-y: auto;
}
.lumen-app .detail-panel::-webkit-scrollbar { width: 8px; }
.lumen-app .detail-panel::-webkit-scrollbar-thumb { background: var(--ink-5); border-radius: 999px; }

.lumen-app .prop-row {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 12px;
  padding: 7px 16px;
  align-items: center;
  font-size: 12.5px;
}
.lumen-app .prop-row .k { color: var(--ink-3); display: flex; align-items: center; gap: 6px; }
.lumen-app .prop-row .k .ico { width: 13px; height: 13px; opacity: 0.7; }
.lumen-app .prop-row .v { color: var(--ink); font-weight: 450; }
.lumen-app .prop-row .v.editable { padding: 3px 6px; margin: -3px -6px; border-radius: 5px; cursor: pointer; }
.lumen-app .prop-row .v.editable:hover { background: rgba(0,0,0,0.05); }

/* ============ activity ============ */
.lumen-app .activity-item {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 10px;
  padding: 10px 16px;
  position: relative;
}
.lumen-app .activity-item:not(:last-child)::before {
  content: ''; position: absolute;
  left: 27px; top: 28px; bottom: -2px;
  width: 1px; background: var(--border);
}
.lumen-app .activity-item .dot {
  width: 24px; height: 24px;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  display: grid; place-items: center;
  color: var(--ink-3);
  z-index: 1;
}
.lumen-app .activity-item .dot svg { width: 11px; height: 11px; }
.lumen-app .activity-item .body { font-size: 12.5px; }
.lumen-app .activity-item .body .who { font-weight: 550; color: var(--ink); }
.lumen-app .activity-item .body .meta { color: var(--ink-3); margin-left: 6px; font-size: 11.5px; }

/* ============ split layout ============ */
.lumen-app .split {
  display: flex;
  flex: 1;
  min-height: 0;
}
.lumen-app .content-col { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.lumen-app .scroll-pad { padding: 22px 28px 80px 28px; }

/* ============ command palette — fixed because it's a modal overlay ============ */
.lumen-app .cmdk-back {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(20,20,20,0.35);
  backdrop-filter: blur(4px);
  display: grid; place-items: start center;
  padding-top: 14vh;
}
.lumen-app .cmdk {
  width: 580px;
  max-width: 92vw;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  box-shadow: var(--shadow-pop);
  overflow: hidden;
}
.lumen-app .cmdk-input {
  width: 100%; height: 48px; border: none; outline: none;
  padding: 0 18px; font-size: 14px;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--ink);
}
.lumen-app .cmdk-list { max-height: 380px; overflow-y: auto; padding: 6px; }
.lumen-app .cmdk-group { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-4); padding: 10px 12px 4px 12px; font-weight: 550; }
.lumen-app .cmdk-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 7px; font-size: 13px; cursor: pointer; color: var(--ink); }
.lumen-app .cmdk-item:hover, .lumen-app .cmdk-item.active { background: rgba(0,0,0,0.05); }
.lumen-app .cmdk-item .ico { width: 14px; height: 14px; color: var(--ink-3); }
.lumen-app .cmdk-item .kbd { margin-left: auto; font-size: 10.5px; color: var(--ink-4); }

/* ============ kbd ============ */
.lumen-app .kbd {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  padding: 1px 5px;
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  background: var(--surface);
  color: var(--ink-3);
  line-height: 1.4;
}

/* ============ assistant ============ */
.lumen-app .ai-bubble {
  background: linear-gradient(180deg, #fafaf6, #f4f1ea);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  font-size: 13px;
  color: var(--ink);
  line-height: 1.55;
}
.lumen-app .ai-bubble .ai-head {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--ink-3); font-weight: 550;
  margin-bottom: 8px;
}
.lumen-app .ai-bubble .ai-head .pulse {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent); box-shadow: 0 0 0 0 var(--accent);
  animation: lumen-pulse 2s infinite;
}
@keyframes lumen-pulse {
  0% { box-shadow: 0 0 0 0 rgba(10,107,72,0.5); }
  70% { box-shadow: 0 0 0 6px rgba(10,107,72,0); }
  100% { box-shadow: 0 0 0 0 rgba(10,107,72,0); }
}

/* ============ utility ============ */
.lumen-app .row { display: flex; align-items: center; }
.lumen-app .col { display: flex; flex-direction: column; }
.lumen-app .gap-4 { gap: 4px; }
.lumen-app .gap-6 { gap: 6px; }
.lumen-app .gap-8 { gap: 8px; }
.lumen-app .gap-12 { gap: 12px; }
.lumen-app .gap-16 { gap: 16px; }
.lumen-app .gap-20 { gap: 20px; }
.lumen-app .gap-24 { gap: 24px; }
.lumen-app .grow { flex: 1; min-width: 0; }
.lumen-app .right { margin-left: auto; }
.lumen-app .mt-4 { margin-top: 4px; }
.lumen-app .mt-8 { margin-top: 8px; }
.lumen-app .mt-12 { margin-top: 12px; }
.lumen-app .mt-16 { margin-top: 16px; }
.lumen-app .mt-20 { margin-top: 20px; }
.lumen-app .mt-24 { margin-top: 24px; }
.lumen-app .mt-32 { margin-top: 32px; }
.lumen-app .mb-4 { margin-bottom: 4px; }
.lumen-app .mb-8 { margin-bottom: 8px; }
.lumen-app .mb-12 { margin-bottom: 12px; }
.lumen-app .mb-16 { margin-bottom: 16px; }
.lumen-app .mb-20 { margin-bottom: 20px; }
.lumen-app .mb-24 { margin-bottom: 24px; }
.lumen-app .text-3 { color: var(--ink-3); }
.lumen-app .text-2 { color: var(--ink-2); }
.lumen-app .fz-11 { font-size: 11px; }
.lumen-app .fz-12 { font-size: 12px; }
.lumen-app .fz-13 { font-size: 13px; }
.lumen-app .fz-14 { font-size: 14px; }
.lumen-app .fw-5 { font-weight: 500; }
.lumen-app .fw-6 { font-weight: 600; }

/* ============ donut legend ============ */
.lumen-app .legend-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0;
  font-size: 12.5px;
  border-bottom: 1px dashed var(--border);
}
.lumen-app .legend-row:last-child { border-bottom: none; }
.lumen-app .legend-row .sw { width: 8px; height: 8px; border-radius: 2px; flex: 0 0 8px; }
.lumen-app .legend-row .lab { color: var(--ink-2); }
.lumen-app .legend-row .pct { margin-left: auto; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.lumen-app .legend-row .amt { width: 80px; text-align: right; color: var(--ink); font-weight: 500; font-variant-numeric: tabular-nums; }

/* ============ accounts cards ============ */
.lumen-app .acct-card {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  display: flex; align-items: center; gap: 14px;
  cursor: pointer;
  transition: all 120ms;
}
.lumen-app .acct-card:hover { border-color: var(--border-strong); transform: translateY(-1px); box-shadow: var(--shadow-card); }
.lumen-app .acct-logo {
  width: 36px; height: 36px;
  border-radius: 8px;
  display: grid; place-items: center;
  color: #fff;
  font-size: 13px; font-weight: 600;
  flex: 0 0 36px;
}

/* ============ goal ring ============ */
.lumen-app .ring-wrap { position: relative; width: 84px; height: 84px; }
.lumen-app .ring-wrap .ring-text {
  position: absolute; inset: 0; display: grid; place-items: center;
  font-family: 'Instrument Serif', serif;
  font-size: 22px; line-height: 1;
}

/* ============ subscription row ============ */
.lumen-app .sub-row {
  display: grid;
  grid-template-columns: 32px 1fr 100px 100px;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.lumen-app .sub-row:last-child { border-bottom: none; }

/* ============ filter bar ============ */
.lumen-app .filter-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.lumen-app .chip {
  display: inline-flex; align-items: center; gap: 5px;
  height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px dashed var(--border-strong);
  color: var(--ink-3);
  font-size: 12px;
  background: transparent;
}
.lumen-app .chip.active {
  border-style: solid;
  background: var(--surface-2);
  color: var(--ink);
}
.lumen-app .chip .x { color: var(--ink-4); }
.lumen-app .chip:hover { color: var(--ink); border-color: var(--ink-3); }

/* ============ search input ============ */
.lumen-app .search-input {
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
.lumen-app .search-input:focus { border-color: var(--ink-3); }
.lumen-app .search-wrap { position: relative; }
.lumen-app .search-wrap svg { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); width: 13px; height: 13px; color: var(--ink-4); }

/* ============ donut ============ */
.lumen-app .donut-c { width: 200px; height: 200px; position: relative; }
.lumen-app .donut-c .center {
  position: absolute; inset: 0; display: grid; place-items: center; text-align: center;
}

/* ============ flow chart bars ============ */
.lumen-app .flow-bars { display: flex; align-items: end; gap: 6px; height: 180px; }
.lumen-app .flow-col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; }
.lumen-app .flow-col .stack { display: flex; flex-direction: column-reverse; width: 100%; gap: 2px; height: 156px; align-items: stretch; justify-content: end; }
.lumen-app .flow-col .b-in { background: var(--accent); border-radius: 3px 3px 0 0; }
.lumen-app .flow-col .b-out { background: var(--ink); border-radius: 0 0 3px 3px; opacity: 0.85; }
.lumen-app .flow-col .lab { font-size: 10.5px; color: var(--ink-3); }

/* ============ investments ============ */
.lumen-app .holding-row {
  display: grid;
  grid-template-columns: 32px 1fr 90px 90px 100px 90px;
  gap: 12px;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.lumen-app .holding-row.head {
  background: var(--surface-2);
  color: var(--ink-3);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 550;
  padding: 8px 16px;
}
.lumen-app .ticker {
  width: 32px; height: 32px;
  border-radius: 7px;
  color: #fff;
  display: grid; place-items: center;
  font-size: 11px; font-weight: 700;
  letter-spacing: -0.02em;
}

/* ============ tweaks panel custom ============ */
.lumen-app .tweak-swatch-row { display: flex; gap: 6px; flex-wrap: wrap; }
.lumen-app .tweak-swatch {
  width: 26px; height: 26px;
  border-radius: 6px;
  border: 2px solid transparent;
  cursor: pointer;
  position: relative;
}
.lumen-app .tweak-swatch.active {
  border-color: var(--ink);
  box-shadow: 0 0 0 2px var(--surface) inset;
}

/* mini segmented */
.lumen-app .seg {
  display: inline-flex;
  background: rgba(0,0,0,0.05);
  border-radius: 7px;
  padding: 2px;
}
.lumen-app .seg button {
  border: none; background: transparent;
  padding: 4px 10px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--ink-3);
  font-weight: 500;
}
.lumen-app .seg button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}

/* ============ popover ============ */
.lumen-app .popover {
  position: absolute;
  z-index: 50;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: 10px;
  box-shadow: var(--shadow-pop);
  padding: 6px;
  min-width: 220px;
}
.lumen-app .popover .pop-head {
  padding: 6px 8px;
  font-size: 11px;
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 550;
}
.lumen-app .popover .pop-item {
  display: flex; align-items: center; gap: 9px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.lumen-app .popover .pop-item:hover { background: rgba(0,0,0,0.05); }
.lumen-app .popover .pop-item .ico { width: 14px; height: 14px; color: var(--ink-3); }

/* sparkline color helpers */
.lumen-app .spark-pos path.line { stroke: var(--pos); }
.lumen-app .spark-pos path.fill { fill: var(--pos); fill-opacity: 0.10; }
.lumen-app .spark-neg path.line { stroke: var(--neg); }
.lumen-app .spark-neg path.fill { fill: var(--neg); fill-opacity: 0.10; }

/* fade-in for screens */
.lumen-app .screen-fade {
  animation: lumen-fadeIn 220ms ease-out;
}
@keyframes lumen-fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
}

/* checkbox */
.lumen-app .ck {
  width: 14px; height: 14px;
  border: 1px solid var(--border-strong);
  border-radius: 3px;
  display: inline-grid; place-items: center;
  background: var(--surface);
  flex: 0 0 14px;
}
.lumen-app .ck.on {
  background: var(--ink);
  border-color: var(--ink);
  color: #fff;
}
.lumen-app .ck svg { width: 10px; height: 10px; display: none; }
.lumen-app .ck.on svg { display: block; }

/* selection */
.lumen-app ::selection { background: var(--accent-soft); color: var(--accent-ink); }

/* ============ dark mode (toggled via .dark on .lumen-app root) ============ */
.lumen-app.dark {
  --bg: #0e0f0d;
  --surface: #18191a;
  --surface-2: #1f2122;
  --surface-3: #25272a;
  --border: #2a2c2e;
  --border-strong: #3a3d40;
  --ink: #ececea;
  --ink-2: #c4c5c2;
  --ink-3: #8a8c89;
  --ink-4: #5a5d5b;
  --ink-5: #3a3d3a;
  --accent-soft: #163a2a;
  --accent-ink: #c8e2d4;
}
.lumen-app.dark .lumen-painterly {
  background: linear-gradient(160deg, #1a3528 0%, #2a4534 25%, #4a3a2a 55%, #2a1f15 80%, #0a0a08 100%);
}
.lumen-app.dark .sidebar {
  background: rgba(24,25,26,0.7);
  border-color: rgba(255,255,255,0.06);
}
.lumen-app.dark .ai-bubble {
  background: linear-gradient(180deg, #1f2122, #18191a);
}

/* ============ tweaks panel (collapsed tab + expanded panel) ============
   These are page-scoped so they can't leak. The expanded panel is fixed
   to the bottom-right corner with a glass backdrop matching the design. */
.lumen-app .lumen-tweaks-tab {
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
.lumen-app .lumen-tweaks-panel {
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
.lumen-app.dark .lumen-tweaks-panel { background: rgba(24,25,26,0.82); color: var(--ink); }
.lumen-app.dark .lumen-tweaks-tab { background: rgba(24,25,26,0.78); color: var(--ink); border-color: rgba(255,255,255,0.08); }
.lumen-app .lumen-tweaks-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 8px 10px 14px;
}
.lumen-app .lumen-tweaks-head b { font-size: 12px; font-weight: 600; }
.lumen-app .lumen-tweaks-x {
  width: 22px; height: 22px;
  border: 0; background: transparent;
  border-radius: 6px;
  font-size: 16px; line-height: 1;
  color: rgba(41,38,27,0.55);
  cursor: pointer;
}
.lumen-app .lumen-tweaks-x:hover { background: rgba(0,0,0,0.06); color: #29261b; }
.lumen-app .lumen-tweaks-body { padding: 2px 14px 14px; display: flex; flex-direction: column; gap: 10px; }
.lumen-app .lumen-tweaks-sect {
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.06em; text-transform: uppercase;
  color: rgba(41,38,27,0.45);
  padding: 6px 0 0;
}
.lumen-app.dark .lumen-tweaks-sect { color: var(--ink-3); }
.lumen-app .lumen-tweaks-radio {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px;
  background: rgba(0,0,0,0.06);
  border-radius: 8px;
  padding: 2px;
}
.lumen-app .lumen-tweaks-radio button {
  border: 0; background: transparent;
  border-radius: 6px;
  padding: 5px 6px;
  font-size: 11px; font-weight: 500;
  color: inherit;
  cursor: pointer;
}
.lumen-app .lumen-tweaks-radio button.active {
  background: rgba(255,255,255,0.9);
  box-shadow: 0 1px 2px rgba(0,0,0,0.12);
}
.lumen-app.dark .lumen-tweaks-radio button.active { background: rgba(255,255,255,0.12); }
.lumen-app .lumen-tweaks-toggle-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 2px 0;
}
.lumen-app .lumen-tweaks-toggle {
  position: relative; width: 32px; height: 18px;
  border: 0; border-radius: 999px;
  background: rgba(0,0,0,0.15);
  transition: background 0.15s;
  cursor: pointer; padding: 0;
}
.lumen-app .lumen-tweaks-toggle[data-on="1"] { background: var(--accent); }
.lumen-app .lumen-tweaks-toggle i {
  position: absolute; top: 2px; left: 2px;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0,0,0,0.25);
  transition: transform 0.15s;
}
.lumen-app .lumen-tweaks-toggle[data-on="1"] i { transform: translateX(14px); }
`;
