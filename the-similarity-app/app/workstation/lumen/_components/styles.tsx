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

/* ====================================================================
 * Lumen palette overrides for the embedded <Workstation> component.
 *
 * These shadow the same custom properties defined on :root by
 * app/globals.css. Because they live deeper in the cascade (under
 * .lumen-app), every descendant of the Lumen route picks the Lumen
 * palette instead of the app's default Newsreader-on-burgundy theme.
 *
 * That is the load-bearing trick that lets us re-skin the entire
 * 3000-line Workstation component without touching a single line in
 * components/workstation/*. Anything that uses var(--bg), var(--ink),
 * var(--accent), etc. inside the Workstation tree resolves against
 * THESE values, not :root's.
 *
 * Token mapping reference (apps/globals.css → Lumen):
 *   --bg            → paper beige                #f4f1ea
 *   --bg-card       → white surface              #ffffff
 *   --ink           → near-black ink             #161614
 *   --rule          → soft beige rule            #ececea
 *   --positive      → forest green (Lumen accent) #0a6b48
 *   --negative      → muted brick                 #b14a3a
 *   --accent        → forest green                #0a6b48
 *   --serif         → Instrument Serif (display)
 *   --sans          → Inter
 *   --mono          → JetBrains Mono
 *
 * Analog/cone color tokens are also overridden so the chart's analog
 * lines + forecast cone use Lumen-friendly hues instead of the
 * burgundy/oxblood roster from the standalone route.
 * ==================================================================== */
.lumen-app {
  --bg: #f4f1ea;
  --bg-elevated: #ffffff;
  --bg-card: #ffffff;
  --bg-inset: #faf9f6;
  --bg-hover: #f4f3ef;

  --ink: #161614;
  --ink-2: #3d3d3a;
  --ink-3: #7a7a75;
  --ink-4: #a8a8a3;

  --rule: #ececea;
  --rule-strong: #dcdbd7;
  --rule-focus: #161614;

  --positive: #0a6b48;
  --positive-soft: rgba(10,107,72,0.08);
  --negative: #b14a3a;
  --negative-soft: rgba(177,74,58,0.08);
  --warn: #b07c1d;

  /* Default accent — overwritten by the tweaks panel via a per-element
     style.setProperty() call on the .lumen-app root, but the Lumen
     palette uses forest green out of the gate. */
  --accent: #0a6b48;
  --accent-soft: rgba(10,107,72,0.08);

  /* Chart palette — query line, analog band, forecast cone, grid. */
  --c-query: #161614;
  --c-analog: #a8a8a3;
  --c-analog-strong: #7a7a75;
  --c-cone-fill: rgba(10,107,72,0.10);
  --c-cone-line: #0a6b48;
  --c-grid: #ececea;

  /* Top-K analog ranks 1–6 — earthy palette that pairs with painterly bg. */
  --c-analog-1: #0a6b48;
  --c-analog-2: #b07c1d;
  --c-analog-3: #2e5d8c;
  --c-analog-4: #7d3aa9;
  --c-analog-5: #b14a3a;
  --c-analog-6: #3d3d3a;

  --serif: 'Instrument Serif', Georgia, "Times New Roman", serif;
  --sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --mono: 'JetBrains Mono', "SF Mono", Consolas, monospace;
}

/* Dark-mode overrides — keyed off the .dark class the tweaks panel
   toggles. Mirrors app/globals.css [data-theme="dark"] so the
   embedded Workstation flips into a Lumen-palette dark mode. */
.lumen-app.dark {
  --bg: #0e0f0d;
  --bg-elevated: #18191a;
  --bg-card: #18191a;
  --bg-inset: #1f2122;
  --bg-hover: #25272a;

  --ink: #ececea;
  --ink-2: #c4c5c2;
  --ink-3: #8a8c89;
  --ink-4: #5a5d5b;

  --rule: #2a2c2e;
  --rule-strong: #3a3d40;
  --rule-focus: #ececea;

  --positive: #6fb88e;
  --positive-soft: rgba(111,184,142,0.10);
  --negative: #c77272;
  --negative-soft: rgba(199,114,114,0.10);
  --warn: #c9a14f;

  --accent: #2c8862;
  --accent-soft: rgba(44,136,98,0.10);

  --c-query: #ececea;
  --c-analog: #5a5d5b;
  --c-analog-strong: #8a8c89;
  --c-cone-fill: rgba(111,184,142,0.10);
  --c-cone-line: #6fb88e;
  --c-grid: #22241f;
}

/* The embedded Workstation reads var(--bg) for its outer background.
   The Lumen card already provides a white surface, so we tell the
   Workstation root to be transparent — letting the Lumen card's own
   background show through and avoiding a doubled paint. */
.lumen-app .workstation {
  background: transparent;
  font-family: var(--sans);
}

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

/* ====================================================================
 * Lumen overrides for the embedded <Workstation> component.
 * --------------------------------------------------------------------
 * Goal: 100% Lumen design language inside the workstation tree. The
 * underlying component (components/workstation/*) was authored in a
 * "research terminal" idiom — mono uppercase labels, sharp 1px rules,
 * boxy chips, burgundy-tinted analog cards, hard contrast. None of
 * that fits Lumen's editorial finance look (Instrument Serif numerals,
 * paper-on-card surfaces, hairline borders, accent-soft tints).
 *
 * Strategy: every workstation class that has a global rule in
 * app/globals.css gets a paired override at .lumen-app .X specificity
 * here. Two ancestors (.lumen-app + .X) beat the global single-class
 * selector without using !important. The token cascade above already
 * paints the correct colors; these rules also tackle layout, geometry,
 * typography, and spacing.
 *
 * Coverage map (every class below has an override in this section):
 *   layout          .workstation, .side, .main, .right, .chart-stack
 *   side panel      .side__section, .side__header, .side__row, .label,
 *                   .saved-list, .saved, .saved__date, .saved__name,
 *                   .saved__score, .chip, .chip-row
 *   topbar/search   .ws-search-row, .ws-search-row__group, .ws-search-row__label,
 *                   .ws-search-row__lastrun, .ws-search-row__fewer-matches,
 *                   .ws-topk, .ws-horizon, .ws-search-btn, .ws-share-btn
 *   chart           .chart-card, .chart-card__head, .chart-card__title,
 *                   .chart-card__body, .chart-card__legend, .legend-dot,
 *                   .ws-chartmode-row, .ws-chartmode, .ws-chart-settings,
 *                   .lw-chart, .svg-chart
 *   analog strip    .strip, .analog-card, .analog-card__head,
 *                   .analog-card__date, .analog-card__title,
 *                   .analog-card__score, .analog-card__note,
 *                   .analog-card__spark, .analog-card__after,
 *                   .analog-card__pin-btn
 *   right rail      .right__section, .lens-head, .lens-bars,
 *                   .lens-bar, .lens-radar, .score, .d
 *   trust           .trust, .trust__item, .trust__expand, .trust__info,
 *                   .trust-panel, .trust-panel--empty,
 *                   .trust-panel__empty-card, .trust-panel__cta,
 *                   .trust-panel__narrative, .trust-panel__grade-*
 *   detail drawer   .adrawer, .adrawer__head, .adrawer__rank-badge,
 *                   .adrawer__date-range, .adrawer__label,
 *                   .adrawer__composite-*, .adrawer__pin-toggle,
 *                   .adrawer__close, .adrawer__context*,
 *                   .adrawer__section, .adrawer__h, .adrawer__h-sub,
 *                   .adrawer__lens-*, .adrawer__spark-*,
 *                   .adrawer__actions, .adrawer__action*
 *   banners/toasts  .ws-banner*, .ws-pin-banner*,
 *                   .ws-share-toast*, .ws-use-as-query-banner*
 *   empty states    .ws-empty-state*, .ws-micro-empty*, .ws-mobile-notice
 *   drawer chrome   .ws-drawer-toggle, .ws-drawer-toggles,
 *                   .ws-drawer-close, .ws-drawer-backdrop
 *   dataset picker  .dataset-trigger*, .dataset-panel*, .dataset-card*,
 *                   .dataset-freshness
 * ==================================================================== */

/* --- A. Layout shell -------------------------------------------------
 * The workstation paints its own .side / .main / .right grid. We strip
 * the harsh 1px dividers between panels and keep the inside transparent
 * so the Lumen card behind it is the visible surface. Padding is
 * relaxed to Lumen's 14-22px rhythm. */
.lumen-app .workstation {
  background: transparent;
  font-family: var(--sans);
  color: var(--ink);
  /* Match the Lumen card geometry: rows = topbar-area + body, no third
     trust row. Trust is rendered inline as a card now, so we collapse
     the auto-3rd-row to 0. The default workstation grid is 260/1fr/320;
     bump the side rails wider to give Lumen typography room. */
  grid-template-columns: 240px 1fr 320px;
}
.lumen-app .workstation > .side,
.lumen-app .workstation > .main,
.lumen-app .workstation > .right {
  background: transparent;
  border: none;
}
.lumen-app .workstation > .side {
  border-right: 1px solid var(--border);
  padding: 4px 0;
}
.lumen-app .workstation > .right {
  border-left: 1px solid var(--border);
  padding: 4px 0;
}

/* --- A1. Split the lens panel into its own Lumen card (desktop only) -
 *
 * Goal (visual): two distinct Lumen white cards sitting side by side
 * with a 14px painterly gap between them. The LEFT card holds .side +
 * .main (sidebar, search row, chart, analog strip, trust panel). The
 * RIGHT card holds the 9-lens radar/bars/reading narrative.
 *
 * Why this approach (different from the failed PR #271):
 *   PR #271 tried to make the OUTER .lumen-main card transparent
 *   so two inner cards could replace it. That broke because dozens of
 *   sub-panels inside the workstation (.ws-search-row, lens radar,
 *   lens bars, etc.) are themselves transparent and rely on the parent
 *   .lumen-main for their visible background. Removing that backdrop
 *   leaked the painterly green-brown gradient through every transparent
 *   panel.
 *
 *   This implementation KEEPS .lumen-main as the outer white card --
 *   we just shrink it horizontally by margin-right: 334px (320 lens
 *   width + 14 gap) so a 334px reservation strip opens on the right.
 *   Then we lift .right out of the workstation grid and absolute-
 *   position it inside .lumen-shell as a separate card with full
 *   Lumen chrome (white surface, hairline border, soft shadow,
 *   rounded radius). Every transparent inner panel still has a card
 *   above it -- .lumen-main for .side/.main children, and the
 *   absolute-positioned .right element itself for the lens children.
 *
 * Scope (mandatory): only at >=1280px because between 1024-1279px the
 * .right becomes a slide-in drawer (position:fixed via globals.css)
 * and below 1024px it is hidden entirely. Wrapping these rules in a
 * desktop-only media query preserves that drawer behavior unchanged.
 *
 * The 1280px breakpoint matches the boundary in app/globals.css where
 * the drawer media query ends (max-width: 1279px).
 */
@media (min-width: 1280px) {
  /* Shrink lumen-main horizontally so the lens card has a slot. The
     14px gap matches .lumen-shell's grid gap: 14px so the rhythm
     between sidebar->main and main->lens is identical.

     Why margin-right (not width): margin pushes the card edge in
     without disturbing the column-flex layout the topbar/scroll
     children inherit, and without breaking the existing
     display: flex; flex-direction: column chain.

     About the surrounding overflow:hidden chain: .lumen-main,
     .lumen-workstation-host, and .workstation all set
     overflow: hidden. By CSS 2.1 sec 11.1.1, an absolutely-positioned
     descendant whose containing block is an ANCESTOR of the
     overflow:hidden box is NOT clipped by that box. Our .right
     below is anchored to .lumen-shell (position:relative), which
     is an ancestor of all three overflow:hidden boxes, so the lens
     card escapes their clipping cleanly. No overflow change needed. */
  .lumen-app .lumen-main:has(.workstation) {
    margin-right: 334px;
    /* Square off the right corners -- the card no longer reaches that
       edge, so the rounded corner there would float in the gap. */
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
  }

  /* Drop the lens column from the workstation grid (the absolutely-
     positioned override below replaces it). The grid only needs
     side + main columns at this point. */
  .lumen-app .workstation {
    grid-template-columns: 240px 1fr;
  }

  /* Lift .right out of normal flow and dock it into the shell's
     reserved 320px slot on the right. .lumen-shell is already
     position: relative (set above near line 228), so absolute
     positioning anchors to it -- and crucially, the intermediate
     overflow:hidden boxes (.lumen-main, .lumen-workstation-host,
     .workstation) do NOT clip a descendant whose containing block
     is one of THEIR ancestors (CSS 2.1 sec 11.1.1).

     Coordinates: top/right/bottom: 0 because the shell already
     contributes a 14px padding gutter -- that gives the outer 14px
     gap from the window edge, identical to what .lumen-main
     occupies. The 320px width matches the original right-rail spec.

     Padding 0 resets the 4px 0 padding from the in-grid rule
     above. The internal .right__section rules already provide
     their own 18px padding, so the card content breathes correctly
     without extra padding here. */
  .lumen-app .workstation > .right {
    position: absolute;
    /* Inset by 14px on top/right/bottom to match .lumen-shell's padding.
       Absolute positioning anchors to the shell's padding box (= the
       element's outer edge since the shell has no border), so top/right/
       bottom: 0 would place this 14px ABOVE, BEYOND, and BELOW the
       content area where .lumen-main lives -- making this card 28px
       taller than .lumen-main. Inset to 14px aligns the two cards. */
    top: 14px;
    right: 14px;
    bottom: 14px;
    width: 320px;
    /* Lumen card chrome -- mirror .lumen-main exactly. */
    background: var(--surface);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-card);
    /* Internal scroll for tall lens content (radar + 9 bars +
       narrative can exceed viewport at 720p). */
    overflow-y: auto;
    overflow-x: hidden;
    /* Reset the 4px 0 padding and border-left: 1px solid var(--border)
       from the in-grid rule above -- the card has its own border now. */
    padding: 0;
    border-left: none;
  }

  /* Defensive: confirm .lumen-shell is the relative anchor. The base
     rule near line 228 already sets position: relative; this no-op
     safety net guards against a future upstream edit accidentally
     breaking the absolute child positioning. */
  .lumen-app .lumen-shell:has(.workstation) {
    position: relative;
  }
}

/* --- B. Side panel (left) — query def, window, pinned, notebook ----- */
.lumen-app .workstation .side__section {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
}
.lumen-app .workstation .side__section:last-child {
  border-bottom: none;
}
.lumen-app .workstation .side__header {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 10px;
}
.lumen-app .workstation .side__row {
  display: flex; justify-content: space-between;
  padding: 6px 0;
  font-size: 12.5px;
  /* Drop the dotted underline — Lumen prefers white-space hierarchy. */
  border-bottom: 1px solid var(--border);
}
.lumen-app .workstation .side__row:last-child { border-bottom: none; }
.lumen-app .workstation .side__row .k {
  color: var(--ink-3);
  font-family: var(--sans);
  font-size: 12.5px;
  letter-spacing: 0;
  text-transform: none;
}
.lumen-app .workstation .side__row .v {
  font-family: var(--mono);
  color: var(--ink);
  font-size: 12px;
  font-feature-settings: 'tnum';
  letter-spacing: 0;
}

/* All .label micro-caps inside the workstation become Lumen eyebrows.
   Drops mono + uppercase + heavy tracking. */
.lumen-app .workstation .label {
  font-family: var(--sans);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  font-weight: 600;
  line-height: 1.2;
}
/* Inline .serif and .mono helpers inside the workstation. */
.lumen-app .workstation .serif {
  font-family: var(--serif);
  font-weight: 400;
  letter-spacing: -0.01em;
}
.lumen-app .workstation .mono {
  font-family: var(--mono);
  font-feature-settings: 'tnum';
  letter-spacing: 0;
  text-transform: none;
  color: inherit;
}
.lumen-app .workstation .sub {
  color: var(--ink-3);
  font-size: 12px;
}

/* --- B1. Chips (window length, view range, etc.) -------------------- */
.lumen-app .workstation .chip-row {
  display: flex; flex-wrap: wrap; gap: 6px;
}
.lumen-app .workstation .chip {
  font-family: var(--sans);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  padding: 4px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--ink-2);
  background: var(--surface);
  cursor: pointer;
  transition: all 120ms;
}
.lumen-app .workstation .chip:hover:not([data-active="true"]) {
  background: var(--surface-2);
  border-color: var(--border-strong);
  color: var(--ink);
}
.lumen-app .workstation .chip[data-active="true"] {
  background: var(--accent-soft);
  color: var(--accent-ink);
  border-color: var(--accent-soft);
}

/* --- B2. Saved analogs / pinned list -------------------------------- */
.lumen-app .workstation .saved-list { gap: 4px; }
.lumen-app .workstation .saved {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  cursor: pointer;
  transition: background 120ms, border-color 120ms;
}
.lumen-app .workstation .saved:hover {
  background: var(--surface-2);
  border-color: var(--border-strong);
}
.lumen-app .workstation .saved__date {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-3);
  width: 64px;
  font-feature-settings: 'tnum';
  letter-spacing: 0;
}
.lumen-app .workstation .saved__name {
  font-family: var(--sans);
  font-size: 12.5px;
  color: var(--ink);
  font-weight: 500;
}
.lumen-app .workstation .saved__score {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-2);
  font-feature-settings: 'tnum';
}

/* --- C. Main column / search row ------------------------------------ */
.lumen-app .workstation .main {
  background: transparent;
}
.lumen-app .workstation .ws-search-row {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 10px 22px;
  gap: 14px;
}
.lumen-app .workstation .ws-search-row__label {
  font-family: var(--sans);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  font-weight: 600;
}
.lumen-app .workstation .ws-search-row__label--secondary { color: var(--ink-3); }
.lumen-app .workstation .ws-search-row__lastrun {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0;
}
.lumen-app .workstation .ws-search-row__fewer-matches {
  font-family: var(--sans);
  color: var(--warn);
  letter-spacing: 0;
}

/* --- C1. Top-K + horizon segmented controls ------------------------- */
.lumen-app .workstation .ws-topk,
.lumen-app .workstation .ws-horizon {
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--surface);
  overflow: hidden;
  padding: 2px;
  gap: 0;
}
.lumen-app .workstation .ws-topk__btn,
.lumen-app .workstation .ws-horizon__btn {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  padding: 4px 11px;
  border: none;
  background: transparent;
  color: var(--ink-3);
  border-radius: 5px;
  font-variant-numeric: tabular-nums;
}
.lumen-app .workstation .ws-topk__btn:hover:not([data-active="true"]),
.lumen-app .workstation .ws-horizon__btn:hover:not([data-active="true"]) {
  background: var(--surface-2);
  color: var(--ink);
}
.lumen-app .workstation .ws-topk__btn[data-active="true"],
.lumen-app .workstation .ws-horizon__btn[data-active="true"] {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}
.lumen-app .workstation .ws-horizon__clip-hint { color: var(--warn); }

/* --- C2. Primary Search button + Share button ----------------------- */
.lumen-app .workstation .ws-search-btn {
  font-family: var(--sans);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  padding: 6px 14px;
  background: var(--ink);
  color: #fff;
  border: 1px solid var(--ink);
  border-radius: 7px;
  height: 30px;
  display: inline-flex; align-items: center; gap: 7px;
}
.lumen-app .workstation .ws-search-btn:hover:not([disabled]) {
  background: #000;
  border-color: #000;
}
.lumen-app .workstation .ws-search-btn[data-dirty="true"] {
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.lumen-app .workstation .ws-search-btn__dot { background: var(--accent); }
.lumen-app .workstation .ws-share-btn {
  font-family: var(--sans);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  padding: 6px 14px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  color: var(--ink);
  background: var(--surface);
  height: 30px;
}
.lumen-app .workstation .ws-share-btn:hover {
  background: var(--surface-2);
}

/* --- D. Chart stack + chart card ------------------------------------ */
.lumen-app .workstation .chart-stack {
  padding: 18px 22px 24px;
  gap: 18px;
  background: transparent;
}
.lumen-app .workstation .chart-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.lumen-app .workstation .chart-card__head {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: transparent;
}
.lumen-app .workstation .chart-card__title .t {
  font-family: var(--serif);
  font-size: 18px;
  font-weight: 400;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.lumen-app .workstation .chart-card__title .sub {
  color: var(--ink-3);
  font-family: var(--sans);
  font-size: 12.5px;
}
.lumen-app .workstation .chart-card__body {
  padding: 14px 18px 18px;
}
.lumen-app .workstation .chart-card__legend {
  font-family: var(--sans);
  font-size: 11.5px;
  letter-spacing: 0;
  text-transform: none;
  color: var(--ink-3);
  padding: 0 18px 14px;
  gap: 18px;
}
.lumen-app .workstation .legend-dot { gap: 7px; }
.lumen-app .workstation .legend-dot i { background: var(--ink); }
.lumen-app .workstation .legend-dot.analog i { background: var(--ink-4); }
.lumen-app .workstation .legend-dot.cone i,
.lumen-app .workstation .legend-dot.p50 i { background: var(--accent); }

/* --- D1. Chart-mode toggle (Fast/Pro) + settings gear --------------- */
.lumen-app .workstation .ws-chartmode-row {
  margin-bottom: 0;
}
.lumen-app .workstation .ws-chartmode {
  border: 1px solid var(--border);
  border-radius: 7px;
  font-family: var(--sans);
  font-size: 11.5px;
  background: var(--surface);
  padding: 2px;
  overflow: hidden;
}
.lumen-app .workstation .ws-chartmode__btn {
  border: none;
  border-right: none;
  padding: 4px 11px;
  letter-spacing: 0;
  text-transform: none;
  font-weight: 500;
  border-radius: 5px;
  color: var(--ink-3);
  background: transparent;
}
.lumen-app .workstation .ws-chartmode__btn:hover:not([data-active="true"]) {
  background: var(--surface-2);
  color: var(--ink);
}
.lumen-app .workstation .ws-chartmode__btn[data-active="true"] {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}
.lumen-app .workstation .ws-chart-settings__btn { border-radius: 7px; }
.lumen-app .workstation .ws-chart-settings__btn:hover,
.lumen-app .workstation .ws-chart-settings__btn[aria-expanded="true"] {
  background: var(--surface-2);
  border-color: var(--border);
  color: var(--ink);
}
.lumen-app .workstation .ws-chart-settings__pop {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-pop);
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-2);
  padding: 6px 4px;
}
.lumen-app .workstation .ws-chart-settings__row {
  border-radius: var(--radius-sm);
  padding: 6px 10px;
}
.lumen-app .workstation .ws-chart-settings__row:hover { background: var(--surface-2); }
.lumen-app .workstation .ws-chart-settings__row input[type="checkbox"] {
  accent-color: var(--accent);
}

/* --- D2. SVG chart internals --------------------------------------- */
.lumen-app .workstation .svg-chart .grid line { stroke: var(--border); }
.lumen-app .workstation .svg-chart .axis text {
  font-family: var(--sans);
  font-size: 10px;
  fill: var(--ink-3);
  letter-spacing: 0;
}
.lumen-app .workstation .svg-chart .price { stroke: var(--ink); stroke-width: 1.4; }
.lumen-app .workstation .svg-chart .data-end { stroke: var(--ink-4); }
.lumen-app .workstation .svg-chart .data-end-label {
  font-family: var(--sans);
  font-size: 10px;
  fill: var(--ink-3);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.lumen-app .workstation .svg-chart .annot {
  font-family: var(--sans);
  font-size: 10.5px;
  fill: var(--ink-3);
}
.lumen-app .workstation .svg-chart .window-rect {
  fill: var(--accent-soft);
  stroke: var(--accent);
}
.lumen-app .workstation .svg-chart .window-handle { fill: var(--accent); }
.lumen-app .workstation .svg-chart .window-label {
  font-family: var(--sans);
  font-size: 10.5px;
  font-weight: 600;
  fill: var(--accent);
  letter-spacing: 0.04em;
  text-transform: none;
}
.lumen-app .workstation .lw-chart__window {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  border-left: 1px solid color-mix(in srgb, var(--accent) 60%, transparent);
  border-right: 1px solid color-mix(in srgb, var(--accent) 60%, transparent);
}
.lumen-app .workstation .lw-chart__window-label {
  font-family: var(--sans);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--accent);
}
.lumen-app .workstation .lw-chart__note {
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0;
  color: var(--ink-3);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 3px 7px;
}

/* --- E. Analog strip + analog cards (KEY VISUAL) -------------------- */
.lumen-app .workstation .strip {
  background: transparent;
  border-top: 1px solid var(--border);
  padding: 14px 22px 18px;
  gap: 12px;
}
.lumen-app .workstation .analog-card {
  min-width: 220px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 14px 12px;
  background: var(--surface);
  box-shadow: var(--shadow-card);
  transition: all 150ms;
  /* Drop the rank-color left stripe; we replace it with a small dot in
     the head row (see analog-badge styling below). */
}
.lumen-app .workstation .analog-card:hover {
  background: var(--surface-2);
  border-color: var(--border-strong);
}
.lumen-app .workstation .analog-card:not([data-active="true"]) { opacity: 0.65; }
.lumen-app .workstation .analog-card:not([data-active="true"]):hover { opacity: 1; }
.lumen-app .workstation .analog-card[data-pinned="true"] {
  background: var(--accent-soft);
  border-color: var(--accent);
}
/* Kill the burgundy left stripe entirely. */
.lumen-app .workstation .analog-card[data-pinned="true"]::before {
  display: none;
}
.lumen-app .workstation .analog-card[data-active="true"] {
  border-color: var(--ink-3);
}
.lumen-app .workstation .analog-card__head {
  margin-bottom: 6px;
  align-items: center;
  gap: 8px;
}
.lumen-app .workstation .analog-card__date {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0;
  font-feature-settings: 'tnum';
}
.lumen-app .workstation .analog-card__score {
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.015em;
  color: var(--ink);
}
.lumen-app .workstation .analog-card__title {
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--ink);
  margin-bottom: 2px;
}
.lumen-app .workstation .analog-card__note {
  color: var(--ink-3);
  font-size: 11.5px;
  font-family: var(--sans);
  margin-bottom: 8px;
  line-height: 1.45;
}
.lumen-app .workstation .analog-card__after {
  font-family: var(--mono);
  font-size: 11.5px;
  font-feature-settings: 'tnum';
  letter-spacing: 0;
  color: var(--ink-2);
}
.lumen-app .workstation .analog-card__after.pos { color: var(--pos); }
.lumen-app .workstation .analog-card__after.neg { color: var(--neg); }

/* Pin button on each analog card — subtle ghost button. */
.lumen-app .workstation .analog-card__pin-btn {
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--ink-4);
  width: 22px; height: 22px;
  display: inline-grid; place-items: center;
  cursor: pointer;
  transition: all 120ms;
}
.lumen-app .workstation .analog-card__pin-btn:hover {
  color: var(--ink);
  background: var(--surface-2);
}
.lumen-app .workstation .analog-card[data-pinned="true"] .analog-card__pin-btn {
  color: var(--accent);
}

/* The rank-numbered colored badge on each card → desaturated dot in
   Lumen so it doesn't fight the score for visual weight. */
.lumen-app .workstation .analog-badge {
  display: inline-flex; align-items: center; gap: 6px;
}
.lumen-app .workstation .analog-badge-circle {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--ink-3);
  /* Keep per-rank color identity but dim it. */
  opacity: 0.7;
}
.lumen-app .workstation .analog-badge-text {
  font-family: var(--sans);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--ink-3);
  letter-spacing: 0.04em;
}

/* --- F. Right rail (lens panel) ------------------------------------- */
.lumen-app .workstation .right__section {
  padding: 18px 18px;
  border-bottom: 1px solid var(--border);
}
.lumen-app .workstation .right__section:last-child { border-bottom: none; }
.lumen-app .workstation .lens-head {
  margin-bottom: 14px;
}
.lumen-app .workstation .lens-head .label {
  font-family: var(--sans);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  font-weight: 600;
}
.lumen-app .workstation .lens-head .score {
  font-family: var(--serif);
  font-size: 38px;
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1;
  color: var(--ink);
}
.lumen-app .workstation .lens-head .score .d {
  font-family: var(--sans);
  font-size: 11.5px;
  color: var(--ink-3);
  letter-spacing: 0;
  margin-left: 4px;
  font-weight: 400;
}

/* Lens bars — hairline outline with accent fill, no dotted dividers. */
.lumen-app .workstation .lens-bars { gap: 4px; }
.lumen-app .workstation .lens-bar {
  padding: 6px 4px 6px 0;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  cursor: pointer;
  transition: background 100ms;
}
.lumen-app .workstation .lens-bar:hover {
  background: transparent;
}
.lumen-app .workstation .lens-bar:last-child { border-bottom: none; }
.lumen-app .workstation .lens-bar__name {
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-2);
  font-weight: 500;
}
.lumen-app .workstation .lens-bar__track {
  height: 5px;
  background: var(--surface-3);
  border-radius: 999px;
  margin-top: 5px;
}
.lumen-app .workstation .lens-bar__fill {
  background: var(--accent);
  border-radius: 999px;
}
.lumen-app .workstation .lens-bar__fill.weak { background: var(--ink-4); }
.lumen-app .workstation .lens-bar__val {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink);
  font-feature-settings: 'tnum';
  letter-spacing: 0;
}

/* Lens radar — keep the geometry, retint the strokes/labels. */
.lumen-app .workstation .lens-radar .grid-poly { stroke: var(--border); }
.lumen-app .workstation .lens-radar .data-poly {
  fill: var(--accent-soft);
  stroke: var(--accent);
  stroke-width: 1.4;
}
.lumen-app .workstation .lens-radar .axis { stroke: var(--border); }
.lumen-app .workstation .lens-radar .axis-label {
  font-family: var(--sans);
  font-size: 10px;
  fill: var(--ink-3);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.lumen-app .workstation .lens-radar .data-dot { fill: var(--accent); }

/* --- G. Trust strip + calibration panel ----------------------------- */
.lumen-app .workstation .trust {
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 0 22px;
  min-height: 60px;
}
.lumen-app .workstation .trust__item {
  padding: 12px 22px 12px 0;
  margin-right: 22px;
  border-right: 1px solid var(--border);
}
.lumen-app .workstation .trust__item .label {
  font-family: var(--sans);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  font-weight: 600;
}
.lumen-app .workstation .trust__item .v {
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.015em;
  color: var(--ink);
  margin-top: 4px;
}
.lumen-app .workstation .trust__item .v.pos { color: var(--pos); }
.lumen-app .workstation .trust__item .v.warn { color: var(--warn); }
.lumen-app .workstation .trust__expand {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  padding: 6px 12px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  color: var(--ink);
  background: var(--surface);
}
.lumen-app .workstation .trust__expand:hover {
  background: var(--surface-2);
}
.lumen-app .workstation .trust__info { color: var(--ink-3); }
.lumen-app .workstation .trust__info:hover { color: var(--ink); }

/* Trust panel (expanded calibration) */
.lumen-app .workstation .trust-panel {
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 22px 22px 28px;
}
.lumen-app .workstation .trust-panel h3 {
  font-family: var(--serif);
  font-size: 18px;
  font-weight: 400;
  letter-spacing: -0.01em;
  color: var(--ink);
  margin: 0 0 12px;
}
.lumen-app .workstation .trust-panel--empty { background: var(--surface); }
.lumen-app .workstation .trust-panel__empty-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-2);
  padding: 22px;
  box-shadow: none;
}
.lumen-app .workstation .trust-panel__empty-card p {
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink-2);
  line-height: 1.55;
}
.lumen-app .workstation .trust-panel__cta {
  font-family: var(--sans);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0;
  color: var(--accent);
  text-decoration: none;
  border-bottom: 1px solid var(--accent);
  padding-bottom: 1px;
}
.lumen-app .workstation .trust-panel__cta:hover {
  color: var(--accent-ink);
  border-bottom-color: var(--accent-ink);
}
.lumen-app .workstation .trust-panel__grade-copy {
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-2);
}
.lumen-app .workstation .trust-panel__grade-list {
  font-family: var(--sans);
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.7;
}
.lumen-app .workstation .trust-panel__grade-list b {
  color: var(--ink);
  font-weight: 600;
}
.lumen-app .workstation .trust-panel__grade-current {
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-3);
  letter-spacing: 0;
}

/* --- H. Analog detail drawer (slide-in) ---------------------------- */
.lumen-app .workstation .adrawer,
.lumen-app .adrawer {
  background: var(--surface);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow-pop);
  width: 440px;
}
.lumen-app .workstation .adrawer__head,
.lumen-app .adrawer__head {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 16px 18px;
}
.lumen-app .workstation .adrawer__rank-badge,
.lumen-app .adrawer__rank-badge {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  border-radius: var(--radius-pill);
  background: var(--ink);
  color: #fff;
  padding: 4px 10px;
  /* Drop the per-rank colors — Lumen prefers a single ink badge. */
}
.lumen-app .workstation .adrawer__rank-badge[data-rank="0"],
.lumen-app .workstation .adrawer__rank-badge[data-rank="1"],
.lumen-app .workstation .adrawer__rank-badge[data-rank="2"],
.lumen-app .workstation .adrawer__rank-badge[data-rank="3"],
.lumen-app .workstation .adrawer__rank-badge[data-rank="4"],
.lumen-app .workstation .adrawer__rank-badge[data-rank="5"] {
  background: var(--ink);
}
.lumen-app .workstation .adrawer__date-range,
.lumen-app .adrawer__date-range {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0;
  font-feature-settings: 'tnum';
}
.lumen-app .workstation .adrawer__label,
.lumen-app .adrawer__label {
  font-family: var(--serif);
  font-size: 16px;
  font-weight: 400;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.lumen-app .workstation .adrawer__composite-v,
.lumen-app .adrawer__composite-v {
  font-family: var(--serif);
  font-size: 26px;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: var(--ink);
}
.lumen-app .workstation .adrawer__composite-k,
.lumen-app .adrawer__composite-k {
  font-family: var(--sans);
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 600;
}
.lumen-app .workstation .adrawer__pin-toggle,
.lumen-app .adrawer__pin-toggle {
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 500;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  padding: 6px 10px;
  color: var(--ink);
  background: var(--surface);
}
.lumen-app .workstation .adrawer__pin-toggle:hover:not(:disabled),
.lumen-app .adrawer__pin-toggle:hover:not(:disabled) {
  background: var(--surface-2);
  border-color: var(--accent);
  color: var(--accent);
}
.lumen-app .workstation .adrawer__pin-toggle[aria-pressed="true"],
.lumen-app .adrawer__pin-toggle[aria-pressed="true"] {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.lumen-app .workstation .adrawer__close,
.lumen-app .adrawer__close {
  width: 28px; height: 28px;
  border-radius: 7px;
  color: var(--ink-3);
  display: inline-grid; place-items: center;
}
.lumen-app .workstation .adrawer__close:hover,
.lumen-app .adrawer__close:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.lumen-app .workstation .adrawer__context,
.lumen-app .adrawer__context {
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
  padding: 10px 18px;
  font-family: var(--sans);
  font-size: 12.5px;
  color: var(--ink-2);
}
.lumen-app .workstation .adrawer__context-text,
.lumen-app .adrawer__context-text {
  font-family: var(--serif);
  font-style: italic;
}
.lumen-app .workstation .adrawer__section,
.lumen-app .adrawer__section {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
}
.lumen-app .workstation .adrawer__h,
.lumen-app .adrawer__h {
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.lumen-app .workstation .adrawer__h-sub,
.lumen-app .adrawer__h-sub {
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0;
  text-transform: none;
  color: var(--ink-3);
  font-weight: 400;
}
.lumen-app .workstation .adrawer__lens-name,
.lumen-app .adrawer__lens-name {
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-2);
  font-weight: 500;
}
.lumen-app .workstation .adrawer__lens-bar,
.lumen-app .adrawer__lens-bar {
  height: 6px;
  background: var(--surface-3);
  border-radius: 999px;
  overflow: hidden;
}
.lumen-app .workstation .adrawer__lens-bar-fill,
.lumen-app .adrawer__lens-bar-fill {
  background: var(--ink-4);
  border-radius: 999px;
}
.lumen-app .workstation .adrawer__lens-row[data-top="true"] .adrawer__lens-bar-fill,
.lumen-app .adrawer__lens-row[data-top="true"] .adrawer__lens-bar-fill {
  background: var(--accent);
}
/* Override per-rank color overrides — single accent in Lumen. */
.lumen-app .workstation .adrawer__lens-row[data-top="true"][data-rank="0"] .adrawer__lens-bar-fill,
.lumen-app .workstation .adrawer__lens-row[data-top="true"][data-rank="1"] .adrawer__lens-bar-fill,
.lumen-app .workstation .adrawer__lens-row[data-top="true"][data-rank="2"] .adrawer__lens-bar-fill,
.lumen-app .workstation .adrawer__lens-row[data-top="true"][data-rank="3"] .adrawer__lens-bar-fill,
.lumen-app .workstation .adrawer__lens-row[data-top="true"][data-rank="4"] .adrawer__lens-bar-fill,
.lumen-app .workstation .adrawer__lens-row[data-top="true"][data-rank="5"] .adrawer__lens-bar-fill,
.lumen-app .adrawer__lens-row[data-top="true"][data-rank="0"] .adrawer__lens-bar-fill,
.lumen-app .adrawer__lens-row[data-top="true"][data-rank="1"] .adrawer__lens-bar-fill,
.lumen-app .adrawer__lens-row[data-top="true"][data-rank="2"] .adrawer__lens-bar-fill,
.lumen-app .adrawer__lens-row[data-top="true"][data-rank="3"] .adrawer__lens-bar-fill,
.lumen-app .adrawer__lens-row[data-top="true"][data-rank="4"] .adrawer__lens-bar-fill,
.lumen-app .adrawer__lens-row[data-top="true"][data-rank="5"] .adrawer__lens-bar-fill {
  background: var(--accent);
}
.lumen-app .workstation .adrawer__lens-score,
.lumen-app .adrawer__lens-score {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-2);
  font-feature-settings: 'tnum';
}
.lumen-app .workstation .adrawer__spark-wrap,
.lumen-app .adrawer__spark-wrap {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: var(--radius-sm);
}
.lumen-app .workstation .adrawer__spark-meta,
.lumen-app .adrawer__spark-meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  font-feature-settings: 'tnum';
}
.lumen-app .workstation .adrawer__actions,
.lumen-app .adrawer__actions {
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 14px 18px;
}
.lumen-app .workstation .adrawer__action,
.lumen-app .adrawer__action {
  font-family: var(--sans);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  padding: 7px 12px;
  color: var(--ink);
  background: var(--surface);
}
.lumen-app .workstation .adrawer__action:hover,
.lumen-app .adrawer__action:hover {
  background: var(--surface-2);
  border-color: var(--ink-3);
}
.lumen-app .workstation .adrawer__action--primary,
.lumen-app .adrawer__action--primary {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.lumen-app .workstation .adrawer__action--primary:hover,
.lumen-app .adrawer__action--primary:hover {
  background: #000;
  border-color: #000;
  color: #fff;
}
.lumen-app .workstation .adrawer__action--ghost,
.lumen-app .adrawer__action--ghost {
  border-color: transparent;
  background: transparent;
  color: var(--ink-3);
}
.lumen-app .workstation .adrawer__action--ghost:hover,
.lumen-app .adrawer__action--ghost:hover {
  background: var(--surface-2);
  color: var(--ink);
  border-color: transparent;
}

/* --- I. Banners + toasts ------------------------------------------- */
.lumen-app .workstation .ws-banner {
  font-family: var(--sans);
  font-size: 12.5px;
  border-bottom: 1px solid var(--border);
  padding: 10px 22px;
  background: var(--surface-2);
}
.lumen-app .workstation .ws-banner--warn {
  background: #fcf6e6;
  border-left: 3px solid var(--warn);
}
.lumen-app .workstation .ws-banner--info {
  background: var(--accent-soft);
  border-left: 3px solid var(--accent);
}
.lumen-app .workstation .ws-banner__text code {
  font-family: var(--mono);
  font-size: 11.5px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1px 6px;
}
.lumen-app .workstation .ws-banner__dismiss {
  border-radius: var(--radius-sm);
}
.lumen-app .workstation .ws-banner__dismiss:hover {
  background: var(--surface);
  border-color: var(--border);
}

.lumen-app .workstation .ws-pin-banner {
  background: var(--accent-soft);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-sm);
  margin: 12px 22px;
  padding: 8px 14px;
  font-family: var(--sans);
  font-size: 12.5px;
}
.lumen-app .workstation .ws-pin-banner__text strong { color: var(--ink); }
.lumen-app .workstation .ws-pin-banner__clear {
  font-family: var(--sans);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 4px 9px;
  color: var(--ink);
  background: var(--surface);
}
.lumen-app .workstation .ws-pin-banner__clear:hover {
  background: var(--surface-2);
  border-color: var(--accent);
  color: var(--accent);
}

.lumen-app .ws-share-toast {
  font-family: var(--sans);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  background: var(--ink);
  color: #fff;
  border: 1px solid var(--ink);
  border-radius: var(--radius);
  padding: 10px 16px;
  box-shadow: var(--shadow-pop);
}

.lumen-app .ws-use-as-query-banner {
  background: var(--surface);
  border: 1px solid var(--accent);
  border-radius: var(--radius);
  box-shadow: var(--shadow-pop);
  padding: 10px 14px;
  font-family: var(--sans);
  font-size: 13px;
  color: var(--ink);
}
.lumen-app .ws-use-as-query-banner__text strong {
  font-family: var(--sans);
  font-weight: 600;
  font-size: 12.5px;
  color: var(--accent);
  text-transform: none;
  letter-spacing: 0;
}
.lumen-app .ws-use-as-query-banner__dismiss {
  border-radius: var(--radius-sm);
  color: var(--ink-3);
}
.lumen-app .ws-use-as-query-banner__dismiss:hover {
  color: var(--ink);
  background: var(--surface-2);
}

/* --- J. Empty states ----------------------------------------------- */
.lumen-app .workstation .ws-empty-state__card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow-card);
  padding: 28px;
}
.lumen-app .workstation .ws-empty-state__headline {
  font-family: var(--serif);
  font-size: 24px;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: var(--ink);
}
.lumen-app .workstation .ws-empty-state__body {
  font-family: var(--sans);
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--ink-2);
}
.lumen-app .workstation .ws-empty-state__cta {
  font-family: var(--sans);
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  padding: 8px 14px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  color: var(--ink);
  background: var(--surface);
}
.lumen-app .workstation .ws-empty-state__cta:hover {
  background: var(--surface-2);
}
.lumen-app .workstation .ws-empty-state__cta--primary {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.lumen-app .workstation .ws-empty-state__cta--primary:hover {
  background: #000;
  border-color: #000;
}

.lumen-app .workstation .ws-micro-empty__title {
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 400;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.lumen-app .workstation .ws-micro-empty__body {
  font-family: var(--sans);
  font-size: 12.5px;
  color: var(--ink-3);
  line-height: 1.55;
}

.lumen-app .workstation .ws-mobile-notice {
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
  font-family: var(--sans);
  font-size: 12.5px;
  color: var(--ink-2);
}

/* --- K. Drawer chrome (mid/mobile drawer toggles) ------------------- */
.lumen-app .workstation .ws-drawer-toggle {
  font-family: var(--sans);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  padding: 5px 10px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  color: var(--ink);
  background: var(--surface);
}
.lumen-app .workstation .ws-drawer-toggle:hover {
  background: var(--surface-2);
}
.lumen-app .workstation .ws-drawer-close {
  border-radius: 7px;
  color: var(--ink-3);
  background: var(--surface);
  border-color: var(--border);
}
.lumen-app .workstation .ws-drawer-close:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.lumen-app .workstation .ws-drawer-backdrop {
  background: rgba(20,20,20,0.35);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

/* --- L. Dataset selector (left sidebar) ----------------------------- */
.lumen-app .workstation .dataset-freshness {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0;
}
.lumen-app .workstation .dataset-freshness[data-warn="true"] { color: var(--warn); }
.lumen-app .workstation .dataset-trigger {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  padding: 8px 11px;
}
.lumen-app .workstation .dataset-trigger:hover,
.lumen-app .workstation .dataset-trigger:focus-visible {
  background: var(--surface-2);
  border-color: var(--border-strong);
}
.lumen-app .workstation .dataset-trigger__symbol {
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0;
}
.lumen-app .workstation .dataset-trigger__meta {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0;
}
.lumen-app .workstation .dataset-trigger__caret {
  color: var(--ink-3);
}
.lumen-app .workstation .dataset-panel {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  box-shadow: var(--shadow-card);
}
.lumen-app .workstation .dataset-panel__search {
  font-family: var(--sans);
  font-size: 12.5px;
  background: var(--surface-2);
  color: var(--ink);
  border-bottom: 1px solid var(--border);
  padding: 10px 12px;
}
.lumen-app .workstation .dataset-panel__search:focus-visible {
  background: var(--surface);
}
.lumen-app .workstation .dataset-panel__group-header {
  font-family: var(--sans);
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-3);
  padding: 8px 12px 4px;
}
.lumen-app .workstation .dataset-panel__empty {
  font-family: var(--sans);
  font-size: 12px;
  color: var(--ink-3);
}
.lumen-app .workstation .dataset-card {
  padding: 8px 12px;
  border-left: 2px solid transparent;
}
.lumen-app .workstation .dataset-card:hover,
.lumen-app .workstation .dataset-card:focus-visible {
  background: var(--surface-2);
}
.lumen-app .workstation .dataset-card[data-selected="true"] {
  background: var(--accent-soft);
  border-left-color: var(--accent);
}
.lumen-app .workstation .dataset-card__title {
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0;
}
.lumen-app .workstation .dataset-card__sub {
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-2);
}
.lumen-app .workstation .dataset-card__sub--muted {
  color: var(--ink-3);
}
.lumen-app .workstation .dataset-card__stale-dot { background: var(--warn); }

/* --- M. Dark mode overrides for embedded workstation ---------------- */
.lumen-app.dark .workstation .ws-banner--warn { background: #2a2218; }
.lumen-app.dark .workstation .ws-banner--info { background: var(--accent-soft); }
.lumen-app.dark .workstation .ws-pin-banner { background: var(--accent-soft); }
.lumen-app.dark .workstation .lens-bar__track,
.lumen-app.dark .workstation .adrawer__lens-bar { background: var(--surface-3); }

/* End of Lumen workstation overrides. */
`;
