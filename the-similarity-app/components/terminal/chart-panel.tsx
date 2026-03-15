"use client";
import { useTerminal } from "../../lib/terminal-context";
import { scalePoints, pointsToPath } from "../../lib/chart-utils";

export function ChartPanel() {
  const { state } = useTerminal();

  const data = state.dashboardData;
  if (!data) {
    return (
      <div className="chart-container">
        <div className="empty-msg">Loading chart data…</div>
      </div>
    );
  }

  const query = data.query || [];
  const bestMatch = data.bestMatch || [];

  const W = 760;
  const H = 300;
  const pad = { top: 20, right: 20, bottom: 30, left: 50 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  // Scale data
  const queryPts = query.length > 1
    ? scalePoints(query, plotW, plotH).map(([x, y]) => [x + pad.left, y + pad.top] as [number, number])
    : [];
  const matchPts = bestMatch.length > 1
    ? scalePoints(bestMatch, plotW, plotH).map(([x, y]) => [x + pad.left, y + pad.top] as [number, number])
    : [];

  // Grid lines
  const gridLines = 5;
  const gridYs = Array.from({ length: gridLines }, (_, i) => pad.top + (plotH / (gridLines - 1)) * i);

  // Highlight region for hovered/selected match
  const highlightIdx = state.hoveredIdx ?? state.selectedIdx;
  const highlightMatch = highlightIdx !== null ? state.matches[highlightIdx] : null;

  let highlightX1 = 0;
  let highlightX2 = 0;
  if (highlightMatch && query.length > 0) {
    const totalBars = query.length;
    highlightX1 = pad.left + (highlightMatch.start_idx / totalBars) * plotW;
    highlightX2 = pad.left + (highlightMatch.end_idx / totalBars) * plotW;
    // Clamp to visible area
    highlightX1 = Math.max(pad.left, Math.min(highlightX1, pad.left + plotW));
    highlightX2 = Math.max(pad.left, Math.min(highlightX2, pad.left + plotW));
  }

  return (
    <div className="chart-container">
      <div className="chart-header">
        <span className="chart-title">Price History</span>
        <div className="chart-legend">
          <span className="chart-legend-item">
            <span className="chart-legend-dot" style={{ background: "var(--chart-query)" }} />
            Query
          </span>
          <span className="chart-legend-item">
            <span className="chart-legend-dot" style={{ background: "var(--chart-match)" }} />
            Best Match
          </span>
          {highlightMatch && (
            <span className="chart-legend-item">
              <span className="chart-legend-dot" style={{ background: "var(--accent)" }} />
              #{(highlightIdx ?? 0) + 1} highlighted
            </span>
          )}
        </div>
      </div>

      <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {/* Grid */}
        {gridYs.map((y, i) => (
          <line key={i} x1={pad.left} y1={y} x2={W - pad.right} y2={y} className="chart-grid-line" />
        ))}

        {/* Match region highlight */}
        {highlightMatch && highlightX2 > highlightX1 && (
          <rect
            x={highlightX1}
            y={pad.top}
            width={highlightX2 - highlightX1}
            height={plotH}
            className="chart-region-highlight"
          />
        )}

        {/* Match line */}
        {matchPts.length > 1 && (
          <path d={pointsToPath(matchPts)} className="chart-line chart-line-match" />
        )}

        {/* Query line */}
        {queryPts.length > 1 && (
          <path d={pointsToPath(queryPts)} className="chart-line chart-line-query" />
        )}

        {/* Axis labels */}
        <text x={pad.left - 8} y={pad.top + 4} className="chart-axis-label" textAnchor="end">H</text>
        <text x={pad.left - 8} y={H - pad.bottom + 4} className="chart-axis-label" textAnchor="end">L</text>
        <text x={pad.left} y={H - 8} className="chart-axis-label">0</text>
        <text x={W - pad.right} y={H - 8} className="chart-axis-label" textAnchor="end">{query.length}</text>
      </svg>
    </div>
  );
}
