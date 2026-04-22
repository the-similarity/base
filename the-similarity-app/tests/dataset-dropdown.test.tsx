/**
 * Tests for the workstation dataset dropdown helpers and the offline
 * synthetic entry.
 *
 * Scope: the pure functions driving the dropdown — symbol / asset-class
 * filtering, staleness detection, safe ISO parsing, human-readable
 * formatting, and the static offline catalog shape.
 *
 * Why not render the full Workstation? The same reason `workstation-
 * search-row.test.tsx` sticks to helpers: the Workstation pulls in the
 * LineChart (SVG, resize observers) and the /healthz probe, so unit
 * coverage lives on the pure surface.
 */
import { describe, it, expect } from "vitest";
import {
  filterCatalog,
  formatBarCount,
  parseIsoOrNull,
  isStale,
  formatShortDate,
  formatUpdatedAt,
  offlineSyntheticCatalog,
} from "../components/workstation/workstation";
import type { CatalogItem } from "../lib/types";

// Factory helper — builds a catalog item with defaults so each test
// only needs to override the fields it cares about.
function mkItem(overrides: Partial<CatalogItem> = {}): CatalogItem {
  return {
    assetClass: "stocks",
    symbol: "spy",
    timeframe: "1d",
    source: "Yahoo Finance",
    rowCount: 7_500,
    startTimestamp: "1995-01-03T00:00:00+00:00",
    endTimestamp: "2026-04-20T00:00:00+00:00",
    lastUpdatedAt: "2026-04-20T16:00:00+00:00",
    frequency: "1 day",
    ...overrides,
  };
}

describe("filterCatalog", () => {
  const items: CatalogItem[] = [
    mkItem({ symbol: "spy", assetClass: "stocks" }),
    mkItem({ symbol: "btcusd", assetClass: "crypto" }),
    mkItem({ symbol: "gold", assetClass: "commodities" }),
  ];

  it("returns everything for an empty query", () => {
    expect(filterCatalog(items, "")).toHaveLength(3);
    expect(filterCatalog(items, "   ")).toHaveLength(3);
  });

  it("matches by symbol substring (case-insensitive)", () => {
    const hit = filterCatalog(items, "BTC");
    expect(hit).toHaveLength(1);
    expect(hit[0].symbol).toBe("btcusd");
  });

  it("matches by asset class substring", () => {
    const hit = filterCatalog(items, "commod");
    expect(hit).toHaveLength(1);
    expect(hit[0].symbol).toBe("gold");
  });

  it("returns empty when no match", () => {
    expect(filterCatalog(items, "xyzzy")).toHaveLength(0);
  });
});

describe("formatBarCount", () => {
  it("inserts thousands separators", () => {
    expect(formatBarCount(7_500)).toBe("7,500 bars");
    expect(formatBarCount(1_234_567)).toBe("1,234,567 bars");
  });

  it("returns empty string for zero / negative counts", () => {
    expect(formatBarCount(0)).toBe("");
    expect(formatBarCount(-1)).toBe("");
  });
});

describe("parseIsoOrNull", () => {
  it("parses a valid ISO timestamp", () => {
    const d = parseIsoOrNull("2026-04-20T16:00:00+00:00");
    expect(d).toBeInstanceOf(Date);
    expect(d?.toISOString()).toBe("2026-04-20T16:00:00.000Z");
  });

  it("returns null for null / undefined / empty", () => {
    expect(parseIsoOrNull(null)).toBeNull();
    expect(parseIsoOrNull(undefined)).toBeNull();
    expect(parseIsoOrNull("")).toBeNull();
  });

  it("returns null for garbage input (no 'Invalid Date' leak)", () => {
    expect(parseIsoOrNull("not-a-date")).toBeNull();
  });
});

describe("isStale", () => {
  // Anchor "now" so test math is deterministic.
  const now = new Date("2026-04-20T12:00:00Z");

  it("flags daily datasets updated >48h ago", () => {
    const item = mkItem({
      timeframe: "1d",
      lastUpdatedAt: "2026-04-17T00:00:00Z", // ~84h ago
    });
    expect(isStale(item, now)).toBe(true);
  });

  it("does not flag fresh daily datasets", () => {
    const item = mkItem({
      timeframe: "1d",
      lastUpdatedAt: "2026-04-20T00:00:00Z", // 12h ago
    });
    expect(isStale(item, now)).toBe(false);
  });

  it("flags intraday datasets at the same 48h threshold", () => {
    const item = mkItem({
      timeframe: "1h",
      lastUpdatedAt: "2026-04-18T00:00:00Z", // ~60h ago
    });
    expect(isStale(item, now)).toBe(true);
  });

  it("never flags weekly or longer timeframes", () => {
    // Weekly data is *expected* to be days old between bars.
    const item = mkItem({
      timeframe: "1w",
      lastUpdatedAt: "2026-04-01T00:00:00Z", // ~19 days ago
    });
    expect(isStale(item, now)).toBe(false);
  });

  it("returns false when lastUpdatedAt is missing (no noise)", () => {
    const item = mkItem({ lastUpdatedAt: null });
    expect(isStale(item, now)).toBe(false);
  });

  it("respects a custom threshold", () => {
    const item = mkItem({
      timeframe: "1h",
      lastUpdatedAt: "2026-04-19T00:00:00Z", // ~36h ago
    });
    expect(isStale(item, now, 24)).toBe(true);
    expect(isStale(item, now, 48)).toBe(false);
  });
});

describe("formatShortDate", () => {
  it("formats ISO timestamps as YYYY-MM-DD", () => {
    expect(formatShortDate("2026-04-20T16:00:00Z")).toBe("2026-04-20");
  });

  it("returns em-dash for null / undefined / invalid", () => {
    expect(formatShortDate(null)).toBe("\u2014");
    expect(formatShortDate(undefined)).toBe("\u2014");
    expect(formatShortDate("garbage")).toBe("\u2014");
  });
});

describe("formatUpdatedAt", () => {
  it("formats as 'MMM DD, YYYY · HH:MM' in UTC", () => {
    // Explicit UTC so the test doesn't depend on the CI timezone.
    expect(formatUpdatedAt("2026-04-22T16:00:00Z")).toBe(
      "Apr 22, 2026 \u00B7 16:00",
    );
  });

  it("handles single-digit minutes with a zero pad", () => {
    expect(formatUpdatedAt("2026-01-05T03:05:00Z")).toBe(
      "Jan 5, 2026 \u00B7 03:05",
    );
  });

  it("returns em-dash for null", () => {
    expect(formatUpdatedAt(null)).toBe("\u2014");
  });
});

describe("offlineSyntheticCatalog", () => {
  it("returns a single SPY entry with synthetic source marker", () => {
    const entries = offlineSyntheticCatalog();
    expect(entries).toHaveLength(1);
    const [spy] = entries;
    expect(spy.symbol).toBe("spy");
    expect(spy.timeframe).toBe("1d");
    expect(spy.source).toMatch(/synthetic/i);
    // Synthetic entries have no real metadata — callers must render
    // "—" rather than showing a fake date range.
    expect(spy.startTimestamp).toBeNull();
    expect(spy.endTimestamp).toBeNull();
    expect(spy.lastUpdatedAt).toBeNull();
  });

  it("returns independent objects on each call (no shared mutation)", () => {
    const a = offlineSyntheticCatalog();
    const b = offlineSyntheticCatalog();
    a[0].symbol = "MUTATED";
    expect(b[0].symbol).toBe("spy");
  });
});
