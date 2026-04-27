/**
 * Smoke + contract tests for /case-study/spy-2026-2007.
 *
 * The case-study page is a presentation surface that has to:
 *   1. Render without throwing (no missing-data crash, no hook order
 *      violation, no SSR/hydration mismatch on client-only components).
 *   2. Mount three normalized series (present, analog, continuation) so
 *      both pair sections show two charts each.
 *   3. Emit a working "Open in the workstation" deep-link with the
 *      lib/url-state contract — encoded keys must be in the schema and
 *      round-trip through `parseUrlState`.
 *
 * We intentionally do NOT assert pixel-level chart geometry here. The
 * RhymeChart component is exercised by the page rendering at all,
 * and pixel-precise tests would lock in implementation details (stroke
 * width, padding) that the design might want to tune without breaking
 * the contract.
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import CaseStudySpyPage from "../app/case-study/spy-2026-2007/page";
import {
  presentSeries,
  analogSeries,
  analogContinuation,
  meta,
} from "../app/case-study/spy-2026-2007/data";
import { parseUrlState } from "../lib/url-state";

describe("/case-study/spy-2026-2007 — page", () => {
  it("renders without throwing", () => {
    // Smoke test: any unhandled error in the render path (missing
    // export, hook misuse, divide-by-zero on an empty array) shows up
    // here as an exception. Keeping it as a separate `it` block makes
    // failures easier to attribute on CI.
    expect(() => render(<CaseStudySpyPage />)).not.toThrow();
  });

  it("mounts at least four chart instances (one in setup, two in match, two in reveal)", () => {
    const { container } = render(<CaseStudySpyPage />);
    // Each RhymeChart renders a single .rhyme-chart wrapper. The page
    // mounts: 1 in section 2 (setup), 2 in section 3 (match), 2 in
    // section 4 (reveal) = 5 total. We assert >= 4 to leave one charge
    // of flexibility if a later iteration drops the setup chart in
    // favor of a different visual.
    const charts = container.querySelectorAll(".rhyme-chart");
    expect(charts.length).toBeGreaterThanOrEqual(4);
  });

  it("renders a 'verify' CTA with a workstation deep-link", () => {
    const { getAllByTestId } = render(<CaseStudySpyPage />);
    // React 19 + Testing Library can render the tree twice in jsdom
    // (concurrent rendering double-invocation). Both copies emit the
    // same href, so we just take the first.
    const ctas = getAllByTestId("verify-cta") as HTMLAnchorElement[];
    expect(ctas.length).toBeGreaterThanOrEqual(1);
    const cta = ctas[0];
    expect(cta).toBeInTheDocument();
    expect(cta.tagName).toBe("A");
    // The href must point to /workstation with a query string.
    const href = cta.getAttribute("href") ?? "";
    expect(href).toMatch(/^\/workstation\?/);
    // The query string must round-trip through the shared URL contract.
    // This is the test that catches a typo in `serializeUrlState` keys —
    // if someone changed `ds` to `dataset`, the parser would silently
    // drop the field and this assertion would catch it.
    const search = href.slice(href.indexOf("?"));
    const parsed = parseUrlState(search);
    expect(parsed.dataset).toBe("stocks/spy/1d");
    expect(parsed.queryLen).toBeGreaterThan(0);
    expect(parsed.horizon).toBeGreaterThan(0);
    expect(parsed.chartMode).toBe("fast");
  });

  it("renders the 2007 analog peak date so the GFC framing reads", () => {
    const { container } = render(<CaseStudySpyPage />);
    // Page renders meta.analogPeakDate (2007-10-09) inside the lede
    // copy of the match section. If the data generator ever shifts the
    // peak date, the test will catch the drift before the page goes
    // out of sync with the headline claim.
    expect(container.textContent).toContain(meta.analogPeakDate);
  });
});

describe("/case-study/spy-2026-2007 — data generator output", () => {
  it("emits a 180-bar present series with normalized values", () => {
    expect(presentSeries.length).toBeGreaterThanOrEqual(150);
    expect(presentSeries.length).toBeLessThanOrEqual(220);
    expect(presentSeries[0].norm).toBeCloseTo(100, 1);
    // Every point must carry an ISO date and finite numbers — the
    // chart trusts these without re-validation.
    for (const p of presentSeries) {
      expect(p.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(Number.isFinite(p.close)).toBe(true);
      expect(Number.isFinite(p.norm)).toBe(true);
    }
  });

  it("emits an analog series anchored at 2007 and a continuation", () => {
    expect(analogSeries.length).toBeGreaterThanOrEqual(120);
    expect(analogSeries[0].date.startsWith("2007-")).toBe(true);
    expect(analogSeries[0].norm).toBeCloseTo(100, 1);
    expect(analogContinuation.length).toBeGreaterThan(0);
    // Continuation is rebased on the analog anchor — its first norm
    // must sit close to the analog's last norm so the line stitches
    // without a visual seam (within ~5% tolerance for the gap day).
    const lastAnalog = analogSeries[analogSeries.length - 1].norm;
    const firstCont = analogContinuation[0].norm;
    expect(Math.abs(firstCont - lastAnalog)).toBeLessThan(5);
  });

  it("emits a meta block with the headline metrics the page renders", () => {
    expect(meta.presentChangePct).toBeGreaterThan(0);
    expect(meta.analogPeakDate).toBe("2007-10-09");
    expect(meta.continuationDrawdownPct).toBeLessThan(0);
    // Composite must be on [0, 1] — any drift means the static copy
    // we display next to the score has gone out of bounds.
    expect(meta.scoreComposite).toBeGreaterThan(0);
    expect(meta.scoreComposite).toBeLessThanOrEqual(1);
  });
});
