import { describe, expect, it } from "vitest";
import {
  GHOST5_DEFAULT_DATASET_ID,
  GHOST5_TOP_K,
  createGhost5ScanFromSeries,
  type Ghost5Dataset,
  type Ghost5Point,
} from "../lib/ghost5";
import { GET } from "../app/api/ghost5/route";

const fixtureDataset: Ghost5Dataset = {
  id: "stocks/spy/1d",
  label: "SPY 1d",
  assetClass: "stocks",
  symbol: "spy",
  timeframe: "1d",
  source: "fixture",
  path: "fixture.parquet",
  rowCount: 520,
  startTimestamp: "2020-01-01T00:00:00Z",
  endTimestamp: "2021-12-31T00:00:00Z",
  lastUpdatedAt: "2026-05-08T00:00:00Z",
};

function makeFixtureSeries(n = 520): Ghost5Point[] {
  const points: Ghost5Point[] = [];
  let value = 100;
  for (let i = 0; i < n; i += 1) {
    const wave = Math.sin(i / 13) * 0.004;
    const cycle = Math.sin(i / 47) * 0.003;
    value *= 1 + 0.0006 + wave + cycle;
    points.push({
      index: i,
      date: new Date(Date.UTC(2020, 0, 1 + i)).toISOString(),
      value,
      open: value * 0.998,
      high: value * 1.006,
      low: value * 0.994,
      volume: 1_000_000 + i,
    });
  }
  return points;
}

describe("createGhost5ScanFromSeries", () => {
  it("returns the 20 closest non-overlapping entry windows", () => {
    const scan = createGhost5ScanFromSeries({
      dataset: fixtureDataset,
      series: makeFixtureSeries(),
      start: 300,
      length: 48,
      horizon: 32,
      entryOffset: 20,
      takeProfitPct: 4,
      stopLossPct: -2,
      now: "test",
    });

    expect(scan.product).toBe("ghost5");
    expect(scan.priceUsdMonthly).toBe(39);
    expect(scan.matches).toHaveLength(GHOST5_TOP_K);
    expect(scan.query.tradePlan.entryOffset).toBe(20);
    expect(scan.query.tradePlan.takeProfitPct).toBe(4);
    expect(scan.query.tradePlan.stopLossPct).toBe(-2);

    for (const match of scan.matches) {
      const overlaps =
        match.start <= scan.query.end + scan.query.horizon &&
        match.end >= scan.query.start - scan.query.horizon;
      expect(overlaps).toBe(false);
      expect(match.values).toHaveLength(scan.query.length);
      expect(match.forwardValues).toHaveLength(scan.query.horizon);
      expect(["take_profit", "stop_loss", "open"]).toContain(match.tradeOutcome.status);
    }
  });

  it("is deterministic for the same requested entry", () => {
    const series = makeFixtureSeries();
    const first = createGhost5ScanFromSeries({
      dataset: fixtureDataset,
      series,
      start: 212,
      length: 64,
      horizon: 40,
      now: "test",
    });
    const second = createGhost5ScanFromSeries({
      dataset: fixtureDataset,
      series,
      start: 212,
      length: 64,
      horizon: 40,
      now: "test",
    });

    expect(second).toEqual(first);
  });
});

describe("/api/ghost5", () => {
  it("returns the paid Ghost5 analog payload from the parquet catalog", async () => {
    const response = await GET(
      new Request(`http://localhost/api/ghost5?dataset=${GHOST5_DEFAULT_DATASET_ID}&start=240&length=48&horizon=24&topK=20`),
    );
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.product).toBe("ghost5");
    expect(body.priceUsdMonthly).toBe(39);
    expect(body.dataset.id).toBe(GHOST5_DEFAULT_DATASET_ID);
    expect(body.dataset.path).toContain(".parquet");
    expect(body.series.length).toBeGreaterThan(1000);
    expect(body.query.start).toBe(240);
    expect(body.query.length).toBe(48);
    expect(body.query.horizon).toBe(24);
    expect(body.query.tradePlan.entryOffset).toBe(47);
    expect(body.matches).toHaveLength(20);
  });
});
