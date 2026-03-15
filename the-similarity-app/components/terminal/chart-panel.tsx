"use client";
import { useTerminal } from "../../lib/terminal-context";
import { scalePoints, pointsToPath } from "../../lib/chart-utils";

export function ChartPanel() {
  const { state } = useTerminal();
  const data = state.dashboardData;

  if (!data) {
    return <div className="chart-container"><div className="empty-msg">Loading chart data…</div></div>;
  }

  const range = data.defaultRange;
  const view = data.views[range];
  const query = view?.query || [];
  const bestMatch = view?.bestMatch || [];

  if (query.length < 2) {
    return <div className="chart-container"><div className="empty-msg">Not enough data to chart.</div></div>;
  }

  const W = 760, H = 300;
  const pad = { top: 20, right: 20, bottom: 30, left: 50 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  // Find global min/max across all series
  const allValues = [...query, ...bestMatch];
  const minVal = Math.min(...allValues);
  const maxVal = Math.max(...allValues);

  const totalSlots = query.length;

  // Scale points using chart-utils
  const queryPts = scalePoints(query, 0, totalSlots, plotW, plotH, minVal, maxVal)
    .map(p => ({ x: p.x + pad.left, y: p.y + pad.top }));
  const matchPts = bestMatch.length > 1
    ? scalePoints(bestMatch, 0, totalSlots, plotW, plotH, minVal, maxVal)
        .map(p => ({ x: p.x + pad.left, y: p.y + pad.top }))
    : [];

  // Grid
  const gridLines = 5;
  const gridYs = Array.from({ length: gridLines }, (_, i) => pad.top + (plotH / (gridLines - 1)) * i);

  // Highlight
  const highlightIdx = state.hoveredIdx ?? state.selectedIdx;
  const hasHighlight = highlightIdx !== null && highlightIdx < state.matches.length;
  let hlX1 = 0, hlX2 = 0;
  if (hasHighlight) {
    const frac = (highlightIdx! + 1) / (state.matches.length + 1);
    hlX1 = Math.max(pad.left, pad.left + (frac - 0.06) * plotW);
    hlX2 = Math.min(pad.left + plotW, pad.left + (frac + 0.06) * plotW);
  }

  return (
    <div className="chart-container">
      <div className="chart-header">
        <span className="chart-title">Price History · {range}</span>
        <div className="chart-legend">
          <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--chart-query)" }} />Query</span>
          <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--chart-match)" }} />Best Match</span>
          {hasHighlight && <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--accent)" }} />#{highlightIdx! + 1}</span>}
        </div>
      </div>
      <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {gridYs.map((y, i) => <line key={i} x1={pad.left} y1={y} x2={W - pad.right} y2={y} className="chart-grid-line" />)}
        {hasHighlight && hlX2 > hlX1 && (
          <rect x={hlX1} y={pad.top} width={hlX2 - hlX1} height={plotH} className="chart-region-highlight" opacity={0.5} />
        )}
        {matchPts.length > 1 && <path d={pointsToPath(matchPts)} className="chart-line chart-line-match" />}
        {queryPts.length > 1 && <path d={pointsToPath(queryPts)} className="chart-line chart-line-query" />}
        <text x={pad.left - 8} y={pad.top + 4} className="chart-axis-label" textAnchor="end">H</text>
        <text x={pad.left - 8} y={H - pad.bottom + 4} className="chart-axis-label" textAnchor="end">L</text>
      </svg>
    </div>
  );
}
