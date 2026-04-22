"use client";

/**
 * 9-axis radar chart for visualizing lens scores.
 *
 * Draws concentric grid polygons at 25/50/75/100% levels, radial axes
 * from center to each vertex, and a filled data polygon showing the
 * current lens score profile. Labels are positioned outside the axes
 * with automatic text-anchor based on angular position.
 */

import { LENS_DEFS, LensScores } from "../../lib/data";

interface LensRadarProps {
  /** Object with per-lens scores (0..1) */
  lenses: LensScores;
  /** SVG size in px (square) */
  size?: number;
}

export function LensRadar({ lenses, size = 240 }: LensRadarProps) {
  /*
   * Horizontal padding reserved for outer labels. Words like
   * "Decomposition" (the longest lens label) are ~82px wide at the
   * 9px mono font; we reserve 60px on each side so the text never
   * clips off the viewBox even in tight right-panel widths. The
   * viewBox itself is widened by 2*LABEL_PAD so the polygon stays
   * centered in a true square on the inside while labels sit in
   * the padding strip outside it.
   */
  const LABEL_PAD = 60;
  const RADIUS_INSET = 18;
  const LABEL_GAP = 12;

  const vbW = size + LABEL_PAD * 2;
  const vbH = size;
  const cx = vbW / 2;
  const cy = vbH / 2;
  const r = size / 2 - RADIUS_INSET;
  const n = LENS_DEFS.length;

  // Compute positions for each lens axis
  const points = LENS_DEFS.map((def, i) => {
    const ang = -Math.PI / 2 + (i / n) * 2 * Math.PI;
    const v = lenses[def.key] ?? 0;
    return {
      x: cx + Math.cos(ang) * r * v,
      y: cy + Math.sin(ang) * r * v,
      ax: cx + Math.cos(ang) * r,
      ay: cy + Math.sin(ang) * r,
      lx: cx + Math.cos(ang) * (r + LABEL_GAP),
      ly: cy + Math.sin(ang) * (r + LABEL_GAP),
      label: def.name,
      anchor: Math.abs(Math.cos(ang)) < 0.25 ? "middle" as const : (Math.cos(ang) > 0 ? "start" as const : "end" as const),
    };
  });

  const gridLevels = [0.25, 0.5, 0.75, 1];

  return (
    <svg
      className="lens-radar"
      viewBox={`0 0 ${vbW} ${vbH}`}
      width="100%"
      height={size}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Concentric grid polygons */}
      {gridLevels.map((lvl, gi) => {
        const pts = LENS_DEFS.map((_, i) => {
          const ang = -Math.PI / 2 + (i / n) * 2 * Math.PI;
          return `${cx + Math.cos(ang) * r * lvl},${cy + Math.sin(ang) * r * lvl}`;
        }).join(" ");
        return <polygon key={gi} className="grid-poly" points={pts} />;
      })}

      {/* Radial axis lines */}
      {points.map((p, i) => <line key={i} className="axis" x1={cx} y1={cy} x2={p.ax} y2={p.ay} />)}

      {/* Data polygon fill + stroke */}
      <polygon className="data-poly" points={points.map(p => `${p.x},${p.y}`).join(" ")} />

      {/* Data dots at each axis */}
      {points.map((p, i) => <circle key={i} className="data-dot" cx={p.x} cy={p.y} r="2.5" />)}

      {/* Axis labels */}
      {points.map((p, i) => (
        <text key={i} className="axis-label" x={p.lx} y={p.ly + 3} textAnchor={p.anchor}>{p.label}</text>
      ))}
    </svg>
  );
}
