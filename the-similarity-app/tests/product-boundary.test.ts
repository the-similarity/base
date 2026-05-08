import { describe, expect, it } from "vitest";
import { labRoutes, scannerProductRoutes } from "../lib/product-boundary";

describe("product boundary manifest", () => {
  it("keeps sellable product routes out of the labs namespace", () => {
    expect(scannerProductRoutes.map(route => route.href)).toEqual(["/scanner", "/try", "/ghost5"]);
    expect(scannerProductRoutes.every(route => route.status === "product")).toBe(true);
    expect(scannerProductRoutes.find(route => route.href === "/ghost5")?.owner).toBe("ghost5");
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
