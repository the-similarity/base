/**
 * Lumen icon set — compact stroke icons matching the painterly inspo.
 *
 * Each entry in `iconMap` is a fragment of SVG <path>/<circle>/etc nodes
 * that get drawn inside a 20x20 viewBox. The wrapper <svg> applies a
 * consistent stroke-width / linecap / linejoin so every glyph reads as
 * the same family. To add an icon: add a new key to `iconMap` whose value
 * is the inner geometry only (no <svg> wrapper).
 *
 * Why a single component (not per-file SVGs): the design ships ~70 icons
 * that get tree-shaken to a few thousand bytes either way; co-locating in
 * one map makes the screen ports one-to-one with the JSX source and
 * avoids 70 separate imports across the page module.
 *
 * The `name` prop is a string for parity with the source design — a union
 * type would be safer but every screen passes literal strings, so any typo
 * would surface as an instantly-visible blank icon.
 */
import type { CSSProperties, JSX } from "react";

const iconMap: Record<string, JSX.Element> = {
  home: (
    <>
      <path d="M3 9.5L10 3l7 6.5V17a1 1 0 0 1-1 1h-3v-5H7v5H4a1 1 0 0 1-1-1V9.5Z" />
    </>
  ),
  wallet: (
    <>
      <rect x="2.5" y="5" width="15" height="11" rx="2" />
      <path d="M14 10.5h3M2.5 8h13" />
    </>
  ),
  list: (
    <>
      <path d="M3 5h14M3 10h14M3 15h14" />
    </>
  ),
  pie: (
    <>
      <path d="M10 3v7l6 3a7 7 0 1 1-6-10Z" />
      <path d="M11 3a7 7 0 0 1 6 6h-6V3Z" />
    </>
  ),
  target: (
    <>
      <circle cx="10" cy="10" r="7" />
      <circle cx="10" cy="10" r="3.5" />
      <circle cx="10" cy="10" r="0.8" fill="currentColor" />
    </>
  ),
  trend: (
    <>
      <path d="M3 13l4-4 3 3 7-7" />
      <path d="M12 5h5v5" />
    </>
  ),
  flow: (
    <>
      <path d="M3 7h10a3 3 0 0 1 0 6H7a3 3 0 0 0 0 6h10" />
      <path d="M14 4l3 3-3 3M6 16l-3 3 3 3" transform="translate(0 -3)" />
    </>
  ),
  repeat: (
    <>
      <path d="M4 8a4 4 0 0 1 4-4h7l-2-2m2 2l-2 2" />
      <path d="M16 12a4 4 0 0 1-4 4H5l2 2m-2-2l2-2" />
    </>
  ),
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
  upload: (
    <>
      <path d="M10 17V7M5 11l5-4 5 4M3 3h14" />
    </>
  ),
  filter: (
    <>
      <path d="M3 5h14l-5 6v5l-4 2v-7L3 5Z" />
    </>
  ),
  sort: (
    <>
      <path d="M5 4v12M5 16l-2-2M5 16l2-2M13 16V4M13 4l-2 2M13 4l2 2" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="10" r="1.2" fill="currentColor" />
      <circle cx="10" cy="10" r="1.2" fill="currentColor" />
      <circle cx="15" cy="10" r="1.2" fill="currentColor" />
    </>
  ),
  moreV: (
    <>
      <circle cx="10" cy="5" r="1.2" fill="currentColor" />
      <circle cx="10" cy="10" r="1.2" fill="currentColor" />
      <circle cx="10" cy="15" r="1.2" fill="currentColor" />
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
  tag: (
    <>
      <path d="M3 3h7l7 7-7 7-7-7V3Z" />
      <circle cx="6.5" cy="6.5" r="1" fill="currentColor" />
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
  note: (
    <>
      <path d="M4 3h9l3 3v11H4V3Z" />
      <path d="M13 3v3h3" />
      <path d="M7 9h6M7 12h6M7 15h4" />
    </>
  ),
  user: (
    <>
      <circle cx="10" cy="7" r="3" />
      <path d="M3 17a7 7 0 0 1 14 0" />
    </>
  ),
  paperclip: (
    <>
      <path d="M14 9l-5.5 5.5a3.5 3.5 0 0 1-5-5L9 4a2.5 2.5 0 0 1 3.5 3.5L7 13" />
    </>
  ),
  link: (
    <>
      <path d="M8 12l4-4M9 5l1-1a3 3 0 0 1 4 4l-1 1M11 15l-1 1a3 3 0 0 1-4-4l1-1" />
    </>
  ),
  star: (
    <>
      <path d="M10 2.5l2.4 5 5.6.8-4 3.9.9 5.6-4.9-2.6-4.9 2.6.9-5.6-4-3.9 5.6-.8L10 2.5Z" />
    </>
  ),
  eye: (
    <>
      <path d="M2 10s3-5.5 8-5.5S18 10 18 10s-3 5.5-8 5.5S2 10 2 10Z" />
      <circle cx="10" cy="10" r="2.5" />
    </>
  ),
  eyeOff: (
    <>
      <path d="M3 3l14 14M9 5.5a8 8 0 0 1 1 0c5 0 8 5 8 5a13 13 0 0 1-2 2.5M5 7s-2 1.5-3 3c0 0 3 5.5 8 5.5 1.5 0 2.8-.5 4-1.2" />
    </>
  ),
  lock: (
    <>
      <rect x="4" y="9" width="12" height="8" rx="1.5" />
      <path d="M7 9V6.5a3 3 0 1 1 6 0V9" />
    </>
  ),
  bank: (
    <>
      <path d="M3 8h14M2 8L10 3l8 5M5 8v7M9 8v7M11 8v7M15 8v7M3 17h14" />
    </>
  ),
  card: (
    <>
      <rect x="2.5" y="5" width="15" height="11" rx="2" />
      <path d="M2.5 9h15M5 13h3" />
    </>
  ),
  dollar: (
    <>
      <path d="M10 3v14M13 6.5C13 5 11.5 4 10 4S7 5 7 6.5 8.5 9 10 9s3 1 3 2.5S11.5 14 10 14 7 13 7 11.5" />
    </>
  ),
  pause: (
    <>
      <path d="M7 4v12M13 4v12" />
    </>
  ),
  flame: (
    <>
      <path d="M10 2c0 3-3 4-3 8a3 3 0 0 0 6 0c0-2-1-3-1-4 0 0 4 2 4 6a6 6 0 0 1-12 0c0-5 6-7 6-10Z" />
    </>
  ),
  leaf: (
    <>
      <path d="M3 17c0-8 6-14 14-14 0 0 0 14-7 14-3 0-7-2-7-7" />
      <path d="M3 17l8-8" />
    </>
  ),
  coffee: (
    <>
      <path d="M3 8h12v5a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V8Z" />
      <path d="M15 9h2a2 2 0 0 1 0 4h-2" />
      <path d="M6 4l-1 2M9 4l-1 2M12 4l-1 2" />
    </>
  ),
  cart: (
    <>
      <circle cx="8" cy="17" r="1" />
      <circle cx="14" cy="17" r="1" />
      <path d="M2 3h2l3 10h10l2-7H6" />
    </>
  ),
  car: (
    <>
      <path d="M3 14V9l2-4h10l2 4v5" />
      <circle cx="6" cy="14" r="1.5" />
      <circle cx="14" cy="14" r="1.5" />
      <path d="M3 12h14" />
    </>
  ),
  music: (
    <>
      <circle cx="6" cy="15" r="2" />
      <circle cx="15" cy="13" r="2" />
      <path d="M8 15V4l9-2v11" />
    </>
  ),
  gym: (
    <>
      <path d="M3 8v4M5 6v8M9 4v12M15 4v12M11 6v8M17 8v4" />
    </>
  ),
  play: (
    <>
      <polygon points="6,4 16,10 6,16" fill="currentColor" />
    </>
  ),
  house: (
    <>
      <path d="M3 9.5L10 3l7 6.5V17a1 1 0 0 1-1 1h-3v-5H7v5H4a1 1 0 0 1-1-1V9.5Z" />
    </>
  ),
  book: (
    <>
      <path d="M3 4h6a3 3 0 0 1 3 3v10a2 2 0 0 0-2-2H3V4Z" />
      <path d="M17 4h-6a3 3 0 0 0-3 3v10a2 2 0 0 1 2-2h7V4Z" />
    </>
  ),
  plane: (
    <>
      <path d="M2 11l16-7-7 16-2-7-7-2Z" />
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
  zap: (
    <>
      <path d="M11 2L4 12h5l-1 6 7-10h-5l1-6Z" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="6" height="6" rx="1" />
      <rect x="11" y="3" width="6" height="6" rx="1" />
      <rect x="3" y="11" width="6" height="6" rx="1" />
      <rect x="11" y="11" width="6" height="6" rx="1" />
    </>
  ),
  receipt: (
    <>
      <path d="M5 2h10v16l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5L3 18V2h2Z" />
      <path d="M7 6h6M7 9h6M7 12h4" />
    </>
  ),
  coins: (
    <>
      <ellipse cx="7" cy="6" rx="4.5" ry="2" />
      <path d="M2.5 6v3c0 1.1 2 2 4.5 2s4.5-.9 4.5-2V6" />
      <ellipse cx="13" cy="13" rx="4.5" ry="2" />
      <path d="M8.5 13v3c0 1.1 2 2 4.5 2s4.5-.9 4.5-2v-3" />
    </>
  ),
  pin: (
    <>
      <path d="M10 2v6l3 3-1 2H8l-1-2 3-3V2Z" />
      <path d="M10 13v5" />
    </>
  ),
  archive: (
    <>
      <rect x="3" y="3" width="14" height="4" rx="1" />
      <path d="M4 7v9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7" />
      <path d="M8 11h4" />
    </>
  ),
  folder: (
    <>
      <path d="M3 5a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5Z" />
    </>
  ),
  palette: (
    <>
      <path d="M10 3a7 7 0 1 0 0 14c1 0 1.5-1 1-2-.5-1 0-2 1-2h2a3 3 0 0 0 3-3 7 7 0 0 0-7-7Z" />
      <circle cx="6.5" cy="9" r="0.8" fill="currentColor" />
      <circle cx="9" cy="6" r="0.8" fill="currentColor" />
      <circle cx="13" cy="6.5" r="0.8" fill="currentColor" />
    </>
  ),
  refresh: (
    <>
      <path d="M3 10a7 7 0 0 1 12-5l2-2v5h-5" />
      <path d="M17 10a7 7 0 0 1-12 5l-2 2v-5h5" />
    </>
  ),
  history: (
    <>
      <path d="M3 10a7 7 0 1 0 2-5L3 7" />
      <path d="M3 3v4h4" />
      <path d="M10 6v4l3 2" />
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
 * a typo doesn't crash the render — it just shows an empty SVG. The "ico"
 * class applies the size/opacity rules from the page-scoped stylesheet
 * (see styles.tsx) so every icon site can layout-shift consistently.
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
      className={`ico ${className}`}
      style={style}
    >
      {iconMap[name] || null}
    </svg>
  );
}
