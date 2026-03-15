import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { Sparkline } from "../components/search/sparkline";

describe("Sparkline", () => {
  it("renders an SVG with a polyline for valid data", () => {
    const { container } = render(<Sparkline values={[10, 20, 30, 25]} />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("width", "80");
    expect(svg).toHaveAttribute("height", "24");
    const polyline = container.querySelector("polyline");
    expect(polyline).toBeInTheDocument();
    expect(polyline?.getAttribute("points")).toBeTruthy();
  });

  it("returns null when fewer than 2 values", () => {
    const { container } = render(<Sparkline values={[42]} />);
    expect(container.querySelector("svg")).not.toBeInTheDocument();
  });

  it("returns null for empty array", () => {
    const { container } = render(<Sparkline values={[]} />);
    expect(container.querySelector("svg")).not.toBeInTheDocument();
  });

  it("respects custom width and height", () => {
    const { container } = render(
      <Sparkline values={[1, 2, 3]} width={120} height={40} />
    );
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "120");
    expect(svg).toHaveAttribute("height", "40");
  });

  it("applies custom color to the polyline stroke", () => {
    const { container } = render(
      <Sparkline values={[1, 2, 3]} color="red" />
    );
    const polyline = container.querySelector("polyline");
    expect(polyline).toHaveAttribute("stroke", "red");
  });

  it("handles flat data (all same values)", () => {
    const { container } = render(<Sparkline values={[5, 5, 5, 5]} />);
    const polyline = container.querySelector("polyline");
    expect(polyline).toBeInTheDocument();
    // clampRatio returns 0.5 when min === max, so all y coords should be equal
    const points = polyline?.getAttribute("points") ?? "";
    const yValues = points.split(" ").map((p) => parseFloat(p.split(",")[1]));
    expect(new Set(yValues).size).toBe(1);
  });

  it("is hidden from accessibility tree", () => {
    const { container } = render(<Sparkline values={[1, 2, 3]} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });
});
