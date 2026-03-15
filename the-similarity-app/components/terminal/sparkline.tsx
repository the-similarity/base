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
  const w = width - pad * 2;
  const h = height - pad * 2;
  const minVal = Math.min(...data);
  const maxVal = Math.max(...data);
  const pts = scalePoints(data, 0, data.length, w, h, minVal, maxVal)
    .map(p => ({ x: p.x + pad, y: p.y + pad }));
  const d = pointsToPath(pts);
  const strokeColor = color || "var(--chart-query)";

  return (
    <svg width={width} height={height} aria-hidden="true" style={{ display: "block" }}>
      <path d={d} fill="none" stroke={strokeColor} strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
