import { describe, expect, it } from "vitest";

import {
  encodeMultidimensional,
  parseNarrative,
  predictNext,
  runExperimentReport,
  runSimilarityCheck,
  type HistoryDay,
} from "../app/tomorrow/engine";

describe("tomorrow prediction engine", () => {
  const history: HistoryDay[] = [
    { day: 5, avg: 42, text: "rough morning. anxious meeting. friend called at night. felt better." },
    { day: 4, avg: 55, text: "slow morning. walk at noon. productive afternoon. calm dinner." },
    { day: 3, avg: 62, text: "great morning run. flow state all morning. nice dinner." },
    { day: 2, avg: 48, text: "tired morning. bad meeting. afternoon dragged. evening got heavy." },
    { day: 1, avg: 58, text: "anxious about the deadline. pushed through. friend called at night. felt better." },
    { day: 0, avg: 50, text: "today" },
  ];

  it("encodes natural language into a multidimensional signal", () => {
    const parsed = parseNarrative("anxious morning. friend called. calm dinner.");
    const signal = encodeMultidimensional(parsed.series, parsed.events);

    expect(signal.avg).toBeGreaterThan(0);
    expect(signal.range).toBeGreaterThan(0);
    expect(signal.social).toBeGreaterThan(0);
    expect(signal.tension).toBeGreaterThan(0);
  });

  it("uses similarity matches to produce next paths and decoded language", () => {
    const today = parseNarrative(
      "anxious about the deadline. pushed through. friend called at night. felt better.",
    );
    const matches = runSimilarityCheck(history, today.series, today.events);
    const prediction = predictNext(history, today.series, today.events);

    expect(matches.length).toBeGreaterThan(0);
    expect(matches[0].day).toBe(1);
    expect(prediction.expectedNextAvg).toBeGreaterThanOrEqual(0);
    expect(prediction.expectedNextAvg).toBeLessThanOrEqual(100);
    expect(prediction.paths).toHaveLength(3);
    expect(prediction.paths.every((path) => path.points.length === 8)).toBe(true);
    expect(prediction.gameTheory.length).toBeGreaterThan(0);
    expect(prediction.decoded).toContain("The next part of the day");
  });

  it("runs the experiment report for natural-language today prediction", () => {
    const today = parseNarrative(
      "Tired morning, bad sleep, lots of meetings. A friend texts later and I might go to the gym.",
    );
    const report = runExperimentReport(history, today.series, today.events);

    expect(report.headline).toContain("Today looks like");
    expect(report.prediction.paths).toHaveLength(3);
    expect(report.backtest.baselines.length).toBeGreaterThanOrEqual(4);
    expect(report.ablations.length).toBeGreaterThanOrEqual(5);
    expect(report.counterfactuals.length).toBeGreaterThan(0);
  });
});
