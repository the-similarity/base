import { describe, it, expect } from "vitest";
import { formatSigned, clampRatio, pointsToPath, scalePoints } from "../lib/chart-utils";

describe("formatSigned", () => {
  it("formats positive values with + prefix", () => {
    expect(formatSigned(5.82)).toBe("+5.8%");
  });

  it("formats negative values with - prefix", () => {
    expect(formatSigned(-3.14)).toBe("-3.1%");
  });

  it("formats zero as +0.0%", () => {
    expect(formatSigned(0)).toBe("+0.0%");
  });
});

describe("clampRatio", () => {
  it("returns 0 for value at min", () => {
    expect(clampRatio(10, 10, 20)).toBe(0);
  });

  it("returns 1 for value at max", () => {
    expect(clampRatio(20, 10, 20)).toBe(1);
  });

  it("returns 0.5 for midpoint", () => {
    expect(clampRatio(15, 10, 20)).toBe(0.5);
  });

  it("returns 0.5 when min equals max", () => {
    expect(clampRatio(10, 10, 10)).toBe(0.5);
  });
});

describe("pointsToPath", () => {
  it("creates SVG path from points", () => {
    const points = [
      { x: 0, y: 10 },
      { x: 5, y: 20 },
      { x: 10, y: 15 },
    ];
    const path = pointsToPath(points);
    expect(path).toContain("M 0.00 10.00");
    expect(path).toContain("L 5.00 20.00");
    expect(path).toContain("L 10.00 15.00");
  });

  it("handles single point", () => {
    const path = pointsToPath([{ x: 0, y: 0 }]);
    expect(path).toContain("M 0.00 0.00");
    expect(path).not.toContain("L");
  });
});

describe("scalePoints", () => {
  it("returns correct number of points", () => {
    const result = scalePoints([10, 20, 30], 0, 3, 100, 50, 10, 30);
    expect(result).toHaveLength(3);
  });

  it("maps values to y coordinates inversely", () => {
    const result = scalePoints([10, 30], 0, 2, 100, 50, 10, 30);
    // value 10 (min) should be at y=50 (bottom)
    expect(result[0].y).toBe(50);
    // value 30 (max) should be at y=0 (top)
    expect(result[1].y).toBe(0);
  });
});
