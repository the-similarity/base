/**
 * Tests for the local-mirror functions in lib/goodruns.ts.
 *
 * These exercise the offline cache layer that powers the workstation's
 * "Saved runs" left-rail panel. The remote ``saveGoodrun`` /
 * ``listGoodruns`` HTTP wrappers are not exercised here — they're tested
 * via the integration tests against the live API.
 *
 * Coverage:
 *   1. Empty / corrupted-storage fallback returns [].
 *   2. saveLocalGoodrun is idempotent on id (replaces, doesn't duplicate).
 *   3. Capacity cap drops oldest beyond GOODRUNS_LOCAL_MAX.
 *   4. removeLocalGoodrun by id; no-op on unknown.
 *   5. Type-guard filters malformed individual records.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  listLocalGoodruns,
  saveLocalGoodrun,
  removeLocalGoodrun,
  writeLocalGoodruns,
  GOODRUNS_LOCAL_KEY,
  GOODRUNS_LOCAL_MAX,
  type GoodrunRecord,
} from "../lib/goodruns";

beforeEach(() => {
  window.localStorage.clear();
});

/**
 * Minimal valid record for tests. ``lens_breakdown`` is intentionally
 * left as an empty object — the type-guard only checks shape, not depth,
 * because the production engine emits a structurally varying breakdown
 * (some lenses absent in offline mode).
 */
function makeRecord(id: string, overrides: Partial<GoodrunRecord> = {}): GoodrunRecord {
  return {
    id,
    saved_at: "2026-04-30T00:00:00.000Z",
    dataset: "stocks/spy/1d",
    horizon: 60,
    match_id: `${id}-match`,
    query: {
      start_idx: 100,
      end_idx: 220,
      start_date: "2025-01-01",
      end_date: "2025-05-01",
      values: [1, 2, 3],
    },
    match: {
      start_idx: 1000,
      end_idx: 1120,
      start_date: "2018-01-01",
      end_date: "2018-05-01",
      values: [4, 5, 6],
    },
    match_after_values: [7, 8, 9],
    lens_breakdown: {} as GoodrunRecord["lens_breakdown"],
    composite: 0.84,
    note: null,
    ...overrides,
  };
}

describe("listLocalGoodruns", () => {
  it("returns [] when storage is empty", () => {
    expect(listLocalGoodruns()).toEqual([]);
  });

  it("returns [] when storage holds non-JSON or non-array", () => {
    window.localStorage.setItem(GOODRUNS_LOCAL_KEY, "garbage{");
    expect(listLocalGoodruns()).toEqual([]);
    window.localStorage.setItem(GOODRUNS_LOCAL_KEY, JSON.stringify({ k: 1 }));
    expect(listLocalGoodruns()).toEqual([]);
  });

  it("filters out malformed individual records", () => {
    const valid = makeRecord("goodrun-1");
    const bad = { id: "goodrun-2" /* missing fields */ };
    window.localStorage.setItem(
      GOODRUNS_LOCAL_KEY,
      JSON.stringify([valid, bad]),
    );
    expect(listLocalGoodruns()).toEqual([valid]);
  });
});

describe("saveLocalGoodrun", () => {
  it("prepends newest-first", () => {
    saveLocalGoodrun(makeRecord("goodrun-a"));
    saveLocalGoodrun(makeRecord("goodrun-b"));
    const all = listLocalGoodruns();
    expect(all.map((r) => r.id)).toEqual(["goodrun-b", "goodrun-a"]);
  });

  it("is idempotent on id (replaces in place, single entry)", () => {
    saveLocalGoodrun(makeRecord("goodrun-a", { composite: 0.1 }));
    saveLocalGoodrun(makeRecord("goodrun-b"));
    saveLocalGoodrun(makeRecord("goodrun-a", { composite: 0.99 }));

    const all = listLocalGoodruns();
    // Only TWO entries — goodrun-a is replaced, not duplicated.
    expect(all.length).toBe(2);
    // The replaced goodrun-a is now newest (writes move records to head).
    expect(all[0].id).toBe("goodrun-a");
    expect(all[0].composite).toBe(0.99);
    expect(all[1].id).toBe("goodrun-b");
  });

  it("trims to GOODRUNS_LOCAL_MAX — oldest dropped first", () => {
    for (let i = 0; i < GOODRUNS_LOCAL_MAX + 5; i++) {
      saveLocalGoodrun(makeRecord(`goodrun-${i}`));
    }
    const all = listLocalGoodruns();
    expect(all.length).toBe(GOODRUNS_LOCAL_MAX);
    expect(all[0].id).toBe(`goodrun-${GOODRUNS_LOCAL_MAX + 4}`);
    expect(all.find((r) => r.id === "goodrun-0")).toBeUndefined();
    expect(all.find((r) => r.id === "goodrun-4")).toBeUndefined();
    // The 5th one we wrote (id 5) is the oldest survivor.
    expect(all[all.length - 1].id).toBe("goodrun-5");
  });
});

describe("removeLocalGoodrun", () => {
  it("removes one record by id", () => {
    saveLocalGoodrun(makeRecord("goodrun-a"));
    saveLocalGoodrun(makeRecord("goodrun-b"));
    const next = removeLocalGoodrun("goodrun-a");
    expect(next.length).toBe(1);
    expect(next[0].id).toBe("goodrun-b");
  });

  it("is a no-op when id is unknown", () => {
    saveLocalGoodrun(makeRecord("goodrun-a"));
    const next = removeLocalGoodrun("goodrun-missing");
    expect(next.length).toBe(1);
    expect(next[0].id).toBe("goodrun-a");
  });
});

describe("writeLocalGoodruns + persistence", () => {
  it("round-trips an arbitrary list", () => {
    const list = [makeRecord("alpha"), makeRecord("beta")];
    writeLocalGoodruns(list);
    expect(listLocalGoodruns()).toEqual(list);
  });
});
