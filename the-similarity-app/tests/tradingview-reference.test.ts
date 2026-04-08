import { describe, expect, it } from "vitest";
import {
  buildNormalizedReturns,
  deriveTradeSignal,
  resampleSeries,
  scoreCandidate,
  searchPattern,
} from "../lib/tradingview-reference";

describe("tradingview reference engine", () => {
  it("builds finite normalized returns", () => {
    const normalized = buildNormalizedReturns([100, 102, 101, 104, 108]);
    expect(normalized).toHaveLength(4);
    expect(normalized.every(Number.isFinite)).toBe(true);
    const mean = normalized.reduce((sum, value) => sum + value, 0) / normalized.length;
    expect(Math.abs(mean)).toBeLessThan(1e-9);
  });

  it("resamples candidate series to the requested length", () => {
    const resampled = resampleSeries([1, 3, 5, 7], 7);
    expect(resampled).toHaveLength(7);
    expect(resampled[0]).toBe(1);
    expect(resampled[6]).toBe(7);
  });

  it("scores identical structures above perturbed ones", () => {
    const query = [100, 104, 103, 108, 112, 116];
    const closeMatch = [200, 208, 206, 216, 224, 232];
    const weakMatch = [200, 198, 201, 197, 199, 198];

    const strong = scoreCandidate(query, closeMatch);
    const weak = scoreCandidate(query, weakMatch);

    expect(strong.score).toBeGreaterThan(weak.score);
    expect(strong.correlation).toBeGreaterThan(0.8);
  });

  it("finds the strongest repeated motif and produces bullish quantiles", () => {
    const closes = [
      100, 103, 101, 106, 111, 116, 122, 129, 135,
      140, 138, 137, 136, 135, 134,
      200, 206, 203, 212, 221, 231,
    ];

    const result = searchPattern(closes, {
      queryLength: 6,
      forecastBars: 3,
      lookbackBars: 18,
      stride: 1,
      scales: [1],
      topMatches: 3,
    });

    expect(result.bestMatch).not.toBeNull();
    expect(result.bestMatch?.startIndex).toBe(0);
    expect(result.bestMatch?.score ?? 0).toBeGreaterThan(70);
    expect(result.quantiles.median[2]).toBeGreaterThan(0);
  });

  it("derives directional signals from quantile projection and confidence", () => {
    const longSignal = deriveTradeSignal(
      {
        matches: [],
        bestMatch: {
          startIndex: 0,
          length: 6,
          scale: 1,
          score: 82,
          breakdown: { shape: 0.9, correlation: 0.9, slope: 0.8, energy: 0.8 },
          projectedReturns: [0.01, 0.03, 0.05],
        },
        quantiles: {
          lower: [0.0, 0.01, 0.02],
          median: [0.01, 0.03, 0.05],
          upper: [0.02, 0.04, 0.06],
        },
      },
      70,
      0.02,
    );
    expect(longSignal.direction).toBe("long");

    const shortSignal = deriveTradeSignal(
      {
        matches: [],
        bestMatch: {
          startIndex: 0,
          length: 6,
          scale: 1,
          score: 77,
          breakdown: { shape: 0.7, correlation: 0.8, slope: 0.8, energy: 0.7 },
          projectedReturns: [-0.01, -0.03, -0.05],
        },
        quantiles: {
          lower: [-0.06, -0.05, -0.04],
          median: [-0.02, -0.03, -0.05],
          upper: [-0.01, -0.02, -0.03],
        },
      },
      70,
      0.02,
    );
    expect(shortSignal.direction).toBe("short");
  });
});
