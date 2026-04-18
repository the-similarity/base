"use client";

/**
 * SVG LineChart with draggable query window, analog overlays, and forecast cone.
 *
 * The chart renders the main price series, optional analog overlay paths
 * (scaled to align at the query window end), and a P10-P90 forecast cone.
 * The query window is fully interactive: drag the body to reposition, drag
 * the left/right handles to resize. Mouse move shows a crosshair annotation.
 *
 * All coordinates are computed from viewStart/viewEnd indices into the series.
 * The chart uses a ResizeObserver to adapt to container width changes.
 */

import { useState, useEffect, useRef } from "react";
import { DataPoint, ConePoint, fmtDate, fmtDateShort } from "../../lib/data";

/** Analog overlay data shape — price window + after path + pinned state */
export interface AnalogOverlay {
  priceWindow: number[];
  after: number[];
  pinned?: boolean;
  composite: number;
}

interface LineChartProps {
  /** Full series array */
  series: DataPoint[];
  /** Start index of visible range */
  viewStart: number;
  /** End index of visible range */
  viewEnd: number;
  /** Query window position and length */
  window: { start: number; len: number };
  /** Callback when query window is dragged */
  onWindowChange: (w: { start: number; len: number }) => void;
  /** Analog overlays to draw on the chart */
  analogsOverlay?: AnalogOverlay[];
  /** Forecast cone quantile data */
  cone?: ConePoint[];
  /** Chart height in px */
  height?: number;
  /** Forecast horizon in trading days */
  forecastHorizon?: number;
  /** Currently hovered data index (for crosshair) */
  crosshairIdx?: number | null;
  /** Callback on hover — receives data index or null */
  onHover?: (idx: number | null) => void;
  /** Whether to show the draggable query window */
  showWindow?: boolean;
  /** Whether to show the forecast cone */
  showCone?: boolean;
}

export function LineChart({
  series,
  viewStart,
  viewEnd,
  window: win,
  onWindowChange,
  analogsOverlay,
  cone,
  height = 380,
  forecastHorizon = 60,
  crosshairIdx,
  onHover,
  showWindow = true,
  showCone = true,
}: LineChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);

  // Drag state ref — must be declared before any early return
  const dragRef = useRef<{
    mode: "move" | "left" | "right";
    startX: number;
    origStart: number;
    origLen: number;
  } | null>(null);

  // Track container width for responsive SVG viewBox
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(e => setW(e[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const padL = 54, padR = 20, padT = 16, padB = 28;
  const plotW = Math.max(100, w - padL - padR);
  const plotH = height - padT - padB;

  // ── Drag interaction (effect must be above early return) ───────────
  useEffect(() => {
    const mm = (e: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = e.clientX - dragRef.current.startX;
      const dIdx = Math.round((dx / plotW) * (viewEnd - viewStart));
      if (dragRef.current.mode === "move") {
        const ns = Math.max(viewStart + 1, Math.min(viewEnd - win.len - forecastHorizon - 5,
          dragRef.current.origStart + dIdx));
        onWindowChange({ start: ns, len: win.len });
      } else if (dragRef.current.mode === "left") {
        const ne = dragRef.current.origStart + dragRef.current.origLen;
        const ns = Math.max(viewStart + 1, Math.min(ne - 20, dragRef.current.origStart + dIdx));
        onWindowChange({ start: ns, len: ne - ns });
      } else if (dragRef.current.mode === "right") {
        const ns = dragRef.current.origStart;
        const newLen = Math.max(20, Math.min(viewEnd - ns - forecastHorizon - 5,
          dragRef.current.origLen + dIdx));
        onWindowChange({ start: ns, len: newLen });
      }
    };
    const mu = () => { dragRef.current = null; };
    globalThis.addEventListener("mousemove", mm);
    globalThis.addEventListener("mouseup", mu);
    return () => {
      globalThis.removeEventListener("mousemove", mm);
      globalThis.removeEventListener("mouseup", mu);
    };
  }, [win, viewStart, viewEnd, plotW, forecastHorizon, onWindowChange]);

  // ── Early return for empty visible slice ───────────────────────────
  const vis = series.slice(viewStart, viewEnd);
  if (!vis.length) return <div ref={ref} />;

  // ── Compute price range ───────────────────────────────────────────
  let minP = Infinity, maxP = -Infinity;
  vis.forEach(d => { if (d.p < minP) minP = d.p; if (d.p > maxP) maxP = d.p; });

  if (cone && showCone) cone.forEach(q => { if (q.p10 < minP) minP = q.p10; if (q.p90 > maxP) maxP = q.p90; });

  const qWinEndIdx = win.start + win.len - 1;
  const qAnchorP = series[qWinEndIdx]?.p;

  if (analogsOverlay && qAnchorP) {
    analogsOverlay.forEach(a => {
      const scale = qAnchorP / a.priceWindow[a.priceWindow.length - 1];
      a.priceWindow.forEach(p => {
        const v = p * scale;
        if (v < minP) minP = v; if (v > maxP) maxP = v;
      });
      a.after.forEach((p, i) => {
        if (i >= forecastHorizon) return;
        const v = p * scale;
        if (v < minP) minP = v; if (v > maxP) maxP = v;
      });
    });
  }

  // Pad vertical range 8%
  const pad = (maxP - minP) * 0.08;
  minP -= pad; maxP += pad;

  // Coordinate mapping functions
  const xOf = (i: number) => padL + ((i - viewStart) / (viewEnd - viewStart - 1)) * plotW;
  const yOf = (p: number) => padT + (1 - (p - minP) / (maxP - minP)) * plotH;

  // Main price path
  const pricePath = vis.map((d, i) =>
    `${i === 0 ? "M" : "L"} ${xOf(viewStart + i).toFixed(1)} ${yOf(d.p).toFixed(1)}`
  ).join(" ");

  // X-axis ticks (6 evenly spaced)
  const ticks = 6;
  const xTicks: { x: number; label: string }[] = [];
  for (let i = 0; i < ticks; i++) {
    const idx = Math.floor(viewStart + (i / (ticks - 1)) * (viewEnd - viewStart - 1));
    xTicks.push({ x: xOf(idx), label: fmtDateShort(series[idx].d) });
  }

  // Y-axis ticks (5 evenly spaced)
  const yTicks: { y: number; label: string }[] = [];
  for (let i = 0; i < 5; i++) {
    const p = minP + (i / 4) * (maxP - minP);
    yTicks.push({ y: yOf(p), label: p.toFixed(p > 1000 ? 0 : 1) });
  }

  // Window rect coordinates
  const winX1 = xOf(win.start);
  const winX2 = xOf(win.start + win.len - 1);
  const winW = Math.max(2, winX2 - winX1);

  const onMouseDown = (e: React.MouseEvent, mode: "move" | "left" | "right") => {
    dragRef.current = { mode, startX: e.clientX, origStart: win.start, origLen: win.len };
    e.preventDefault();
  };

  // Crosshair hover
  const onMove = (e: React.MouseEvent) => {
    if (!onHover || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const frac = (x - padL) / plotW;
    const idx = Math.round(viewStart + frac * (viewEnd - viewStart - 1));
    if (idx >= viewStart && idx < viewEnd) onHover(idx);
  };
  const onLeave = () => onHover && onHover(null);

  // ── Forecast cone path ────────────────────────────────────────────
  let coneUpper = "", coneLower = "", medianPath = "";
  if (cone && showCone && qAnchorP) {
    const pts = cone.slice(0, forecastHorizon);
    const conePts = pts.map((q, i) => ({
      x: xOf(qWinEndIdx + i),
      yU: yOf(q.p90), yL: yOf(q.p10), yM: yOf(q.p50),
    }));
    if (conePts.length > 1) {
      coneUpper = "M " + conePts.map(p => `${p.x.toFixed(1)} ${p.yU.toFixed(1)}`).join(" L ");
      coneLower = " L " + [...conePts].reverse().map(p => `${p.x.toFixed(1)} ${p.yL.toFixed(1)}`).join(" L ") + " Z";
      medianPath = conePts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.yM.toFixed(1)}`).join(" ");
    }
  }

  // ── Analog overlay paths ──────────────────────────────────────────
  const analogPaths: { d: string; pinned: boolean }[] = [];
  if (analogsOverlay && qAnchorP) {
    analogsOverlay.forEach((a) => {
      const scale = qAnchorP / a.priceWindow[a.priceWindow.length - 1];
      const combined = [...a.priceWindow, ...a.after.slice(0, forecastHorizon)];
      const startOffset = qWinEndIdx - (a.priceWindow.length - 1);
      const pts = combined.map((p, k) => {
        const idx = startOffset + k;
        if (idx < viewStart || idx > viewEnd) return null;
        return `${xOf(idx).toFixed(1)} ${yOf(p * scale).toFixed(1)}`;
      }).filter(Boolean);
      if (pts.length > 1) {
        analogPaths.push({
          d: "M " + pts.join(" L "),
          pinned: !!a.pinned,
        });
      }
    });
  }

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg className="svg-chart" viewBox={`0 0 ${w} ${height}`} width="100%" height={height}
        onMouseMove={onMove} onMouseLeave={onLeave}>
        {/* Grid lines */}
        <g className="grid">
          {yTicks.map((t, i) => <line key={i} x1={padL} x2={w - padR} y1={t.y} y2={t.y} />)}
        </g>
        <g className="axis">
          {yTicks.map((t, i) => <text key={i} x={padL - 6} y={t.y + 3} textAnchor="end">{t.label}</text>)}
          {xTicks.map((t, i) => <text key={i} x={t.x} y={height - padB + 14} textAnchor="middle">{t.label}</text>)}
        </g>

        {/* Cone (behind everything) */}
        {coneUpper && <path className="cone-fill" d={coneUpper + coneLower} />}
        {coneUpper && <path className="cone-line" d={coneUpper} />}
        {medianPath && <path className="median" d={medianPath} />}

        {/* Analog overlays */}
        {analogPaths.map((a, i) =>
          <path key={i} className={"analog" + (a.pinned ? " strong" : "")} d={a.d} />
        )}

        {/* Main price line */}
        <path className="price" d={pricePath} />

        {/* Draggable query window */}
        {showWindow && (
          <g>
            <rect className="window-rect" x={winX1} y={padT} width={winW} height={plotH}
              onMouseDown={(e) => onMouseDown(e, "move")} />
            <rect className="window-handle" x={winX1 - 3} y={padT + plotH / 2 - 14} width={6} height={28}
              onMouseDown={(e) => onMouseDown(e, "left")} />
            <rect className="window-handle" x={winX2 - 3} y={padT + plotH / 2 - 14} width={6} height={28}
              onMouseDown={(e) => onMouseDown(e, "right")} />
            <text className="window-label" x={winX1 + 6} y={padT + 12}>
              QUERY WINDOW &middot; {win.len}D
            </text>
          </g>
        )}

        {/* Crosshair */}
        {crosshairIdx != null && crosshairIdx >= viewStart && crosshairIdx < viewEnd && (
          <g>
            <line className="crosshair" x1={xOf(crosshairIdx)} x2={xOf(crosshairIdx)} y1={padT} y2={padT + plotH} />
            <text className="annot" x={xOf(crosshairIdx) + 4} y={padT + 12}>
              {fmtDate(series[crosshairIdx].d)} &middot; {series[crosshairIdx].p.toFixed(1)}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
