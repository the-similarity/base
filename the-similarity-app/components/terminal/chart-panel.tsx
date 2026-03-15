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

/** Convert ISO timestamp to UTC seconds for lightweight-charts. */
function isoToUtc(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

/** Fallback: generate synthetic UTC timestamp from index (86400s = 1 day). */
function indexToUtc(idx: number): number {
  const base = new Date(2020, 0, 1).getTime() / 1000;
  return base + idx * 86400;
}

function timeVal(dates: string[], i: number): LineData["time"] {
  return (dates[i] ? isoToUtc(dates[i]) : indexToUtc(i)) as unknown as LineData["time"];
}

function toLineDataWithDates(values: number[], dates: string[]): LineData[] {
  return values.map((value, i) => ({
    time: timeVal(dates, i),
    value,
  }));
}

function toCandleDataWithDates(
  open: number[], high: number[], low: number[], close: number[], dates: string[],
): CandlestickData[] {
  return close.map((_, i) => ({
    time: timeVal(dates, i) as unknown as CandlestickData["time"],
    open: open[i], high: high[i], low: low[i], close: close[i],
  }));
}

/** Generate continuation timestamps by incrementing from the last date. */
function continuationTimestamps(lastIso: string, count: number, intervalSec: number): number[] {
  const base = isoToUtc(lastIso);
  return Array.from({ length: count }, (_, i) => base + (i + 1) * intervalSec);
}

/** Guess interval in seconds from dates array. */
function guessInterval(dates: string[]): number {
  if (dates.length < 2) return 86400;
  const a = isoToUtc(dates[dates.length - 2]);
  const b = isoToUtc(dates[dates.length - 1]);
  return Math.max(b - a, 60); // at least 1 minute
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
  // Offset match 25% below query so it's clearly separated from candles
  const normalizedMatch = matchToDisplay.length > 1 ? normalizeToRange(matchToDisplay, query, 0.25) : [];

  // Continuation: what happened after the matched pattern
  // Anchor from the END of the normalized match (so continuation extends the purple line, not the query)
  const forwardWindow = selectedMatch?.forwardWindow ?? (sr?.matches[0]?.forwardWindow ?? null);
  const matchAnchor = normalizedMatch.length > 0 ? normalizedMatch[normalizedMatch.length - 1] : 0;
  const continuationSeries = forwardWindow && matchAnchor !== 0
    ? [matchAnchor, ...forwardWindow.map((r) => matchAnchor * (1 + r))]
    : [];

  // ── Full OHLC data for scrollable chart (show history + query + continuation) ──
  // Show the entire dataset so user can scroll back/forward
  const hasOhlcData = ohlc && ohlc.close.length > 0 && ohlc.dates.length > 0;
  const queryLen = query.length;

  // Dates for the query window (from full OHLC dates, last N entries)
  const queryDates = hasOhlcData ? ohlc!.dates.slice(-queryLen) : [];

  // Continuation timestamps (extend from last query date)
  const lastQueryIso = queryDates.length > 0 ? queryDates[queryDates.length - 1] : "";
  const interval = hasOhlcData ? guessInterval(ohlc!.dates) : 86400;
  const contTimestamps = lastQueryIso && continuationSeries.length > 1
    ? [isoToUtc(lastQueryIso), ...continuationTimestamps(lastQueryIso, continuationSeries.length - 1, interval)]
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

    // Continuation (extends past query with generated timestamps)
    if (continuationSeries.length > 1 && contTimestamps.length > 0) {
      s.continuation?.setData(continuationSeries.map((value, i) => ({
        time: contTimestamps[i] as unknown as LineData["time"],
        value,
      })));
    } else {
      s.continuation?.setData([]);
    }

    // Scroll to show the query window (last N bars + continuation)
    if (hasOhlcData && queryDates.length > 0) {
      const ts = chartRef.current?.timeScale();
      if (ts) {
        const visibleBarsBack = Math.min(queryLen + 20, ohlc!.close.length);
        const fromIdx = ohlc!.close.length - visibleBarsBack;
        const fromUtc = isoToUtc(ohlc!.dates[fromIdx]);
        const toUtc = contTimestamps.length > 0
          ? contTimestamps[contTimestamps.length - 1]
          : isoToUtc(queryDates[queryDates.length - 1]);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (ts as any).setVisibleRange({ from: fromUtc, to: toUtc });
      }
    } else {
      chartRef.current?.timeScale().fitContent();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sr, data, ohlc, chartMode, highlightIdx]);

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
