import { describe, expect, it } from "vitest";

import {
  decideTradeSignal,
  findBestPatternMatch,
  linearResample,
  scalePathToAnchor,
} from "../lib/tradingview/pattern-engine";

function buildSegment(length: number, start: number, slope: number, amplitude: number, phase = 0): number[] {
  return Array.from({ length }, (_, index) => {
    const wave = Math.sin(index * 0.45 + phase) * amplitude;
    const harmonic = Math.cos(index * 0.18 + phase * 0.5) * amplitude * 0.35;
    return Number((start + index * slope + wave + harmonic).toFixed(4));
  });
}

describe("pattern-engine", () => {
  it("resamples scaled windows back to the target length", () => {
    const source = [10, 15, 20, 25];
    expect(linearResample(source, 7)).toEqual([10, 12.5, 15, 17.5, 20, 22.5, 25]);
  });

  it("finds the strongest analog in history and preserves the expected future direction", () => {
    const candidate = buildSegment(12, 100, 0.8, 2.4, 0.2);
    const candidateFuture = [112.8, 114.7, 116.9, 118.5];
    const distractor = buildSegment(12, 88, -0.25, 4.8, 1.1);
    const query = buildSegment(12, 210, 1.68, 5.04, 0.2);
    const series = [
      ...buildSegment(18, 75, 0.15, 1.1, 0.1),
      ...candidate,
      ...candidateFuture,
      ...distractor,
      ...buildSegment(16, 132, 0.3, 1.6, 0.8),
      ...query,
    ];

    const match = findBestPatternMatch(series, {
      patternLength: 12,
      searchDepth: 48,
      searchStep: 1,
      forecastBars: 4,
      scaleFactors: [1],
    });

    expect(match).not.toBeNull();
    expect(match!.candidateStart).toBe(18);
    expect(match!.confidence).toBeGreaterThan(80);
    expect(match!.projectedReturn).toBeGreaterThan(0);
  });

  it("matches different playback speeds through scale-aware search", () => {
    const slowCandidate = buildSegment(18, 120, 0.55, 2.2, 0.4);
    const slowFuture = [131.4, 133.2, 135.6, 138.1];
    const query = linearResample(slowCandidate, 12).map((value) => Number((value * 1.4).toFixed(4)));
    const series = [
      ...buildSegment(20, 80, 0.2, 1.0, 0.3),
      ...slowCandidate,
      ...slowFuture,
      ...buildSegment(22, 92, -0.15, 2.8, 1.0),
      ...query,
    ];

    const match = findBestPatternMatch(series, {
      patternLength: 12,
      searchDepth: 56,
      searchStep: 1,
      forecastBars: 4,
      scaleFactors: [0.75, 1, 1.5],
    });

    expect(match).not.toBeNull();
    expect(match!.scaleFactor).toBe(1.5);
    expect(match!.confidence).toBeGreaterThan(75);
  });

  it("anchors projected prices to the current market anchor", () => {
    const scaled = scalePathToAnchor([102, 104, 108], 100, 250);
    expect(scaled).toEqual([255, 260, 270]);
  });

  it("turns match confidence and projection into long/short/flat decisions", () => {
    expect(decideTradeSignal({
      confidence: 82,
      projectedReturn: 0.035,
      minConfidence: 70,
      minProjectedMove: 0.01,
    }).direction).toBe("long");

    expect(decideTradeSignal({
      confidence: 81,
      projectedReturn: -0.028,
      minConfidence: 70,
      minProjectedMove: 0.01,
    }).direction).toBe("short");

    expect(decideTradeSignal({
      confidence: 55,
      projectedReturn: 0.05,
      minConfidence: 70,
      minProjectedMove: 0.01,
    }).direction).toBe("flat");
  });
});
