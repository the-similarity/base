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
  /**
   * Callback when the user zooms the time axis via the wheel. Receives the
   * new [start, end] range. The parent owns viewRange, so this is a lift.
   * If omitted, the chart is read-only on the time axis.
   */
  onRangeChange?: (r: { start: number; end: number }) => void;
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
  onRangeChange,
  analogsOverlay,
  cone,
  height = 300,
  forecastHorizon = 60,
  crosshairIdx,
  onHover,
  showWindow = true,
  showCone = true,
  hoveredAnalogId = null,
}: LineChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [w, setW] = useState(800);
  /*
   * Price-axis override for shift-wheel zoom.
   *
   * null → auto-compute from the visible price range (default behavior,
   *         preserved for the unzoomed case).
   * [min, max] → user pinned the y-axis; rendering uses these bounds
   *         instead of recomputing each frame.
   *
   * Kept local because it's purely a presentation concern — the parent
   * doesn't need to know whether the user is visually zoomed. Reset via
   * double-click on the chart (see onDoubleClick below).
   */
  const [priceOverride, setPriceOverride] = useState<[number, number] | null>(null);
  /*
   * Live mirror of the auto-computed [minP, maxP] from the current render.
   *
   * Why a ref (not state or closed-over locals): the wheel-zoom effect is
   * registered ONCE and re-bound only when the deps change; we don't want
   * the auto-range to be in those deps (it changes on every pan/query
   * update, which would thrash the listener). Writing into a ref during
   * render then reading it from the effect is the idiomatic way to bridge
   * the "latest value needed in a stable callback" gap.
   *
   * Initialized to [0, 1] as a benign placeholder — the first render
   * overwrites it before any wheel event can fire.
   */
  const autoPriceRangeRef = useRef<[number, number]>([0, 1]);

  /*
   * Drag state ref — must be declared before any early return.
   *
   * Four modes:
   *   - "move" / "left" / "right" : query-window manipulation; payload is
   *     the window origin (origStart, origLen).
   *   - "pan" : view-range pan; payload is the viewRange origin
   *     (origViewStart, origViewEnd). We use discriminated types so the
   *     handler can't accidentally mix window/view state across modes.
   */
  const dragRef = useRef<
    | {
        mode: "move" | "left" | "right";
        startX: number;
        origStart: number;
        origLen: number;
      }
    | {
        mode: "pan";
        startX: number;
        origViewStart: number;
        origViewEnd: number;
      }
    | null
  >(null);

  const padL = 54, padR = 20, padT = 16, padB = 28;
  const plotW = Math.max(100, w - padL - padR);
  const plotH = height - padT - padB;

  // Track container width for responsive SVG viewBox
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(e => setW(e[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  // ── Wheel zoom ─────────────────────────────────────────────────────
  //
  // - Plain wheel           → zoom the TIME axis (viewStart..viewEnd) via
  //                           `onRangeChange`. Anchored on the cursor so
  //                           the bar under the mouse stays put.
  // - Shift + wheel         → zoom the PRICE axis (priceOverride state).
  //                           Anchored on the cursor's y position.
  // - Double-click          → reset priceOverride to null (re-auto-fits).
  //
  // We attach a NATIVE wheel listener (not React's onWheel) with
  // `{ passive: false }` so preventDefault() is actually honored —
  // React's synthetic wheel handlers are passive by default in
  // Chromium, which means calling preventDefault is a silent no-op
  // and the page scrolls anyway. Attaching directly to the SVG node
  // bypasses that.
  //
  // The "live" price range (auto-computed each render) is read through
  // `autoPriceRangeRef` rather than closed-over locals so the listener
  // only re-binds when geometry / structural deps change — not on every
  // pan that shifts minP/maxP.
  //
  // Guards:
  //   - Refuse to shrink the time range below 50 bars (anything tighter
  //     and a single bar spans too many px to be useful).
  //   - Refuse to grow the time range past `series.length * 1.25` (we
  //     don't want the user to "zoom out" into a mostly-empty chart).
  //   - Price zoom clamps to >0 width to avoid divide-by-zero in yOf.
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      // Only zoom when the cursor is over the plot area (not the axis
      // gutters). Using the SVG's bounding rect keeps the math right
      // even when the chart is embedded in a flex layout.
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      if (x < padL || x > padL + plotW || y < padT || y > padT + plotH) return;
      e.preventDefault();

      // Normalize wheel delta. Trackpads report small fractional deltas,
      // mice report ~100 per notch — `deltaY` sign is all we need.
      // zoomFactor < 1 = zoom IN, > 1 = zoom OUT.
      const zoomFactor = e.deltaY < 0 ? 0.88 : 1.12;

      if (e.shiftKey) {
        // ── Price-axis zoom ────────────────────────────────────────
        const [cMin, cMax] = priceOverride ?? autoPriceRangeRef.current;
        const range = cMax - cMin;
        if (range <= 0) return;
        const yFrac = (y - padT) / plotH;         // 0 at top, 1 at bottom
        const priceFrac = 1 - yFrac;              // invert: price grows up
        const anchorPrice = cMin + priceFrac * range;
        const newRange = Math.max(1e-9, range * zoomFactor);
        setPriceOverride([
          anchorPrice - priceFrac * newRange,
          anchorPrice + (1 - priceFrac) * newRange,
        ]);
      } else if (onRangeChange) {
        // ── Time-axis zoom ─────────────────────────────────────────
        const rangeWidth = viewEnd - viewStart;
        if (rangeWidth < 2) return;
        const xFrac = (x - padL) / plotW;
        const anchorIdx = viewStart + xFrac * rangeWidth;
        const newWidth = Math.max(50, Math.min(Math.floor(series.length * 1.25),
          Math.round(rangeWidth * zoomFactor)));
        const newStart = Math.max(0, Math.round(anchorIdx - xFrac * newWidth));
        const newEnd = newStart + newWidth;
        onRangeChange({ start: newStart, end: newEnd });
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [viewStart, viewEnd, plotW, plotH, padL, padT, series.length, priceOverride, onRangeChange]);

  // Reset price-axis override on double-click. Time axis reset is the
  // parent's concern (preset range chips live on the side panel), so
  // dblclick here only touches the piece of state we own.
  const onDoubleClick = () => setPriceOverride(null);

  // ── Drag interaction (effect must be above early return) ───────────
  //
  // Window clamps use the series length (`series.length - 1`) as the right
  // boundary, NOT `viewEnd`. viewEnd is allowed to run past real data so the
  // forecast cone can extend into "future" space on the right of the chart;
  // the query window itself must stay anchored in real history.
  useEffect(() => {
    const N = series.length;
    const maxAnchor = Math.max(0, N - 1);
    const mm = (e: MouseEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const dx = e.clientX - drag.startX;
      const dIdx = Math.round((dx / plotW) * (viewEnd - viewStart));
      if (drag.mode === "move") {
        const ns = Math.max(viewStart + 1, Math.min(maxAnchor - win.len + 1,
          drag.origStart + dIdx));
        onWindowChange({ start: ns, len: win.len });
      } else if (drag.mode === "left") {
        const ne = drag.origStart + drag.origLen;
        const ns = Math.max(viewStart + 1, Math.min(ne - 20, drag.origStart + dIdx));
        onWindowChange({ start: ns, len: ne - ns });
      } else if (drag.mode === "right") {
        const ns = drag.origStart;
        const newLen = Math.max(20, Math.min(maxAnchor - ns + 1,
          drag.origLen + dIdx));
        onWindowChange({ start: ns, len: newLen });
      } else if (drag.mode === "pan" && onRangeChange) {
        // Pan the whole view by the mouse delta. Dragging right should
        // move the visible range backwards in time (standard chart
        // convention), hence the minus sign on dIdx.
        const width = drag.origViewEnd - drag.origViewStart;
        const rawStart = drag.origViewStart - dIdx;
        // Clamp so we can't scroll off the left of history; the right
        // side is intentionally uncapped so the user can drag into the
        // forecast's "future" space past N. The guardrail in
        // workstation.tsx keeps viewEnd ≥ queryEnd + horizon + 5, so
        // this will never hide the cone.
        const newStart = Math.max(0, Math.min(rawStart, maxAnchor));
        onRangeChange({ start: newStart, end: newStart + width });
      }
    };
    const mu = () => { dragRef.current = null; };
    globalThis.addEventListener("mousemove", mm);
    globalThis.addEventListener("mouseup", mu);
    return () => {
      globalThis.removeEventListener("mousemove", mm);
      globalThis.removeEventListener("mouseup", mu);
    };
  }, [win, viewStart, viewEnd, plotW, forecastHorizon, onWindowChange, onRangeChange, series.length]);

  // ── Early return for empty visible slice ───────────────────────────
  const vis = series.slice(viewStart, viewEnd);
  if (!vis.length) return <div ref={ref} />;

  // ── Compute price range ───────────────────────────────────────────
  //
  // The range is driven by the VISIBLE SERIES first (always well-behaved
  // since it's the raw price column). The cone and analog overlays are
  // then allowed to *expand* that range, but only within a sanity clamp
  // of ±50% of the base span. This prevents a single mis-scaled analog
  // or an impossibly-wide cone tail from hijacking the y-axis — the
  // symptom the user saw was a GOLD chart y-axis running from −444 to
  // 5992 when the actual prices lived in 4000..5500, caused by a
  // scaled analog point near zero.
  //
  // Points that fall outside the clamp are still RENDERED (the SVG just
  // draws them past the axis edge); they just don't get to push the
  // axis itself around. When the user needs to see those tails, they
  // can shift-wheel to zoom out manually.
  let baseMin = Infinity, baseMax = -Infinity;
  vis.forEach(d => { if (d.p < baseMin) baseMin = d.p; if (d.p > baseMax) baseMax = d.p; });
  if (!isFinite(baseMin) || !isFinite(baseMax)) { baseMin = 0; baseMax = 1; }
  const baseSpan = Math.max(1e-9, baseMax - baseMin);
  const clampLo = baseMin - baseSpan * 0.5;
  const clampHi = baseMax + baseSpan * 0.5;
  const expand = (v: number) => {
    if (v < clampLo || v > clampHi) return;
    if (v < baseMin) baseMin = v;
    if (v > baseMax) baseMax = v;
  };
  if (cone && showCone) cone.forEach(q => { expand(q.p10); expand(q.p90); });

  const qWinEndIdx = win.start + win.len - 1;
  const qAnchorP = series[qWinEndIdx]?.p;

  if (analogsOverlay && qAnchorP) {
    analogsOverlay.forEach(a => {
      const analogEnd = a.priceWindow[a.priceWindow.length - 1];
      if (!analogEnd) return;
      const scale = qAnchorP / analogEnd;
      a.priceWindow.forEach(p => expand(p * scale));
      a.after.forEach((p, i) => { if (i < forecastHorizon) expand(p * scale); });
    });
  }

  let minP = baseMin, maxP = baseMax;
  // Pad vertical range 8% — only applied to the auto-computed range. A
  // user-pinned `priceOverride` wins verbatim so double-click → zoom →
  // double-click returns to the same frame the user started from.
  if (priceOverride) {
    [minP, maxP] = priceOverride;
  } else {
    const pad = (maxP - minP) * 0.08;
    minP -= pad; maxP += pad;
  }
  // Push the auto-computed range into the wheel-handler ref so shift-wheel
  // anchoring uses the current frame's bounds, not stale ones.
  autoPriceRangeRef.current = [minP, maxP];

  // Coordinate mapping functions
  const xOf = (i: number) => padL + ((i - viewStart) / (viewEnd - viewStart - 1)) * plotW;
  const yOf = (p: number) => padT + (1 - (p - minP) / (maxP - minP)) * plotH;

  // Main price path
  const pricePath = vis.map((d, i) =>
    `${i === 0 ? "M" : "L"} ${xOf(viewStart + i).toFixed(1)} ${yOf(d.p).toFixed(1)}`
  ).join(" ");

  // X-axis ticks (6 evenly spaced). When `viewEnd` extends past the last
  // real bar (to make room for the forecast cone), indices ≥ N have no
  // corresponding entry in `series` — we synthesize a date by extrapolating
  // the cadence of the final two real bars. This lets the axis label the
  // future region (e.g. "Jun 2027") instead of crashing on `series[idx].d`.
  const N = series.length;
  const cadenceMs = N >= 2
    ? series[N - 1].d.getTime() - series[N - 2].d.getTime()
    : 86400_000;
  const dateAtIdx = (idx: number): Date => {
    if (idx >= 0 && idx < N) return series[idx].d;
    if (idx >= N && N > 0) return new Date(series[N - 1].d.getTime() + (idx - (N - 1)) * cadenceMs);
    // Negative indices shouldn't reach this code path (viewStart ≥ 0 in
    // practice); fall back to epoch to fail visibly rather than crash.
    return new Date(0);
  };
  const ticks = 6;
  const xTicks: { x: number; label: string }[] = [];
  for (let i = 0; i < ticks; i++) {
    const idx = Math.floor(viewStart + (i / (ticks - 1)) * (viewEnd - viewStart - 1));
    xTicks.push({ x: xOf(idx), label: fmtDateShort(dateAtIdx(idx)) });
  }
  // "Today" marker — a faint vertical rule at the boundary between real
  // history and synthesized future space. Only rendered when the chart
  // actually extends past the data end.
  const dataEndX = N > 0 && viewEnd > N ? xOf(N - 1) : null;

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

  // Pan the view when the user mousedowns on the chart background (i.e.,
  // anywhere inside the plot area that isn't the query window rect/handles).
  // The window has its own onMouseDown={move/left/right} handlers that
  // stopPropagation via e.preventDefault, so those still win when clicked.
  const onPanStart = (e: React.MouseEvent) => {
    if (!onRangeChange) return;
    // Primary button only — right-click should remain available for
    // future context-menu use.
    if (e.button !== 0) return;
    dragRef.current = {
      mode: "pan",
      startX: e.clientX,
      origViewStart: viewStart,
      origViewEnd: viewEnd,
    };
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
      <svg
        ref={svgRef}
        className="svg-chart"
        viewBox={`0 0 ${w} ${height}`}
        width="100%"
        height={height}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        onDoubleClick={onDoubleClick}
      >
        {/* Invisible pan-capture rect covering the plot area. Must sit
            BELOW the query window in render order so the window's own
            mousedown handlers still win when the user grabs the window.
            `fill="transparent"` keeps it invisible but hittable;
            `pointer-events="all"` is implicit for a filled rect. */}
        <rect
          className="pan-catcher"
          x={padL}
          y={padT}
          width={Math.max(1, plotW)}
          height={Math.max(1, plotH)}
          fill="transparent"
          onMouseDown={onPanStart}
        />
        {/* Grid lines */}
        <g className="grid" style={{ pointerEvents: "none" }}>
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

        {/* "Today" divider — shown when viewEnd extends past the last real bar
            so the forecast cone can run into synthesized future space. Sits
            between the price line and the window overlay so it reads as a
            soft axis marker, not a chart feature. */}
        {dataEndX != null && (
          <g>
            <line className="data-end" x1={dataEndX} x2={dataEndX} y1={padT} y2={padT + plotH} />
            <text className="data-end-label" x={dataEndX + 4} y={padT + plotH - 4}>
              today
            </text>
          </g>
        )}

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

        {/* Crosshair — the annotation reads from `series[idx]`, so the label
            is suppressed when the cursor is in the synthesized future region
            (idx ≥ N). The vertical rule still renders there as a visual
            reference; we just can't annotate a price that doesn't exist yet. */}
        {crosshairIdx != null && crosshairIdx >= viewStart && crosshairIdx < viewEnd && (
          <g>
            <line className="crosshair" x1={xOf(crosshairIdx)} x2={xOf(crosshairIdx)} y1={padT} y2={padT + plotH} />
            {crosshairIdx < N && series[crosshairIdx] && (
              <text className="annot" x={xOf(crosshairIdx) + 4} y={padT + 12}>
                {fmtDate(series[crosshairIdx].d)} &middot; {series[crosshairIdx].p.toFixed(1)}
              </text>
            )}
          </g>
        )}
      </svg>
    </div>
  );
}
