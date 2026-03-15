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

/** Normalize `src` into the value range of `target` (preserving shape).
 *  Offset shifts the result down by a fraction of the range (e.g. 0.08 = 8% below). */
function normalizeToRange(src: number[], target: number[], offset = 0): number[] {
  if (src.length === 0 || target.length === 0) return [];
  const sMin = Math.min(...src);
  const sMax = Math.max(...src);
  const tMin = Math.min(...target);
  const tMax = Math.max(...target);
  const sRange = sMax - sMin || 1;
  const tRange = tMax - tMin || 1;
  const shift = tRange * offset;
  return src.map((v) => tMin + ((v - sMin) / sRange) * tRange - shift);
}

/** Parse ISO date to YYYY-MM-DD for lightweight-charts. */
function isoToDay(iso: string): string {
  return iso.slice(0, 10); // "2024-01-15T00:00:00+00:00" → "2024-01-15"
}

/** Fallback: generate a synthetic date from an index (used when no real dates). */
function indexToDate(idx: number): string {
  const base = new Date(2020, 0, 1);
  const d = new Date(base.getTime() + idx * 86400000);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

type TimeStr = LineData["time"];

function toLineDataWithDates(values: number[], dates: string[]): LineData[] {
  return values.map((value, i) => ({
    time: (dates[i] ? isoToDay(dates[i]) : indexToDate(i)) as unknown as TimeStr,
    value,
  }));
}

function toCandleDataWithDates(
  open: number[], high: number[], low: number[], close: number[], dates: string[],
): CandlestickData[] {
  return close.map((_, i) => ({
    time: (dates[i] ? isoToDay(dates[i]) : indexToDate(i)) as unknown as CandlestickData["time"],
    open: open[i], high: high[i], low: low[i], close: close[i],
  }));
}

/** Generate continuation dates by incrementing from the last date. */
function continuationDates(lastDate: string, count: number): string[] {
  const base = new Date(lastDate);
  const dates: string[] = [];
  let d = new Date(base);
  for (let i = 0; i < count; i++) {
    d.setDate(d.getDate() + 1);
    // Skip weekends for non-crypto
    while (d.getDay() === 0 || d.getDay() === 6) {
      d.setDate(d.getDate() + 1);
    }
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    dates.push(`${y}-${m}-${day}`);
  }
  return dates;
}

const COLORS = {
  query: "#e8e9ed",
  match: "#818cf8",
  matchContinuation: "#a78bfa",
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
  const isSearching = state.loading;

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
  const selMatchSeries = sr && selectedMatch?.matchedSeries ? selectedMatch.matchedSeries : null;
  const matchToDisplay = selMatchSeries ?? bestMatch;
  // Offset match 8% below query so it doesn't obscure candles
  const normalizedMatch = matchToDisplay.length > 1 ? normalizeToRange(matchToDisplay, query, 0.08) : [];

  // Continuation: what happened after the matched pattern
  const forwardWindow = selectedMatch?.forwardWindow ?? (sr?.matches[0]?.forwardWindow ?? null);
  const anchor = query.length > 0 ? query[query.length - 1] : 0;
  const continuationSeries = forwardWindow
    ? [anchor, ...forwardWindow.map((r) => anchor * (1 + r))]
    : [];

  // ── Full OHLC data for scrollable chart (show history + query + continuation) ──
  // Show the entire dataset so user can scroll back/forward
  const hasOhlcData = ohlc && ohlc.close.length > 0 && ohlc.dates.length > 0;
  const queryLen = query.length;

  // Dates for the query window (from full OHLC dates, last N entries)
  const queryDates = hasOhlcData ? ohlc!.dates.slice(-queryLen) : [];

  // Continuation dates (extend from last query date)
  const lastQueryDate = queryDates.length > 0 ? isoToDay(queryDates[queryDates.length - 1]) : "";
  const contDates = lastQueryDate && continuationSeries.length > 1
    ? [lastQueryDate, ...continuationDates(lastQueryDate, continuationSeries.length - 1)]
    : [];

  // Match dates = same as query dates (overlay)
  const matchDates = queryDates;

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

    // Candlestick series (full dataset)
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

    // Query line (used when not in candle mode)
    const queryLine = chart.addSeries(LineSeries, {
      color: COLORS.query,
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: false,
    });

    // Continuation line
    const contLine = chart.addSeries(LineSeries, {
      color: COLORS.matchContinuation,
      lineWidth: 2,
      lineStyle: 0,
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

    const useCandles = chartMode === "candle" && hasOhlcData;

    if (useCandles) {
      // Show FULL dataset as candles (scrollable history)
      s.queryCandle?.setData(
        toCandleDataWithDates(ohlc!.open, ohlc!.high, ohlc!.low, ohlc!.close, ohlc!.dates)
      );
      s.queryLine?.setData([]);
    } else if (hasOhlcData) {
      // Line mode but with real dates — show full close series
      s.queryLine?.setData(toLineDataWithDates(ohlc!.close, ohlc!.dates));
      s.queryCandle?.setData([]);
    } else {
      // Fallback: query-only with synthetic dates
      s.queryLine?.setData(toLineDataWithDates(query, queryDates));
      s.queryCandle?.setData([]);
    }

    // Match overlay (aligned to query window dates)
    if (normalizedMatch.length > 1 && matchDates.length > 0) {
      s.match?.setData(toLineDataWithDates(normalizedMatch, matchDates));
    } else if (normalizedMatch.length > 1) {
      s.match?.setData(toLineDataWithDates(normalizedMatch, []));
    } else {
      s.match?.setData([]);
    }

    // Continuation (extends past query with generated dates)
    if (continuationSeries.length > 1 && contDates.length > 0) {
      s.continuation?.setData(toLineDataWithDates(continuationSeries, contDates));
    } else {
      s.continuation?.setData([]);
    }

    // Scroll to show the query window (last N bars + continuation)
    if (hasOhlcData && queryDates.length > 0) {
      const ts = chartRef.current?.timeScale();
      if (ts) {
        const visibleBarsBack = Math.min(queryLen + 20, ohlc!.close.length);
        const fromIdx = ohlc!.close.length - visibleBarsBack;
        const fromDate = isoToDay(ohlc!.dates[fromIdx]);
        const toDate = contDates.length > 0
          ? contDates[contDates.length - 1]
          : isoToDay(queryDates[queryDates.length - 1]);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (ts as any).setVisibleRange({ from: fromDate, to: toDate });
      }
    } else {
      chartRef.current?.timeScale().fitContent();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    // Use stable primitives as deps to avoid array identity issues
    query.length,
    normalizedMatch.length,
    continuationSeries.length,
    chartMode,
    hasOhlcData,
    ohlc?.rowCount,
    highlightIdx,
    sr,
  ]);

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

  const isLoading = query.length < 2 && !isSearching;

  return (
    <div className="chart-container">
      {isLoading ? (
        <div className="empty-msg">Loading chart data…</div>
      ) : (
        <div className="chart-header">
          <span className="chart-title">{chartTitle}</span>
          <div className="chart-legend">
            {hasOhlcData && (
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
      <div
        ref={containerRef}
        style={{ flex: 1, minHeight: 0, position: "relative", display: isLoading ? "none" : "block" }}
      />
      {isSearching && (
        <div className="chart-loading-overlay">
          <div className="chart-loading-spinner" />
          <span>Searching…</span>
        </div>
      )}
    </div>
  );
}
