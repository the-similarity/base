import { describe, expect, it } from "vitest";

import { withForwardWindowsFromSeries } from "../lib/api";
import type { SearchResponse } from "../lib/types";

const baseResponse: SearchResponse = {
  queryValues: [50, 51, 52],
  matches: [
    {
      startIdx: 1,
      endIdx: 4,
      startDate: null,
      endDate: null,
      confidenceScore: 91,
      scoreBreakdown: {
        bempedelisR2: 0,
        bempedelisSmoothness: 0,
        koopman: 0,
        waveletSpectrum: 0,
        emd: 0,
        tda: 0,
        dtw: 1,
        pearsonWarped: 1,
        transferEntropy: 0,
      },
      matchedSeries: [101, 102, 103],
      transformAlpha: null,
      transformBeta: null,
      transformR2: 0,
      koopmanEigenvalues: null,
      fractalSpectrum: null,
      persistenceDiagram: null,
      forwardWindow: null,
    },
  ],
  forecast: {
    bars: 5,
    percentiles: [50],
    curves: { "50": [0, 0, 0, 0, 0] },
    allPaths: [],
    weights: [],
  },
  metrics: {
    coverage: 0,
    crps: 0,
    hitRate: 0,
    grade: "unknown",
    regimeDrift: "unknown",
    reliability: [],
    nAnalogs: 0,
  },
};

describe("withForwardWindowsFromSeries", () => {
  it("fills display forward windows from the full chart series", () => {
    const result = withForwardWindowsFromSeries(
      baseResponse,
      [100, 101, 102, 103, 106, 109, 112, 115],
      4,
    );

    expect(result.matches[0].forwardWindow).toEqual([
      (106 - 103) / 103,
      (109 - 103) / 103,
      (112 - 103) / 103,
      (115 - 103) / 103,
    ]);
  });

  it("keeps a partial continuation when fewer future bars exist", () => {
    const result = withForwardWindowsFromSeries(
      baseResponse,
      [100, 101, 102, 103, 106],
      4,
    );

    expect(result.matches[0].forwardWindow).toEqual([(106 - 103) / 103]);
  });
});
