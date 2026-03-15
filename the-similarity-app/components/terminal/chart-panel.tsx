"use client";
import { useEffect, useRef } from "react";
import { createChart, LineSeries, AreaSeries, type IChartApi, type ISeriesApi, type LineData, type AreaData } from "lightweight-charts";
import { useTerminal } from "../../lib/terminal-context";

/** Normalize `src` into the value range of `target` (preserving shape). */
function normalizeToRange(src: number[], target: number[]): number[] {
  if (src.length === 0 || target.length === 0) return [];
  const sMin = Math.min(...src);
  const sMax = Math.max(...src);
  const tMin = Math.min(...target);
  const tMax = Math.max(...target);
  const sRange = sMax - sMin || 1;
  const tRange = tMax - tMin || 1;
  return src.map((v) => tMin + ((v - sMin) / sRange) * tRange);
}

/**
 * Convert an index to a synthetic business-day string (YYYY-MM-DD).
 * Lightweight-charts needs real-looking dates, not raw numbers.
 */
function indexToDate(idx: number): string {
  const base = new Date(2020, 0, 1); // Jan 1, 2020
  const d = new Date(base.getTime() + idx * 86400000);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function toLineData(values: number[], offset = 0): LineData[] {
  return values.map((value, i) => ({
    time: indexToDate(offset + i) as unknown as LineData["time"],
    value,
  }));
}

function toAreaData(values: number[], offset = 0): AreaData[] {
  return values.map((value, i) => ({
    time: indexToDate(offset + i) as unknown as AreaData["time"],
    value,
  }));
}

const COLORS = {
  query: "#e8e9ed",
  match: "#818cf8",
  forecast: "#34d399",
  forecastFill: "rgba(52, 211, 153, 0.08)",
  trajectory: "#fbbf24",
  bg: "#08090d",
  grid: "rgba(255, 255, 255, 0.04)",
  border: "rgba(255, 255, 255, 0.06)",
  text: "#454857",
};

export function ChartPanel() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<{
    query?: ISeriesApi<"Line">;
    match?: ISeriesApi<"Line">;
    forecastP50?: ISeriesApi<"Line">;
    forecastP90?: ISeriesApi<"Area">;
    forecastP10?: ISeriesApi<"Area">;
    trajectory?: ISeriesApi<"Line">;
  }>({});

  const { state } = useTerminal();
  const sr = state.searchResponse;
  const data = state.dashboardData;

  // ── Resolve data ──
  let query: number[] = [];
  let bestMatch: number[] = [];
  let fP10: number[] = [];
  let fP50: number[] = [];
  let fP90: number[] = [];
  let chartTitle = "Price History";

  if (sr) {
    query = sr.queryValues;
    const topMatch = sr.matches[0];
    bestMatch = topMatch?.matchedSeries ?? [];
    if (sr.forecast) {
      const curves = sr.forecast.curves;
      const p50Raw = curves["50"] ?? [];
      const p10Raw = curves["10"] ?? [];
      const p90Raw = curves["90"] ?? [];
      const anchor = query.length > 0 ? query[query.length - 1] : 0;
      const toPrice = (ret: number) => anchor * (1 + ret);
      fP10 = p10Raw.length > 0 ? [anchor, ...p10Raw.map(toPrice)] : [];
      fP50 = p50Raw.length > 0 ? [anchor, ...p50Raw.map(toPrice)] : [];
      fP90 = p90Raw.length > 0 ? [anchor, ...p90Raw.map(toPrice)] : [];
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

  // ── Selected match overlay ──
  const highlightIdx = state.hoveredIdx ?? state.selectedIdx;
  const selectedMatch = highlightIdx !== null ? state.matches[highlightIdx] : null;
  const trajectory = selectedMatch?.forwardWindow ?? null;
  const anchor = query.length > 0 ? query[query.length - 1] : 0;
  const trajSeries = trajectory ? [anchor, ...trajectory.map((r) => anchor * (1 + r))] : [];

  // Selected match's matchedSeries (search mode)
  const selMatchSeries = sr && selectedMatch?.matchedSeries ? selectedMatch.matchedSeries : null;
  const matchToDisplay = selMatchSeries ?? bestMatch;

  // Normalize match to query range for shape comparison
  const normalizedMatch = matchToDisplay.length > 1 ? normalizeToRange(matchToDisplay, query) : [];

  const fStart = query.length - 1;

  // ── Create chart once ──
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { color: COLORS.bg },
        textColor: COLORS.text,
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: COLORS.grid },
        horzLines: { color: COLORS.grid },
      },
      crosshair: {
        vertLine: { color: "rgba(255,255,255,0.1)", width: 1, style: 2 },
        horzLine: { color: "rgba(255,255,255,0.1)", width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: COLORS.border,
        textColor: COLORS.text,
      },
      timeScale: {
        borderColor: COLORS.border,
        timeVisible: false,
        tickMarkFormatter: () => "",
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: true,
      handleScale: true,
    });
    chartRef.current = chart;

    // Forecast p90 area (upper bound)
    const p90Area = chart.addSeries(AreaSeries, {
      lineColor: "transparent",
      topColor: COLORS.forecastFill,
      bottomColor: "transparent",
      lineWidth: 1 as const,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
    });

    // Forecast p10 area (erase below lower bound)
    const p10Area = chart.addSeries(AreaSeries, {
      lineColor: "transparent",
      topColor: COLORS.bg,
      bottomColor: COLORS.bg,
      lineWidth: 1 as const,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
    });

    // Match line (normalized to overlay query)
    const matchLine = chart.addSeries(LineSeries, {
      color: COLORS.match,
      lineWidth: 1,
      lineStyle: 2, // dashed
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: false,
    });

    // Query line
    const queryLine = chart.addSeries(LineSeries, {
      color: COLORS.query,
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: false,
    });

    // Forecast p50 (median)
    const p50Line = chart.addSeries(LineSeries, {
      color: COLORS.forecast,
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: true,
    });

    // Trajectory overlay
    const trajLine = chart.addSeries(LineSeries, {
      color: COLORS.trajectory,
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: false,
    });

    seriesRefs.current = {
      query: queryLine,
      match: matchLine,
      forecastP50: p50Line,
      forecastP90: p90Area,
      forecastP10: p10Area,
      trajectory: trajLine,
    };

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Update data ──
  useEffect(() => {
    const s = seriesRefs.current;
    if (!s.query || query.length < 2) return;

    s.query.setData(toLineData(query));

    if (normalizedMatch.length > 1) {
      s.match?.setData(toLineData(normalizedMatch));
    } else {
      s.match?.setData([]);
    }

    if (fP50.length > 1) {
      s.forecastP50?.setData(toLineData(fP50, fStart));
    } else {
      s.forecastP50?.setData([]);
    }

    if (fP90.length > 1) {
      s.forecastP90?.setData(toAreaData(fP90, fStart));
    } else {
      s.forecastP90?.setData([]);
    }

    if (fP10.length > 1) {
      s.forecastP10?.setData(toAreaData(fP10, fStart));
    } else {
      s.forecastP10?.setData([]);
    }

    if (trajSeries.length > 1) {
      s.trajectory?.setData(toLineData(trajSeries, fStart));
    } else {
      s.trajectory?.setData([]);
    }

    chartRef.current?.timeScale().fitContent();
  }, [query, normalizedMatch, fP50, fP10, fP90, trajSeries, fStart]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Legend items ──
  const legendItems: { color: string; label: string }[] = [
    { color: COLORS.query, label: "Query" },
  ];
  if (normalizedMatch.length > 0) {
    const matchLabel = sr && highlightIdx !== null ? `Match #${highlightIdx + 1}` : "Best Match";
    legendItems.push({ color: COLORS.match, label: matchLabel });
  }
  if (fP50.length > 0) {
    legendItems.push({ color: COLORS.forecast, label: "Forecast" });
  }
  if (trajSeries.length > 0) {
    legendItems.push({ color: COLORS.trajectory, label: "Trajectory" });
  }

  const isLoading = query.length < 2;

  return (
    <div className="chart-container">
      {isLoading ? (
        <div className="empty-msg">Loading chart data…</div>
      ) : (
        <div className="chart-header">
          <span className="chart-title">{chartTitle}</span>
          <div className="chart-legend">
            {legendItems.map((item) => (
              <span key={item.label} className="chart-legend-item">
                <span className="chart-legend-dot" style={{ background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
        </div>
      )}
      <div ref={containerRef} style={{ flex: 1, minHeight: 0, position: "relative", display: isLoading ? "none" : "block" }} />
    </div>
  );
}
