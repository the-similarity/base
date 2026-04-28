/**
 * Cadence health-themed icon set — compact stroke icons matching the
 * painterly inspo and sized to the same 20x20 viewBox as Lumen's icons.
 *
 * Each entry in `iconMap` is a fragment of SVG <path>/<circle>/etc nodes
 * that get drawn inside a 20x20 viewBox. The wrapper <svg> applies a
 * consistent stroke-width / linecap / linejoin so every glyph reads as
 * the same family. To add an icon: add a new key to `iconMap` whose value
 * is the inner geometry only (no <svg> wrapper).
 *
 * Health iconography mapping (from spec):
 *   today    → heartPulse (heart + ECG line)
 *   flow     → waveform (sine bars)
 *   rhymes   → echoRings (concentric arcs — analogue retrieval visual)
 *   cycles   → circleArrow (loop)
 *   log      → ledger (lined paper)
 *   targets  → target (concentric ring)
 *   goals    → flag (banner)
 *   sources  → plug (electrical plug)
 *   labs     → beaker (lab vial)
 *
 * Why a single component (not per-file SVGs): the design ships ~50 icons
 * that get tree-shaken to a few thousand bytes either way; co-locating in
 * one map makes the screen ports one-to-one with the JSX source and
 * avoids 50 separate imports across the page module.
 */
import type { CSSProperties, JSX } from "react";

const iconMap: Record<string, JSX.Element> = {
  // ─────── primary nav (one per screen) ───────
  heartPulse: (
    <>
      <path d="M3 11l3-1 2-4 3 8 2-4 4 1" />
      <path d="M3 11c-1-2-1-5 1.5-6.5C6.5 3 8.5 4 10 6c1.5-2 3.5-3 5.5-1.5 2.5 1.5 2.5 4.5 1.5 6.5l-7 7-7-7Z" />
    </>
  ),
  waveform: (
    <>
      <path d="M2 10h2M5 5v10M8 7v6M11 4v12M14 6v8M17 9v2" />
    </>
  ),
  echoRings: (
    <>
      <circle cx="10" cy="10" r="2" />
      <path d="M5.5 10a4.5 4.5 0 0 1 9 0M3 10a7 7 0 0 1 14 0" />
    </>
  ),
  circleArrow: (
    <>
      <path d="M3 10a7 7 0 1 0 2-5L3 7" />
      <path d="M3 3v4h4" />
    </>
  ),
  ledger: (
    <>
      <rect x="3" y="3" width="14" height="14" rx="1.5" />
      <path d="M6 7h8M6 10h8M6 13h5" />
    </>
  ),
  target: (
    <>
      <circle cx="10" cy="10" r="7" />
      <circle cx="10" cy="10" r="3.5" />
      <circle cx="10" cy="10" r="0.8" fill="currentColor" />
    </>
  ),
  flag: (
    <>
      <path d="M5 3v15" />
      <path d="M5 4h10l-2 3 2 3H5" />
    </>
  ),
  plug: (
    <>
      <path d="M7 3v3M13 3v3" />
      <path d="M5 6h10v3a5 5 0 0 1-10 0V6Z" />
      <path d="M10 14v4" />
    </>
  ),
  beaker: (
    <>
      <path d="M7 3v5l-4 8a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-4-8V3" />
      <path d="M6 3h8" />
      <path d="M5 14h10" />
    </>
  ),

  // ─────── action / utility ───────
  bell: (
    <>
      <path d="M5 8a5 5 0 1 1 10 0v4l1.5 2.5h-13L5 12V8Z" />
      <path d="M8 16a2 2 0 0 0 4 0" />
    </>
  ),
  sparkle: (
    <>
      <path d="M10 2v4M10 14v4M2 10h4M14 10h4M5 5l2.5 2.5M12.5 12.5L15 15M5 15l2.5-2.5M12.5 7.5L15 5" />
    </>
  ),
  settings: (
    <>
      <circle cx="10" cy="10" r="2.5" />
      <path d="M10 2v2M10 16v2M4 10H2M18 10h-2M5 5L3.5 3.5M16.5 16.5L15 15M5 15l-1.5 1.5M16.5 3.5L15 5" />
    </>
  ),
  plus: (
    <>
      <path d="M10 4v12M4 10h12" />
    </>
  ),
  search: (
    <>
      <circle cx="9" cy="9" r="5.5" />
      <path d="M13 13l4 4" />
    </>
  ),
  chevron: (
    <>
      <path d="M7 5l5 5-5 5" />
    </>
  ),
  chevronDown: (
    <>
      <path d="M5 7l5 5 5-5" />
    </>
  ),
  arrowUp: (
    <>
      <path d="M10 16V4M5 9l5-5 5 5" />
    </>
  ),
  arrowDown: (
    <>
      <path d="M10 4v12M5 11l5 5 5-5" />
    </>
  ),
  arrowRight: (
    <>
      <path d="M4 10h12M11 5l5 5-5 5" />
    </>
  ),
  arrowUpRight: (
    <>
      <path d="M6 14L14 6M7 6h7v7" />
    </>
  ),
  download: (
    <>
      <path d="M10 3v10M5 9l5 4 5-4M3 17h14" />
    </>
  ),
  refresh: (
    <>
      <path d="M3 10a7 7 0 0 1 12-5l2-2v5h-5" />
      <path d="M17 10a7 7 0 0 1-12 5l-2 2v-5h5" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="10" r="1.2" fill="currentColor" />
      <circle cx="10" cy="10" r="1.2" fill="currentColor" />
      <circle cx="15" cy="10" r="1.2" fill="currentColor" />
    </>
  ),
  check: (
    <>
      <path d="M4 10l3.5 3.5L16 5" />
    </>
  ),
  x: (
    <>
      <path d="M5 5l10 10M15 5L5 15" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="4.5" width="14" height="13" rx="1.5" />
      <path d="M3 8h14M7 3v3M13 3v3" />
    </>
  ),
  clock: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6v4l3 2" />
    </>
  ),
  user: (
    <>
      <circle cx="10" cy="7" r="3" />
      <path d="M3 17a7 7 0 0 1 14 0" />
    </>
  ),
  link: (
    <>
      <path d="M8 12l4-4M9 5l1-1a3 3 0 0 1 4 4l-1 1M11 15l-1 1a3 3 0 0 1-4-4l1-1" />
    </>
  ),
  info: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 13V9M10 7v.01" strokeLinecap="round" />
    </>
  ),
  sun: (
    <>
      <circle cx="10" cy="10" r="3.5" />
      <path d="M10 2v2M10 16v2M2 10h2M16 10h2M5 5L3.5 3.5M16.5 16.5L15 15M5 15l-1.5 1.5M16.5 3.5L15 5" />
    </>
  ),
  moon: (
    <>
      <path d="M16 12a7 7 0 1 1-9-9 5.5 5.5 0 0 0 9 9Z" />
    </>
  ),
  history: (
    <>
      <path d="M3 10a7 7 0 1 0 2-5L3 7" />
      <path d="M3 3v4h4" />
      <path d="M10 6v4l3 2" />
    </>
  ),

  // ─────── health-domain glyphs (used inside screens) ───────
  heart: (
    <>
      <path d="M3 8a4 4 0 0 1 7-2.5A4 4 0 0 1 17 8c0 4-7 9-7 9S3 12 3 8Z" />
    </>
  ),
  bed: (
    <>
      <path d="M2 14V6h6a4 4 0 0 1 4 4h6v4" />
      <path d="M2 14v3M18 14v3" />
      <circle cx="6" cy="11" r="1.5" />
    </>
  ),
  zap: (
    <>
      <path d="M11 2L4 12h5l-1 6 7-10h-5l1-6Z" />
    </>
  ),
  drop: (
    <>
      <path d="M10 2c0 5-5 7-5 11a5 5 0 0 0 10 0c0-4-5-6-5-11Z" />
    </>
  ),
  flame: (
    <>
      <path d="M10 2c0 3-3 4-3 8a3 3 0 0 0 6 0c0-2-1-3-1-4 0 0 4 2 4 6a6 6 0 0 1-12 0c0-5 6-7 6-10Z" />
    </>
  ),
  run: (
    <>
      <circle cx="13" cy="4" r="1.5" />
      <path d="M5 18l3-5 4-1-1-4 4 1 2 4M9 11L7 8l-3 1" />
    </>
  ),
  pill: (
    <>
      <rect x="2" y="7" width="16" height="6" rx="3" transform="rotate(-15 10 10)" />
      <path d="M7 6l6 8" transform="rotate(-15 10 10)" />
    </>
  ),
  fork: (
    <>
      <path d="M5 3v6a2 2 0 0 0 4 0V3M7 9v8" />
      <path d="M13 3v6c0 1 .5 1 1 1h0v7" />
    </>
  ),
  brain: (
    <>
      <path d="M7 4a3 3 0 0 0-3 3v2a3 3 0 0 0 0 4v2a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3v-2a3 3 0 0 0 0-4V7a3 3 0 0 0-3-3" />
      <path d="M10 4v12" />
    </>
  ),
  glass: (
    <>
      <path d="M5 3h10l-1 14H6L5 3Z" />
      <path d="M5.5 7h9" />
    </>
  ),
  cigarette: (
    <>
      <rect x="3" y="11" width="14" height="3" rx="0.5" />
      <path d="M5 5v3M7 5v3" />
    </>
  ),
};

export interface IconProps {
  name: string;
  className?: string;
  style?: CSSProperties;
}

/**
 * Renders a 20x20 stroke icon. `name` falls back to nothing if unknown so
 * a typo doesn't crash the render — it just shows an empty SVG. The
 * `cadence-ico` class applies the size/opacity rules from the page-scoped
 * stylesheet (see styles.tsx) so every icon site can layout-shift
 * consistently. The class is `cadence-` prefixed to avoid collision with
 * any global `.ico` rule from `app/globals.css`.
 */
export function Icon({ name, className = "", style = {} }: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`cadence-ico ${className}`}
      style={style}
    >
      {iconMap[name] || null}
    </svg>
  );
}
