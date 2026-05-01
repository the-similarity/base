import { describe, expect, it } from "vitest";

import { buildDatasetDataUrl } from "../lib/api";

describe("buildDatasetDataUrl", () => {
  it("passes generated timeframe options to series requests", () => {
    const url = buildDatasetDataUrl(
      "http://localhost:8787/",
      "crypto",
      "btcusd",
      "5m",
      "series",
      { column: "close", targetTimeframe: "1h" },
    );

    expect(url).toBe(
      "http://localhost:8787/datasets/crypto/btcusd/5m/series?column=close&target_timeframe=1h",
    );
  });

  it("can opt into incomplete generated OHLC candles", () => {
    const url = buildDatasetDataUrl(
      "http://localhost:8787",
      "crypto",
      "btcusd",
      "5m",
      "ohlc",
      { targetTimeframe: "45m", includeIncomplete: true },
    );

    expect(url).toBe(
      "http://localhost:8787/datasets/crypto/btcusd/5m/ohlc?target_timeframe=45m&include_incomplete=true",
    );
  });
});
