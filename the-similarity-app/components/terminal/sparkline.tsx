"use client";

import { clampRatio } from "@/lib/chart-utils";

type SparklineProps = {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
};

export function Sparkline({
  data,
  width = 80,
  height = 24,
  color = "var(--chart-query)",
}: SparklineProps) {
  if (data.length < 2) return null;

  const padX = 1;
  const padY = 2;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const denominator = Math.max(data.length - 1, 1);

  const points = data
    .map((v, i) => {
      const x = padX + (i / denominator) * innerW;
      const y = padY + innerH - clampRatio(v, min, max) * innerH;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
