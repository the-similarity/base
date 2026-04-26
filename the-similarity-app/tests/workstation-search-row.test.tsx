/**
 * Tests for the manual-search row on the Retrieve workstation.
 *
 * Scope: the pure helpers and light behavioral contract around the
 * Search button + top-K selector + last-run timestamp. The full
 * Workstation render pulls in the LineChart (SVG, resize observers)
 * and the API probe — exercised in the overlay-chart / api tests —
 * so this file sticks to the surfaces we can verify without those.
 */
import { describe, it, expect } from "vitest";
import { formatRelativeTime } from "../components/workstation/workstation";

describe("formatRelativeTime", () => {
  // Anchor "now" so the relative math is deterministic regardless of
  // when the suite runs.
  const now = new Date("2026-04-20T12:00:00Z");

  it('returns "just now" for sub-45-second deltas', () => {
    const when = new Date(now.getTime() - 10_000); // 10s ago
    expect(formatRelativeTime(when, now)).toBe("just now");
  });

  it("rounds down to minute resolution under an hour", () => {
    const when = new Date(now.getTime() - 2 * 60_000 - 15_000); // 2m15s ago
    expect(formatRelativeTime(when, now)).toBe("2m ago");
  });

  it("transitions to hour resolution at 60m", () => {
    const when = new Date(now.getTime() - 90 * 60_000); // 1h30m ago
    expect(formatRelativeTime(when, now)).toBe("1h ago");
  });

  it("transitions to day resolution at 24h", () => {
    const when = new Date(now.getTime() - 2 * 24 * 3600_000); // 2 days ago
    expect(formatRelativeTime(when, now)).toBe("2d ago");
  });

  it("clamps future dates to 'just now' (no negative output)", () => {
    // Clock skew can put `when` slightly ahead of `now`; the label must
    // never render "-1m ago" or otherwise confuse the reader.
    const when = new Date(now.getTime() + 10_000);
    expect(formatRelativeTime(when, now)).toBe("just now");
  });
});
