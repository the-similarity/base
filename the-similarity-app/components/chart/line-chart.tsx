"use client";

/**
 * LineChart — minimal, reusable SVG line chart.
 *
 * Takes a flat `data: number[]` array and renders a responsive SVG polyline
 * with optional grid lines and axis labels. Designed for the editorial "deck"
 * theme: monochrome ink line on an off-white surface, quiet grid, mono labels.
 *
 * The chart auto-scales Y to the data range with a small padding factor so
 * the line never touches the top/bottom edges. X is evenly spaced across
 * the viewBox width.
 *
 * Usage:
 *   <LineChart data={[1, 2, 3, 2.5, 4]} />
 *   <LineChart data={prices} width={600} height={200} color="var(--positive)" />
 */

interface LineChartProps {
  /** Array of numeric values to plot (Y axis). X is evenly spaced. */
  data: number[];
  /** SVG viewBox width in virtual units (default 600). */
  width?: number;
  /** SVG viewBox height in virtual units (default 200). */
  height?: number;
  /** Stroke color for the line (default: var(--chart-query) = #1a1a1a). */
  color?: string;
  /** Whether to render horizontal grid lines (default true). */
  showGrid?: boolean;
  /** Optional accessible label for the SVG element. */
  label?: string;
}

export function LineChart({
  data,
  width = 600,
  height = 200,
  color = "var(--chart-query)",
  showGrid = true,
  label = "Line chart",
}: LineChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="line-chart-empty">
        <span className="line-chart-empty__text">No data</span>
      </div>
    );
  }

  // Compute Y bounds with a small padding so the line doesn't hug edges.
  const yMin = Math.min(...data);
  const yMax = Math.max(...data);
  const yRange = yMax - yMin || 1; // avoid division by zero for flat data
  const padding = yRange * 0.1;
  const scaledMin = yMin - padding;
  const scaledMax = yMax + padding;
  const scaledRange = scaledMax - scaledMin;

  // Map data indices to SVG coordinates.
  // X: evenly spaced across [0, width].
  // Y: inverted (SVG y=0 is top) and scaled to [0, height].
  const points = data.map((value, i) => {
    const x = data.length === 1 ? width / 2 : (i / (data.length - 1)) * width;
    const y = height - ((value - scaledMin) / scaledRange) * height;
    return { x, y };
  });

  // Build the SVG polyline path string.
  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(" ");

  // Grid lines at 25%, 50%, 75% of height.
  const gridRatios = [0.25, 0.5, 0.75];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="line-chart-svg"
      role="img"
      aria-label={label}
      preserveAspectRatio="none"
    >
      {showGrid &&
        gridRatios.map((ratio) => (
          <line
            key={ratio}
            x1="0"
            x2={width}
            y1={height * ratio}
            y2={height * ratio}
            className="chart-grid-line"
          />
        ))}
      <path d={pathD} className="chart-line" style={{ stroke: color }} />
      {/* End-point dot */}
      <circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r="3"
        fill={color}
      />
    </svg>
  );
}
