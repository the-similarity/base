/**
 * Lumen scoped stylesheet for /workstation/lumen.
 *
 * Bug context (fixed in this revision):
 *   The previous revision still used generic class names like `.app`,
 *   `.main`, `.pill`, `.brand`, `.cmdk`, `.kbd`, `.num`, `.mono`,
 *   `.label`, `.right`, `.chip` — all of which COLLIDE with global rules
 *   defined in `app/globals.css`. Even with the `.lumen-app` prefix on
 *   selectors, the global rules still applied for properties NOT
 *   explicitly overridden by the Lumen rules. The killer example was
 *   `.app { display: grid; grid-template-rows: 44px 1fr 26px; ...}` in
 *   globals.css combining with `.lumen-app .app { grid-template-columns:
 *   220px 1fr; ... }` here. Result: a 3-row × 2-col grid where the
 *   sidebar+main got squeezed into the 44px first row, leaving the main
 *   panel visually empty.
 *
 * The bulletproof fix: rename every Lumen-owned class to a `lumen-`
 * prefixed name. No prefix collision with anything else in the app, no
 * specificity gymnastics. Selectors here all read `.lumen-app
 * .lumen-foo`. The JSX tree was updated in lockstep — every
 * `className=` under this route now uses `lumen-foo` instead of `foo`.
 *
 * IMPORTANT: NEVER add un-prefixed selectors to this file. Anything
 * without the `.lumen-app` ancestor would leak into the rest of the app,
 * and any class without a `lumen-` prefix can collide with `globals.css`.
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

/* ============ app shell — renamed from .app to avoid colliding with
   the global .app rule in globals.css that sets a 3-row grid template. */
.lumen-app .lumen-shell {
  position: relative; z-index: 1;
  height: 100vh;
  padding: 14px;
  display: grid;
  grid-template-columns: 220px 1fr;
  grid-template-rows: 1fr;
  gap: 14px;
}

/* ============ sidebar ============ */
.lumen-app .lumen-sidebar {
  background: rgba(255,255,255,0.72);
  backdrop-filter: blur(20px) saturate(120%);
  -webkit-backdrop-filter: blur(20px) saturate(120%);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: var(--radius-lg);
  padding: 14px 10px;
  display: flex; flex-direction: column;
  box-shadow: var(--shadow-card);
}
.lumen-app .lumen-brand {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px 18px 8px;
}
.lumen-app .lumen-brand-mark {
  width: 22px; height: 22px;
  display: grid; place-items: center;
  color: var(--ink);
  line-height: 1;
}
.lumen-app .lumen-brand-mark svg { display: block; }
.lumen-app .lumen-brand-name {
  font-family: 'Instrument Serif', serif;
  font-size: 18px;
  letter-spacing: -0.01em;
}
.lumen-app .lumen-brand-name em {
  font-style: italic;
}
.lumen-app .lumen-brand-sub {
  margin-left: auto;
  font-size: 10px;
  color: var(--ink-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.lumen-app .lumen-nav-group { display: flex; flex-direction: column; gap: 1px; }
.lumen-app .lumen-nav-label {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-4);
  padding: 14px 10px 6px 10px;
  font-weight: 550;
}
.lumen-app .lumen-nav-item {
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
.lumen-app .lumen-nav-item:hover { background: rgba(0,0,0,0.04); color: var(--ink); }
.lumen-app .lumen-nav-item.is-active {
  background: rgba(0,0,0,0.06);
  color: var(--ink);
  font-weight: 550;
}
.lumen-app .lumen-nav-item .lumen-ico { width: 15px; height: 15px; flex: 0 0 15px; opacity: 0.75; }
.lumen-app .lumen-nav-item.is-active .lumen-ico { opacity: 1; }
.lumen-app .lumen-nav-item .lumen-badge {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--ink-3);
  background: rgba(0,0,0,0.05);
  padding: 1px 6px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}

.lumen-app .lumen-sidebar-foot {
  margin-top: auto;
  padding: 10px 8px 4px 8px;
  border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 9px;
}
.lumen-app .lumen-sidebar-foot .lumen-who { font-size: 12px; font-weight: 500; line-height: 1.2; color: var(--ink-2); }
.lumen-app .lumen-sidebar-foot .lumen-plan { font-size: 11px; color: var(--ink-3); line-height: 1.2; }

/* ============ main panel — renamed from .main to avoid collision with
   the global .main rule in globals.css. */
.lumen-app .lumen-main {
  background: var(--surface);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255,255,255,0.5);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  display: flex; flex-direction: column;
  min-width: 0;
}

.lumen-app .lumen-topbar {
  height: 46px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 16px;
  gap: 10px;
  flex: 0 0 46px;
}
.lumen-app .lumen-crumbs {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px;
  color: var(--ink-3);
}
.lumen-app .lumen-crumbs .lumen-sep { color: var(--ink-4); }
.lumen-app .lumen-crumbs .lumen-here { color: var(--ink); font-weight: 500; }
.lumen-app .lumen-top-actions { margin-left: auto; display: flex; align-items: center; gap: 6px; }

.lumen-app .lumen-icon-btn {
  width: 28px; height: 28px;
  display: grid; place-items: center;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink-2);
  transition: all 120ms;
}
.lumen-app .lumen-icon-btn:hover { background: rgba(0,0,0,0.05); color: var(--ink); }
.lumen-app .lumen-icon-btn.outline { border-color: var(--border-strong); }
.lumen-app .lumen-icon-btn svg { width: 15px; height: 15px; }

.lumen-app .lumen-btn {
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
  text-decoration: none;
}
.lumen-app .lumen-btn:hover { background: var(--surface-2); }
.lumen-app .lumen-btn.is-primary {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.lumen-app .lumen-btn.is-primary:hover { background: #000; }
.lumen-app .lumen-btn.is-accent {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.lumen-app .lumen-btn.is-ghost { border-color: transparent; }
.lumen-app .lumen-btn.is-ghost:hover { background: rgba(0,0,0,0.05); }
.lumen-app .lumen-btn .lumen-ico { width: 13px; height: 13px; }

.lumen-app .lumen-scroll {
  flex: 1; min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.lumen-app .lumen-scroll::-webkit-scrollbar { width: 10px; }
.lumen-app .lumen-scroll::-webkit-scrollbar-thumb { background: var(--ink-5); border-radius: 999px; border: 3px solid var(--surface); background-clip: padding-box; }
.lumen-app .lumen-scroll::-webkit-scrollbar-thumb:hover { background: var(--ink-4); border: 3px solid var(--surface); background-clip: padding-box; }

/* ============ typography ============ */
.lumen-app .lumen-eyebrow {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--ink-3); font-weight: 550;
}
.lumen-app .lumen-display {
  font-family: 'Instrument Serif', serif;
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1;
}
.lumen-app .lumen-num { font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; }
.lumen-app .lumen-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-feature-settings: 'tnum'; }
.lumen-app .lumen-pos { color: var(--pos); }
.lumen-app .lumen-neg { color: var(--neg); }

/* ============ pills ============ */
.lumen-app .lumen-pill {
  display: inline-flex; align-items: center; gap: 5px;
  height: 22px; padding: 0 8px;
  border-radius: 999px;
  background: rgba(0,0,0,0.04);
  color: var(--ink-2);
  font-size: 11.5px;
  font-weight: 500;
}
.lumen-app .lumen-pill .lumen-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.lumen-app .lumen-pill.is-pos { background: var(--accent-soft); color: var(--accent-ink); }
.lumen-app .lumen-pill.is-neg { background: #f5e4e0; color: #7a2f24; }
.lumen-app .lumen-pill.is-warn { background: #f6ecd6; color: #6b4f0f; }
.lumen-app .lumen-pill.is-info { background: #e3ecf5; color: #1f4569; }
.lumen-app .lumen-pill.is-outline { background: transparent; border: 1px solid var(--border-strong); }

/* ============ section title ============ */
.lumen-app .lumen-section-head {
  display: flex; align-items: baseline; gap: 12px;
  padding: 6px 0 12px 0;
}
.lumen-app .lumen-section-head .lumen-title {
  font-size: 13px; font-weight: 600; color: var(--ink);
}
.lumen-app .lumen-section-head .lumen-sub { font-size: 12.5px; color: var(--ink-3); }
.lumen-app .lumen-section-head .lumen-actions { margin-left: auto; display: flex; gap: 4px; align-items: center; }

/* ============ card ============ */
.lumen-app .lumen-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.lumen-app .lumen-card.is-tinted { background: var(--surface-2); }
.lumen-app .lumen-card-pad { padding: 16px; }
.lumen-app .lumen-card-pad-lg { padding: 22px; }

/* ============ table rows ============ */
.lumen-app .lumen-tx-row {
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
.lumen-app .lumen-tx-row:hover { background: var(--surface-2); }
.lumen-app .lumen-tx-row.is-head {
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
.lumen-app .lumen-tx-row.is-head:hover { background: var(--surface-2); }
.lumen-app .lumen-tx-row.is-selected { background: var(--accent-soft); }
.lumen-app .lumen-tx-row.is-selected:hover { background: #dde8e1; }

/* ============ KPI ============ */
.lumen-app .lumen-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.lumen-app .lumen-kpi {
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex; flex-direction: column;
  min-height: 108px;
}
.lumen-app .lumen-kpi .lumen-label {
  font-size: 11.5px; color: var(--ink-3); font-weight: 500;
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 8px;
  font-family: inherit;
  letter-spacing: 0;
  text-transform: none;
}
.lumen-app .lumen-kpi .lumen-label .lumen-ico { width: 13px; height: 13px; opacity: 0.7; }
.lumen-app .lumen-kpi .lumen-value {
  font-family: 'Instrument Serif', serif;
  font-size: 30px; line-height: 1;
  letter-spacing: -0.015em;
  color: var(--ink);
}
.lumen-app .lumen-kpi .lumen-delta {
  margin-top: auto; padding-top: 10px;
  font-size: 11.5px; color: var(--ink-3);
  display: flex; align-items: center; gap: 4px;
}
.lumen-app .lumen-kpi .lumen-delta .lumen-arrow { font-weight: 600; }

/* ============ chart wrap ============ */
.lumen-app .lumen-chart-wrap { position: relative; }
.lumen-app .lumen-chart-wrap svg { display: block; width: 100%; height: 100%; }

/* ============ split layout ============ */
.lumen-app .lumen-split {
  display: flex;
  flex: 1;
  min-height: 0;
}
.lumen-app .lumen-content-col { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.lumen-app .lumen-scroll-pad { padding: 22px 28px 80px 28px; }

/* ============ command palette ============ */
.lumen-app .lumen-cmdk-back {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(20,20,20,0.35);
  backdrop-filter: blur(4px);
  display: grid; place-items: start center;
  padding-top: 14vh;
}
.lumen-app .lumen-cmdk {
  width: 580px;
  max-width: 92vw;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  box-shadow: var(--shadow-pop);
  overflow: hidden;
}
.lumen-app .lumen-cmdk-input {
  width: 100%; height: 48px; border: none; outline: none;
  padding: 0 18px; font-size: 14px;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--ink);
}
.lumen-app .lumen-cmdk-list { max-height: 380px; overflow-y: auto; padding: 6px; }
.lumen-app .lumen-cmdk-group { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-4); padding: 10px 12px 4px 12px; font-weight: 550; }
.lumen-app .lumen-cmdk-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 7px; font-size: 13px; cursor: pointer; color: var(--ink); }
.lumen-app .lumen-cmdk-item:hover, .lumen-app .lumen-cmdk-item.is-active { background: rgba(0,0,0,0.05); }
.lumen-app .lumen-cmdk-item .lumen-ico { width: 14px; height: 14px; color: var(--ink-3); }
.lumen-app .lumen-cmdk-item .lumen-kbd { margin-left: auto; }

/* ============ kbd ============ */
.lumen-app .lumen-kbd {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  padding: 1px 5px;
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  background: var(--surface);
  color: var(--ink-3);
  line-height: 1.4;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
}

/* ============ AI insight bubble ============ */
.lumen-app .lumen-ai-bubble {
  background: linear-gradient(180deg, #fafaf6, #f4f1ea);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  font-size: 13px;
  color: var(--ink);
  line-height: 1.55;
}
.lumen-app .lumen-ai-bubble .lumen-ai-head {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--ink-3); font-weight: 550;
  margin-bottom: 8px;
  font-family: inherit;
}
.lumen-app .lumen-ai-bubble .lumen-ai-head .lumen-pulse {
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
.lumen-app .lumen-row { display: flex; align-items: center; }
.lumen-app .lumen-col { display: flex; flex-direction: column; }
.lumen-app .lumen-gap-4 { gap: 4px; }
.lumen-app .lumen-gap-6 { gap: 6px; }
.lumen-app .lumen-gap-8 { gap: 8px; }
.lumen-app .lumen-gap-12 { gap: 12px; }
.lumen-app .lumen-gap-16 { gap: 16px; }
.lumen-app .lumen-gap-20 { gap: 20px; }
.lumen-app .lumen-gap-24 { gap: 24px; }
.lumen-app .lumen-grow { flex: 1; min-width: 0; }
.lumen-app .lumen-right { margin-left: auto; }
.lumen-app .lumen-mt-4 { margin-top: 4px; }
.lumen-app .lumen-mt-8 { margin-top: 8px; }
.lumen-app .lumen-mt-12 { margin-top: 12px; }
.lumen-app .lumen-mt-16 { margin-top: 16px; }
.lumen-app .lumen-mt-20 { margin-top: 20px; }
.lumen-app .lumen-mt-24 { margin-top: 24px; }
.lumen-app .lumen-mt-32 { margin-top: 32px; }
.lumen-app .lumen-mb-4 { margin-bottom: 4px; }
.lumen-app .lumen-mb-8 { margin-bottom: 8px; }
.lumen-app .lumen-mb-12 { margin-bottom: 12px; }
.lumen-app .lumen-mb-16 { margin-bottom: 16px; }
.lumen-app .lumen-mb-20 { margin-bottom: 20px; }
.lumen-app .lumen-mb-24 { margin-bottom: 24px; }
.lumen-app .lumen-text-3 { color: var(--ink-3); }
.lumen-app .lumen-text-2 { color: var(--ink-2); }
.lumen-app .lumen-fz-11 { font-size: 11px; }
.lumen-app .lumen-fz-12 { font-size: 12px; }
.lumen-app .lumen-fz-13 { font-size: 13px; }
.lumen-app .lumen-fz-14 { font-size: 14px; }
.lumen-app .lumen-fw-5 { font-weight: 500; }
.lumen-app .lumen-fw-6 { font-weight: 600; }

/* sparkline color helpers */
.lumen-app .lumen-spark-pos path.line { stroke: var(--pos); }
.lumen-app .lumen-spark-pos path.fill { fill: var(--pos); fill-opacity: 0.10; }
.lumen-app .lumen-spark-neg path.line { stroke: var(--neg); }
.lumen-app .lumen-spark-neg path.fill { fill: var(--neg); fill-opacity: 0.10; }

/* fade-in for screens */
.lumen-app .lumen-screen-fade {
  animation: lumen-fadeIn 220ms ease-out;
}
@keyframes lumen-fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
}

/* checkbox */
.lumen-app .lumen-ck {
  width: 14px; height: 14px;
  border: 1px solid var(--border-strong);
  border-radius: 3px;
  display: inline-grid; place-items: center;
  background: var(--surface);
  flex: 0 0 14px;
}
.lumen-app .lumen-ck.is-on {
  background: var(--ink);
  border-color: var(--ink);
  color: #fff;
}
.lumen-app .lumen-ck svg { width: 10px; height: 10px; display: none; }
.lumen-app .lumen-ck.is-on svg { display: block; }

/* selection */
.lumen-app ::selection { background: var(--accent-soft); color: var(--accent-ink); }

/* mini segmented control */
.lumen-app .lumen-seg {
  display: inline-flex;
  background: rgba(0,0,0,0.05);
  border-radius: 7px;
  padding: 2px;
}
.lumen-app .lumen-seg button {
  border: none; background: transparent;
  padding: 4px 10px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--ink-3);
  font-weight: 500;
}
.lumen-app .lumen-seg button.is-active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}

/* status pill (run lifecycle) */
.lumen-app .lumen-status {
  display: inline-flex; align-items: center; gap: 5px;
  height: 20px; padding: 0 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border: 1px solid currentColor;
}
.lumen-app .lumen-status.is-complete { color: var(--pos); }
.lumen-app .lumen-status.is-running { color: var(--info); }
.lumen-app .lumen-status.is-failed { color: var(--neg); }
.lumen-app .lumen-status.is-pending { color: var(--ink-3); }

/* search input (topbar search button) — kept thin */
.lumen-app .lumen-search-wrap { position: relative; display: inline-flex; }
.lumen-app .lumen-search-wrap svg { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); width: 13px; height: 13px; color: var(--ink-4); }

/* ============ runs table — generic table layout used by Runs screen ============ */
.lumen-app .lumen-table {
  width: 100%;
  border-collapse: collapse;
}
.lumen-app .lumen-table th {
  text-align: left;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 550;
  color: var(--ink-3);
  background: var(--surface-2);
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
.lumen-app .lumen-table th.is-right { text-align: right; }
.lumen-app .lumen-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--ink);
}
.lumen-app .lumen-table td.is-right { text-align: right; }
.lumen-app .lumen-table td.is-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; font-feature-settings: 'tnum'; }
.lumen-app .lumen-table tr.is-link { cursor: pointer; transition: background 80ms; }
.lumen-app .lumen-table tr.is-link:hover { background: var(--surface-2); }

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
.lumen-app.dark .lumen-sidebar {
  background: rgba(24,25,26,0.7);
  border-color: rgba(255,255,255,0.06);
}
.lumen-app.dark .lumen-ai-bubble {
  background: linear-gradient(180deg, #1f2122, #18191a);
}

/* ============ tweaks panel ============ */
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
.lumen-app .lumen-tweaks-radio button.is-active {
  background: rgba(255,255,255,0.9);
  box-shadow: 0 1px 2px rgba(0,0,0,0.12);
}
.lumen-app.dark .lumen-tweaks-radio button.is-active { background: rgba(255,255,255,0.12); }
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

.lumen-app .lumen-tweak-swatch-row { display: flex; gap: 6px; flex-wrap: wrap; }
.lumen-app .lumen-tweak-swatch {
  width: 26px; height: 26px;
  border-radius: 6px;
  border: 2px solid transparent;
  cursor: pointer;
  position: relative;
}
.lumen-app .lumen-tweak-swatch.is-active {
  border-color: var(--ink);
  box-shadow: 0 0 0 2px var(--surface) inset;
}
`;
