"use client";
import { useTerminal } from "../../lib/terminal-context";
import { scalePoints, pointsToPath, areaPath } from "../../lib/chart-utils";

export function ChartPanel() {
  const { state } = useTerminal();
  const sr = state.searchResponse;
  const data = state.dashboardData;

  // ── Resolve data source: searchResponse > dashboardData ──
  let query: number[] = [];
  let bestMatch: number[] = [];
  let fP10: number[] = [];
  let fP50: number[] = [];
  let fP90: number[] = [];
  let chartTitle = "Price History";

  if (sr) {
    query = sr.queryValues;
    // Best match = top match's matchedSeries (if available)
    const topMatch = sr.matches[0];
    bestMatch = topMatch?.matchedSeries ?? [];
    // Forecast from search response
    if (sr.forecast) {
      const curves = sr.forecast.curves;
      // Curves keyed by percentile string ("10", "50", "90")
      const p50Raw = curves["50"] ?? [];
      const p10Raw = curves["10"] ?? [];
      const p90Raw = curves["90"] ?? [];
      // Anchor at last query value for continuity
      const anchor = query.length > 0 ? query[query.length - 1] : 0;
      fP10 = p10Raw.length > 0 ? [anchor, ...p10Raw] : [];
      fP50 = p50Raw.length > 0 ? [anchor, ...p50Raw] : [];
      fP90 = p90Raw.length > 0 ? [anchor, ...p90Raw] : [];
    }
    chartTitle = `Search Results · ${sr.matches.length} matches`;
  } else if (data) {
    const range = data.defaultRange;
    const view = data.views[range];
    query = view?.query || [];
    bestMatch = view?.bestMatch || [];
    const forecast = view?.forecast;
    if (forecast && query.length > 0) {
      const anchor = query[query.length - 1];
      fP10 = [anchor, ...forecast.p10];
      fP50 = [anchor, ...forecast.p50];
      fP90 = [anchor, ...forecast.p90];
    }
    chartTitle = `Price History · ${range}`;
  }

  if (query.length < 2) {
    return <div className="chart-container"><div className="empty-msg">Loading chart data…</div></div>;
  }

  // ── Selected match trajectory overlay ──
  const highlightIdx = state.hoveredIdx ?? state.selectedIdx;
  const selectedMatch = highlightIdx !== null ? state.matches[highlightIdx] : null;
  const trajectory = selectedMatch?.forwardWindow ?? null;

  const W = 760, H = 300;
  const pad = { top: 20, right: 20, bottom: 30, left: 50 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  // Trajectory anchored at last query value
  const anchor = query[query.length - 1];
  const trajSeries = trajectory ? [anchor, ...trajectory] : [];
  const fStart = query.length - 1;
  const totalSlots = query.length + Math.max(
    fP50.length > 0 ? fP50.length - 1 : 0,
    trajSeries.length > 0 ? trajSeries.length - 1 : 0,
  );

  // Global min/max including all series
  const allValues = [
    ...query, ...bestMatch,
    ...fP10, ...fP90,
    ...trajSeries,
  ];
  const minVal = Math.min(...allValues) - 1.5;
  const maxVal = Math.max(...allValues) + 1.5;

  const off = (p: { x: number; y: number }) => ({ x: p.x + pad.left, y: p.y + pad.top });
  const queryPts = scalePoints(query, 0, totalSlots, plotW, plotH, minVal, maxVal).map(off);
  const matchPts = bestMatch.length > 1
    ? scalePoints(bestMatch, 0, totalSlots, plotW, plotH, minVal, maxVal).map(off)
    : [];

  const p10Pts = fP10.length > 1 ? scalePoints(fP10, fStart, totalSlots, plotW, plotH, minVal, maxVal).map(off) : [];
  const p50Pts = fP50.length > 1 ? scalePoints(fP50, fStart, totalSlots, plotW, plotH, minVal, maxVal).map(off) : [];
  const p90Pts = fP90.length > 1 ? scalePoints(fP90, fStart, totalSlots, plotW, plotH, minVal, maxVal).map(off) : [];
  const trajPts = trajSeries.length > 1 ? scalePoints(trajSeries, fStart, totalSlots, plotW, plotH, minVal, maxVal).map(off) : [];

  const dividerX = ((query.length - 1) / Math.max(totalSlots - 1, 1)) * plotW + pad.left;
  const lastPt = p50Pts.length > 0 ? p50Pts[p50Pts.length - 1] : null;
  const lastVal = fP50.length > 0 ? fP50[fP50.length - 1] : null;

  // Grid
  const gridYs = Array.from({ length: 5 }, (_, i) => pad.top + (plotH / 4) * i);

  // Match highlight region (for non-search mode, approximate position)
  const hasHighlight = highlightIdx !== null && highlightIdx < state.matches.length;
  let hlX1 = 0, hlX2 = 0;
  if (hasHighlight && !sr) {
    const frac = (highlightIdx! + 1) / (state.matches.length + 1);
    hlX1 = Math.max(pad.left, pad.left + (frac - 0.06) * plotW);
    hlX2 = Math.min(pad.left + plotW, pad.left + (frac + 0.06) * plotW);
  }

  // Selected match's matchedSeries overlay (when in search mode, show matched pattern)
  const selMatchSeries = selectedMatch?.matchedSeries ?? null;
  const selMatchPts = selMatchSeries && selMatchSeries.length > 1
    ? scalePoints(selMatchSeries, 0, totalSlots, plotW, plotH, minVal, maxVal).map(off)
    : [];

  return (
    <div className="chart-container">
      <div className="chart-header">
        <span className="chart-title">{chartTitle}</span>
        <div className="chart-legend">
          <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--chart-query)" }} />Query</span>
          {matchPts.length > 0 && <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--chart-match)" }} />Best Match</span>}
          {p50Pts.length > 0 && <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--chart-forecast)" }} />Forecast</span>}
          {trajPts.length > 0 && <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "#fb923c" }} />Trajectory</span>}
          {selMatchPts.length > 0 && <span className="chart-legend-item"><span className="chart-legend-dot" style={{ background: "var(--chart-match)" }} />#{highlightIdx! + 1}</span>}
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
        {/* Match highlight region (dashboard mode) */}
        {hasHighlight && !sr && hlX2 > hlX1 && (
          <rect x={hlX1} y={pad.top} width={hlX2 - hlX1} height={plotH} className="chart-region-highlight" opacity={0.5} />
        )}
        {/* Forecast cone fill */}
        {p10Pts.length > 1 && p90Pts.length > 1 && (
          <path d={areaPath(p90Pts, p10Pts)} fill="url(#fc-grad)" />
        )}
        {/* Divider line between history and forecast */}
        {(p50Pts.length > 0 || trajPts.length > 0) && (
          <line x1={dividerX} y1={pad.top} x2={dividerX} y2={pad.top + plotH}
            stroke="var(--border-strong)" strokeWidth={1} strokeDasharray="4 3" />
        )}
        {/* Best match line */}
        {matchPts.length > 1 && <path d={pointsToPath(matchPts)} className="chart-line chart-line-match" />}
        {/* Selected match's matched series (different match, shown as overlay) */}
        {selMatchPts.length > 1 && sr && (
          <path d={pointsToPath(selMatchPts)} className="chart-line" stroke="var(--chart-match)" strokeWidth={1.5} strokeDasharray="5 3" opacity={0.7} />
        )}
        {/* Query line */}
        {queryPts.length > 1 && <path d={pointsToPath(queryPts)} className="chart-line chart-line-query" />}
        {/* Forecast median */}
        {p50Pts.length > 1 && <path d={pointsToPath(p50Pts)} className="chart-line chart-line-forecast" />}
        {/* Per-match trajectory overlay (forwardWindow) */}
        {trajPts.length > 1 && (
          <path d={pointsToPath(trajPts)} className="chart-line chart-line-trajectory" />
        )}
        {/* Forecast endpoint label */}
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
