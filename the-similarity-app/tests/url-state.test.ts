/**
 * Tests for lib/url-state.ts — the share-link serialization contract.
 *
 * We exercise three classes of behavior:
 *   1. Round-trip stability: parse(serialize(x)) === x for any populated state.
 *   2. Default omission: no entries on undefined keys; short URLs in the
 *      common case.
 *   3. Defensive parse: malformed values (NaN, negatives, overflow, invalid
 *      enums, corrupted comma-separated lists) are silently dropped.
 */

import { describe, it, expect } from "vitest";
import {
  parseUrlState,
  serializeUrlState,
  URL_STATE_MAX_PINNED,
  type WorkstationUrlState,
} from "../lib/url-state";

describe("serializeUrlState", () => {
  it("emits only defined keys in the compact schema", () => {
    const s: WorkstationUrlState = {
      dataset: "stocks/spy/1d",
      queryStart: 6800,
      queryLen: 120,
      k: 6,
      horizon: 180,
      chartMode: "pro",
      viewStart: 6000,
      viewEnd: 7500,
      pinned: ["3f9ab2", "e21c44"],
      showAnalogs: "all",
      theme: "dark",
      surface: "retrieve",
    };
    const out = serializeUrlState(s);
    // URLSearchParams percent-encodes slashes — the workstation reads them
    // back via `params.get`, which decodes them, so round-trip is stable.
    // We pin the exact string so any schema drift is caught immediately.
    expect(out).toBe(
      "ds=stocks%2Fspy%2F1d" +
        "&qs=6800&ql=120&k=6&h=180&cm=pro" +
        "&va=6000&vb=7500" +
        "&p=3f9ab2%2Ce21c44" +
        "&sa=all&th=dark&sr=retrieve",
    );
  });

  it("omits undefined fields entirely", () => {
    // Only dataset + horizon set — the rest should not appear.
    expect(serializeUrlState({ dataset: "stocks/aapl/1d", horizon: 180 }))
      .toBe("ds=stocks%2Faapl%2F1d&h=180");
  });

  it("returns empty string for fully-undefined state", () => {
    // The "everything default" case — a link with no query string is the
    // cleanest share-link. serializeUrlState({}) must be byte-empty.
    expect(serializeUrlState({})).toBe("");
  });

  it("omits empty pinned arrays", () => {
    // An empty pinned[] represents "no pins" which IS the default — it
    // should not serialize to `&p=`.
    expect(serializeUrlState({ pinned: [] })).toBe("");
  });

  it("truncates pinned lists to MAX_PINNED", () => {
    // Generate MAX+10 ids, verify only MAX make it into the output.
    const ids = Array.from({ length: URL_STATE_MAX_PINNED + 10 }, (_, i) => `id${i}`);
    const out = serializeUrlState({ pinned: ids });
    const roundTrip = parseUrlState(out);
    expect(roundTrip.pinned).toHaveLength(URL_STATE_MAX_PINNED);
    expect(roundTrip.pinned?.[0]).toBe("id0");
    expect(roundTrip.pinned?.[URL_STATE_MAX_PINNED - 1])
      .toBe(`id${URL_STATE_MAX_PINNED - 1}`);
  });
});

describe("parseUrlState", () => {
  it("parses the canonical populated URL", () => {
    // Accepts both leading "?" and bare pairs — test the "?"-prefixed form.
    const s = parseUrlState(
      "?ds=stocks/spy/1d&qs=6800&ql=120&k=6&h=180&cm=pro" +
        "&va=6000&vb=7500&p=3f9ab2,e21c44" +
        "&sa=all&th=dark&sr=retrieve",
    );
    expect(s).toEqual({
      dataset: "stocks/spy/1d",
      queryStart: 6800,
      queryLen: 120,
      k: 6,
      horizon: 180,
      chartMode: "pro",
      viewStart: 6000,
      viewEnd: 7500,
      pinned: ["3f9ab2", "e21c44"],
      showAnalogs: "all",
      theme: "dark",
      surface: "retrieve",
    });
  });

  it("accepts a query string with no leading ?", () => {
    // Some call sites pass location.search.slice(1) — both must work.
    expect(parseUrlState("ds=stocks/aapl/1d&k=3"))
      .toEqual({ dataset: "stocks/aapl/1d", k: 3 });
  });

  it("returns empty object for empty input", () => {
    expect(parseUrlState("")).toEqual({});
    expect(parseUrlState("?")).toEqual({});
  });

  it("ignores unknown keys (forward-compat)", () => {
    // A future field `&xyz=1` should not crash today's parser.
    expect(parseUrlState("?ds=stocks/spy/1d&xyz=1&future=true"))
      .toEqual({ dataset: "stocks/spy/1d" });
  });

  describe("malformed values are silently dropped", () => {
    it("drops non-integer query-start values", () => {
      expect(parseUrlState("?qs=abc")).toEqual({});
      expect(parseUrlState("?qs=-5")).toEqual({});
      expect(parseUrlState("?qs=3.14")).toEqual({});
      expect(parseUrlState("?qs=Infinity")).toEqual({});
    });

    it("drops query-len below minimum (2)", () => {
      expect(parseUrlState("?ql=0")).toEqual({});
      expect(parseUrlState("?ql=1")).toEqual({});
      // 2 is the minimum meaningful window; anything below is dropped.
      expect(parseUrlState("?ql=2")).toEqual({ queryLen: 2 });
    });

    it("drops k / horizon out of range", () => {
      // k must be >= 1
      expect(parseUrlState("?k=0")).toEqual({});
      // k must be <= 50
      expect(parseUrlState("?k=1000")).toEqual({});
      // horizon must be <= 2000
      expect(parseUrlState("?h=9999")).toEqual({});
    });

    it("drops invalid enum values", () => {
      expect(parseUrlState("?cm=banana")).toEqual({});
      expect(parseUrlState("?sa=invalid")).toEqual({});
      expect(parseUrlState("?th=pink")).toEqual({});
    });

    it("accepts all valid enum values", () => {
      expect(parseUrlState("?cm=fast").chartMode).toBe("fast");
      expect(parseUrlState("?cm=pro").chartMode).toBe("pro");
      expect(parseUrlState("?sa=top3").showAnalogs).toBe("top3");
      expect(parseUrlState("?sa=all").showAnalogs).toBe("all");
      expect(parseUrlState("?sa=pinned").showAnalogs).toBe("pinned");
      expect(parseUrlState("?th=light").theme).toBe("light");
      expect(parseUrlState("?th=dark").theme).toBe("dark");
    });

    it("drops inverted view range (vb <= va)", () => {
      // Drop BOTH bounds rather than silently flip — user gets defaults.
      const s = parseUrlState("?va=7000&vb=6000");
      expect(s.viewStart).toBeUndefined();
      expect(s.viewEnd).toBeUndefined();
    });

    it("accepts equal-valued bounds as invalid (vb must be > va)", () => {
      // A zero-width view range is nonsensical — no chart visible.
      const s = parseUrlState("?va=6000&vb=6000");
      expect(s.viewStart).toBeUndefined();
      expect(s.viewEnd).toBeUndefined();
    });

    it("accepts positive view range", () => {
      expect(parseUrlState("?va=6000&vb=7500"))
        .toEqual({ viewStart: 6000, viewEnd: 7500 });
    });

    it("drops dataset longer than 200 chars", () => {
      const huge = "x".repeat(300);
      expect(parseUrlState(`?ds=${huge}`)).toEqual({});
    });
  });

  describe("pinned list edge cases", () => {
    it("parses a simple comma-separated list", () => {
      expect(parseUrlState("?p=a,b,c").pinned).toEqual(["a", "b", "c"]);
    });

    it("trims whitespace and drops empty segments", () => {
      // Commas at the boundaries or adjacent commas produce empty
      // segments — these must be filtered, not parsed as empty-string ids.
      expect(parseUrlState("?p=,a,,b, ,c,").pinned).toEqual(["a", "b", "c"]);
    });

    it("returns undefined for empty p=", () => {
      // Explicit-empty differs from "all empty segments" only in that we
      // never saw a single token. Both normalize to undefined.
      expect(parseUrlState("?p=").pinned).toBeUndefined();
      expect(parseUrlState("?p=,,,").pinned).toBeUndefined();
    });

    it("truncates pinned lists above MAX_PINNED", () => {
      // Build a big raw list and verify parse truncates.
      const many = Array.from({ length: URL_STATE_MAX_PINNED + 25 }, (_, i) => `x${i}`);
      const raw = "?p=" + many.join(",");
      const out = parseUrlState(raw);
      expect(out.pinned).toHaveLength(URL_STATE_MAX_PINNED);
    });

    it("preserves insertion order", () => {
      // Order is stable across round-trip. The workstation ignores order,
      // but stable ordering keeps share-links byte-identical between
      // serialize calls with the same state.
      expect(parseUrlState("?p=zz,aa,mm").pinned).toEqual(["zz", "aa", "mm"]);
    });
  });
});

describe("round-trip stability", () => {
  /**
   * Round-trip invariant: serialize → parse yields the original state
   * (modulo default-omission). We test representative populated states.
   */
  const cases: WorkstationUrlState[] = [
    // Full state — every field populated.
    {
      dataset: "stocks/spy/1d",
      queryStart: 6800,
      queryLen: 120,
      k: 6,
      horizon: 180,
      chartMode: "pro",
      viewStart: 6000,
      viewEnd: 7500,
      pinned: ["3f9ab2", "e21c44"],
      showAnalogs: "all",
      theme: "dark",
      surface: "retrieve",
    },
    // Sparse — only dataset.
    { dataset: "commodities/gc/1d" },
    // Sparse — only horizon + theme.
    { horizon: 365, theme: "light" },
    // Sparse — only pinned.
    { pinned: ["abc", "def"] },
    // Sparse — chart mode + surface only.
    { chartMode: "fast", surface: "represent" },
  ];

  it.each(cases)("round-trips populated state %#", (state) => {
    const serialized = serializeUrlState(state);
    const parsed = parseUrlState(serialized);
    expect(parsed).toEqual(state);
  });

  it("empty state round-trips as empty", () => {
    expect(parseUrlState(serializeUrlState({}))).toEqual({});
  });
});
