import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { SplitPane } from "../components/ui/split-pane";

afterEach(cleanup);

describe("SplitPane", () => {
  it("renders both panels", () => {
    render(
      <SplitPane
        direction="horizontal"
        first={<div>First Panel</div>}
        second={<div>Second Panel</div>}
      />,
    );

    expect(screen.getByText("First Panel")).toBeDefined();
    expect(screen.getByText("Second Panel")).toBeDefined();
  });

  it("renders a draggable divider with separator role", () => {
    render(
      <SplitPane
        direction="horizontal"
        first={<div>A</div>}
        second={<div>B</div>}
      />,
    );

    const divider = screen.getByRole("separator");
    expect(divider).toBeDefined();
    expect(divider.getAttribute("aria-orientation")).toBe("vertical");
  });

  it("renders vertical orientation for vertical split", () => {
    render(
      <SplitPane
        direction="vertical"
        first={<div>Top</div>}
        second={<div>Bottom</div>}
      />,
    );

    const divider = screen.getByRole("separator");
    expect(divider.getAttribute("aria-orientation")).toBe("horizontal");
  });

  it("applies default ratio as flex-basis", () => {
    const { container } = render(
      <SplitPane
        direction="horizontal"
        defaultRatio={0.5}
        first={<div>A</div>}
        second={<div>B</div>}
      />,
    );

    const panels = container.querySelectorAll(".split-pane__panel");
    expect(panels.length).toBe(2);
    expect((panels[0] as HTMLElement).style.flexBasis).toBe("50%");
    expect((panels[1] as HTMLElement).style.flexBasis).toBe("50%");
  });

  it("applies className to container", () => {
    const { container } = render(
      <SplitPane
        direction="horizontal"
        className="my-custom-class"
        first={<div>A</div>}
        second={<div>B</div>}
      />,
    );

    expect(container.querySelector(".my-custom-class")).toBeDefined();
  });
});
