"use client";

/**
 * Spatium — Pillar III (3D Data Space) dashboard page.
 *
 * Route: /spatium (prod: app.thesimilarity.tech/spatium).
 *
 * Purpose
 * -------
 * Embed multiple time-series datasets as vectors in a shared 3D manifold
 * and let the user click into cross-domain self-similarity. This is a
 * client-only page: it boots a three.js scene inside a single useEffect
 * and owns all render/interaction state locally. No SSR payload beyond
 * the DOM shell (WebGL and window listeners live on the browser).
 *
 * Lifecycle
 * ---------
 * 1. First render paints the dashboard shell (nav, top bar, left panel,
 *    empty canvas, right panel, status bar).
 * 2. useEffect (mount only) constructs the point cloud, spins up the
 *    three.js renderer, wires event listeners (pointerdown/move/up,
 *    wheel, resize), and starts the requestAnimationFrame loop.
 * 3. On unmount every listener is removed, the RAF loop is cancelled,
 *    the WebGL context is released via renderer.dispose(), and every
 *    Points/Lines geometry is freed. This is critical — Next.js dev
 *    HMR will remount the component many times per session.
 *
 * State discipline
 * ----------------
 * - Render-driving state (selected window, threshold, legend rows,
 *   right-panel contents, tweak flags) lives in React useState so the
 *   JSX stays declarative.
 * - The three.js scene graph is held inside a mutable ref (`engineRef`)
 *   so the animation loop can read/write without triggering rerenders.
 * - The scene is the source of truth for camera position and frame
 *   timing; React is the source of truth for the surrounding chrome.
 * - `STATE` inside the engine ref mirrors a subset of the React state
 *   so the RAF loop does not have to close over React setState calls.
 *
 * Immutability
 * ------------
 * - DATASETS and DOMAIN_ORDER are imported frozen-by-convention.
 * - The points array is rebuilt (not mutated) when density changes.
 * - React state transitions never mutate prior values — every
 *   setState hands back a fresh object.
 *
 * Math notes
 * ----------
 * - Layout: UMAP-flavoured deterministic embedding (see datasets.ts).
 *   Each domain sits on a ring; intra-cluster spread is driven by
 *   (slope, hurst, sd) → (dx, dy, dz).
 * - Neighbour search: feature-space weighted Euclidean distance, mapped
 *   to similarity via `1 - d/3`, then thresholded by the slider.
 * - Orbit: auto-mode drives camera along a circle at
 *   radius=hypot(18,22), height=10, angular velocity 0.08 rad/s.
 */

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import styles from "./spatium.module.css";
import {
  DATASETS,
  DOMAIN_ORDER,
  SpatiumPoint,
  buildPoints,
  clamp,
  distance,
  regimeLabel,
  similarityFromDist,
} from "./datasets";

/* ──────────────────────────────────────────────────────────────────
   Tweak state shape (mirrors the design's persisted blob)
   ────────────────────────────────────────────────────────────────── */

type SceneMode = "dark" | "light";
type ColorBy = "domain" | "regime" | "era";
type OrbitMode = "auto" | "manual" | "stop";
type EdgesMode = "on" | "off";
type PointStyle = "dot" | "ring" | "cross";

interface EngineState {
  density: 0 | 1 | 2;
  colorBy: ColorBy;
  orbit: OrbitMode;
  threshold: number;
  sceneMode: SceneMode;
  edges: EdgesMode;
  pointStyle: PointStyle;
  selectedIdx: number | null;
  hoverIdx: number | null;
}

interface Hit {
  p: SpatiumPoint;
  i: number;
  d: number;
  sim: number;
}

/* ──────────────────────────────────────────────────────────────────
   Utilities used by the page (SVG sparkline, hex conversion).
   Kept close to the component so they can read the CSS module
   classNames without a circular import.
   ────────────────────────────────────────────────────────────────── */

/** Format a three.js hex colour as `#rrggbb`. */
function toHexCss(n: number): string {
  return "#" + n.toString(16).padStart(6, "0");
}

/**
 * Render a 1D series as an SVG path into an existing <svg> element.
 *
 * The SVG must already have a viewBox set. We compute min/max on the
 * series, normalise with a 2px pad, then emit a single M/L path. This
 * mirrors the design file's sparkline routine byte-for-byte so layout
 * widths stay identical.
 */
function drawSpark(svg: SVGSVGElement, series: number[], cls: string): void {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const vb = svg.viewBox.baseVal;
  const W = vb.width;
  const H = vb.height;
  let min = Infinity;
  let max = -Infinity;
  for (const v of series) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const span = max - min || 1;
  const pad = 2;
  let d = "";
  for (let i = 0; i < series.length; i++) {
    const x = pad + (i / (series.length - 1)) * (W - pad * 2);
    const y = H - pad - ((series[i] - min) / span) * (H - pad * 2);
    d += (i === 0 ? "M" : "L") + x.toFixed(2) + "," + y.toFixed(2);
  }
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("class", cls);
  p.setAttribute("d", d);
  svg.appendChild(p);
}

/* ──────────────────────────────────────────────────────────────────
   Canvas texture factory for the point sprite.
   ────────────────────────────────────────────────────────────────── */

function makePointTexture(style: PointStyle): THREE.CanvasTexture {
  const size = 64;
  const cv = document.createElement("canvas");
  cv.width = size;
  cv.height = size;
  const ctx = cv.getContext("2d")!;
  ctx.clearRect(0, 0, size, size);
  const cx = size / 2;
  const cy = size / 2;
  if (style === "dot") {
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, size / 2);
    grad.addColorStop(0, "rgba(255,255,255,1)");
    grad.addColorStop(0.4, "rgba(255,255,255,0.85)");
    grad.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, size / 2, 0, Math.PI * 2);
    ctx.fill();
  } else if (style === "ring") {
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.arc(cx, cy, size / 2 - 6, 0, Math.PI * 2);
    ctx.stroke();
  } else {
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.moveTo(10, cy);
    ctx.lineTo(size - 10, cy);
    ctx.moveTo(cx, 10);
    ctx.lineTo(cx, size - 10);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.needsUpdate = true;
  return tex;
}

/* ──────────────────────────────────────────────────────────────────
   Nav rail icons. Kept as inline SVGs so the dark rail doesn't need
   an icon-font dependency.
   ────────────────────────────────────────────────────────────────── */

function IconHome() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12 12 4l9 8" />
      <path d="M5 10v10h14V10" />
    </svg>
  );
}
function IconFinance() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M14 7h7v7" />
    </svg>
  );
}
function IconSynthetic() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx={12} cy={12} r={8} />
      <path d="M4 12h16M12 4c3 3 3 13 0 16M12 4c-3 3-3 13 0 16" />
    </svg>
  );
}
function IconCube() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l9 5-9 5-9-5 9-5z" />
      <path d="M3 13l9 5 9-5" />
      <path d="M3 8v5M21 8v5M12 8v5" />
    </svg>
  );
}
function IconEvents() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <rect x={3} y={5} width={18} height={16} rx={2} />
      <path d="M3 9h18M8 3v4M16 3v4" />
    </svg>
  );
}
function IconNarrative() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6h16M4 12h10M4 18h16" />
    </svg>
  );
}
function IconSettings() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx={12} cy={12} r={3} />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </svg>
  );
}
function IconTweaks() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 6h10M4 12h6M4 18h14" />
      <circle cx={18} cy={6} r={2} />
      <circle cx={14} cy={12} r={2} />
      <circle cx={20} cy={18} r={2} />
    </svg>
  );
}
function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
function IconDownload() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v12M6 9l6 6 6-6" />
      <path d="M5 21h14" />
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────────
   Page component
   ────────────────────────────────────────────────────────────────── */

/** Legend row shape — colour hex + label. Derived from colorBy. */
interface LegendRow {
  color: string;
  label: string;
  queryGlow?: boolean;
}

/** Right-panel details computed from a selection pass. */
interface SelectionPayload {
  query: SpatiumPoint;
  hits: Hit[];
  cross: Hit[];
}

const DENSITY_LABELS = ["sparse", "medium", "dense"] as const;

export default function SpatiumPage() {
  /* ── Refs for DOM nodes owned by the three.js boot ─────────────── */
  const rootRef = useRef<HTMLDivElement | null>(null);
  const sceneElRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const tipRef = useRef<HTMLDivElement | null>(null);
  const tipTitleRef = useRef<HTMLDivElement | null>(null);
  const tipMetaRef = useRef<HTMLDivElement | null>(null);
  const qSparkRef = useRef<SVGSVGElement | null>(null);
  const selChartRef = useRef<SVGSVGElement | null>(null);
  const fpsRef = useRef<HTMLSpanElement | null>(null);
  const hudNRef = useRef<HTMLSpanElement | null>(null);
  const hudSessionRef = useRef<HTMLSpanElement | null>(null);

  /* ── React state (drives JSX) ──────────────────────────────────── */
  const [density, setDensity] = useState<0 | 1 | 2>(1);
  const [colorBy, setColorBy] = useState<ColorBy>("domain");
  const [orbit, setOrbit] = useState<OrbitMode>("auto");
  const [threshold, setThreshold] = useState<number>(0.72);
  const [sceneMode, setSceneMode] = useState<SceneMode>("dark");
  const [edges, setEdges] = useState<EdgesMode>("on");
  const [pointStyle, setPointStyle] = useState<PointStyle>("dot");
  const [visible, setVisible] = useState<Set<string>>(() => new Set(DATASETS.map((d) => d.id)));
  const [tweaksOpen, setTweaksOpen] = useState(false);

  // Visible selection payload — mirrors what's shown in the right panel.
  const [selection, setSelection] = useState<SelectionPayload | null>(null);
  const [pointCount, setPointCount] = useState<number>(0);

  /* ── Mutable engine container (not React state) ────────────────── */
  // Everything in here lives outside React's reconciliation boundary so
  // the RAF loop and pointer handlers do not cause rerenders.
  const engineRef = useRef<{
    renderer?: THREE.WebGLRenderer;
    scene?: THREE.Scene;
    camera?: THREE.PerspectiveCamera;
    pointsGroup?: THREE.Group;
    edgesGroup?: THREE.Group;
    ringGroup?: THREE.Group;
    grid?: THREE.GridHelper;
    worldAxes?: THREE.LineSegments;
    points: SpatiumPoint[];
    STATE: EngineState;
    orbitAngle: number;
    orbitRadius: number;
    orbitHeight: number;
    last: number;
    fpsAcc: number;
    fpsN: number;
    rafId: number;
    visible: Set<string>;
    onResize?: () => void;
    onPointerDown?: (e: PointerEvent) => void;
    onPointerMove?: (e: PointerEvent) => void;
    onPointerUp?: (e: PointerEvent) => void;
    onWheel?: (e: WheelEvent) => void;
  }>({
    points: [],
    STATE: {
      density: 1,
      colorBy: "domain",
      orbit: "auto",
      threshold: 0.72,
      sceneMode: "dark",
      edges: "on",
      pointStyle: "dot",
      selectedIdx: null,
      hoverIdx: null,
    },
    orbitAngle: Math.atan2(22, 18),
    orbitRadius: Math.hypot(18, 22),
    orbitHeight: 10,
    last: 0,
    fpsAcc: 0,
    fpsN: 0,
    rafId: 0,
    visible: new Set(DATASETS.map((d) => d.id)),
  });

  /* ── Derived: dataset counts for the left-panel list ──────────── */
  const domainCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of engineRef.current.points) {
      c[p.ds] = (c[p.ds] ?? 0) + 1;
    }
    // If points haven't been built yet, fall back to a synthetic count
    // consistent with current density so the initial render isn't blank.
    if (Object.keys(c).length === 0) {
      const per = [15, 32, 60][density];
      for (const ds of DATASETS) c[ds.id] = per;
    }
    return c;
  }, [density, pointCount]);

  /* ── Derived: legend rows (driven by colorBy) ──────────────────── */
  const legend: LegendRow[] = useMemo(() => {
    if (colorBy === "domain") {
      const seen = new Set<string>();
      const rows: LegendRow[] = [];
      for (const ds of DATASETS) {
        if (seen.has(ds.domain)) continue;
        seen.add(ds.domain);
        rows.push({ color: toHexCss(ds.color), label: ds.domain });
      }
      rows.push({ color: "#4fa8ff", label: "query", queryGlow: true });
      rows.push({ color: "#e2a846", label: "cross-domain match" });
      return rows;
    }
    if (colorBy === "regime") {
      return [
        { color: "#7fb3c7", label: "anti-persistent" },
        { color: "#b2aea2", label: "random" },
        { color: "#e6b45c", label: "trending" },
      ];
    }
    return [
      { color: "#dcb478", label: "pre-2000" },
      { color: "#b6b4c4", label: "2000s" },
      { color: "#8cb4e6", label: "post-2015" },
    ];
  }, [colorBy]);

  /* ── Helper: colour lookup that respects colorBy ───────────────── */
  function colorForPoint(p: SpatiumPoint, mode: ColorBy): THREE.Color {
    let hex = p.color;
    if (mode === "regime") {
      const h = p.feat.hurst;
      if (h < 0.42) hex = 0x4fa8ff;
      else if (h > 0.58) hex = 0xe2a846;
      else hex = 0xa7aec0;
    } else if (mode === "era") {
      const t = clamp((p.year - 1960) / (2025 - 1960), 0, 1);
      const r = Math.round(220 * (1 - t) + 140 * t);
      const g = Math.round(180 * (1 - t) + 180 * t);
      const b = Math.round(120 * (1 - t) + 230 * t);
      hex = (r << 16) | (g << 8) | b;
    }
    return new THREE.Color(hex);
  }

  /* ── Helper: rebuild the Points objects (one per dataset) ──────── */
  function rebuildPoints() {
    const E = engineRef.current;
    if (!E.pointsGroup || !E.ringGroup) return;
    while (E.pointsGroup.children.length) {
      const c = E.pointsGroup.children[0];
      E.pointsGroup.remove(c);
      // Free GPU resources to prevent leaks when tweaks toggle.
      (c as THREE.Points).geometry?.dispose?.();
      const mat = (c as THREE.Points).material as THREE.PointsMaterial | undefined;
      mat?.map?.dispose?.();
      mat?.dispose?.();
    }
    while (E.ringGroup.children.length) {
      const c = E.ringGroup.children[0];
      E.ringGroup.remove(c);
      (c as THREE.Mesh).geometry?.dispose?.();
      const mm = (c as THREE.Mesh).material as THREE.Material | undefined;
      mm?.dispose?.();
    }

    const texture = makePointTexture(E.STATE.pointStyle);
    for (const ds of DATASETS) {
      const dsPoints = E.points.filter((p) => p.ds === ds.id);
      if (!dsPoints.length) continue;
      const geo = new THREE.BufferGeometry();
      const positions = new Float32Array(dsPoints.length * 3);
      const colors = new Float32Array(dsPoints.length * 3);
      for (let i = 0; i < dsPoints.length; i++) {
        const p = dsPoints[i];
        positions[i * 3] = p.pos[0];
        positions[i * 3 + 1] = p.pos[1];
        positions[i * 3 + 2] = p.pos[2];
        const col = colorForPoint(p, E.STATE.colorBy);
        colors[i * 3] = col.r;
        colors[i * 3 + 1] = col.g;
        colors[i * 3 + 2] = col.b;
      }
      geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
      const mat = new THREE.PointsMaterial({
        size: 0.55,
        vertexColors: true,
        map: texture,
        transparent: true,
        depthWrite: false,
        sizeAttenuation: true,
        opacity: 0.95,
      });
      const pts = new THREE.Points(geo, mat);
      pts.userData.ds = ds.id;
      pts.userData.indices = dsPoints.map((p) => E.points.indexOf(p));
      pts.visible = E.visible.has(ds.id);
      E.pointsGroup.add(pts);
    }
  }

  /* ── Helper: compute nearest-neighbour rings + edges ───────────── */
  function updateSelectionVisuals() {
    const E = engineRef.current;
    if (!E.ringGroup || !E.edgesGroup) return;
    while (E.ringGroup.children.length) {
      const c = E.ringGroup.children[0];
      E.ringGroup.remove(c);
      (c as THREE.Mesh).geometry?.dispose?.();
      const mm = (c as THREE.Mesh).material as THREE.Material | undefined;
      mm?.dispose?.();
    }
    while (E.edgesGroup.children.length) {
      const c = E.edgesGroup.children[0];
      E.edgesGroup.remove(c);
      (c as THREE.LineSegments).geometry?.dispose?.();
      const mm = (c as THREE.LineSegments).material as THREE.Material | undefined;
      mm?.dispose?.();
    }
    if (E.STATE.selectedIdx == null) return;
    const q = E.points[E.STATE.selectedIdx];
    if (!q) return;

    // Query ring (blue disc facing camera).
    const ringGeo = new THREE.RingGeometry(0.45, 0.62, 40);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x4fa8ff, side: THREE.DoubleSide, transparent: true, opacity: 0.95 });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(q.pos[0], q.pos[1], q.pos[2]);
    ring.userData.billboard = true;
    E.ringGroup.add(ring);

    // Nearest neighbours in feature space.
    const scored = E.points.map((p, i) => ({ p, i, d: distance(q, p) }));
    scored.sort((a, b) => a.d - b.d);
    const hits: Hit[] = [];
    for (const s of scored) {
      if (s.i === E.STATE.selectedIdx) continue;
      if (!E.visible.has(s.p.ds)) continue;
      const sim = similarityFromDist(s.d);
      if (sim < E.STATE.threshold) break;
      hits.push({ ...s, sim });
      if (hits.length >= 12) break;
    }

    if (E.STATE.edges === "on" && hits.length) {
      const segs: number[] = [];
      const colors: number[] = [];
      for (const h of hits) {
        const sameDomain = h.p.ds === q.ds;
        const col = new THREE.Color(sameDomain ? 0x4fa8ff : 0xe2a846);
        segs.push(q.pos[0], q.pos[1], q.pos[2], h.p.pos[0], h.p.pos[1], h.p.pos[2]);
        colors.push(col.r, col.g, col.b, col.r, col.g, col.b);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(segs, 3));
      g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
      const m = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.55 });
      E.edgesGroup.add(new THREE.LineSegments(g, m));
    }

    // Amber rings for the cross-domain hits.
    for (const h of hits) {
      if (h.p.ds === q.ds) continue;
      const rg = new THREE.RingGeometry(0.32, 0.44, 32);
      const rm = new THREE.MeshBasicMaterial({ color: 0xe2a846, side: THREE.DoubleSide, transparent: true, opacity: 0.8 });
      const rr = new THREE.Mesh(rg, rm);
      rr.position.set(h.p.pos[0], h.p.pos[1], h.p.pos[2]);
      rr.userData.billboard = true;
      E.ringGroup.add(rr);
    }

    const cross = hits.filter((h) => h.p.ds !== q.ds);
    setSelection({ query: q, hits, cross });

    // Side-effect: update the query sparkline + selection chart (DOM-direct
    // for parity with the design file — fast and avoids React re-rendering
    // on every interaction).
    if (qSparkRef.current) drawSpark(qSparkRef.current, q.series, styles.sparkLineQuery);
    if (selChartRef.current) drawSpark(selChartRef.current, q.series, styles.sparkLine);
  }

  /* ── Helper: select nearest BTC-2020 window as default ─────────── */
  function selectDefault() {
    const E = engineRef.current;
    const btc = E.points.filter((p) => p.ds === "btc");
    if (!btc.length) {
      E.STATE.selectedIdx = 0;
      updateSelectionVisuals();
      return;
    }
    let best = btc[0];
    let bd = Math.abs(best.year - 2020);
    for (const p of btc) {
      const d = Math.abs(p.year - 2020);
      if (d < bd) {
        bd = d;
        best = p;
      }
    }
    E.STATE.selectedIdx = E.points.indexOf(best);
    updateSelectionVisuals();
  }

  /* ═══════════════════════════════════════════════════════════════
     BOOT + LIFECYCLE (runs once, teardown on unmount)
     ═══════════════════════════════════════════════════════════════ */

  useEffect(() => {
    const E = engineRef.current;
    const sceneEl = sceneElRef.current;
    const canvas = canvasRef.current;
    if (!sceneEl || !canvas) return;

    // Build points deterministically. Stored on the engine ref; components
    // that need to display counts re-read via state.
    E.points = buildPoints(E.STATE.density);
    setPointCount(E.points.length);

    const rect = sceneEl.getBoundingClientRect();
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(rect.width, rect.height, false);
    E.renderer = renderer;

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x0b0d13, 30, 80);
    E.scene = scene;

    const camera = new THREE.PerspectiveCamera(45, rect.width / rect.height, 0.1, 200);
    camera.position.set(18, 10, 22);
    camera.lookAt(0, 0, 0);
    E.camera = camera;

    // Faint grid floor + three short axes lines (design parity).
    const grid = new THREE.GridHelper(40, 20, 0x1a1d24, 0x141620);
    grid.position.y = -8;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.35;
    scene.add(grid);
    E.grid = grid;

    const axesMat = new THREE.LineBasicMaterial({ color: 0x2a2d36, transparent: true, opacity: 0.5 });
    const axesG = new THREE.BufferGeometry();
    axesG.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(
        [-18, 0, 0, 18, 0, 0, 0, -6, 0, 0, 9, 0, 0, 0, -18, 0, 0, 18],
        3,
      ),
    );
    const axesLs = new THREE.LineSegments(axesG, axesMat);
    scene.add(axesLs);
    E.worldAxes = axesLs;

    E.pointsGroup = new THREE.Group();
    scene.add(E.pointsGroup);
    E.edgesGroup = new THREE.Group();
    scene.add(E.edgesGroup);
    E.ringGroup = new THREE.Group();
    scene.add(E.ringGroup);

    rebuildPoints();
    selectDefault();

    // HUD text (session timestamp + point count) — static, written once.
    if (hudNRef.current) hudNRef.current.textContent = String(E.points.length);
    if (hudSessionRef.current) {
      const now = new Date();
      hudSessionRef.current.textContent = now.toISOString().slice(0, 16).replace("T", " ") + " UTC";
    }

    /* ── Interactions ───────────────────────────────────────────── */
    const raycaster = new THREE.Raycaster();
    raycaster.params.Points!.threshold = 0.35;
    const mouse = new THREE.Vector2();

    function pickPoint(clientX: number, clientY: number): number | null {
      if (!E.camera || !E.pointsGroup || !canvas) return null;
      const r = canvas.getBoundingClientRect();
      mouse.x = ((clientX - r.left) / r.width) * 2 - 1;
      mouse.y = -((clientY - r.top) / r.height) * 2 + 1;
      raycaster.setFromCamera(mouse, E.camera);
      const hits = raycaster.intersectObjects(E.pointsGroup.children, false);
      if (!hits.length) return null;
      const hit = hits[0];
      const idx = hit.object.userData.indices[hit.index!];
      return idx ?? null;
    }

    let dragging = false;
    let lastX = 0;
    let lastY = 0;

    const onPointerDown = (e: PointerEvent) => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
      canvas.setPointerCapture(e.pointerId);
    };
    const onPointerUp = (e: PointerEvent) => {
      dragging = false;
      if (Math.hypot(e.clientX - lastX, e.clientY - lastY) < 3) {
        const idx = pickPoint(e.clientX, e.clientY);
        if (idx != null) {
          E.STATE.selectedIdx = idx;
          updateSelectionVisuals();
        }
      }
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!E.camera) return;
      if (dragging) {
        const dx = e.clientX - lastX;
        const dy = e.clientY - lastY;
        E.orbitAngle -= dx * 0.007;
        E.orbitHeight = clamp(E.orbitHeight + dy * 0.05, -6, 22);
        E.camera.position.x = Math.cos(E.orbitAngle) * E.orbitRadius;
        E.camera.position.z = Math.sin(E.orbitAngle) * E.orbitRadius;
        E.camera.position.y = E.orbitHeight;
        E.camera.lookAt(0, 0, 0);
        lastX = e.clientX;
        lastY = e.clientY;
      } else {
        const idx = pickPoint(e.clientX, e.clientY);
        const tip = tipRef.current;
        if (!tip) return;
        if (idx != null) {
          const p = E.points[idx];
          if (tipTitleRef.current) tipTitleRef.current.textContent = p.dsName;
          if (tipMetaRef.current) tipMetaRef.current.textContent = `${p.year} · ${p.domain} · window #${p.idxInDs + 1}`;
          tip.setAttribute("data-visible", "true");
          const sr = sceneEl.getBoundingClientRect();
          tip.style.left = e.clientX - sr.left + "px";
          tip.style.top = e.clientY - sr.top + "px";
        } else {
          tip.setAttribute("data-visible", "false");
        }
      }
    };
    const onWheel = (e: WheelEvent) => {
      if (!E.camera) return;
      e.preventDefault();
      E.orbitRadius = clamp(E.orbitRadius * (1 + e.deltaY * 0.001), 10, 45);
      E.camera.position.x = Math.cos(E.orbitAngle) * E.orbitRadius;
      E.camera.position.z = Math.sin(E.orbitAngle) * E.orbitRadius;
      E.camera.lookAt(0, 0, 0);
    };
    const onResize = () => {
      if (!E.renderer || !E.camera || !sceneEl) return;
      const r = sceneEl.getBoundingClientRect();
      E.renderer.setSize(r.width, r.height, false);
      E.camera.aspect = r.width / r.height;
      E.camera.updateProjectionMatrix();
    };

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("resize", onResize);
    E.onPointerDown = onPointerDown;
    E.onPointerMove = onPointerMove;
    E.onPointerUp = onPointerUp;
    E.onWheel = onWheel;
    E.onResize = onResize;

    /* ── Render loop ────────────────────────────────────────────── */
    E.last = performance.now();
    const animate = () => {
      if (!E.renderer || !E.camera || !E.scene || !E.ringGroup) return;
      const now = performance.now();
      const dt = (now - E.last) / 1000;
      E.last = now;
      E.fpsAcc += 1 / Math.max(dt, 1e-6);
      E.fpsN++;
      if (E.fpsN > 30) {
        if (fpsRef.current) fpsRef.current.textContent = Math.round(E.fpsAcc / E.fpsN) + " fps";
        E.fpsAcc = 0;
        E.fpsN = 0;
      }
      if (E.STATE.orbit === "auto") {
        E.orbitAngle += dt * 0.08;
        E.camera.position.x = Math.cos(E.orbitAngle) * E.orbitRadius;
        E.camera.position.z = Math.sin(E.orbitAngle) * E.orbitRadius;
        E.camera.position.y = E.orbitHeight;
        E.camera.lookAt(0, 0, 0);
      }
      E.ringGroup.children.forEach((m) => {
        if (m.userData.billboard) m.lookAt(E.camera!.position);
      });
      E.renderer.render(E.scene, E.camera);
      E.rafId = requestAnimationFrame(animate);
    };
    E.rafId = requestAnimationFrame(animate);

    /* ── Teardown ───────────────────────────────────────────────── */
    return () => {
      cancelAnimationFrame(E.rafId);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("wheel", onWheel);
      window.removeEventListener("resize", onResize);
      // Dispose every geometry/material/texture to release GPU memory.
      scene.traverse((obj) => {
        const maybeMesh = obj as THREE.Mesh & THREE.Points & THREE.LineSegments;
        maybeMesh.geometry?.dispose?.();
        const mat = maybeMesh.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else mat?.dispose?.();
      });
      renderer.dispose();
    };
    // Intentionally empty deps: the engine boots once per mount. All
    // dynamic state is funnelled in via the sync useEffects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Keep engine STATE in sync with React state without remount ─ */
  useEffect(() => {
    const E = engineRef.current;
    E.STATE.threshold = threshold;
    updateSelectionVisuals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threshold]);

  useEffect(() => {
    const E = engineRef.current;
    E.STATE.colorBy = colorBy;
    rebuildPoints();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colorBy]);

  useEffect(() => {
    const E = engineRef.current;
    E.STATE.orbit = orbit;
  }, [orbit]);

  useEffect(() => {
    const E = engineRef.current;
    E.STATE.edges = edges;
    updateSelectionVisuals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edges]);

  useEffect(() => {
    const E = engineRef.current;
    E.STATE.pointStyle = pointStyle;
    rebuildPoints();
    updateSelectionVisuals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointStyle]);

  useEffect(() => {
    const E = engineRef.current;
    E.STATE.sceneMode = sceneMode;
    if (!E.scene) return;
    E.scene.fog = new THREE.Fog(sceneMode === "light" ? 0xfafbfc : 0x0b0d13, 30, 80);
    // Recolour helpers without rebuilding the scene graph.
    E.scene.traverse((o) => {
      const grid = o as THREE.GridHelper;
      if ((grid as unknown as { isGridHelper?: boolean }).isGridHelper) {
        const gm = grid.material as THREE.LineBasicMaterial;
        gm.opacity = sceneMode === "light" ? 0.35 : 0.4;
        gm.color = new THREE.Color(sceneMode === "light" ? 0xd6dae0 : 0x1a1d24);
      }
      if ((o as THREE.LineSegments).isLineSegments) {
        const ls = o as THREE.LineSegments;
        const posAttr = ls.geometry.getAttribute("position");
        if (posAttr && posAttr.count === 6) {
          const lm = ls.material as THREE.LineBasicMaterial;
          lm.color = new THREE.Color(sceneMode === "light" ? 0xcccccc : 0x2a2d36);
        }
      }
    });
    rebuildPoints();
    updateSelectionVisuals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneMode]);

  useEffect(() => {
    const E = engineRef.current;
    if (!E.pointsGroup) return;
    E.visible = visible;
    E.pointsGroup.children.forEach((pts) => {
      const ds = (pts as THREE.Points).userData.ds as string | undefined;
      if (ds) (pts as THREE.Points).visible = visible.has(ds);
    });
    updateSelectionVisuals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  useEffect(() => {
    const E = engineRef.current;
    if (!E.scene) return;
    E.STATE.density = density;
    E.points = buildPoints(density);
    setPointCount(E.points.length);
    if (hudNRef.current) hudNRef.current.textContent = String(E.points.length);
    rebuildPoints();
    selectDefault();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [density]);

  /* ── Derived strings for status bar ────────────────────────────── */
  const hits = selection?.hits ?? [];
  const cross = selection?.cross ?? [];
  const matchText = selection
    ? `${hits.length} matches above ${threshold.toFixed(2)}`
    : "— matches above threshold";

  const selectedHurst = selection ? selection.query.feat.hurst.toFixed(2) : "0.61";
  const selectedRegime = selection ? regimeLabel(selection.query.feat) : "Expansion";
  const selectedNearest = hits.length ? hits[0].sim.toFixed(2) : "—";
  const selectedCD = `${cross.length} matches`;

  /* ── Render ────────────────────────────────────────────────────── */
  return (
    <div className={styles.spatium} ref={rootRef}>
      {/* ── Nav rail ────────────────────────────────────────────── */}
      <nav className={styles.nav}>
        <div className={styles.navLogo}>{"\u2058"}</div>
        <Link href="/" className={styles.navBtn} title="Home">
          <IconHome />
        </Link>
        <Link href="/finance" className={styles.navBtn} title="Finance">
          <IconFinance />
        </Link>
        <Link href="/reports" className={styles.navBtn} title="Synthetic">
          <IconSynthetic />
        </Link>
        <Link href="/spatium" className={styles.navBtn} data-active="true" title="3D Space">
          <IconCube />
        </Link>
        <Link href="/explore" className={styles.navBtn} title="Events">
          <IconEvents />
        </Link>
        <Link href="/narrative" className={styles.navBtn} title="Narratives">
          <IconNarrative />
        </Link>
        <div className={styles.navSpacer} />
        <button className={styles.navBtn} title="Settings" type="button">
          <IconSettings />
        </button>
        <div className={styles.navAvatar}>NC</div>
      </nav>

      {/* ── Top bar ─────────────────────────────────────────────── */}
      <header className={styles.topbar}>
        <div className={styles.crumbs}>
          <span>The Similarity</span>
          <span className="sep">/</span>
          <span>Pillar III</span>
          <span className="sep">/</span>
          <span className="cur">3D Data Space</span>
        </div>
        <div className={styles.tbActions}>
          <button
            className={styles.btn}
            onClick={() => setTweaksOpen((v) => !v)}
            data-active={tweaksOpen ? "true" : undefined}
            type="button"
          >
            <IconTweaks />
            Tweaks
          </button>
          <button className={styles.btn} type="button">
            <IconPlus />
            Add dataset
          </button>
          <button className={`${styles.btn} ${styles.primary}`} type="button">
            <IconDownload />
            Export embedding
          </button>
          <span className={styles.chip}>
            <span className="dot" />
            engine online
          </span>
        </div>
      </header>

      {/* ── Left panel ──────────────────────────────────────────── */}
      <aside className={styles.left}>
        <div className={styles.sectionH}>
          Query <small>dim 512</small>
        </div>
        <div className={styles.queryCard} data-highlight="true">
          <div className={styles.qLabel}>Selected window</div>
          <div className={styles.qTitle}>
            {selection ? selection.query.dsName : "BTC/USD · 180d window"}
          </div>
          <div className={styles.qSub}>
            {selection ? `${selection.query.year} · ${selection.query.domain}` : "2020-10-14 → 2021-04-13"}
          </div>
          <svg
            ref={qSparkRef}
            className={styles.qSpark}
            viewBox="0 0 220 32"
            preserveAspectRatio="none"
          />
        </div>

        <div className={styles.sectionH}>
          Datasets
          <small>
            <span>{visible.size}</span>/{DATASETS.length} visible
          </small>
        </div>
        <div className={styles.domainList}>
          {DATASETS.map((ds) => {
            const on = visible.has(ds.id);
            return (
              <div
                key={ds.id}
                className={styles.domainItem}
                data-on={on ? "true" : "false"}
                style={{ color: toHexCss(ds.color) }}
                onClick={() => {
                  setVisible((prev) => {
                    const next = new Set(prev);
                    if (next.has(ds.id)) next.delete(ds.id);
                    else next.add(ds.id);
                    return next;
                  });
                }}
              >
                <span className={styles.domainSwatch} />
                <span className={styles.domainName} style={{ color: "var(--text)" }}>
                  {ds.name}
                </span>
                <span className={styles.domainCount}>{domainCounts[ds.id] ?? 0}</span>
              </div>
            );
          })}
        </div>

        <div className={styles.controls}>
          <div>
            <div className={styles.ctrlRow} style={{ marginBottom: 6 }}>
              <span className={styles.ctrlLabel}>Similarity threshold</span>
              <span className={styles.ctrlValue}>{threshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0.4}
              max={0.98}
              step={0.01}
              value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
            />
          </div>

          <div>
            <div className={styles.ctrlLabel} style={{ marginBottom: 6 }}>
              Color by
            </div>
            <div className={styles.seg}>
              {(["domain", "regime", "era"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  data-active={colorBy === v ? "true" : undefined}
                  onClick={() => setColorBy(v)}
                >
                  {v === "domain" ? "Domain" : v === "regime" ? "Regime" : "Era"}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className={styles.ctrlLabel} style={{ marginBottom: 6 }}>
              Orbit
            </div>
            <div className={styles.seg}>
              {(["auto", "manual", "stop"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  data-active={orbit === v ? "true" : undefined}
                  onClick={() => setOrbit(v)}
                >
                  {v === "auto" ? "Auto" : v === "manual" ? "Manual" : "Stop"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </aside>

      {/* ── Scene ────────────────────────────────────────────────── */}
      <main
        className={`${styles.scene} ${sceneMode === "light" ? styles.light : ""}`}
        ref={sceneElRef}
      >
        <canvas className={styles.sceneCanvas} ref={canvasRef} />

        <div className={styles.sceneHud}>
          <div>
            <span className="k">embedding</span> &nbsp;wavelet-leader · dtw · hurst · spectral
          </div>
          <div>
            <span className="k">projection</span> &nbsp;umap → 3d · n=
            <span ref={hudNRef}>—</span>
          </div>
          <div>
            <span className="k">session</span> &nbsp;
            <span ref={hudSessionRef}>—</span>
          </div>
        </div>

        <div className={styles.sceneTitle}>
          <div className="t1">Self-similarity manifold</div>
          <div className="t2">{DATASETS.length} datasets · 512d → 3d</div>
        </div>

        <div className={styles.sceneLegend}>
          {legend.map((row, i) => (
            <div key={i} className={styles.sceneLegendRow} style={i === legend.length - 2 && colorBy === "domain" ? { marginTop: 4, borderTop: "1px solid rgba(231,233,238,0.12)", paddingTop: 6 } : undefined}>
              <span
                className={styles.sceneLegendDot}
                style={{
                  background: row.color,
                  boxShadow: row.queryGlow ? `0 0 0 2px rgba(79,168,255,0.25)` : undefined,
                }}
              />
              {row.label}
            </div>
          ))}
        </div>

        <svg className={styles.sceneAxes} viewBox="0 0 72 72">
          <g
            stroke={sceneMode === "light" ? "rgba(26,26,26,0.5)" : "rgba(232,230,221,0.5)"}
            strokeWidth={1}
          >
            <line x1={12} y1={58} x2={58} y2={58} />
            <line x1={12} y1={58} x2={12} y2={12} />
            <line x1={12} y1={58} x2={30} y2={40} />
          </g>
          <g
            fontFamily="SF Mono, Consolas, monospace"
            fontSize={7}
            fill={sceneMode === "light" ? "rgba(26,26,26,0.6)" : "rgba(232,230,221,0.6)"}
          >
            <text x={60} y={60}>slope</text>
            <text x={2} y={10}>hurst</text>
            <text x={32} y={38}>volatility</text>
          </g>
        </svg>

        <div className={styles.sceneTooltip} ref={tipRef}>
          <div className={styles.tTitle} ref={tipTitleRef}>
            —
          </div>
          <div className={styles.tMeta} ref={tipMetaRef}>
            —
          </div>
        </div>
      </main>

      {/* ── Right panel ─────────────────────────────────────────── */}
      <aside className={styles.right}>
        <div className={styles.selCard}>
          <div className={styles.selTag}>Query selected</div>
          <div className={styles.selTitle}>
            {selection ? `${selection.query.dsName} — ${selection.query.year}` : "BTC/USD — Nov 2020"}
          </div>
          <div className={styles.selSub}>
            {selection
              ? `${selection.query.domain} · 180d window · #${selection.query.idxInDs + 1}`
              : "crypto · daily · 180d window"}
          </div>
          <svg
            ref={selChartRef}
            className={styles.selChart}
            viewBox="0 0 300 58"
            preserveAspectRatio="none"
          />
          <div className={styles.statGrid}>
            <div className={styles.statCell}>
              <div className={styles.statLbl}>Hurst</div>
              <div className={styles.statVal}>{selectedHurst}</div>
            </div>
            <div className={styles.statCell}>
              <div className={styles.statLbl}>Regime</div>
              <div className={styles.statVal}>{selectedRegime}</div>
            </div>
            <div className={styles.statCell}>
              <div className={styles.statLbl}>Nearest</div>
              <div className={`${styles.statVal} ${styles.good}`}>{selectedNearest}</div>
            </div>
            <div className={styles.statCell}>
              <div className={styles.statLbl}>Cross-domain</div>
              <div className={styles.statVal}>{selectedCD}</div>
            </div>
          </div>
        </div>

        <div className={styles.rhymes}>
          <div className={styles.rhymesH}>
            <span className="title">Cross-domain rhymes</span>
            <span className="count">{cross.length} matches</span>
          </div>
          <RhymesList
            cross={cross}
            onPick={(idx) => {
              const E = engineRef.current;
              E.STATE.selectedIdx = idx;
              updateSelectionVisuals();
            }}
          />
        </div>
      </aside>

      {/* ── Status bar ──────────────────────────────────────────── */}
      <footer className={styles.status}>
        <span>{pointCount || 0} points</span>
        <span className="sep">/</span>
        <span>{new Set(DATASETS.map((d) => d.domain)).size} domains · {DATASETS.length} datasets</span>
        <span className="sep">/</span>
        <span>{matchText}</span>
        <span className="spacer" />
        <span ref={fpsRef}>— fps</span>
        <span className="sep">/</span>
        <span>drag to orbit · scroll to zoom · click a point</span>
      </footer>

      {/* ── Tweaks floating panel ───────────────────────────────── */}
      <div className={styles.tweaks} data-open={tweaksOpen ? "true" : undefined}>
        <div className={styles.tweaksH}>
          Tweaks
          <button className="x" onClick={() => setTweaksOpen(false)} type="button" aria-label="Close tweaks">
            ×
          </button>
        </div>

        <div className={styles.tweak}>
          <div className={styles.tweakLabel}>
            Scene <span className="v">{sceneMode}</span>
          </div>
          <div className={styles.seg}>
            {(["dark", "light"] as const).map((v) => (
              <button
                key={v}
                type="button"
                data-active={sceneMode === v ? "true" : undefined}
                onClick={() => setSceneMode(v)}
              >
                {v === "dark" ? "Dark" : "Light"}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.tweak}>
          <div className={styles.tweakLabel}>
            Density <span className="v">{DENSITY_LABELS[density]}</span>
          </div>
          <input
            type="range"
            min={0}
            max={2}
            step={1}
            value={density}
            onChange={(e) => setDensity(parseInt(e.target.value, 10) as 0 | 1 | 2)}
          />
        </div>

        <div className={styles.tweak}>
          <div className={styles.tweakLabel}>Show edges</div>
          <div className={styles.seg}>
            {(["on", "off"] as const).map((v) => (
              <button
                key={v}
                type="button"
                data-active={edges === v ? "true" : undefined}
                onClick={() => setEdges(v)}
              >
                {v === "on" ? "On" : "Off"}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.tweak}>
          <div className={styles.tweakLabel}>Point style</div>
          <div className={styles.seg}>
            {(["dot", "ring", "cross"] as const).map((v) => (
              <button
                key={v}
                type="button"
                data-active={pointStyle === v ? "true" : undefined}
                onClick={() => setPointStyle(v)}
              >
                {v === "dot" ? "Dot" : v === "ring" ? "Ring" : "Cross"}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────
   Cross-domain rhymes list — one row per hit, each with an inline
   SVG sparkline drawn on mount (preserves visual parity with design).
   ────────────────────────────────────────────────────────────────── */

interface RhymesListProps {
  cross: Hit[];
  onPick: (idx: number) => void;
}

function RhymesList({ cross, onPick }: RhymesListProps) {
  const sorted = [...cross].sort((a, b) => b.sim - a.sim).slice(0, 10);
  if (sorted.length === 0) {
    return (
      <div className={styles.rhymesEmpty}>
        No cross-domain matches above threshold.<br />Lower threshold or pick another window.
      </div>
    );
  }
  return (
    <>
      {sorted.map((h, r) => (
        <RhymeRow key={h.i} rank={r} hit={h} onPick={onPick} />
      ))}
    </>
  );
}

function RhymeRow({ rank, hit, onPick }: { rank: number; hit: Hit; onPick: (i: number) => void }) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  useEffect(() => {
    if (svgRef.current) drawSpark(svgRef.current, hit.p.series, styles.sparkLineMatch);
  }, [hit]);
  return (
    <div className={styles.rhyme} onClick={() => onPick(hit.i)}>
      <div className={styles.rhymeRank}>{String(rank + 1).padStart(2, "0")}</div>
      <div className={styles.rhymeMain}>
        <div className={styles.rhymeTitle}>
          {hit.p.dsName} — {hit.p.year}
        </div>
        <div className={styles.rhymeSub}>
          {hit.p.domain} · window #{hit.p.idxInDs + 1}
        </div>
      </div>
      <svg ref={svgRef} className={styles.rhymeSpark} viewBox="0 0 60 22" preserveAspectRatio="none" />
      <div className={styles.rhymeScore}>{hit.sim.toFixed(2)}</div>
    </div>
  );
}

/* Suppress unused imports warnings for DOMAIN_ORDER — kept imported for
   future regime-coloured clustering; remove once real embeddings land. */
void DOMAIN_ORDER;
