import { describe, expect, it } from "vitest";
import { labRoutes, scannerProductRoutes } from "../lib/product-boundary";

describe("product boundary manifest", () => {
  it("keeps scanner product routes out of the labs namespace", () => {
    expect(scannerProductRoutes.map(route => route.href)).toEqual(["/scanner", "/try"]);
    expect(scannerProductRoutes.every(route => route.owner === "scanner" && route.status === "product")).toBe(true);
  });

  it("quarantines legacy product ideas under /labs", () => {
    expect(labRoutes.length).toBeGreaterThan(0);
    expect(labRoutes.every(route => route.href.startsWith("/labs/"))).toBe(true);
    expect(labRoutes.every(route => route.owner === "labs" && route.status === "lab")).toBe(true);
  });

  it("does not leave old lab URLs as the canonical route", () => {
    const canonicalUrls = new Set(labRoutes.map(route => route.href));
    for (const route of labRoutes) {
      expect(route.legacyHref).toBeTruthy();
      expect(canonicalUrls.has(route.legacyHref ?? "")).toBe(false);
    }
  });
});
