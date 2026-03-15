"use client";
import { scalePoints, pointsToPath } from "../../lib/chart-utils";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}

export function Sparkline({ data, width = 80, height = 20, color }: SparklineProps) {
  if (!data || data.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" />;
  }

  const pad = 1;
  const pts = scalePoints(data, width - pad * 2, height - pad * 2);
  const shifted = pts.map(([x, y]) => [x + pad, y + pad] as [number, number]);
  const d = pointsToPath(shifted);

  const strokeColor = color || "var(--chart-query)";

  return (
    <svg width={width} height={height} aria-hidden="true" style={{ display: "block" }}>
      <path d={d} fill="none" stroke={strokeColor} strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
