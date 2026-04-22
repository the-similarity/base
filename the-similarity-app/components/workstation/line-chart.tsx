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

/** Analog overlay data shape — price window + after path + pinned state.
 *
 * `id` is included so the chart can correlate an overlay with the
 * workstation's `hoveredAnalogId` state (set from the analog-card strip)
 * and render a hover emphasis. The field is optional for backward
 * compatibility with any callers that only built the geometric fields,
 * but the workstation always populates it (see `analogOverlays` useMemo
 * in `workstation.tsx`). */
export interface AnalogOverlay {
  id?: string;
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
  /**
   * The `id` of the analog currently hovered in the card strip — drives
   * a "preview" emphasis on the matching overlay path (brighter, bolder
   * stroke). Null when nothing is hovered. Ignored if the overlay lacks
   * `id` fields.
   */
  hoveredAnalogId?: string | null;
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
  hoveredAnalogId = null,
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
  //
  // Four-state rendering rule — read together with the .analog CSS
  // (and the mirror in `line-chart-lw.tsx` for the Pro canvas view):
  //
  //   1. No pins AND no hover            → palette variant: each analog
  //      gets its rank-indexed color (--c-analog-{rank+1}) with an
  //      opacity+width ramp so rank 1 dominates, rank 6 fades into the
  //      background. This is the default "K analogs, tell them apart"
  //      look introduced by Agent G.
  //   2. No pins, hover set              → one analog gets a
  //      "hover-preview" bump (opacity 1.0, width 2.0, brightness 1.15)
  //      on top of its palette color; others keep the palette ramp.
  //   3. Pins active                     → pinned analogs use .strong
  //      (accent red), unpinned use .context (muted ink). Palette does
  //      NOT apply in this mode — pin trumps palette so the curated
  //      subset dominates the composition.
  //   4. Pins active + hover set         → hovered AND pinned gets
  //      extra-thick strong (stroke-width 2.2); hovered AND unpinned
  //      temporarily un-fades from context → opacity 0.7 so the user
  //      can preview before deciding to pin.
  //
  // The concrete CSS lives in `app/globals.css` — this path emits
  // SVG `style` attributes inline for palette/opacity because CSS
  // variable selection per rank would need rank-indexed class names
  // and duplicating six classes is messier than a single style string.
  const hasAnyPin = !!(analogsOverlay?.some(a => a.pinned));

  /** Inline-style payload for a single analog path. */
  type AnalogPath = {
    d: string;
    variant: "default" | "strong" | "context";
    // Per-rank palette fields — null when pinning is active (the
    // .strong / .context CSS classes take over).
    stroke?: string;
    strokeWidth?: number;
    opacity?: number;
    // Filter brightness bump for hover preview (default variant only).
    filter?: string;
    /** Rank index for stable keying + badge placement. */
    rank: number;
    /** Coordinates of the forward-terminal point for badge rendering. */
    badge?: { x: number; y: number };
    /** Label shown in the badge (1-indexed). */
    badgeLabel?: string;
    /** Badge fill color (matches stroke). */
    badgeColor?: string;
  };
  const analogPaths: AnalogPath[] = [];
  // Fixed ramps keyed by rank index (0-indexed internally). Six slots
  // matches the workstation's Top-K cap; any rank beyond 5 falls back
  // to the rank-5 end of the ramp so we never crash on a surprise 7th
  // analog — the defaults still read as "background" context.
  const RAMP_OPACITY = [0.95, 0.85, 0.75, 0.65, 0.55, 0.45];
  const RAMP_WIDTH = [1.5, 1.3, 1.1, 1.0, 1.0, 1.0];
  const PALETTE_VAR = (rank: number) =>
    `var(--c-analog-${Math.min(rank, 5) + 1})`;

  if (analogsOverlay && qAnchorP) {
    analogsOverlay.forEach((a, rank) => {
      const scale = qAnchorP / a.priceWindow[a.priceWindow.length - 1];
      const combined = [...a.priceWindow, ...a.after.slice(0, forecastHorizon)];
      const startOffset = qWinEndIdx - (a.priceWindow.length - 1);
      const pts = combined.map((p, k) => {
        const idx = startOffset + k;
        if (idx < viewStart || idx > viewEnd) return null;
        return `${xOf(idx).toFixed(1)} ${yOf(p * scale).toFixed(1)}`;
      }).filter(Boolean);
      if (pts.length > 1) {
        const isHovered = !!(a.id && hoveredAnalogId && a.id === hoveredAnalogId);
        const variant: "default" | "strong" | "context" =
          !hasAnyPin ? "default"
          : a.pinned ? "strong"
          : "context";
        // Compute inline style for the palette/hover cases. The CSS
        // class continues to handle the pinned .strong/.context cases
        // as well as the baseline defaults (stroke-width, etc.) — we
        // only override when we have a per-rank or hover decision.
        let stroke: string | undefined;
        let strokeWidth: number | undefined;
        let opacity: number | undefined;
        let filter: string | undefined;
        if (!hasAnyPin) {
          // Mode 1 / 2 — palette + optional hover bump.
          stroke = PALETTE_VAR(rank);
          strokeWidth = isHovered ? 2.0 : RAMP_WIDTH[Math.min(rank, 5)];
          opacity = isHovered ? 1.0 : RAMP_OPACITY[Math.min(rank, 5)];
          if (isHovered) filter = "brightness(1.15)";
        } else if (isHovered) {
          // Mode 4 — emphasize hover within pin mode.
          if (a.pinned) {
            strokeWidth = 2.2;
          } else {
            // Un-fade the hovered-but-not-pinned overlay so the user
            // can preview what pinning it would contribute. We bump
            // opacity on top of the `.context` baseline via inline
            // style — CSS context opacity is .18, here we raise it
            // to .7 while keeping the muted ink color.
            opacity = 0.7;
          }
        }
        // Badge placement — only when palette mode is active (no pins).
        // We anchor to the forward terminal (last k-index in combined,
        // inside the forecast horizon). If that index is outside the
        // visible range we skip the badge; the line itself may still
        // have visible segments.
        let badge: { x: number; y: number } | undefined;
        let badgeLabel: string | undefined;
        let badgeColor: string | undefined;
        if (!hasAnyPin) {
          const terminalK = combined.length - 1;
          const terminalIdx = startOffset + terminalK;
          if (terminalIdx >= viewStart && terminalIdx <= viewEnd) {
            badge = {
              x: xOf(terminalIdx),
              y: yOf(combined[terminalK] * scale),
            };
            badgeLabel = String(rank + 1);
            badgeColor = PALETTE_VAR(rank);
          }
        }
        analogPaths.push({
          d: "M " + pts.join(" L "),
          variant,
          stroke,
          strokeWidth,
          opacity,
          filter,
          rank,
          badge,
          badgeLabel,
          badgeColor,
        });
      }
    });
  }

  // ── Badge overlap avoidance ───────────────────────────────────────
  // If two terminal points are close vertically (within 12px), nudge
  // the later (lower-ranked) badge down by 14px so the numerals don't
  // stack on top of each other. We do this iteratively — each later
  // badge is compared against all already-placed ones, and pushed by
  // multiples of 14px until it clears them. O(K^2) but K <= 6.
  const placedBadges: { x: number; y: number }[] = [];
  for (const a of analogPaths) {
    if (!a.badge) continue;
    let { x, y } = a.badge;
    let attempts = 0;
    while (attempts < 8) {
      const conflict = placedBadges.find(
        p => Math.abs(p.x - x) < 20 && Math.abs(p.y - y) < 12,
      );
      if (!conflict) break;
      y = conflict.y + 14;
      attempts += 1;
    }
    a.badge = { x, y };
    placedBadges.push({ x, y });
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

        {/* Analog overlays — classname picks one of three variants and
            inline style overrides apply the rank-indexed palette, the
            opacity/width ramp, and hover bumps. See the analogPaths
            computation above for the full selection matrix.

            Why inline `style`: the palette is keyed by rank (0..5),
            which would otherwise require six separate CSS classes. A
            single inline style payload is shorter and keeps the rank
            decision colocated with the data. React memoizes the
            attribute string under the hood. */}
        {analogPaths.map((a) => {
          const inline: React.CSSProperties = {};
          if (a.stroke) inline.stroke = a.stroke;
          if (a.strokeWidth != null) inline.strokeWidth = a.strokeWidth;
          if (a.opacity != null) inline.opacity = a.opacity;
          if (a.filter) inline.filter = a.filter;
          return (
            <path
              key={a.rank}
              className={
                "analog" + (a.variant === "strong" ? " strong"
                  : a.variant === "context" ? " context" : "")
              }
              d={a.d}
              style={inline}
              data-rank={a.rank}
            />
          );
        })}

        {/* Rank badges at forward terminals — palette mode only (no pins).
            Each badge is a filled circle + white numeral; placement has
            already been de-collided above. Skipped entirely when pins
            are active because the pin itself is the visual emphasis. */}
        {analogPaths.map((a) => {
          if (!a.badge || !a.badgeLabel || !a.badgeColor) return null;
          return (
            <g key={`b-${a.rank}`} className="analog-badge" data-rank={a.rank}>
              <circle
                className="analog-badge-circle"
                cx={a.badge.x}
                cy={a.badge.y}
                r={7}
                fill={a.badgeColor}
              />
              <text
                className="analog-badge-text"
                x={a.badge.x}
                y={a.badge.y + 0.5}
              >
                {a.badgeLabel}
              </text>
            </g>
          );
        })}

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
