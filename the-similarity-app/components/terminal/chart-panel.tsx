"use client";
import { useRef, useState, useEffect } from "react";
import { useTerminal } from "@/lib/terminal-context";
import {
  scalePoints,
  pointsToPath,
  areaPath,
  clampRatio,
} from "@/lib/chart-utils";

export function ChartPanel() {
  const { state } = useTerminal();
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(760);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const dashData = state.dashboardData;

  // Use the default range view from dashboard data, or show empty state
  if (!dashData) {
    return (
      <div className="terminal-panel" style={{ height: "100%" }}>
        <div className="terminal-panel-header">Chart</div>
        <div
          style={{
            color: "var(--text-muted)",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "var(--space-xl)",
            textAlign: "center",
          }}
        >
          Loading chart data...
        </div>
      </div>
    );
  }

  const view = dashData.views[dashData.defaultRange];
  const width = containerWidth;
  const height = 300;

  const forecastAnchor = view.query[view.query.length - 1];
  const forecastP10 = [forecastAnchor, ...view.forecast.p10];
  const forecastP50 = [forecastAnchor, ...view.forecast.p50];
  const forecastP90 = [forecastAnchor, ...view.forecast.p90];
  const totalSlots = view.query.length + view.forecast.p50.length;
  const allValues = [
    ...view.query,
    ...view.bestMatch,
    ...forecastP10,
    ...forecastP90,
  ];
  const min = Math.min(...allValues) - 1.5;
  const max = Math.max(...allValues) + 1.5;

  const queryPoints = scalePoints(
    view.query,
    0,
    totalSlots,
    width,
    height,
    min,
    max,
  );
  const matchPoints = scalePoints(
    view.bestMatch,
    0,
    totalSlots,
    width,
    height,
    min,
    max,
  );
  const p10Points = scalePoints(
    forecastP10,
    view.query.length - 1,
    totalSlots,
    width,
    height,
    min,
    max,
  );
  const p50Points = scalePoints(
    forecastP50,
    view.query.length - 1,
    totalSlots,
    width,
    height,
    min,
    max,
  );
  const p90Points = scalePoints(
    forecastP90,
    view.query.length - 1,
    totalSlots,
    width,
    height,
    min,
    max,
  );
  const dividerX =
    ((view.query.length - 1) / Math.max(totalSlots - 1, 1)) * width;
  const latestPoint = p50Points[p50Points.length - 1];

  // Calculate highlighted region for hovered/selected match
  const activeIdx =
    state.hoveredIdx !== null ? state.hoveredIdx : state.selectedIdx;
  const activeMatch =
    activeIdx !== null && activeIdx < state.matches.length
      ? state.matches[activeIdx]
      : null;

  let highlightX = 0;
  let highlightW = 0;
  if (activeMatch && view.query.length > 0) {
    const queryLen = view.query.length;
    const historyLen = queryLen; // approximate
    const startRatio = activeMatch.startIdx / Math.max(historyLen - 1, 1);
    const endRatio = activeMatch.endIdx / Math.max(historyLen - 1, 1);
    highlightX = startRatio * dividerX;
    highlightW = Math.max((endRatio - startRatio) * dividerX, 2);
  }

  return (
    <div
      className="terminal-panel"
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
    >
      <div className="terminal-panel-header">
        {view.label} &middot; {dashData.defaultRange}
        <span
          style={{
            marginLeft: "auto",
            display: "flex",
            gap: "var(--space-md)",
            fontSize: 10,
            color: "var(--text-muted)",
          }}
        >
          <span>
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 2,
                background: "var(--chart-query)",
                marginRight: 4,
                verticalAlign: "middle",
              }}
            />
            Query
          </span>
          <span>
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 2,
                background: "var(--chart-match)",
                marginRight: 4,
                verticalAlign: "middle",
              }}
            />
            Match
          </span>
          <span>
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 2,
                background: "var(--chart-forecast)",
                marginRight: 4,
                verticalAlign: "middle",
              }}
            />
            Forecast
          </span>
        </span>
      </div>
      <div ref={containerRef} style={{ flex: 1, minHeight: 0, padding: "var(--space-sm)" }}>
        <svg
          viewBox={`0 0 ${width} ${height + 28}`}
          width="100%"
          height="100%"
          preserveAspectRatio="none"
          role="img"
          aria-label="Pattern match forecast chart"
          style={{ display: "block" }}
        >
          <defs>
            <linearGradient id="forecast-fill" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor="var(--chart-forecast-fill, var(--chart-forecast))"
                stopOpacity="0.18"
              />
              <stop
                offset="100%"
                stopColor="var(--chart-forecast-fill, var(--chart-forecast))"
                stopOpacity="0"
              />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
            <line
              key={ratio}
              x1="0"
              x2={width}
              y1={height * ratio}
              y2={height * ratio}
              stroke="var(--chart-grid)"
              strokeWidth="0.5"
              strokeDasharray="2,4"
            />
          ))}

          {/* Match highlight region */}
          {activeMatch && (
            <rect
              className="chart-region-highlight"
              x={highlightX}
              y={0}
              width={highlightW}
              height={height}
              fill="var(--accent-dim, rgba(59,130,246,0.1))"
              stroke="var(--accent, #3b82f6)"
              strokeWidth="0.5"
              strokeDasharray="3,3"
            />
          )}

          {/* Forecast cone */}
          <path
            d={areaPath(p90Points, p10Points)}
            fill="url(#forecast-fill)"
          />

          {/* Lines */}
          <path
            d={pointsToPath(matchPoints)}
            fill="none"
            stroke="var(--chart-match-dim, var(--chart-match))"
            strokeWidth="1.2"
            opacity="0.5"
          />
          <path
            d={pointsToPath(queryPoints)}
            fill="none"
            stroke="var(--chart-query)"
            strokeWidth="1.5"
          />
          <path
            d={pointsToPath(p50Points)}
            fill="none"
            stroke="var(--chart-forecast)"
            strokeWidth="1.2"
            strokeDasharray="4,3"
          />

          {/* Divider */}
          <line
            x1={dividerX}
            x2={dividerX}
            y1={0}
            y2={height}
            stroke="var(--border-strong)"
            strokeWidth="1"
            strokeDasharray="4,4"
          />

          {/* Forecast end dot + label */}
          <circle
            cx={latestPoint.x}
            cy={latestPoint.y}
            r="3"
            fill="var(--chart-forecast)"
          />
          <g
            transform={`translate(${Math.min(latestPoint.x + 8, width - 48)}, ${latestPoint.y - 14})`}
          >
            <rect
              width="40"
              height="16"
              rx="3"
              fill="var(--bg-elevated)"
              stroke="var(--border)"
              strokeWidth="0.5"
            />
            <text
              x="20"
              y="11.5"
              textAnchor="middle"
              fill="var(--text-primary)"
              fontSize="9"
              fontFamily="var(--font-mono)"
            >
              {view.forecast.p50[view.forecast.p50.length - 1].toFixed(1)}
            </text>
          </g>

          {/* Axis labels */}
          <text
            x="4"
            y={height + 16}
            fill="var(--text-muted)"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            query window
          </text>
          <text
            x={width - 4}
            y={height + 16}
            textAnchor="end"
            fill="var(--text-muted)"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            forward bars
          </text>
        </svg>
      </div>
    </div>
  );
}
