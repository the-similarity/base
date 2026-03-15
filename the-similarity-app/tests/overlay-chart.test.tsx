import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OverlayChart } from "../components/search/overlay-chart";

describe("OverlayChart", () => {
  const queryValues = [100, 105, 98, 110, 103];
  const matchValues = [50, 55, 48, 60, 53];

  it("renders an SVG with role=img and accessible label", () => {
    render(<OverlayChart queryValues={queryValues} matchValues={matchValues} />);
    const svg = screen.getByRole("img");
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute(
      "aria-label",
      "Query and match overlay chart"
    );
  });

  it("renders two path elements (query + match lines)", () => {
    const { container } = render(
      <OverlayChart queryValues={queryValues} matchValues={matchValues} />
    );
    const paths = container.querySelectorAll("path");
    expect(paths).toHaveLength(2);
  });

  it("renders grid lines", () => {
    const { container } = render(
      <OverlayChart queryValues={queryValues} matchValues={matchValues} />
    );
    const gridLines = container.querySelectorAll(".chart-grid-line");
    expect(gridLines).toHaveLength(4);
  });

  it("uses default labels when none provided", () => {
    const { container } = render(
      <OverlayChart queryValues={queryValues} matchValues={matchValues} />
    );
    const legendItems = container.querySelectorAll(".legend-item");
    const labels = Array.from(legendItems).map((el) => el.textContent);
    expect(labels).toContain("Query");
    expect(labels).toContain("Match");
  });

  it("uses custom labels when provided", () => {
    const { container } = render(
      <OverlayChart
        queryValues={queryValues}
        matchValues={matchValues}
        queryLabel="My query"
        matchLabel="Match #3"
      />
    );
    const legendItems = container.querySelectorAll(".legend-item");
    const labels = Array.from(legendItems).map((el) => el.textContent);
    expect(labels).toContain("My query");
    expect(labels).toContain("Match #3");
  });

  it("displays bar count from the longer series", () => {
    const { container } = render(
      <OverlayChart
        queryValues={[1, 2, 3]}
        matchValues={[1, 2, 3, 4, 5]}
      />
    );
    const axisLabels = container.querySelectorAll(".chart-axis-label");
    const texts = Array.from(axisLabels).map((el) => el.textContent);
    expect(texts.some((t) => t?.includes("5"))).toBe(true);
  });

  it("renders legend swatches for query and match", () => {
    const { container } = render(
      <OverlayChart queryValues={queryValues} matchValues={matchValues} />
    );
    expect(container.querySelector(".legend-swatch.query")).toBeInTheDocument();
    expect(container.querySelector(".legend-swatch.match")).toBeInTheDocument();
  });

  it("handles flat data without crashing", () => {
    const { container } = render(
      <OverlayChart queryValues={[5, 5, 5]} matchValues={[10, 10, 10]} />
    );
    const paths = container.querySelectorAll("path");
    expect(paths).toHaveLength(2);
  });
});
