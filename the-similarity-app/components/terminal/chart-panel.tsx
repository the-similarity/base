"use client";
import { useTerminal } from "../../lib/terminal-context";
import { scalePoints, pointsToPath, areaPath } from "../../lib/chart-utils";

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
  const forecast = view?.forecast;

  if (query.length < 2) {
    return <div className="chart-container"><div className="empty-msg">Not enough data to chart.</div></div>;
  }

  const W = 760, H = 300;
  const pad = { top: 20, right: 20, bottom: 30, left: 50 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  // Forecast series anchored to last query value for continuity
  const anchor = query[query.length - 1];
  const fP10 = forecast ? [anchor, ...forecast.p10] : [];
  const fP50 = forecast ? [anchor, ...forecast.p50] : [];
  const fP90 = forecast ? [anchor, ...forecast.p90] : [];
  const totalSlots = query.length + (forecast ? forecast.p50.length : 0);

  // Global min/max including forecast bands
  const allValues = [...query, ...bestMatch, ...fP10, ...fP90];
  const minVal = Math.min(...allValues) - 1.5;
  const maxVal = Math.max(...allValues) + 1.5;

  const off = (p: { x: number; y: number }) => ({ x: p.x + pad.left, y: p.y + pad.top });
  const queryPts = scalePoints(query, 0, totalSlots, plotW, plotH, minVal, maxVal).map(off);
  const matchPts = bestMatch.length > 1
    ? scalePoints(bestMatch, 0, totalSlots, plotW, plotH, minVal, maxVal).map(off)
    : [];

  const fStart = query.length - 1;
  const p10Pts = fP10.length > 1 ? scalePoints(fP10, fStart, totalSlots, plotW, plotH, minVal, maxVal).map(off) : [];
  const p50Pts = fP50.length > 1 ? scalePoints(fP50, fStart, totalSlots, plotW, plotH, minVal, maxVal).map(off) : [];
  const p90Pts = fP90.length > 1 ? scalePoints(fP90, fStart, totalSlots, plotW, plotH, minVal, maxVal).map(off) : [];

  const dividerX = ((query.length - 1) / Math.max(totalSlots - 1, 1)) * plotW + pad.left;
  const lastPt = p50Pts.length > 0 ? p50Pts[p50Pts.length - 1] : null;
  const lastVal = fP50.length > 0 ? fP50[fP50.length - 1] : null;

  // Grid
  const gridYs = Array.from({ length: 5 }, (_, i) => pad.top + (plotH / 4) * i);

  // Match highlight
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
          {p50Pts.length > 0 && <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--chart-forecast)" }} />Forecast</span>}
          {hasHighlight && <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--accent)" }} />#{highlightIdx! + 1}</span>}
        </div>
      </div>
      <svg className="chart-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="fc-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-forecast)" stopOpacity="0.15" />
            <stop offset="100%" stopColor="var(--chart-forecast)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {gridYs.map((y, i) => <line key={i} x1={pad.left} y1={y} x2={W - pad.right} y2={y} className="chart-grid-line" />)}
        {hasHighlight && hlX2 > hlX1 && (
          <rect x={hlX1} y={pad.top} width={hlX2 - hlX1} height={plotH} className="chart-region-highlight" opacity={0.5} />
        )}
        {p10Pts.length > 1 && p90Pts.length > 1 && (
          <path d={areaPath(p90Pts, p10Pts)} fill="url(#fc-grad)" />
        )}
        {p50Pts.length > 0 && (
          <line x1={dividerX} y1={pad.top} x2={dividerX} y2={pad.top + plotH}
            stroke="var(--border-strong)" strokeWidth={1} strokeDasharray="4 3" />
        )}
        {matchPts.length > 1 && <path d={pointsToPath(matchPts)} className="chart-line chart-line-match" />}
        {queryPts.length > 1 && <path d={pointsToPath(queryPts)} className="chart-line chart-line-query" />}
        {p50Pts.length > 1 && <path d={pointsToPath(p50Pts)} className="chart-line chart-line-forecast" />}
        {lastPt && lastVal !== null && (
          <>
            <circle cx={lastPt.x} cy={lastPt.y} r={3} fill="var(--chart-forecast)" />
            <rect x={lastPt.x + 6} y={lastPt.y - 10} width={44} height={18} rx={3}
              fill="var(--bg-elevated)" stroke="var(--border-strong)" strokeWidth={0.5} />
            <text x={lastPt.x + 28} y={lastPt.y + 2} textAnchor="middle" fill="var(--chart-forecast)"
              style={{ fontSize: 10, fontWeight: 600, fontFamily: "var(--font-mono)" }}>
              {lastVal.toFixed(1)}
            </text>
          </>
        )}
        <text x={pad.left - 8} y={pad.top + 4} className="chart-axis-label" textAnchor="end">H</text>
        <text x={pad.left - 8} y={H - pad.bottom + 4} className="chart-axis-label" textAnchor="end">L</text>
      </svg>
    </div>
  );
}
