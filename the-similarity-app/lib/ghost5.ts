export type Ghost5Point = {
  index: number;
  date: string;
  value: number;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
};

export type Ghost5Dataset = {
  id: string;
  label: string;
  assetClass: string;
  symbol: string;
  timeframe: string;
  source: string;
  path: string;
  rowCount: number;
  startTimestamp: string | null;
  endTimestamp: string | null;
  lastUpdatedAt: string | null;
};

export type Ghost5Query = {
  dataset: string;
  start: number;
  length: number;
  horizon: number;
  end: number;
  entryDate: string;
  entryPrice: number;
  tradePlan: Ghost5TradePlan;
  values: number[];
};

export type Ghost5TradePlan = {
  entryOffset: number;
  entryIndex: number;
  entryDate: string;
  entryPrice: number;
  takeProfitPct: number;
  takeProfitPrice: number;
  stopLossPct: number;
  stopLossPrice: number;
};

export type Ghost5TradeOutcome = {
  status: "take_profit" | "stop_loss" | "open";
  exitIndex: number | null;
  exitDate: string | null;
  exitPrice: number | null;
  returnPct: number;
  barsToExit: number | null;
};

export type Ghost5Analog = {
  id: string;
  rank: number;
  start: number;
  end: number;
  startDate: string;
  entryDate: string;
  confidence: number;
  distance: number;
  setupMovePct: number;
  forwardMovePct: number;
  maxDrawdownPct: number;
  tradeOutcome: Ghost5TradeOutcome;
  values: number[];
  forwardValues: number[];
};

export type Ghost5Scan = {
  product: "ghost5";
  priceUsdMonthly: 39;
  generatedAt: string;
  dataset: Ghost5Dataset;
  catalog: Ghost5Dataset[];
  series: Ghost5Point[];
  query: Ghost5Query;
  matches: Ghost5Analog[];
  summary: {
    sampleSize: number;
    medianForwardMovePct: number;
    winRatePct: number;
    worstDrawdownPct: number;
  };
};

export const GHOST5_DEFAULT_DATASET_ID = "stocks/spy/1d";
export const GHOST5_MIN_LENGTH = 24;
export const GHOST5_MAX_LENGTH = 180;
export const GHOST5_DEFAULT_LENGTH = 60;
export const GHOST5_DEFAULT_HORIZON = 40;
export const GHOST5_TOP_K = 20;

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.round(value)));
}

function round(value: number, digits = 4): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function logReturnVector(values: number[]): number[] {
  const returns: number[] = [];
  for (let i = 1; i < values.length; i += 1) {
    if (values[i - 1] > 0 && values[i] > 0) {
      returns.push(Math.log(values[i] / values[i - 1]));
    }
  }
  return returns;
}

function zscore(values: number[]): number[] {
  if (values.length === 0) return [];
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance =
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  const std = Math.sqrt(variance) || 1;
  return values.map((value) => (value - mean) / std);
}

function shapeDistance(left: number[], right: number[]): number {
  const a = zscore(logReturnVector(left));
  const b = zscore(logReturnVector(right));
  const count = Math.min(a.length, b.length);
  if (count === 0) return Number.POSITIVE_INFINITY;

  let squared = 0;
  for (let i = 0; i < count; i += 1) {
    squared += (a[i] - b[i]) ** 2;
  }
  return Math.sqrt(squared / count);
}

function percentMove(values: number[]): number {
  if (values.length < 2 || values[0] === 0) return 0;
  return ((values[values.length - 1] - values[0]) / values[0]) * 100;
}

function maxDrawdown(values: number[]): number {
  let peak = values[0] ?? 0;
  let worst = 0;
  for (const value of values) {
    peak = Math.max(peak, value);
    if (peak > 0) worst = Math.min(worst, ((value - peak) / peak) * 100);
  }
  return worst;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

function normalizedTradeInputs(options: {
  length: number;
  entryOffset?: number;
  takeProfitPct?: number;
  stopLossPct?: number;
}): {
  entryOffset: number;
  takeProfitPct: number;
  stopLossPct: number;
} {
  const entryOffset = clamp(options.entryOffset ?? options.length - 1, 0, options.length - 1);
  const takeProfitPct = Math.max(
    0.1,
    Math.min(100, Number.isFinite(options.takeProfitPct) ? options.takeProfitPct ?? 3 : 3),
  );
  const rawStop = Number.isFinite(options.stopLossPct) ? options.stopLossPct ?? -1.5 : -1.5;
  const stopLossPct = -Math.max(0.1, Math.min(100, Math.abs(rawStop)));
  return { entryOffset, takeProfitPct: round(takeProfitPct, 2), stopLossPct: round(stopLossPct, 2) };
}

function buildTradePlan(series: Ghost5Point[], start: number, inputs: {
  entryOffset: number;
  takeProfitPct: number;
  stopLossPct: number;
}): Ghost5TradePlan {
  const entryIndex = start + inputs.entryOffset;
  const entryPoint = series[entryIndex];
  const entryPrice = entryPoint.value;
  return {
    entryOffset: inputs.entryOffset,
    entryIndex,
    entryDate: entryPoint.date,
    entryPrice: round(entryPrice, 4),
    takeProfitPct: inputs.takeProfitPct,
    takeProfitPrice: round(entryPrice * (1 + inputs.takeProfitPct / 100), 4),
    stopLossPct: inputs.stopLossPct,
    stopLossPrice: round(entryPrice * (1 + inputs.stopLossPct / 100), 4),
  };
}

function evaluateTradeOutcome(
  series: Ghost5Point[],
  entryIndex: number,
  horizon: number,
  takeProfitPrice: number,
  stopLossPrice: number,
): Ghost5TradeOutcome {
  const entryPrice = series[entryIndex]?.value ?? 0;
  const lastIndex = Math.min(series.length - 1, entryIndex + horizon);
  for (let index = entryIndex + 1; index <= lastIndex; index += 1) {
    const point = series[index];
    const value = point.value;
    if (value >= takeProfitPrice) {
      return {
        status: "take_profit",
        exitIndex: index,
        exitDate: point.date,
        exitPrice: round(value, 4),
        returnPct: round(((value - entryPrice) / entryPrice) * 100, 2),
        barsToExit: index - entryIndex,
      };
    }
    if (value <= stopLossPrice) {
      return {
        status: "stop_loss",
        exitIndex: index,
        exitDate: point.date,
        exitPrice: round(value, 4),
        returnPct: round(((value - entryPrice) / entryPrice) * 100, 2),
        barsToExit: index - entryIndex,
      };
    }
  }

  const lastPoint = series[lastIndex];
  return {
    status: "open",
    exitIndex: null,
    exitDate: null,
    exitPrice: lastPoint ? round(lastPoint.value, 4) : null,
    returnPct: lastPoint && entryPrice
      ? round(((lastPoint.value - entryPrice) / entryPrice) * 100, 2)
      : 0,
    barsToExit: null,
  };
}

export function datasetId(dataset: Pick<Ghost5Dataset, "assetClass" | "symbol" | "timeframe">): string {
  return `${dataset.assetClass}/${dataset.symbol}/${dataset.timeframe}`;
}

export function createGhost5ScanFromSeries(options: {
  dataset: Ghost5Dataset;
  catalog?: Ghost5Dataset[];
  series: Ghost5Point[];
  start?: number;
  length?: number;
  horizon?: number;
  topK?: number;
  entryOffset?: number;
  takeProfitPct?: number;
  stopLossPct?: number;
  now?: string;
}): Ghost5Scan {
  const series = options.series.filter((point) => Number.isFinite(point.value) && point.value > 0);
  const horizon = clamp(options.horizon ?? GHOST5_DEFAULT_HORIZON, 12, 120);
  const length = clamp(
    options.length ?? GHOST5_DEFAULT_LENGTH,
    GHOST5_MIN_LENGTH,
    GHOST5_MAX_LENGTH,
  );
  const latestStart = series.length - length - horizon - 1;
  if (latestStart < 1) {
    throw new Error(`Dataset ${options.dataset.id} does not have enough bars for Ghost5.`);
  }

  const defaultStart = Math.max(0, latestStart - Math.floor(length * 1.5));
  const start = clamp(options.start ?? defaultStart, 0, latestStart);
  const topK = clamp(options.topK ?? GHOST5_TOP_K, 1, 40);
  const end = start + length - 1;
  const tradeInputs = normalizedTradeInputs({
    length,
    entryOffset: options.entryOffset,
    takeProfitPct: options.takeProfitPct,
    stopLossPct: options.stopLossPct,
  });
  const queryTradePlan = buildTradePlan(series, start, tradeInputs);
  const queryValues = series.slice(start, start + length).map((point) => point.value);
  const candidates: Ghost5Analog[] = [];

  for (let candidateStart = 0; candidateStart <= latestStart; candidateStart += 1) {
    const candidateEnd = candidateStart + length - 1;
    const overlaps =
      candidateStart <= end + horizon && candidateEnd >= start - horizon;
    if (overlaps) continue;

    const candidateValues = series
      .slice(candidateStart, candidateStart + length)
      .map((point) => point.value);
    const forwardValues = series
      .slice(candidateStart + length, candidateStart + length + horizon)
      .map((point) => point.value);
    const distance = shapeDistance(queryValues, candidateValues);
    if (!Number.isFinite(distance)) continue;

    const confidence = Math.max(0, Math.min(99, 100 - distance * 29));
    const forwardPath = [candidateValues[candidateValues.length - 1], ...forwardValues];
    const candidateTradePlan = buildTradePlan(series, candidateStart, tradeInputs);

    candidates.push({
      id: `g5-${options.dataset.id}-${candidateStart}-${length}`,
      rank: 0,
      start: candidateStart,
      end: candidateEnd,
      startDate: series[candidateStart].date,
      entryDate: series[candidateEnd].date,
      confidence: round(confidence, 1),
      distance: round(distance, 5),
      setupMovePct: round(percentMove(candidateValues), 2),
      forwardMovePct: round(percentMove(forwardPath), 2),
      maxDrawdownPct: round(maxDrawdown(forwardPath), 2),
      tradeOutcome: evaluateTradeOutcome(
        series,
        candidateTradePlan.entryIndex,
        horizon,
        candidateTradePlan.takeProfitPrice,
        candidateTradePlan.stopLossPrice,
      ),
      values: candidateValues.map((value) => round(value, 4)),
      forwardValues: forwardValues.map((value) => round(value, 4)),
    });
  }

  const matches = candidates
    .sort((a, b) => a.distance - b.distance)
    .slice(0, topK)
    .map((match, index) => ({ ...match, rank: index + 1 }));
  const forwardMoves = matches.map((match) => match.forwardMovePct);

  return {
    product: "ghost5",
    priceUsdMonthly: 39,
    generatedAt: options.now ?? new Date().toISOString(),
    dataset: options.dataset,
    catalog: options.catalog ?? [options.dataset],
    series: series.map((point, index) => ({
      ...point,
      index,
      value: round(point.value, 4),
      open: point.open === undefined ? undefined : round(point.open, 4),
      high: point.high === undefined ? undefined : round(point.high, 4),
      low: point.low === undefined ? undefined : round(point.low, 4),
      volume: point.volume === undefined ? undefined : round(point.volume, 2),
    })),
    query: {
      dataset: options.dataset.id,
      start,
      length,
      horizon,
      end,
      entryDate: queryTradePlan.entryDate,
      entryPrice: queryTradePlan.entryPrice,
      tradePlan: queryTradePlan,
      values: queryValues.map((value) => round(value, 4)),
    },
    matches,
    summary: {
      sampleSize: matches.length,
      medianForwardMovePct: round(median(forwardMoves), 2),
      winRatePct: round(
        (forwardMoves.filter((move) => move > 0).length / Math.max(1, forwardMoves.length)) * 100,
        1,
      ),
      worstDrawdownPct: matches.length
        ? round(Math.min(...matches.map((match) => match.maxDrawdownPct)), 2)
        : 0,
    },
  };
}
