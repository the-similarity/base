"use client";

/**
 * Tiny sparkline SVG component for analog cards.
 *
 * Renders a minimal line chart with an optional vertical split line
 * that divides the "match window" portion from the "what happened after"
 * portion. The highlight prop (0..1) controls how much of the right
 * side is considered the "after" region.
 */

interface SparklineProps {
  /** Array of numeric values to plot */
  values: number[];
  /** SVG width in px */
  width?: number;
  /** SVG height in px */
  height?: number;
  /** Fraction (0..1) of the right side to mark as "after" with a dashed divider */
  highlight?: number;
}

export function Sparkline({ values, width = 80, height = 22, highlight = 0 }: SparklineProps) {
  if (!values || values.length < 2) return null;

  const min = Math.min(...values), max = Math.max(...values);
  const rng = max - min || 1;
  const xOf = (i: number) => (i / (values.length - 1)) * (width - 2) + 1;
  const yOf = (v: number) => height - 1 - ((v - min) / rng) * (height - 2);
  const d = values.map((v, i) => `${i ? "L" : "M"} ${xOf(i).toFixed(1)} ${yOf(v).toFixed(1)}`).join(" ");

  // Split index: where the "after" portion begins
  const splitIdx = Math.max(0, Math.floor(values.length * (1 - highlight)));

  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <line x1={xOf(splitIdx)} x2={xOf(splitIdx)} y1={1} y2={height - 1}
        stroke="var(--rule-strong)" strokeWidth="1" strokeDasharray="2 2" />
      <path d={d} fill="none" stroke="var(--ink-2)" strokeWidth="1.1" />
    </svg>
  );
}
