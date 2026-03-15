"use client";
import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  LineSeries,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type CandlestickData,
} from "lightweight-charts";
import { useTerminal, type ChartMode } from "../../lib/terminal-context";

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

function indexToDate(idx: number): string {
  const base = new Date(2020, 0, 1);
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

function toCandleData(
  open: number[],
  high: number[],
  low: number[],
  close: number[],
  offset = 0,
): CandlestickData[] {
  return close.map((_, i) => ({
    time: indexToDate(offset + i) as unknown as CandlestickData["time"],
    open: open[i],
    high: high[i],
    low: low[i],
    close: close[i],
  }));
}

const COLORS = {
  query: "#e8e9ed",
  match: "#818cf8",
  matchContinuation: "#a78bfa", // lighter purple for continuation
  bg: "#08090d",
  bgLight: "#f8f9fa",
  grid: "rgba(255, 255, 255, 0.04)",
  gridLight: "rgba(0, 0, 0, 0.06)",
  border: "rgba(255, 255, 255, 0.06)",
  borderLight: "rgba(0, 0, 0, 0.1)",
  text: "#454857",
  textLight: "#6b7280",
  candleUp: "#34d399",
  candleDown: "#f87171",
};

export function ChartPanel() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<{
    queryLine?: ISeriesApi<"Line">;
    queryCandle?: ISeriesApi<"Candlestick">;
    match?: ISeriesApi<"Line">;
    continuation?: ISeriesApi<"Line">;
  }>({});

  const { state, dispatch } = useTerminal();
  const sr = state.searchResponse;
  const data = state.dashboardData;
  const ohlc = state.ohlcData;
  const chartMode = state.chartMode;
  const isDark = state.theme === "dark";

  // ── Resolve data ──
  let query: number[] = [];
  let bestMatch: number[] = [];
  let chartTitle = "Price History";

  if (sr) {
    query = sr.queryValues;
    const topMatch = sr.matches[0];
    bestMatch = topMatch?.matchedSeries ?? [];
    chartTitle = `Search Results · ${sr.matches.length} matches`;
  } else if (data) {
    const range = data.defaultRange;
    const view = data.views[range];
    query = view?.query || [];
    bestMatch = view?.bestMatch || [];
    chartTitle = `Price History · ${range}`;
  }

  // ── Selected match overlay ──
  const highlightIdx = state.hoveredIdx ?? state.selectedIdx;
  const selectedMatch = highlightIdx !== null ? state.matches[highlightIdx] : null;

  // Match series: use selected match if in search mode, else top match
  const selMatchSeries = sr && selectedMatch?.matchedSeries ? selectedMatch.matchedSeries : null;
  const matchToDisplay = selMatchSeries ?? bestMatch;
  const normalizedMatch = matchToDisplay.length > 1 ? normalizeToRange(matchToDisplay, query) : [];

  // Continuation: what actually happened after the match (forwardWindow)
  // This replaces the old green forecast — shows the real historical continuation
  const forwardWindow = selectedMatch?.forwardWindow ?? (sr?.matches[0]?.forwardWindow ?? null);
  const anchor = query.length > 0 ? query[query.length - 1] : 0;
  const continuationSeries = forwardWindow
    ? [anchor, ...forwardWindow.map((r) => anchor * (1 + r))]
    : [];

  const fStart = query.length - 1;

  // OHLC sliced to the query window
  const queryOhlc = ohlc && sr ? {
    open: ohlc.open.slice(-query.length),
    high: ohlc.high.slice(-query.length),
    low: ohlc.low.slice(-query.length),
    close: ohlc.close.slice(-query.length),
  } : null;

  const toggleMode = useCallback(() => {
    dispatch({ type: "SET_CHART_MODE", mode: chartMode === "line" ? "candle" : "line" });
  }, [chartMode, dispatch]);

  // ── Create chart ──
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { color: isDark ? COLORS.bg : COLORS.bgLight },
        textColor: isDark ? COLORS.text : COLORS.textLight,
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: isDark ? COLORS.grid : COLORS.gridLight },
        horzLines: { color: isDark ? COLORS.grid : COLORS.gridLight },
      },
      crosshair: {
        vertLine: { color: isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)", width: 1, style: 2 },
        horzLine: { color: isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)", width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: isDark ? COLORS.border : COLORS.borderLight,
        textColor: isDark ? COLORS.text : COLORS.textLight,
      },
      timeScale: {
        borderColor: isDark ? COLORS.border : COLORS.borderLight,
        timeVisible: false,
        tickMarkFormatter: () => "",
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: true,
      handleScale: true,
    });
    chartRef.current = chart;

    // Match line (normalized, dashed)
    const matchLine = chart.addSeries(LineSeries, {
      color: COLORS.match,
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: false,
    });

    // Candlestick series for query (created but may not be used)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.candleUp,
      downColor: COLORS.candleDown,
      borderUpColor: COLORS.candleUp,
      borderDownColor: COLORS.candleDown,
      wickUpColor: COLORS.candleUp,
      wickDownColor: COLORS.candleDown,
      priceLineVisible: false,
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

    // Continuation line (what happened after the match — extends the purple)
    const contLine = chart.addSeries(LineSeries, {
      color: COLORS.matchContinuation,
      lineWidth: 2,
      lineStyle: 0, // solid
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: true,
    });

    seriesRefs.current = {
      queryLine,
      queryCandle: candleSeries,
      match: matchLine,
      continuation: contLine,
    };

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [isDark]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Update data ──
  useEffect(() => {
    const s = seriesRefs.current;
    if (!s.queryLine || query.length < 2) return;

    const useCandles = chartMode === "candle" && queryOhlc && queryOhlc.close.length === query.length;

    if (useCandles) {
      s.queryCandle?.setData(toCandleData(queryOhlc!.open, queryOhlc!.high, queryOhlc!.low, queryOhlc!.close));
      s.queryLine?.setData([]); // hide line when showing candles
    } else {
      s.queryLine?.setData(toLineData(query));
      s.queryCandle?.setData([]); // hide candles when showing line
    }

    if (normalizedMatch.length > 1) {
      s.match?.setData(toLineData(normalizedMatch));
    } else {
      s.match?.setData([]);
    }

    if (continuationSeries.length > 1) {
      s.continuation?.setData(toLineData(continuationSeries, fStart));
    } else {
      s.continuation?.setData([]);
    }

    chartRef.current?.timeScale().fitContent();
  }, [query, normalizedMatch, continuationSeries, fStart, chartMode, queryOhlc]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Legend ──
  const legendItems: { color: string; label: string }[] = [
    { color: COLORS.query, label: "Query" },
  ];
  if (normalizedMatch.length > 0) {
    const matchLabel = sr && highlightIdx !== null ? `Match #${highlightIdx + 1}` : "Best Match";
    legendItems.push({ color: COLORS.match, label: matchLabel });
  }
  if (continuationSeries.length > 0) {
    legendItems.push({ color: COLORS.matchContinuation, label: "Continuation" });
  }

  const isLoading = query.length < 2;
  const hasOhlc = queryOhlc && queryOhlc.close.length === query.length;

  return (
    <div className="chart-container">
      {isLoading ? (
        <div className="empty-msg">Loading chart data…</div>
      ) : (
        <div className="chart-header">
          <span className="chart-title">{chartTitle}</span>
          <div className="chart-legend">
            {hasOhlc && (
              <button
                type="button"
                className="chart-mode-toggle"
                onClick={toggleMode}
                title={chartMode === "candle" ? "Switch to line" : "Switch to candles"}
              >
                {chartMode === "candle" ? "⊞" : "⊟"}
              </button>
            )}
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
