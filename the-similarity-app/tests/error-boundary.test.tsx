import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
import { ErrorBoundary } from "../components/error-boundary";

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test explosion");
  return <div>Child rendered OK</div>;
}

describe("ErrorBoundary", () => {
  const originalError = console.error;
  beforeAll(() => {
    console.error = vi.fn();
  });
  afterAll(() => {
    console.error = originalError;
  });
  afterEach(() => {
    cleanup();
  });

  it("renders children when no error occurs", () => {
    const { container } = render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={false} />
      </ErrorBoundary>
    );
    expect(within(container).getByText("Child rendered OK")).toBeInTheDocument();
  });

  it("shows default fallback UI when child throws", () => {
    const { container } = render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(within(container).getByText("Something went wrong")).toBeInTheDocument();
    expect(within(container).getByText("Test explosion")).toBeInTheDocument();
    expect(within(container).queryByText("Child rendered OK")).not.toBeInTheDocument();
  });

  it("shows custom fallback when provided", () => {
    const { container } = render(
      <ErrorBoundary fallback={<div>Custom error page</div>}>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(within(container).getByText("Custom error page")).toBeInTheDocument();
    expect(within(container).queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  it("shows a Try again button in the error state", () => {
    const { container } = render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>
    );
    const btn = within(container).getByRole("button", { name: "Try again" });
    expect(btn).toBeInTheDocument();
  });
});
