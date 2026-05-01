/**
 * Tests for lib/notebook.ts — durable left-rail notebook entries.
 *
 * Coverage:
 *   1. Empty / SSR / corrupted-storage fallback returns [].
 *   2. addEntry trims text, rejects empty, prepends newest-first.
 *   3. Capacity cap drops oldest beyond MAX_ENTRIES.
 *   4. removeEntry by id, no-op on unknown.
 *   5. Persistence — what the previous call wrote, the next call reads.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  listEntries,
  addEntry,
  removeEntry,
  writeAll,
  STORAGE_KEY,
  MAX_ENTRIES,
  type NotebookEntry,
} from "../lib/notebook";

beforeEach(() => {
  // Storage is shared across tests in the same file — reset between each
  // so test order doesn't matter. The mock shim from tests/setup.ts
  // exposes a real Storage-shaped API.
  window.localStorage.clear();
});

describe("listEntries", () => {
  it("returns [] when storage is empty", () => {
    expect(listEntries()).toEqual([]);
  });

  it("returns [] when storage holds non-JSON", () => {
    window.localStorage.setItem(STORAGE_KEY, "not json{{");
    expect(listEntries()).toEqual([]);
  });

  it("returns [] when storage holds a non-array", () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ foo: 1 }));
    expect(listEntries()).toEqual([]);
  });

  it("filters out malformed individual entries", () => {
    // One valid + one missing-field record — only the valid one survives.
    const valid: NotebookEntry = {
      id: "nb-1-aaaa",
      ts: "2026-04-30T00:00:00.000Z",
      text: "hello",
      dataset: "stocks/spy/1d",
      windowStart: 100,
      windowEnd: 200,
    };
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([valid, { id: "nb-2", ts: "x" /* missing fields */ }]),
    );
    expect(listEntries()).toEqual([valid]);
  });
});

describe("addEntry", () => {
  it("trims text and prepends newest-first", () => {
    const after1 = addEntry({
      text: "first note",
      dataset: "stocks/spy/1d",
      windowStart: 1000,
      windowEnd: 1120,
    });
    const after2 = addEntry({
      text: "  second note  ",
      dataset: "stocks/spy/1d",
      windowStart: 1200,
      windowEnd: 1320,
    });

    expect(after1.length).toBe(1);
    expect(after2.length).toBe(2);
    // Newest first
    expect(after2[0].text).toBe("second note");
    expect(after2[1].text).toBe("first note");
  });

  it("rejects whitespace-only entries (does not mutate list)", () => {
    addEntry({
      text: "real entry",
      dataset: "stocks/spy/1d",
      windowStart: 0,
      windowEnd: 1,
    });
    const before = listEntries();
    const after = addEntry({
      text: "   \n  ",
      dataset: "stocks/spy/1d",
      windowStart: 0,
      windowEnd: 1,
    });
    expect(after).toEqual(before);
    expect(listEntries().length).toBe(1);
  });

  it("trims to MAX_ENTRIES — oldest dropped first", () => {
    // Stuff the store with MAX_ENTRIES + 5 entries; expect MAX_ENTRIES
    // remaining and the oldest 5 dropped.
    for (let i = 0; i < MAX_ENTRIES + 5; i++) {
      addEntry({
        text: `entry ${i}`,
        dataset: "stocks/spy/1d",
        windowStart: i,
        windowEnd: i + 1,
      });
    }
    const all = listEntries();
    expect(all.length).toBe(MAX_ENTRIES);
    // Newest is the LAST one we wrote (index MAX_ENTRIES + 4).
    expect(all[0].text).toBe(`entry ${MAX_ENTRIES + 4}`);
    // The 5 oldest (entry 0..4) should be gone.
    expect(all.find((e) => e.text === "entry 0")).toBeUndefined();
    expect(all.find((e) => e.text === "entry 4")).toBeUndefined();
    // entry 5 is the oldest survivor.
    expect(all[all.length - 1].text).toBe("entry 5");
  });

  it("coerces fractional window indices to integers", () => {
    // The component computes windowEnd = start + len; both should be
    // integers in practice but we defensively floor on the way in.
    const after = addEntry({
      text: "fractional",
      dataset: "stocks/spy/1d",
      windowStart: 100.7,
      windowEnd: 220.2,
    });
    expect(after[0].windowStart).toBe(100);
    expect(after[0].windowEnd).toBe(220);
  });
});

describe("removeEntry", () => {
  it("removes a single entry by id", () => {
    const after = addEntry({
      text: "to delete",
      dataset: "stocks/spy/1d",
      windowStart: 0,
      windowEnd: 1,
    });
    const id = after[0].id;
    addEntry({
      text: "to keep",
      dataset: "stocks/spy/1d",
      windowStart: 2,
      windowEnd: 3,
    });

    const next = removeEntry(id);
    expect(next.length).toBe(1);
    expect(next[0].text).toBe("to keep");
  });

  it("is a no-op when id is unknown", () => {
    addEntry({
      text: "lonely",
      dataset: "stocks/spy/1d",
      windowStart: 0,
      windowEnd: 1,
    });
    const next = removeEntry("nb-missing");
    expect(next.length).toBe(1);
    expect(next[0].text).toBe("lonely");
  });
});

describe("writeAll + persistence", () => {
  it("round-trips an arbitrary list", () => {
    const entries: NotebookEntry[] = [
      {
        id: "nb-a",
        ts: "2026-04-30T01:00:00.000Z",
        text: "alpha",
        dataset: "crypto/btc/1d",
        windowStart: 10,
        windowEnd: 20,
      },
      {
        id: "nb-b",
        ts: "2026-04-30T02:00:00.000Z",
        text: "beta",
        dataset: "crypto/btc/1d",
        windowStart: 30,
        windowEnd: 40,
      },
    ];
    writeAll(entries);
    expect(listEntries()).toEqual(entries);
  });
});
