"use client";

/**
 * Explore — 3D State Map page.
 *
 * Renders all platform runs as a 2D scatter plot (canvas-based fallback
 * since @react-three/fiber is not installed). Each run is a circle colored
 * by kind and sized by a quality metric. Supports:
 *   - Pan (drag) and zoom (scroll wheel)
 *   - Hover tooltips
 *   - Click to select a run and show a detail panel
 *   - Cluster overlay (convex hulls) toggled on/off
 *   - "Find Similar" button that highlights nearest neighbors
 *
 * The page fetches from three endpoints:
 *   GET /platform/state/projection  — scatter positions
 *   GET /platform/state/nearest/{id} — neighbor lookup
 *   GET /platform/state/clusters    — cluster groupings
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchProjection,
  fetchNearest,
  fetchClusters,
  type ProjectionPoint,
  type Neighbor,
  type Cluster,
} from "../../lib/platform-api";

// ---------------------------------------------------------------------------
// Constants — kind-to-color mapping matching the editorial palette
// ---------------------------------------------------------------------------

/** Kind-to-color map: muted editorial tones, no neon. */
const KIND_COLORS: Record<string, string> = {
  finance: "#3366aa",   // quiet blue
  copies: "#2d7d46",    // editorial green
  worlds: "#c07020",    // warm ochre/orange
};

/** Fallback color for unknown kinds. */
const DEFAULT_COLOR = "#6b6b6b";

/**
 * Extract a 0-1 quality metric from a projection point's metadata.
 * Tries kind-specific keys, falls back to 0.5 (uniform size).
 */
function qualityMetric(pt: ProjectionPoint): number {
  const md = pt.metadata ?? {};
  // finance → trust_score, copies → fidelity, worlds → alive_ratio
  const val =
    (md.trust_score as number | undefined) ??
    (md.fidelity as number | undefined) ??
    (md.alive_ratio as number | undefined);
  if (typeof val === "number" && isFinite(val)) {
    return Math.max(0, Math.min(1, val));
  }
  return 0.5;
}

/** Sphere radius in canvas px for a given quality [0-1]. Min 4, max 14. */
function radiusForQuality(q: number): number {
  return 4 + q * 10;
}

// ---------------------------------------------------------------------------
// Convex hull helper — Graham scan for 2D points
// ---------------------------------------------------------------------------

function cross(o: [number, number], a: [number, number], b: [number, number]) {
  return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
}

function convexHull(points: [number, number][]): [number, number][] {
  if (points.length < 3) return points;
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const lower: [number, number][] = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0)
      lower.pop();
    lower.push(p);
  }
  const upper: [number, number][] = [];
  for (const p of sorted.reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0)
      upper.pop();
    upper.push(p);
  }
  upper.pop();
  lower.pop();
  return lower.concat(upper);
}

// ---------------------------------------------------------------------------
// Canvas scatter component
// ---------------------------------------------------------------------------

interface ScatterProps {
  points: ProjectionPoint[];
  clusters: Cluster[];
  showClusters: boolean;
  selectedId: string | null;
  neighborIds: Set<string>;
  onSelect: (id: string | null) => void;
  onHover: (pt: ProjectionPoint | null, x: number, y: number) => void;
}

/**
 * 2D canvas scatter plot with pan/zoom. Projects point.x / point.y into
 * canvas space using a simple linear transform with zoom + offset.
 */
function Scatter({
  points,
  clusters,
  showClusters,
  selectedId,
  neighborIds,
  onSelect,
  onHover,
}: ScatterProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Camera state — zoom (scale factor) and pan offset (in data coords)
  const zoomRef = useRef(1);
  const panRef = useRef({ x: 0, y: 0 });
  const draggingRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });

  // Data bounds — computed once when points change
  const boundsRef = useRef({ minX: 0, maxX: 1, minY: 0, maxY: 1 });

  // Recompute bounds when points change
  useEffect(() => {
    if (points.length === 0) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const p of points) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }
    // Add 10% padding so edge points aren't clipped
    const dx = (maxX - minX) * 0.1 || 1;
    const dy = (maxY - minY) * 0.1 || 1;
    boundsRef.current = {
      minX: minX - dx,
      maxX: maxX + dx,
      minY: minY - dy,
      maxY: maxY + dy,
    };
    // Reset camera when data changes
    zoomRef.current = 1;
    panRef.current = { x: 0, y: 0 };
  }, [points]);

  /** Map data coords to canvas px, accounting for zoom and pan. */
  const toCanvas = useCallback(
    (dataX: number, dataY: number, w: number, h: number) => {
      const b = boundsRef.current;
      const zoom = zoomRef.current;
      const pan = panRef.current;
      const nx = (dataX - b.minX) / (b.maxX - b.minX); // 0-1
      const ny = (dataY - b.minY) / (b.maxY - b.minY);
      const cx = (nx - 0.5) * zoom * w + w / 2 + pan.x;
      const cy = (0.5 - ny) * zoom * h + h / 2 + pan.y; // flip Y
      return { cx, cy };
    },
    []
  );

  /** Map canvas px back to data coords (for hit testing). */
  const toData = useCallback(
    (cx: number, cy: number, w: number, h: number) => {
      const b = boundsRef.current;
      const zoom = zoomRef.current;
      const pan = panRef.current;
      const nx = (cx - w / 2 - pan.x) / (zoom * w) + 0.5;
      const ny = 0.5 - (cy - h / 2 - pan.y) / (zoom * h);
      return {
        x: nx * (b.maxX - b.minX) + b.minX,
        y: ny * (b.maxY - b.minY) + b.minY,
      };
    },
    []
  );

  // ----------- Draw loop -----------

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    // -- cluster hulls --
    if (showClusters && clusters.length > 0) {
      const clusterColors = [
        "rgba(51,102,170,0.08)",
        "rgba(45,125,70,0.08)",
        "rgba(192,112,32,0.08)",
        "rgba(107,107,107,0.08)",
      ];
      const clusterStrokes = [
        "rgba(51,102,170,0.25)",
        "rgba(45,125,70,0.25)",
        "rgba(192,112,32,0.25)",
        "rgba(107,107,107,0.25)",
      ];
      // Build a run_id → point map for quick lookup
      const ptMap = new Map(points.map((p) => [p.run_id, p]));
      for (let ci = 0; ci < clusters.length; ci++) {
        const cl = clusters[ci];
        const memberPts = cl.run_ids
          .map((id) => ptMap.get(id))
          .filter(Boolean) as ProjectionPoint[];
        if (memberPts.length < 2) continue;
        const canvasPts = memberPts.map((p) => {
          const { cx, cy } = toCanvas(p.x, p.y, w, h);
          return [cx, cy] as [number, number];
        });
        const hull = convexHull(canvasPts);
        if (hull.length < 3) continue;
        ctx.beginPath();
        ctx.moveTo(hull[0][0], hull[0][1]);
        for (let i = 1; i < hull.length; i++) ctx.lineTo(hull[i][0], hull[i][1]);
        ctx.closePath();
        ctx.fillStyle = clusterColors[ci % clusterColors.length];
        ctx.fill();
        ctx.strokeStyle = clusterStrokes[ci % clusterStrokes.length];
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

    // -- points --
    for (const pt of points) {
      const { cx, cy } = toCanvas(pt.x, pt.y, w, h);
      const q = qualityMetric(pt);
      const r = radiusForQuality(q);
      const color = KIND_COLORS[pt.kind] ?? DEFAULT_COLOR;
      const isSelected = pt.run_id === selectedId;
      const isNeighbor = neighborIds.has(pt.run_id);

      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);

      if (isSelected) {
        // Selected: solid fill + dark ring
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = "#1a1a1a";
        ctx.lineWidth = 2.5;
        ctx.stroke();
      } else if (isNeighbor) {
        // Neighbor: bright fill + dashed ring
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.9;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = "#1a1a1a";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        // Normal: semi-transparent fill
        ctx.globalAlpha = 0.65;
        ctx.fillStyle = color;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.strokeStyle = color;
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
    }
  }, [points, clusters, showClusters, selectedId, neighborIds, toCanvas]);

  // Redraw whenever state changes
  useEffect(() => {
    draw();
  }, [draw]);

  // Resize canvas to match container
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        const ctx = canvas.getContext("2d");
        if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        draw();
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [draw]);

  // ----------- Interaction handlers -----------

  const hitTest = useCallback(
    (mx: number, my: number): ProjectionPoint | null => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const w = canvas.width / (window.devicePixelRatio || 1);
      const h = canvas.height / (window.devicePixelRatio || 1);
      // Search in reverse so top-drawn points are tested first
      for (let i = points.length - 1; i >= 0; i--) {
        const pt = points[i];
        const { cx, cy } = toCanvas(pt.x, pt.y, w, h);
        const r = radiusForQuality(qualityMetric(pt));
        const dx = mx - cx;
        const dy = my - cy;
        if (dx * dx + dy * dy <= (r + 2) * (r + 2)) return pt;
      }
      return null;
    },
    [points, toCanvas]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const rect = canvasRef.current!.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      if (draggingRef.current) {
        const dx = e.clientX - lastMouseRef.current.x;
        const dy = e.clientY - lastMouseRef.current.y;
        panRef.current = {
          x: panRef.current.x + dx,
          y: panRef.current.y + dy,
        };
        lastMouseRef.current = { x: e.clientX, y: e.clientY };
        draw();
        return;
      }

      const hit = hitTest(mx, my);
      if (hit) {
        onHover(hit, e.clientX, e.clientY);
        if (canvasRef.current) canvasRef.current.style.cursor = "pointer";
      } else {
        onHover(null, 0, 0);
        if (canvasRef.current) canvasRef.current.style.cursor = "grab";
      }
    },
    [hitTest, onHover, draw]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      draggingRef.current = true;
      lastMouseRef.current = { x: e.clientX, y: e.clientY };
      if (canvasRef.current) canvasRef.current.style.cursor = "grabbing";
    },
    []
  );

  const handleMouseUp = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!draggingRef.current) return;
      const dx = Math.abs(e.clientX - lastMouseRef.current.x);
      const dy = Math.abs(e.clientY - lastMouseRef.current.y);
      draggingRef.current = false;
      if (canvasRef.current) canvasRef.current.style.cursor = "grab";

      // If the mouse barely moved, treat as a click
      if (dx < 3 && dy < 3) {
        const rect = canvasRef.current!.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const hit = hitTest(mx, my);
        onSelect(hit ? hit.run_id : null);
      }
    },
    [hitTest, onSelect]
  );

  const handleWheel = useCallback(
    (e: React.WheelEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.9 : 1.1;
      zoomRef.current = Math.max(0.2, Math.min(10, zoomRef.current * factor));
      draw();
    },
    [draw]
  );

  const handleMouseLeave = useCallback(() => {
    draggingRef.current = false;
    onHover(null, 0, 0);
  }, [onHover]);

  return (
    <div ref={containerRef} className="explore-canvas-container">
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
        onMouseLeave={handleMouseLeave}
        style={{ display: "block", cursor: "grab" }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail panel component
// ---------------------------------------------------------------------------

interface DetailPanelProps {
  point: ProjectionPoint;
  onFindSimilar: () => void;
  loadingNearest: boolean;
}

function DetailPanel({ point, onFindSimilar, loadingNearest }: DetailPanelProps) {
  const md = point.metadata ?? {};
  const created = md.created_at as string | undefined;

  /** Build the detail page link based on kind. */
  const detailHref = (() => {
    switch (point.kind) {
      case "finance":
        return `/finance/${encodeURIComponent(point.run_id)}`;
      default:
        return null;
    }
  })();

  return (
    <aside className="explore-detail">
      <div className="explore-detail__header">
        <span className="mono-label">Selected Run</span>
      </div>

      <div className="explore-detail__field">
        <span className="explore-detail__label">Run ID</span>
        <span className="explore-detail__value explore-detail__value--mono">
          {point.run_id}
        </span>
      </div>

      <div className="explore-detail__field">
        <span className="explore-detail__label">Kind</span>
        <span
          className="explore-detail__badge"
          style={{
            borderColor: KIND_COLORS[point.kind] ?? DEFAULT_COLOR,
            color: KIND_COLORS[point.kind] ?? DEFAULT_COLOR,
          }}
        >
          {point.kind}
        </span>
      </div>

      <div className="explore-detail__field">
        <span className="explore-detail__label">Label</span>
        <span className="explore-detail__value">{point.label || "--"}</span>
      </div>

      {created && (
        <div className="explore-detail__field">
          <span className="explore-detail__label">Created</span>
          <span className="explore-detail__value explore-detail__value--mono">
            {new Date(created).toLocaleDateString()}
          </span>
        </div>
      )}

      {/* Key metrics from metadata */}
      <div className="explore-detail__metrics">
        {Object.entries(md)
          .filter(([k]) => k !== "created_at")
          .slice(0, 6)
          .map(([key, val]) => (
            <div key={key} className="explore-detail__metric">
              <span className="explore-detail__metric-label">{key}</span>
              <span className="explore-detail__metric-value">
                {typeof val === "number" ? val.toFixed(3) : String(val ?? "--")}
              </span>
            </div>
          ))}
      </div>

      <div className="explore-detail__actions">
        <button
          className="explore-detail__btn explore-detail__btn--primary"
          onClick={onFindSimilar}
          disabled={loadingNearest}
        >
          {loadingNearest ? "Searching..." : "Find Similar"}
        </button>

        {detailHref && (
          <a href={detailHref} className="explore-detail__btn explore-detail__btn--secondary">
            View Run
          </a>
        )}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Tooltip component
// ---------------------------------------------------------------------------

function Tooltip({
  point,
  x,
  y,
}: {
  point: ProjectionPoint;
  x: number;
  y: number;
}) {
  return (
    <div
      className="explore-tooltip"
      style={{
        left: x + 12,
        top: y - 8,
      }}
    >
      <div className="explore-tooltip__id">{point.run_id}</div>
      <div className="explore-tooltip__kind">{point.kind}</div>
      {point.label && (
        <div className="explore-tooltip__label">{point.label}</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function ExplorePage() {
  const [points, setPoints] = useState<ProjectionPoint[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [showClusters, setShowClusters] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [neighborIds, setNeighborIds] = useState<Set<string>>(new Set());
  const [loadingNearest, setLoadingNearest] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Hover tooltip state
  const [hoverPt, setHoverPt] = useState<ProjectionPoint | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });

  const selectedPoint = points.find((p) => p.run_id === selectedId) ?? null;

  // ---- Initial fetch ----
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [proj, cl] = await Promise.all([
          fetchProjection(),
          fetchClusters().catch(() => [] as Cluster[]),
        ]);
        if (cancelled) return;
        setPoints(proj);
        setClusters(cl);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load state map");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // ---- Find Similar handler ----
  const handleFindSimilar = useCallback(async () => {
    if (!selectedId) return;
    setLoadingNearest(true);
    try {
      const neighbors = await fetchNearest(selectedId, 5);
      setNeighborIds(new Set(neighbors.map((n) => n.run_id)));
    } catch {
      // Silently fail — neighbors just won't highlight
      setNeighborIds(new Set());
    } finally {
      setLoadingNearest(false);
    }
  }, [selectedId]);

  // Clear neighbors when selection changes
  useEffect(() => {
    setNeighborIds(new Set());
  }, [selectedId]);

  const handleHover = useCallback(
    (pt: ProjectionPoint | null, x: number, y: number) => {
      setHoverPt(pt);
      setHoverPos({ x, y });
    },
    []
  );

  // ---- Empty / Loading / Error states ----
  if (loading) {
    return (
      <div className="explore-page">
        <div className="explore-page__loading">
          <div className="chart-loading-spinner" />
          <span>Loading state map...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="explore-page">
        <div className="match-list-error">
          <div className="match-list-error__icon">!</div>
          <div className="match-list-error__text">{error}</div>
        </div>
      </div>
    );
  }

  if (points.length === 0) {
    return (
      <div className="explore-page">
        <div className="explore-empty">
          <div className="explore-empty__icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <circle cx="24" cy="24" r="20" stroke="#e5e5e5" strokeWidth="2" />
              <circle cx="16" cy="20" r="3" fill="#e5e5e5" />
              <circle cx="30" cy="16" r="2" fill="#e5e5e5" />
              <circle cx="28" cy="30" r="4" fill="#e5e5e5" />
            </svg>
          </div>
          <p className="explore-empty__title">No runs registered yet</p>
          <p className="explore-empty__hint">
            Register finance backtests, synthetic copies, or world runs to see
            them projected into this state map.
          </p>
        </div>
      </div>
    );
  }

  // ---- Main render ----
  return (
    <div className="explore-page">
      {/* Toolbar */}
      <div className="explore-toolbar">
        <span className="explore-toolbar__title">State Map</span>
        <span className="explore-toolbar__count">
          {points.length} run{points.length !== 1 ? "s" : ""}
        </span>

        {/* Legend */}
        <div className="explore-toolbar__legend">
          {Object.entries(KIND_COLORS).map(([kind, color]) => (
            <span key={kind} className="explore-toolbar__legend-item">
              <span
                className="explore-toolbar__legend-dot"
                style={{ background: color }}
              />
              {kind}
            </span>
          ))}
        </div>

        <span className="explore-toolbar__spacer" />

        {/* Cluster toggle */}
        <button
          className="config-pill"
          data-active={showClusters ? "true" : "false"}
          onClick={() => setShowClusters((v) => !v)}
        >
          Clusters {showClusters ? "ON" : "OFF"}
        </button>
      </div>

      {/* Main body: scatter + optional detail panel */}
      <div className="explore-body">
        <div className="explore-scatter-wrap">
          <Scatter
            points={points}
            clusters={clusters}
            showClusters={showClusters}
            selectedId={selectedId}
            neighborIds={neighborIds}
            onSelect={setSelectedId}
            onHover={handleHover}
          />

          {/* Hover tooltip */}
          {hoverPt && <Tooltip point={hoverPt} x={hoverPos.x} y={hoverPos.y} />}
        </div>

        {/* Detail panel — slides in when a run is selected */}
        {selectedPoint && (
          <DetailPanel
            point={selectedPoint}
            onFindSimilar={handleFindSimilar}
            loadingNearest={loadingNearest}
          />
        )}
      </div>
    </div>
  );
}
