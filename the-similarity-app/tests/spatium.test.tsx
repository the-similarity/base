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
import { cleanup, render, screen } from "@testing-library/react";

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
});
