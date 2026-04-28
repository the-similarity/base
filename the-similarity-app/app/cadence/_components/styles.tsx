/**
 * Cadence health workstation scoped stylesheet.
 *
 * Bug context (fixed in this revision):
 *   The previous revision used generic class names like `.app`, `.main`,
 *   `.sidebar`, `.scroll`, `.card`, `.btn`, `.pill`, `.kbd`, `.num`,
 *   `.mono`, `.row`, `.col`, `.crumbs`, `.brand`, `.nav-item`,
 *   `.h-eyebrow`, `.h-display`, etc. — every one of which COLLIDES with
 *   rules in `app/globals.css`. Even though every selector here is
 *   prefixed with `.cadence-app`, the global rules still apply for any
 *   property NOT explicitly overridden. The killer example was
 *   `.app { display: grid; grid-template-rows: 44px 1fr 26px; ...}` in
 *   globals.css combining with `.cadence-app .app { grid-template-columns:
 *   220px 1fr; ... }` here. Result: the inner shell became a 3-row × 2-col
 *   grid where the sidebar+main got squeezed into the 44px first row,
 *   leaving the main panel visually empty (just the painterly background
 *   showing through).
 *
 * The bulletproof fix (mirrors what Lumen did in
 * `app/workstation/lumen/_components/styles.tsx`): rename every
 * Cadence-owned class to a `cadence-` prefixed name. No prefix collision
 * with anything else in the app, no specificity gymnastics. Selectors
 * here all read `.cadence-app .cadence-foo`. The JSX tree was updated in
 * lockstep — every `className=` under this route now uses `cadence-foo`
 * instead of `foo`.
 *
 * Design palette rationale (different from Lumen's earthy forest/sienna):
 *   - Default accent: #5b8a72 (sage green) — calm clinical biological feel
 *   - Bloom default: warm coral → sage gradient (sunrise + plant)
 *   - Dawn alt: deeper sunrise → indigo (early-morning feel)
 *   - Paper: clinical white (chart-of-the-day mode)
 *   - Slate: dark mode bias (night reading / sleep tracking)
 *
 * Background note: the painterly background is rendered by a sibling
 * element with class `.cadence-painterly`. It is absolutely positioned
 * (NOT fixed) so it stays inside this route's wrapper and doesn't bleed
 * into other pages. Its background-image is mutated at runtime by the
 * tweaks panel to swap between Bloom/Dawn/Paper/Slate presets.
 *
 * IMPORTANT: NEVER add un-prefixed selectors here. Anything without a
 * `.cadence-app` ancestor would leak into the rest of the app, and any
 * class without a `cadence-` prefix can collide with `globals.css`.
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
  background: linear-gradient(160deg, #4a7a5a 0%, #6b9a72 25%, #c4b896 55%, #8a6a4a 80%, #3d2f1f 100%);
  pointer-events: none;
}
.cadence-app .cadence-painterly::before {
  content: ''; position: absolute; inset: -10%;
  background:
    radial-gradient(ellipse 60% 40% at 20% 30%, rgba(120,160,140,0.6), transparent 60%),
    radial-gradient(ellipse 50% 35% at 75% 60%, rgba(180,150,100,0.5), transparent 60%),
    radial-gradient(ellipse 40% 30% at 50% 85%, rgba(60,40,25,0.4), transparent 60%),
    radial-gradient(ellipse 70% 50% at 90% 15%, rgba(90,130,110,0.5), transparent 70%);
  filter: blur(40px);
}
.cadence-app .cadence-painterly::after {
  content: ''; position: absolute; inset: 0;
  background-image:
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.4 0 0 0 0 0.35 0 0 0 0 0.25 0 0 0 0.6 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.35'/></svg>");
  mix-blend-mode: overlay;
  opacity: 0.5;
}

/* ============ app shell ============
   .cadence-app-shell (formerly .app) wraps sidebar + main. The rename is
   THE bugfix for the empty-main-panel problem: the global .app selector
   in app/globals.css set grid-template-rows: 44px 1fr 26px, which
   combined with our grid-template-columns: 220px 1fr to push the main
   panel into a 44px-tall first row. */
.cadence-app .cadence-app-shell {
  position: relative; z-index: 1;
  height: 100vh;
  padding: 14px;
  display: grid;
  grid-template-columns: 220px 1fr;
  grid-template-rows: 1fr;
  gap: 14px;
}

/* ============ sidebar ============ */
.cadence-app .cadence-sidebar {
  background: rgba(255,255,255,0.72);
  backdrop-filter: blur(20px) saturate(120%);
  -webkit-backdrop-filter: blur(20px) saturate(120%);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: var(--radius-lg);
  padding: 14px 10px;
  display: flex; flex-direction: column;
  box-shadow: var(--shadow-card);
}
.cadence-app .cadence-brand {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px 18px 8px;
}
.cadence-app .cadence-brand-mark {
  width: 22px; height: 22px;
  border-radius: 6px;
  background: var(--ink);
  display: grid; place-items: center;
  color: #f4f1ea;
  font-family: 'Instrument Serif', serif;
  font-size: 16px; font-style: italic;
  line-height: 1;
}
.cadence-app .cadence-brand-name {
  font-family: 'Instrument Serif', serif;
  font-size: 18px;
  letter-spacing: -0.01em;
}
.cadence-app .cadence-brand-sub {
  margin-left: auto;
  font-size: 10px;
  color: var(--ink-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.cadence-app .cadence-nav-group { display: flex; flex-direction: column; gap: 1px; }
.cadence-app .cadence-nav-label {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-4);
  padding: 14px 10px 6px 10px;
  font-weight: 550;
}
.cadence-app .cadence-nav-item {
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
.cadence-app .cadence-nav-item:hover { background: rgba(0,0,0,0.04); color: var(--ink); }
.cadence-app .cadence-nav-item.is-active {
  background: rgba(0,0,0,0.06);
  color: var(--ink);
  font-weight: 550;
}
/* Default icon size — every site that wraps Icon in a sized parent overrides
   this. Without it, an SVG with no width/height attrs fills its container,
   which blew up the composer "+" to ~600px. */
.cadence-app .cadence-ico { width: 14px; height: 14px; flex: 0 0 auto; }
.cadence-app .cadence-nav-item .cadence-ico { width: 15px; height: 15px; flex: 0 0 15px; opacity: 0.75; }
.cadence-app .cadence-nav-item.is-active .cadence-ico { opacity: 1; }
.cadence-app .cadence-nav-item .cadence-badge {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--ink-3);
  background: rgba(0,0,0,0.05);
  padding: 1px 6px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}
.cadence-app .cadence-nav-item .cadence-badge.cadence-dot {
  width: 6px; height: 6px;
  padding: 0;
  background: var(--accent);
}

.cadence-app .cadence-sidebar-foot {
  margin-top: auto;
  padding: 10px 8px 4px 8px;
  border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 9px;
}
.cadence-app .cadence-avatar {
  width: 26px; height: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, #d4a3a3, #5b8a72);
  color: #fff;
  display: grid; place-items: center;
  font-size: 11px; font-weight: 600;
  flex: 0 0 26px;
}
.cadence-app .cadence-sidebar-foot .cadence-who { font-size: 12.5px; font-weight: 550; line-height: 1.1; }
.cadence-app .cadence-sidebar-foot .cadence-plan { font-size: 11px; color: var(--ink-3); line-height: 1.1; }

/* ============ main panel ============ */
.cadence-app .cadence-main {
  background: var(--surface);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255,255,255,0.5);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  display: flex; flex-direction: column;
  min-width: 0;
}

.cadence-app .cadence-topbar {
  height: 46px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 16px;
  gap: 10px;
  flex: 0 0 46px;
}
.cadence-app .cadence-crumbs {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px;
  color: var(--ink-3);
}
.cadence-app .cadence-crumbs .cadence-sep { color: var(--ink-4); }
.cadence-app .cadence-crumbs .cadence-here { color: var(--ink); font-weight: 500; }
.cadence-app .cadence-top-actions { margin-left: auto; display: flex; align-items: center; gap: 6px; }

.cadence-app .cadence-icon-btn {
  width: 28px; height: 28px;
  display: grid; place-items: center;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink-2);
  transition: all 120ms;
}
.cadence-app .cadence-icon-btn:hover { background: rgba(0,0,0,0.05); color: var(--ink); }
.cadence-app .cadence-icon-btn.cadence-outline { border-color: var(--border-strong); }
.cadence-app .cadence-icon-btn svg { width: 15px; height: 15px; }

.cadence-app .cadence-btn {
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
.cadence-app .cadence-btn:hover { background: var(--surface-2); }
.cadence-app .cadence-btn.cadence-btn-primary {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
}
.cadence-app .cadence-btn.cadence-btn-primary:hover { background: #000; }
.cadence-app .cadence-btn.cadence-btn-accent {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.cadence-app .cadence-btn.cadence-btn-ghost { border-color: transparent; }
.cadence-app .cadence-btn.cadence-btn-ghost:hover { background: rgba(0,0,0,0.05); }
.cadence-app .cadence-btn .cadence-ico { width: 13px; height: 13px; }

.cadence-app .cadence-scroll {
  flex: 1; min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.cadence-app .cadence-scroll::-webkit-scrollbar { width: 10px; }
.cadence-app .cadence-scroll::-webkit-scrollbar-thumb { background: var(--ink-5); border-radius: 999px; border: 3px solid var(--surface); background-clip: padding-box; }
.cadence-app .cadence-scroll::-webkit-scrollbar-thumb:hover { background: var(--ink-4); border: 3px solid var(--surface); background-clip: padding-box; }

/* ============ typography ============ */
.cadence-app .cadence-h-eyebrow {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--ink-3); font-weight: 550;
}
.cadence-app .cadence-h-display {
  font-family: 'Instrument Serif', serif;
  font-weight: 400;
  letter-spacing: -0.02em;
  line-height: 1;
}
.cadence-app .cadence-num { font-variant-numeric: tabular-nums; font-feature-settings: 'tnum'; }
.cadence-app .cadence-mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.cadence-app .cadence-pos { color: var(--pos); }
.cadence-app .cadence-neg { color: var(--neg); }

/* ============ pills / chips ============ */
.cadence-app .cadence-pill {
  display: inline-flex; align-items: center; gap: 5px;
  height: 22px; padding: 0 8px;
  border-radius: 999px;
  background: rgba(0,0,0,0.04);
  color: var(--ink-2);
  font-size: 11.5px;
  font-weight: 500;
}
.cadence-app .cadence-pill .cadence-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.cadence-app .cadence-pill.cadence-pill-pos { background: var(--accent-soft); color: var(--accent-ink); }
.cadence-app .cadence-pill.cadence-pill-neg { background: #f5e4e0; color: #7a2f24; }
.cadence-app .cadence-pill.cadence-pill-warn { background: #f6ecd6; color: #6b4f0f; }
.cadence-app .cadence-pill.cadence-pill-info { background: #e3ecf5; color: #1f4569; }
.cadence-app .cadence-pill.cadence-pill-outline { background: transparent; border: 1px solid var(--border-strong); }

/* ============ section title ============ */
.cadence-app .cadence-section-head {
  display: flex; align-items: baseline; gap: 12px;
  padding: 6px 0 12px 0;
}
.cadence-app .cadence-section-head .cadence-title {
  font-size: 13px; font-weight: 600; color: var(--ink);
}
.cadence-app .cadence-section-head .cadence-sub { font-size: 12.5px; color: var(--ink-3); }
.cadence-app .cadence-section-head .cadence-actions { margin-left: auto; display: flex; gap: 4px; align-items: center; }

/* ============ card ============ */
.cadence-app .cadence-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.cadence-app .cadence-card.cadence-card-tinted { background: var(--surface-2); }
.cadence-app .cadence-card-pad { padding: 16px; }
.cadence-app .cadence-card-pad-lg { padding: 22px; }

/* ============ KPI ============ */
.cadence-app .cadence-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.cadence-app .cadence-kpi {
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex; flex-direction: column;
  min-height: 108px;
}
.cadence-app .cadence-kpi .cadence-label {
  font-size: 11.5px; color: var(--ink-3); font-weight: 500;
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 8px;
}
.cadence-app .cadence-kpi .cadence-label .cadence-ico { width: 13px; height: 13px; opacity: 0.7; }
.cadence-app .cadence-kpi .cadence-value {
  font-family: 'Instrument Serif', serif;
  font-size: 30px; line-height: 1;
  letter-spacing: -0.015em;
  color: var(--ink);
}
.cadence-app .cadence-kpi .cadence-delta {
  margin-top: auto; padding-top: 10px;
  font-size: 11.5px; color: var(--ink-3);
  display: flex; align-items: center; gap: 4px;
}
.cadence-app .cadence-kpi .cadence-delta .cadence-arrow { font-weight: 600; }

/* ============ metrics column (Today screen) — 6 vertical key metrics ============ */
.cadence-app .cadence-metric-col { display: flex; flex-direction: column; gap: 8px; }
.cadence-app .cadence-metric-row {
  display: grid;
  grid-template-columns: 18px 1fr auto auto;
  gap: 10px;
  align-items: center;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.cadence-app .cadence-metric-row .cadence-ico { width: 16px; height: 16px; color: var(--ink-3); }
.cadence-app .cadence-metric-row .cadence-lab { font-size: 12px; color: var(--ink-3); font-weight: 500; }
.cadence-app .cadence-metric-row .cadence-val {
  font-family: 'Instrument Serif', serif;
  font-size: 22px; line-height: 1;
  letter-spacing: -0.015em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.cadence-app .cadence-metric-row .cadence-unit { font-size: 11px; color: var(--ink-3); margin-left: 2px; }
.cadence-app .cadence-metric-row .cadence-delta {
  font-size: 11px; font-variant-numeric: tabular-nums;
  padding: 1px 6px; border-radius: 999px;
}
.cadence-app .cadence-metric-row .cadence-delta.cadence-pos { background: var(--accent-soft); color: var(--accent-ink); }
.cadence-app .cadence-metric-row .cadence-delta.cadence-neg { background: #f5e4e0; color: #7a2f24; }
.cadence-app .cadence-metric-row .cadence-delta.cadence-flat { background: rgba(0,0,0,0.04); color: var(--ink-3); }

/* ============ progress ============ */
.cadence-app .cadence-progress {
  height: 6px; background: rgba(0,0,0,0.06); border-radius: 999px; overflow: hidden;
  position: relative;
}
.cadence-app .cadence-progress > .cadence-fill { height: 100%; background: var(--ink); border-radius: 999px; }
.cadence-app .cadence-progress.cadence-progress-thin { height: 4px; }
.cadence-app .cadence-progress > .cadence-fill.cadence-fill-accent { background: var(--accent); }
.cadence-app .cadence-progress > .cadence-fill.cadence-fill-warn { background: var(--warn); }
.cadence-app .cadence-progress > .cadence-fill.cadence-fill-neg { background: var(--neg); }

/* ============ chart helpers ============ */
.cadence-app .cadence-chart-wrap { position: relative; }
.cadence-app .cadence-chart-wrap svg { display: block; width: 100%; height: 100%; }

/* ============ split layout ============ */
.cadence-app .cadence-split {
  display: flex;
  flex: 1;
  min-height: 0;
}
.cadence-app .cadence-content-col { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.cadence-app .cadence-scroll-pad { padding: 22px 28px 80px 28px; }

/* ============ command palette — fixed because it's a modal overlay ============ */
.cadence-app .cadence-cmdk-back {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(20,20,20,0.35);
  backdrop-filter: blur(4px);
  display: grid; place-items: start center;
  padding-top: 14vh;
}
.cadence-app .cadence-cmdk {
  width: 580px;
  max-width: 92vw;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  box-shadow: var(--shadow-pop);
  overflow: hidden;
}
.cadence-app .cadence-cmdk-input {
  width: 100%; height: 48px; border: none; outline: none;
  padding: 0 18px; font-size: 14px;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--ink);
}
.cadence-app .cadence-cmdk-list { max-height: 380px; overflow-y: auto; padding: 6px; }
.cadence-app .cadence-cmdk-group { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-4); padding: 10px 12px 4px 12px; font-weight: 550; }
.cadence-app .cadence-cmdk-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 7px; font-size: 13px; cursor: pointer; color: var(--ink); }
.cadence-app .cadence-cmdk-item:hover, .cadence-app .cadence-cmdk-item.is-active { background: rgba(0,0,0,0.05); }
.cadence-app .cadence-cmdk-item .cadence-ico { width: 14px; height: 14px; color: var(--ink-3); }
.cadence-app .cadence-cmdk-item .cadence-kbd { margin-left: auto; font-size: 10.5px; color: var(--ink-4); }

/* ============ kbd ============ */
.cadence-app .cadence-kbd {
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
.cadence-app .cadence-ai-bubble {
  background: linear-gradient(180deg, #fafaf6, #f4f1ea);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  font-size: 13px;
  color: var(--ink);
  line-height: 1.55;
}
.cadence-app .cadence-ai-bubble .cadence-ai-head {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--ink-3); font-weight: 550;
  margin-bottom: 8px;
}
.cadence-app .cadence-ai-bubble .cadence-ai-head .cadence-pulse {
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
.cadence-app .cadence-row { display: flex; align-items: center; }
.cadence-app .cadence-col { display: flex; flex-direction: column; }
.cadence-app .cadence-gap-4 { gap: 4px; }
.cadence-app .cadence-gap-6 { gap: 6px; }
.cadence-app .cadence-gap-8 { gap: 8px; }
.cadence-app .cadence-gap-12 { gap: 12px; }
.cadence-app .cadence-gap-16 { gap: 16px; }
.cadence-app .cadence-gap-20 { gap: 20px; }
.cadence-app .cadence-gap-24 { gap: 24px; }
.cadence-app .cadence-grow { flex: 1; min-width: 0; }
.cadence-app .cadence-right { margin-left: auto; }
.cadence-app .cadence-mt-4 { margin-top: 4px; }
.cadence-app .cadence-mt-8 { margin-top: 8px; }
.cadence-app .cadence-mt-12 { margin-top: 12px; }
.cadence-app .cadence-mt-16 { margin-top: 16px; }
.cadence-app .cadence-mt-20 { margin-top: 20px; }
.cadence-app .cadence-mt-24 { margin-top: 24px; }
.cadence-app .cadence-mt-32 { margin-top: 32px; }
.cadence-app .cadence-mb-4 { margin-bottom: 4px; }
.cadence-app .cadence-mb-8 { margin-bottom: 8px; }
.cadence-app .cadence-mb-12 { margin-bottom: 12px; }
.cadence-app .cadence-mb-16 { margin-bottom: 16px; }
.cadence-app .cadence-mb-20 { margin-bottom: 20px; }
.cadence-app .cadence-mb-24 { margin-bottom: 24px; }
.cadence-app .cadence-text-3 { color: var(--ink-3); }
.cadence-app .cadence-text-2 { color: var(--ink-2); }
.cadence-app .cadence-fz-11 { font-size: 11px; }
.cadence-app .cadence-fz-12 { font-size: 12px; }
.cadence-app .cadence-fz-13 { font-size: 13px; }
.cadence-app .cadence-fz-14 { font-size: 14px; }
.cadence-app .cadence-fw-5 { font-weight: 500; }
.cadence-app .cadence-fw-6 { font-weight: 600; }

/* ============ donut legend ============ */
.cadence-app .cadence-legend-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0;
  font-size: 12.5px;
  border-bottom: 1px dashed var(--border);
}
.cadence-app .cadence-legend-row:last-child { border-bottom: none; }
.cadence-app .cadence-legend-row .cadence-sw { width: 8px; height: 8px; border-radius: 2px; flex: 0 0 8px; }
.cadence-app .cadence-legend-row .cadence-lab { color: var(--ink-2); }
.cadence-app .cadence-legend-row .cadence-pct { margin-left: auto; color: var(--ink-3); font-variant-numeric: tabular-nums; }
.cadence-app .cadence-legend-row .cadence-amt { width: 80px; text-align: right; color: var(--ink); font-weight: 500; font-variant-numeric: tabular-nums; }

/* ============ rhyme card ============ */
.cadence-app .cadence-rhyme-card {
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  display: flex; flex-direction: column; gap: 12px;
  cursor: pointer;
  transition: all 120ms;
}
.cadence-app .cadence-rhyme-card:hover { border-color: var(--border-strong); transform: translateY(-1px); box-shadow: var(--shadow-card); }
.cadence-app .cadence-rhyme-card.cadence-rhyme-card-featured {
  border-color: var(--accent);
  background: linear-gradient(180deg, var(--accent-soft), var(--surface));
}
.cadence-app .cadence-rhyme-card .cadence-rh-head { display: flex; align-items: baseline; gap: 12px; }
.cadence-app .cadence-rhyme-card .cadence-rh-date { font-size: 13px; font-weight: 600; color: var(--ink); }
.cadence-app .cadence-rhyme-card .cadence-rh-score {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; padding: 2px 7px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent-ink); font-weight: 600;
}
.cadence-app .cadence-rhyme-card .cadence-rh-outcome { font-size: 12.5px; color: var(--ink-2); }

/* ============ ring ============ */
.cadence-app .cadence-ring-wrap { position: relative; width: 84px; height: 84px; }
.cadence-app .cadence-ring-wrap .cadence-ring-text {
  position: absolute; inset: 0; display: grid; place-items: center;
  font-family: 'Instrument Serif', serif;
  font-size: 22px; line-height: 1;
}

/* ============ log entry ============ */
.cadence-app .cadence-log-row {
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
.cadence-app .cadence-log-row:hover { background: var(--surface-2); }
.cadence-app .cadence-log-row .cadence-tm { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--ink-3); }
.cadence-app .cadence-log-row .cadence-ic {
  width: 24px; height: 24px;
  border-radius: 6px;
  display: grid; place-items: center;
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--ink-3);
}
.cadence-app .cadence-log-row .cadence-ic svg { width: 12px; height: 12px; }
.cadence-app .cadence-log-row .cadence-body { min-width: 0; }
.cadence-app .cadence-log-row .cadence-body .cadence-ttl { font-weight: 500; color: var(--ink); }
.cadence-app .cadence-log-row .cadence-body .cadence-sub { font-size: 11.5px; color: var(--ink-3); }
.cadence-app .cadence-log-row .cadence-meta { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--ink-2); text-align: right; }

/* composer */
.cadence-app .cadence-composer {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 14px;
}
.cadence-app .cadence-composer input {
  flex: 1; height: 32px;
  border: none; background: transparent;
  font-size: 13.5px;
  outline: none;
  color: var(--ink);
}
.cadence-app .cadence-composer input::placeholder { color: var(--ink-4); }

/* ============ source card ============ */
.cadence-app .cadence-source-card {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  display: flex; align-items: center; gap: 14px;
}
.cadence-app .cadence-source-logo {
  width: 36px; height: 36px;
  border-radius: 8px;
  display: grid; place-items: center;
  color: #fff;
  font-size: 13px; font-weight: 600;
  flex: 0 0 36px;
}

/* ============ lab row ============ */
.cadence-app .cadence-lab-row {
  display: grid;
  grid-template-columns: 1fr 100px 130px 100px 120px;
  gap: 14px;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.cadence-app .cadence-lab-row.cadence-lab-row-head {
  background: var(--surface-2);
  color: var(--ink-3);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 550;
  padding: 8px 16px;
}
.cadence-app .cadence-lab-row .cadence-nm { font-weight: 500; }
.cadence-app .cadence-lab-row .cadence-vl { font-family: 'Instrument Serif', serif; font-size: 18px; }

/* ============ filter bar ============ */
.cadence-app .cadence-filter-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.cadence-app .cadence-chip {
  display: inline-flex; align-items: center; gap: 5px;
  height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px dashed var(--border-strong);
  color: var(--ink-3);
  font-size: 12px;
  background: transparent;
}
.cadence-app .cadence-chip.is-active {
  border-style: solid;
  background: var(--surface-2);
  color: var(--ink);
}
.cadence-app .cadence-chip:hover { color: var(--ink); border-color: var(--ink-3); }

/* ============ search input ============ */
.cadence-app .cadence-search-input {
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
.cadence-app .cadence-search-input:focus { border-color: var(--ink-3); }
.cadence-app .cadence-search-wrap { position: relative; }
.cadence-app .cadence-search-wrap svg { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); width: 13px; height: 13px; color: var(--ink-4); }

/* ============ donut ============ */
.cadence-app .cadence-donut-c { width: 200px; height: 200px; position: relative; }
.cadence-app .cadence-donut-c .cadence-center {
  position: absolute; inset: 0; display: grid; place-items: center; text-align: center;
}

/* ============ tweaks panel custom ============ */
.cadence-app .cadence-tweak-swatch-row { display: flex; gap: 6px; flex-wrap: wrap; }
.cadence-app .cadence-tweak-swatch {
  width: 26px; height: 26px;
  border-radius: 6px;
  border: 2px solid transparent;
  cursor: pointer;
  position: relative;
}
.cadence-app .cadence-tweak-swatch.is-active {
  border-color: var(--ink);
  box-shadow: 0 0 0 2px var(--surface) inset;
}

/* mini segmented */
.cadence-app .cadence-seg {
  display: inline-flex;
  background: rgba(0,0,0,0.05);
  border-radius: 7px;
  padding: 2px;
}
.cadence-app .cadence-seg button {
  border: none; background: transparent;
  padding: 4px 10px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--ink-3);
  font-weight: 500;
}
.cadence-app .cadence-seg button.is-active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}

/* sparkline color helpers — .cadence-line / .cadence-fill are applied
   by Sparkline (charts.tsx) on the inner path elements. */
.cadence-app .cadence-spark-pos path.cadence-line { stroke: var(--pos); }
.cadence-app .cadence-spark-pos path.cadence-fill { fill: var(--pos); fill-opacity: 0.10; }
.cadence-app .cadence-spark-neg path.cadence-line { stroke: var(--neg); }
.cadence-app .cadence-spark-neg path.cadence-fill { fill: var(--neg); fill-opacity: 0.10; }

/* fade-in for screens */
.cadence-app .cadence-screen-fade {
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
.cadence-app.dark .cadence-sidebar {
  background: rgba(36,40,42,0.7);
  border-color: rgba(255,255,255,0.06);
}
.cadence-app.dark .cadence-ai-bubble {
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
.cadence-app .cadence-tweaks-radio button.is-active {
  background: rgba(255,255,255,0.9);
  box-shadow: 0 1px 2px rgba(0,0,0,0.12);
}
.cadence-app.dark .cadence-tweaks-radio button.is-active { background: rgba(255,255,255,0.12); }
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
