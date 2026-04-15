import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScoreBreakdownBar } from "../components/search/score-breakdown-bar";

describe("ScoreBreakdownBar", () => {
  const sampleBreakdown = {
    dtw: 0.3,
    koopman: 0.5,
    tda: 0.2,
  };

  it("renders segments for each non-zero method", () => {
    const { container } = render(
      <ScoreBreakdownBar breakdown={sampleBreakdown} />
    );
    const segments = container.querySelectorAll(".score-bar-segment");
    expect(segments).toHaveLength(3);
  });

  it("returns null when all scores are zero", () => {
    const { container } = render(
      <ScoreBreakdownBar breakdown={{ dtw: 0, koopman: 0 }} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("returns null for empty breakdown", () => {
    const { container } = render(<ScoreBreakdownBar breakdown={{}} />);
    expect(container.firstChild).toBeNull();
  });

  it("filters out zero-value methods", () => {
    const { container } = render(
      <ScoreBreakdownBar breakdown={{ dtw: 0.5, koopman: 0, tda: 0.5 }} />
    );
    const segments = container.querySelectorAll(".score-bar-segment");
    expect(segments).toHaveLength(2);
  });

  it("shows title with method label and score on each segment", () => {
    const { container } = render(
      <ScoreBreakdownBar breakdown={{ dtw: 0.3 }} />
    );
    const segment = container.querySelector(".score-bar-segment");
    expect(segment?.getAttribute("title")).toContain("DTW");
    expect(segment?.getAttribute("title")).toContain("0.300");
  });

  it("dims other segments on hover", () => {
    const { container } = render(
      <ScoreBreakdownBar breakdown={sampleBreakdown} />
    );
    const segments = container.querySelectorAll(".score-bar-segment");
    fireEvent.mouseEnter(segments[0]);
    // Hovered segment should be full opacity
    expect(segments[0]).toHaveStyle({ opacity: 1 });
    // Other segments should be dimmed
    expect(segments[1]).toHaveStyle({ opacity: 0.4 });
    expect(segments[2]).toHaveStyle({ opacity: 0.4 });
  });

  it("restores opacity on mouse leave", () => {
    const { container } = render(
      <ScoreBreakdownBar breakdown={sampleBreakdown} />
    );
    const segments = container.querySelectorAll(".score-bar-segment");
    fireEvent.mouseEnter(segments[0]);
    fireEvent.mouseLeave(segments[0]);
    expect(segments[1]).toHaveStyle({ opacity: 1 });
  });

  it("shows legend labels for methods with >= 15% share", () => {
    // koopman is 50%, dtw is 30%, tda is 20% — all >= 15% should show
    const { container } = render(
      <ScoreBreakdownBar breakdown={sampleBreakdown} />
    );
    const legendItems = container.querySelectorAll(".score-bar-legend-item");
    expect(legendItems.length).toBe(3);
  });

  it("hides legend for methods under 15% share", () => {
    // dtw is 95%, tda is 5% — tda should be hidden from legend
    const { container } = render(
      <ScoreBreakdownBar breakdown={{ dtw: 0.95, tda: 0.05 }} />
    );
    const legendItems = container.querySelectorAll(".score-bar-legend-item");
    expect(legendItems.length).toBe(1);
  });

  it("uses fallback color for unknown methods", () => {
    // Fallback is now the editorial `--text-muted` token. Inline style resolves
    // to the literal `var(--text-muted)` string because jsdom doesn't compute
    // custom property values, so we assert on the var reference directly.
    const { container } = render(
      <ScoreBreakdownBar breakdown={{ unknown_method: 1.0 }} />
    );
    const segment = container.querySelector<HTMLElement>(".score-bar-segment");
    expect(segment?.style.backgroundColor).toBe("var(--text-muted)");
  });
});
