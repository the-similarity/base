import { describe, it, expect } from "vitest";
import { reducer } from "../lib/terminal-context";
import type { TerminalState } from "../lib/terminal-context";
import type { MatchResult, SearchResponse } from "../lib/types";

function makeState(overrides?: Partial<TerminalState>): TerminalState {
  return {
    matches: [],
    searchResponse: null,
    dashboardData: null,
    ohlcData: null,
    chartMode: "candle",
    forwardBars: 30,
    loading: false,
    error: null,
    selectedIdx: null,
    hoveredIdx: null,
    focusedIdx: 0,
    activeMethods: ["dtw", "pearson_warped"],
    theme: "dark",
    activeDataset: null,
    queryPicking: false,
    customQueryRange: null,
    ...overrides,
  };
}

function makeMatch(overrides?: Partial<MatchResult>): MatchResult {
  return {
    startIdx: 0,
    endIdx: 60,
    startDate: "2020-01-01",
    endDate: "2020-03-01",
    confidenceScore: 85.0,
    scoreBreakdown: {
      bempedelisR2: 0.7, bempedelisSmoothness: 0.5, koopman: 0.6,
      waveletSpectrum: 0.4, emd: 0.3, tda: 0.2, dtw: 0.9,
      pearsonWarped: 0.8, transferEntropy: 0.1,
    },
    matchedSeries: [1, 2, 3, 4, 5],
    transformAlpha: null,
    transformBeta: null,
    transformR2: 0.95,
    koopmanEigenvalues: null,
    fractalSpectrum: null,
    persistenceDiagram: null,
    forwardWindow: [5, 6, 7, 8],
    ...overrides,
  };
}

function makeSearchResponse(matches: MatchResult[]): SearchResponse {
  return {
    queryValues: [10, 20, 30, 40, 50],
    matches,
    forecast: {
      bars: 50,
      percentiles: [10, 50, 90],
      curves: { "10": [1, 2], "50": [3, 4], "90": [5, 6] },
      allPaths: [[1, 2], [3, 4]],
      weights: [0.5, 0.5],
    },
  };
}

describe("terminal reducer", () => {
  describe("SET_SEARCH_RESPONSE", () => {
    it("stores the response and populates matches", () => {
      const match = makeMatch();
      const response = makeSearchResponse([match]);
      const state = makeState({ loading: true, selectedIdx: 2, focusedIdx: 3 });

      const next = reducer(state, { type: "SET_SEARCH_RESPONSE", response });

      expect(next.searchResponse).toBe(response);
      expect(next.matches).toEqual([match]);
      expect(next.loading).toBe(false);
      expect(next.error).toBeNull();
      expect(next.selectedIdx).toBeNull();
      expect(next.hoveredIdx).toBeNull();
      expect(next.focusedIdx).toBe(0);
    });

    it("handles empty matches", () => {
      const response = makeSearchResponse([]);
      const next = reducer(makeState(), { type: "SET_SEARCH_RESPONSE", response });

      expect(next.matches).toEqual([]);
      expect(next.searchResponse).toBe(response);
    });
  });

  describe("SET_MATCHES", () => {
    it("sets matches and clears loading/error", () => {
      const match = makeMatch();
      const state = makeState({ loading: true, error: "old error" });
      const next = reducer(state, { type: "SET_MATCHES", matches: [match] });

      expect(next.matches).toEqual([match]);
      expect(next.loading).toBe(false);
      expect(next.error).toBeNull();
    });
  });

  describe("navigation actions", () => {
    const matches = [makeMatch(), makeMatch({ startIdx: 60 }), makeMatch({ startIdx: 120 })];

    it("FOCUS_NEXT increments focusedIdx", () => {
      const state = makeState({ matches, focusedIdx: 0 });
      const next = reducer(state, { type: "FOCUS_NEXT" });
      expect(next.focusedIdx).toBe(1);
    });

    it("FOCUS_NEXT clamps at last match", () => {
      const state = makeState({ matches, focusedIdx: 2 });
      const next = reducer(state, { type: "FOCUS_NEXT" });
      expect(next.focusedIdx).toBe(2);
    });

    it("FOCUS_PREV decrements focusedIdx", () => {
      const state = makeState({ matches, focusedIdx: 2 });
      const next = reducer(state, { type: "FOCUS_PREV" });
      expect(next.focusedIdx).toBe(1);
    });

    it("FOCUS_PREV clamps at 0", () => {
      const state = makeState({ matches, focusedIdx: 0 });
      const next = reducer(state, { type: "FOCUS_PREV" });
      expect(next.focusedIdx).toBe(0);
    });

    it("SELECT sets selectedIdx", () => {
      const next = reducer(makeState(), { type: "SELECT", idx: 1 });
      expect(next.selectedIdx).toBe(1);
    });

    it("SELECT null clears selection", () => {
      const state = makeState({ selectedIdx: 1 });
      const next = reducer(state, { type: "SELECT", idx: null });
      expect(next.selectedIdx).toBeNull();
    });

    it("HOVER sets hoveredIdx", () => {
      const next = reducer(makeState(), { type: "HOVER", idx: 2 });
      expect(next.hoveredIdx).toBe(2);
    });
  });

  describe("TOGGLE_METHOD", () => {
    it("removes an active method", () => {
      const state = makeState({ activeMethods: ["dtw", "pearson_warped"] });
      const next = reducer(state, { type: "TOGGLE_METHOD", method: "dtw" });
      expect(next.activeMethods).toEqual(["pearson_warped"]);
    });

    it("adds an inactive method", () => {
      const state = makeState({ activeMethods: ["dtw"] });
      const next = reducer(state, { type: "TOGGLE_METHOD", method: "emd" });
      expect(next.activeMethods).toEqual(["dtw", "emd"]);
    });
  });

  describe("TOGGLE_THEME", () => {
    it("toggles dark to light", () => {
      const next = reducer(makeState({ theme: "dark" }), { type: "TOGGLE_THEME" });
      expect(next.theme).toBe("light");
    });

    it("toggles light to dark", () => {
      const next = reducer(makeState({ theme: "light" }), { type: "TOGGLE_THEME" });
      expect(next.theme).toBe("dark");
    });
  });

  describe("SET_ERROR", () => {
    it("sets error and clears loading", () => {
      const state = makeState({ loading: true });
      const next = reducer(state, { type: "SET_ERROR", error: "API unavailable" });
      expect(next.error).toBe("API unavailable");
      expect(next.loading).toBe(false);
    });

    it("clears error with null", () => {
      const state = makeState({ error: "old" });
      const next = reducer(state, { type: "SET_ERROR", error: null });
      expect(next.error).toBeNull();
    });
  });
});
