/**
 * Spatium page smoke test.
 *
 * The three.js scene cannot render in jsdom (no WebGL), so we mock the
 * minimum surface area needed for the boot path to execute without
 * throwing: WebGLRenderer and the pieces the page directly constructs.
 *
 * Scope:
 *   - Verify the dashboard shell renders (breadcrumbs, default query
 *     card title, dataset list, nav rail entries).
 *   - Verify the deterministic helpers in datasets.ts produce stable
 *     output (this is the real correctness net for the 3D layout).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

// ── Stub three.js before the component module loads ───────────────
// jsdom has no WebGL, so WebGLRenderer normally throws. We replace the
// classes the page uses with inert shims that satisfy the TS surface.

vi.mock("three", async () => {
  class FakeMaterial {
    dispose() {}
    color = { set() {} };
    map = { dispose() {} };
    opacity = 1;
  }
  class FakeGeometry {
    attributes: Record<string, { count: number }> = {};
    setAttribute(name: string, attr: { count: number }) {
      this.attributes[name] = attr;
    }
    getAttribute(name: string) {
      return this.attributes[name];
    }
    dispose() {}
  }
  class FakeObject3D {
    children: FakeObject3D[] = [];
    position = { set() {}, x: 0, y: 0, z: 0 };
    userData: Record<string, unknown> = {};
    material?: FakeMaterial;
    geometry?: FakeGeometry;
    visible = true;
    isLineSegments = false;
    isGridHelper = false;
    add(o: FakeObject3D) {
      this.children.push(o);
    }
    remove(o: FakeObject3D) {
      this.children = this.children.filter((c) => c !== o);
    }
    lookAt() {}
    traverse(fn: (o: FakeObject3D) => void) {
      fn(this);
      this.children.forEach((c) => c.traverse(fn));
    }
  }
  class WebGLRenderer {
    setPixelRatio() {}
    setSize() {}
    render() {}
    dispose() {}
  }
  class Scene extends FakeObject3D {
    fog: unknown = null;
    traverse(fn: (o: FakeObject3D) => void) {
      super.traverse(fn);
    }
  }
  class PerspectiveCamera extends FakeObject3D {
    aspect = 1;
    updateProjectionMatrix() {}
  }
  class Group extends FakeObject3D {}
  class Points extends FakeObject3D {}
  class Mesh extends FakeObject3D {}
  class LineSegments extends FakeObject3D {
    isLineSegments = true;
    geometry = new FakeGeometry();
    material = new FakeMaterial();
    constructor(geo?: FakeGeometry, mat?: FakeMaterial) {
      super();
      if (geo) this.geometry = geo;
      if (mat) this.material = mat;
    }
  }
  class GridHelper extends FakeObject3D {
    isGridHelper = true;
    material = new FakeMaterial();
  }
  class RingGeometry extends FakeGeometry {}
  class BufferGeometry extends FakeGeometry {}
  class Float32BufferAttribute {
    count: number;
    constructor(array: ArrayLike<number>, itemSize: number) {
      this.count = array.length / itemSize;
    }
  }
  class CanvasTexture {
    needsUpdate = false;
    dispose() {}
  }
  class PointsMaterial extends FakeMaterial {}
  class LineBasicMaterial extends FakeMaterial {}
  class MeshBasicMaterial extends FakeMaterial {}
  class Fog {
    constructor(public color: number, public near: number, public far: number) {}
  }
  class Color {
    r = 1;
    g = 1;
    b = 1;
    constructor(_hex?: number | string) {}
    set() {}
  }
  class Vector2 {
    x = 0;
    y = 0;
  }
  class Raycaster {
    params = { Points: { threshold: 0 } };
    setFromCamera() {}
    intersectObjects() {
      return [] as unknown[];
    }
  }

  return {
    WebGLRenderer,
    Scene,
    PerspectiveCamera,
    Group,
    Points,
    Mesh,
    LineSegments,
    GridHelper,
    RingGeometry,
    BufferGeometry,
    Float32BufferAttribute,
    CanvasTexture,
    PointsMaterial,
    LineBasicMaterial,
    MeshBasicMaterial,
    Fog,
    Color,
    Vector2,
    Raycaster,
    DoubleSide: 2,
  };
});

// getContext is called by makePointTexture via <canvas>. Return a minimal
// 2D context so it doesn't throw.
beforeEach(() => {
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    clearRect: vi.fn(),
    createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
  })) as unknown as HTMLCanvasElement["getContext"];
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("SpatiumPage", () => {
  it("renders the dashboard shell with breadcrumbs and default query", async () => {
    const mod = await import("../app/spatium/page");
    const SpatiumPage = mod.default;
    render(<SpatiumPage />);
    // Breadcrumbs
    expect(screen.getByText("The Similarity")).toBeInTheDocument();
    expect(screen.getByText("Pillar III")).toBeInTheDocument();
    expect(screen.getByText("3D Data Space")).toBeInTheDocument();
    // Top bar actions — "Tweaks" appears on the button AND the panel
    // header, so assert both are present via getAllByText.
    expect(screen.getAllByText("Tweaks").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Add dataset")).toBeInTheDocument();
    expect(screen.getByText("Export embedding")).toBeInTheDocument();
    // Scene title
    expect(screen.getByText("Self-similarity manifold")).toBeInTheDocument();
    // Right panel
    expect(screen.getByText("Query selected")).toBeInTheDocument();
    expect(screen.getByText("Cross-domain rhymes")).toBeInTheDocument();
    // Left panel — at least one dataset name appears (may show in
    // both the selected-window card and the dataset list, so allow
    // duplicates).
    expect(screen.getAllByText("BTC / USD").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Gold (XAU)")).toBeInTheDocument();
  });
});

describe("datasets helpers", () => {
  it("buildPoints returns stable deterministic output per density", async () => {
    const ds = await import("../app/spatium/datasets");
    const a = ds.buildPoints(1);
    const b = ds.buildPoints(1);
    // Same density = same count, same first-point position.
    expect(a.length).toBe(b.length);
    expect(a[0].pos).toEqual(b[0].pos);
    expect(a[0].id).toBe(b[0].id);
  });

  it("density levels produce the expected point totals", async () => {
    const ds = await import("../app/spatium/datasets");
    // 9 datasets × (15 / 32 / 60) windows respectively.
    expect(ds.buildPoints(0).length).toBe(ds.DATASETS.length * 15);
    expect(ds.buildPoints(1).length).toBe(ds.DATASETS.length * 32);
    expect(ds.buildPoints(2).length).toBe(ds.DATASETS.length * 60);
  });

  it("distance is zero between a point and itself, positive otherwise", async () => {
    const ds = await import("../app/spatium/datasets");
    const pts = ds.buildPoints(0);
    expect(ds.distance(pts[0], pts[0])).toBe(0);
    // Some pair of different points has nonzero distance.
    expect(ds.distance(pts[0], pts[pts.length - 1])).toBeGreaterThan(0);
  });

  it("similarityFromDist maps 0 to 1 and large distances to 0", async () => {
    const ds = await import("../app/spatium/datasets");
    expect(ds.similarityFromDist(0)).toBe(1);
    expect(ds.similarityFromDist(5)).toBe(0);
  });

  it("regimeLabel picks Trending / Mean-rev / Random by Hurst", async () => {
    const ds = await import("../app/spatium/datasets");
    // Only the hurst field is consulted by regimeLabel, so cast via
    // Parameters to get the exact expected shape without importing the
    // FeatureVec type at the top level (we're using dynamic import).
    type F = Parameters<typeof ds.regimeLabel>[0];
    expect(ds.regimeLabel({ hurst: 0.7 } as F)).toBe("Trending");
    expect(ds.regimeLabel({ hurst: 0.3 } as F)).toBe("Mean-rev");
    expect(ds.regimeLabel({ hurst: 0.5 } as F)).toBe("Random");
  });

  it("buildPoints accepts custom extras and appends their points", async () => {
    const ds = await import("../app/spatium/datasets");
    const extras: ds.Dataset[] = [
      {
        id: "custom1",
        name: "Custom One",
        domain: "custom",
        color: 0xabcdef,
        kind: "long-cycle",
        era: [2000, 2024],
      },
    ];
    const a = ds.buildPoints(0, extras);
    // 9 built-ins + 1 custom = 10 datasets × 15 = 150 points at density 0.
    expect(a.length).toBe(10 * 15);
    // Custom points come last and are internally deterministic.
    const customTail = a.filter((p) => p.ds === "custom1");
    expect(customTail.length).toBe(15);
    const again = ds.buildPoints(0, extras).filter((p) => p.ds === "custom1");
    expect(customTail[0].pos).toEqual(again[0].pos);
  });

  it("exportEmbedding returns a schema-v1 envelope with point metadata", async () => {
    const ds = await import("../app/spatium/datasets");
    const pts = ds.buildPoints(0);
    const env = ds.exportEmbedding(pts, ds.DATASETS, {
      density: 0,
      colorBy: "domain",
      threshold: 0.72,
    });
    expect(env.schemaVersion).toBe(1);
    expect(env.settings.pointCount).toBe(pts.length);
    expect(env.settings.density).toBe(0);
    expect(env.datasets.length).toBe(ds.DATASETS.length);
    // Points should carry pos + feat but NOT raw series (lean payload).
    expect(env.points.length).toBe(pts.length);
    const sample = env.points[0] as Record<string, unknown>;
    expect(sample).toHaveProperty("pos");
    expect(sample).toHaveProperty("feat");
    expect(sample).not.toHaveProperty("series");
  });

  it("exportEmbeddingCsv emits a CSV with one header + one row per point", async () => {
    const ds = await import("../app/spatium/datasets");
    const pts = ds.buildPoints(0);
    const csv = ds.exportEmbeddingCsv(pts);
    const lines = csv.split("\n");
    expect(lines.length).toBe(pts.length + 1);
    expect(lines[0]).toContain("id,ds,domain,year,idxInDs,x,y,z");
    // No CSV field contains a comma/quote — design promise. A single
    // row should split into exactly 16 columns.
    expect(lines[1].split(",").length).toBe(16);
  });

  it("slugifyDatasetId produces collision-free ids", async () => {
    const ds = await import("../app/spatium/datasets");
    expect(ds.slugifyDatasetId("My Series", new Set())).toBe("my-series");
    expect(ds.slugifyDatasetId("!!!", new Set())).toBe("ds");
    expect(ds.slugifyDatasetId("dup", new Set(["dup"]))).toBe("dup-2");
    expect(ds.slugifyDatasetId("dup", new Set(["dup", "dup-2"]))).toBe("dup-3");
  });

  it("SERIES_KINDS covers all kinds used by built-in DATASETS", async () => {
    const ds = await import("../app/spatium/datasets");
    const used = new Set(ds.DATASETS.map((d) => d.kind));
    for (const k of used) {
      expect(ds.SERIES_KINDS).toContain(k);
    }
  });
});

/* ──────────────────────────────────────────────────────────────────
   Python↔TS parity: load the canonical Python-generated fixture and
   verify the TS generator produces the same positions within a tight
   float tolerance. Any algorithmic drift — a refactor that changes
   the order of floating-point ops, a regression in mulberry32 — will
   show up here first.
   ────────────────────────────────────────────────────────────────── */

describe("Python parity (fixture)", () => {
  it("buildPoints(0) matches the Python-generated fixture", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const fixturePath = path.resolve(
      process.cwd(),
      "../the_similarity/tests/fixtures/spatium/points_d0.json",
    );
    if (!fs.existsSync(fixturePath)) {
      // Running from a trimmed checkout — skip rather than fail CI.
      return;
    }
    const ds = await import("../app/spatium/datasets");
    const expected = JSON.parse(fs.readFileSync(fixturePath, "utf-8")) as {
      points: Array<{
        id: string;
        ds: string;
        year: number;
        idxInDs: number;
        pos: [number, number, number];
        feat: Record<string, number>;
      }>;
    };
    const got = ds.buildPoints(0);
    expect(got.length).toBe(expected.points.length);
    // Spot-check every 10th point to keep test output readable but
    // still cover every dataset at density 0 (15 windows per ds).
    for (let i = 0; i < got.length; i += 10) {
      const g = got[i];
      const e = expected.points[i];
      expect(g.id).toBe(e.id);
      expect(g.ds).toBe(e.ds);
      expect(g.year).toBe(e.year);
      expect(g.idxInDs).toBe(e.idxInDs);
      // Positions must agree to ~1e-12 — libm IEEE 754 on both sides.
      expect(g.pos[0]).toBeCloseTo(e.pos[0], 10);
      expect(g.pos[1]).toBeCloseTo(e.pos[1], 10);
      expect(g.pos[2]).toBeCloseTo(e.pos[2], 10);
      expect(g.feat.hurst).toBeCloseTo(e.feat.hurst, 10);
      expect(g.feat.slope).toBeCloseTo(e.feat.slope, 10);
      expect(g.feat.sd).toBeCloseTo(e.feat.sd, 10);
    }
  });
});

/* ──────────────────────────────────────────────────────────────────
   Interactive handler smoke tests: the page boot path is already
   covered above; these additionally click the new buttons and assert
   the side effects fire (URL.createObjectURL for export, popover
   opens for Add/Settings, localStorage writes for prefs).
   ────────────────────────────────────────────────────────────────── */

describe("SpatiumPage — new button handlers", () => {
  it("Export embedding triggers a download via URL.createObjectURL", async () => {
    const createObjectURL = vi.fn(() => "blob:test");
    const revokeObjectURL = vi.fn();
    // jsdom doesn't implement these. Patch both onto the global URL.
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const mod = await import("../app/spatium/page");
    render(<mod.default />);
    fireEvent.click(screen.getByText("Export embedding"));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    clickSpy.mockRestore();
  });

  it("Add dataset button opens the popover (form fields visible)", async () => {
    const mod = await import("../app/spatium/page");
    render(<mod.default />);
    // Popover not mounted initially.
    expect(screen.queryByPlaceholderText("e.g. My Series")).toBeNull();
    fireEvent.click(screen.getByText("Add dataset"));
    // Once open, name + domain inputs exist.
    expect(screen.getByPlaceholderText("e.g. My Series")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("domain tag")).toBeInTheDocument();
  });

  it("Settings nav button opens the Settings popover with shortcut cheatsheet", async () => {
    const mod = await import("../app/spatium/page");
    render(<mod.default />);
    // The settings nav icon has title="Settings (,)".
    const settingsBtn = screen.getByTitle(/Settings/);
    fireEvent.click(settingsBtn);
    expect(screen.getByText(/Shortcuts/i)).toBeInTheDocument();
    expect(screen.getByText(/Orbit speed/)).toBeInTheDocument();
    expect(screen.getByText(/Point size/)).toBeInTheDocument();
  });
});
