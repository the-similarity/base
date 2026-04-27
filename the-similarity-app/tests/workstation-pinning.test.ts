/**
 * Tests for the pinning → forecast contract.
 *
 * Scope: the pure data-layer guarantees that underpin the workstation's
 * pin-driven behavior. We do NOT mount the full Workstation here
 * (too many side effects: resize observers, API probe, canvas engine);
 * instead we verify the invariants that Workstation relies on:
 *
 *   1. `buildCone(effectiveAnalogs, ...)` produces a DIFFERENT cone
 *      than `buildCone(allAnalogs, ...)` when the pinned subset is a
 *      strict subset of the top-K. This is the "pinning changes the
 *      forecast" contract — without it, the feature would be cosmetic.
 *   2. Filtering by pinned id set preserves rank order (the filter is
 *      a subset, not a re-sort).
 *   3. Empty pinned set is a no-op (`effectiveAnalogs === analogs`).
 *
 * If any of these fail in the future, the pinning feature is broken at
 * the semantic level and the UI behavior follows.
 */
import { describe, it, expect } from "vitest";
import { buildCone, type AnalogMatch, type LensScores } from "../lib/data";

/** Minimal lens bundle — values are irrelevant for these tests. */
const ZERO_LENSES: LensScores = {
  lens1: 0, lens2: 0, lens3: 0, lens4: 0, lens5: 0,
  lens6: 0, lens7: 0, lens8: 0, lens9: 0,
};

/**
 * Build a synthetic AnalogMatch with a known priceWindow (ending at 100)
 * and a known `after` trajectory controlled by `afterFactor`. The cone
 * quantiles at time t scale linearly with the spread of afterFactors
 * across the analog set, so we can make the "full set" and "pin subset"
 * cones diverge predictably.
 */
function makeAnalog(id: string, rank: number, afterFactor: number): AnalogMatch {
  const priceWindow = Array.from({ length: 20 }, (_, i) => 80 + i);
  // priceWindow ends at 99 — use 100 as a clean divisor for afterFactor.
  const endPrice = priceWindow[priceWindow.length - 1];
  const after = Array.from({ length: 10 }, (_, t) => endPrice * afterFactor * (1 + t * 0.001));
  return {
    id,
    rank,
    startIdx: 0,
    date: new Date("2026-01-01"),
    endDate: new Date("2026-02-01"),
    label: `Test ${id}`,
    composite: 1 - rank * 0.1,
    lenses: ZERO_LENSES,
    priceWindow,
    after,
    afterReturn: afterFactor - 1,
    note: "",
    scoreBreakdown: null,
  };
}

/** Apply the same filter the Workstation applies when pins are active. */
function effectiveAnalogs(
  analogs: AnalogMatch[],
  pinned: Set<string>,
): AnalogMatch[] {
  if (pinned.size === 0) return analogs;
  const filtered = analogs.filter(a => pinned.has(a.id));
  return filtered.length > 0 ? filtered : analogs;
}

describe("pinning → forecast", () => {
  // Build a deliberately dispersed analog set: half bullish, half bearish.
  // With this setup, pinning only the bullish half should produce a
  // strictly-higher p50 than the full-set cone — a concrete, observable
  // semantic difference.
  const bullish = [
    makeAnalog("bull-a", 0, 1.10),
    makeAnalog("bull-b", 1, 1.08),
    makeAnalog("bull-c", 2, 1.06),
  ];
  const bearish = [
    makeAnalog("bear-a", 3, 0.94),
    makeAnalog("bear-b", 4, 0.92),
    makeAnalog("bear-c", 5, 0.90),
  ];
  const all = [...bullish, ...bearish];
  const queryLastPrice = 100;
  const horizon = 10;

  it("produces a different (higher) cone when only bullish analogs are pinned", () => {
    const allCone = buildCone(all, horizon, queryLastPrice);
    const pinned = new Set(bullish.map(a => a.id));
    const subsetCone = buildCone(effectiveAnalogs(all, pinned), horizon, queryLastPrice);

    // Median of the bullish-only subset must exceed the full-set median:
    // pinning pulled the cone upward because we removed the bearish tail.
    expect(subsetCone.length).toBe(allCone.length);
    for (let i = 0; i < subsetCone.length; i++) {
      expect(subsetCone[i].p50).toBeGreaterThan(allCone[i].p50);
    }
  });

  it("produces a strictly-narrower cone when only bearish analogs are pinned (less dispersion)", () => {
    const allCone = buildCone(all, horizon, queryLastPrice);
    const pinned = new Set(bearish.map(a => a.id));
    const subsetCone = buildCone(effectiveAnalogs(all, pinned), horizon, queryLastPrice);

    // The bearish subset is tighter than the full mix, so the p10-p90
    // spread at the final step must shrink.
    const allWidth = allCone[allCone.length - 1].p90 - allCone[allCone.length - 1].p10;
    const subsetWidth =
      subsetCone[subsetCone.length - 1].p90 - subsetCone[subsetCone.length - 1].p10;
    expect(subsetWidth).toBeLessThan(allWidth);
  });

  it("filtering by pinned ids preserves input rank order (is a subset, not a re-sort)", () => {
    const pinned = new Set(["bull-c", "bull-a"]);
    const filtered = effectiveAnalogs(all, pinned);
    // Both analogs are present.
    expect(filtered.map(a => a.id)).toEqual(["bull-a", "bull-c"]);
    // Ranks are preserved from the source array.
    expect(filtered.map(a => a.rank)).toEqual([0, 2]);
  });

  it("empty pinned set is a no-op — returns the full analog array by reference", () => {
    const filtered = effectiveAnalogs(all, new Set());
    // Strict reference equality: the baseline-unpinned path must not
    // allocate a fresh array, or downstream useMemo identities thrash.
    expect(filtered).toBe(all);
  });

  it("non-empty pins that match zero ids fall back to the full set", () => {
    const pinned = new Set(["does-not-exist", "also-gone"]);
    const filtered = effectiveAnalogs(all, pinned);
    // Same content as the full set (defensive degrade).
    expect(filtered).toBe(all);
  });
});
