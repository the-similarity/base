export interface MatchBreakdown {
  shape: number;
  correlation: number;
  slope: number;
  energy: number;
}

export interface MatchResult {
  startIndex: number;
  length: number;
  scale: number;
  score: number;
  breakdown: MatchBreakdown;
  projectedReturns: number[];
}

export interface SearchOptions {
  queryLength: number;
  forecastBars: number;
  lookbackBars: number;
  stride: number;
  scales: number[];
  topMatches: number;
}

export interface SearchResult {
  matches: MatchResult[];
  bestMatch: MatchResult | null;
  quantiles: {
    lower: number[];
    median: number[];
    upper: number[];
  };
}

export interface TradeSignal {
  direction: "long" | "short" | "flat";
  confidence: number;
  projectedReturn: number;
}

const EPSILON = 1e-9;

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);
}

function stdDev(values: number[], avg: number): number {
  const variance = values.reduce((sum, value) => {
    const delta = value - avg;
    return sum + delta * delta;
  }, 0) / Math.max(values.length, 1);
  return Math.sqrt(variance);
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function resampleSeries(values: number[], targetLength: number): number[] {
  if (targetLength <= 0) {
    return [];
  }
  if (values.length === 0) {
    return Array.from({ length: targetLength }, () => 0);
  }
  if (values.length === 1 || targetLength === 1) {
    return Array.from({ length: targetLength }, () => values[values.length - 1]);
  }

  return Array.from({ length: targetLength }, (_, index) => {
    const position = (index * (values.length - 1)) / (targetLength - 1);
    const left = Math.floor(position);
    const right = Math.min(values.length - 1, Math.ceil(position));
    if (left === right) {
      return values[left];
    }
    const weight = position - left;
    return values[left] * (1 - weight) + values[right] * weight;
  });
}

export function buildNormalizedReturns(prices: number[]): number[] {
  if (prices.length < 2) {
    return [];
  }

  const returns = prices.slice(1).map((price, index) => {
    const prev = prices[index];
    const safePrev = Math.max(prev, EPSILON);
    const safePrice = Math.max(price, EPSILON);
    return Math.log(safePrice / safePrev);
  });

  const avg = mean(returns);
  const deviation = stdDev(returns, avg);
  if (deviation < EPSILON) {
    return returns.map(() => 0);
  }
  return returns.map((value) => (value - avg) / deviation);
}

function correlation(a: number[], b: number[]): number {
  if (a.length !== b.length || a.length === 0) {
    return 0;
  }
  const aMean = mean(a);
  const bMean = mean(b);
  let numerator = 0;
  let aDenominator = 0;
  let bDenominator = 0;
  for (let index = 0; index < a.length; index += 1) {
    const aDelta = a[index] - aMean;
    const bDelta = b[index] - bMean;
    numerator += aDelta * bDelta;
    aDenominator += aDelta * aDelta;
    bDenominator += bDelta * bDelta;
  }
  const denominator = Math.sqrt(aDenominator * bDenominator);
  if (denominator < EPSILON) {
    return 0;
  }
  return numerator / denominator;
}

function totalReturn(prices: number[]): number {
  if (prices.length < 2) {
    return 0;
  }
  return prices[prices.length - 1] / Math.max(prices[0], EPSILON) - 1;
}

function energyProfile(values: number[], slices = 4): number[] {
  if (values.length === 0) {
    return Array.from({ length: slices }, () => 0);
  }
  const energies: number[] = [];
  for (let slice = 0; slice < slices; slice += 1) {
    const start = Math.floor((slice * values.length) / slices);
    const end = Math.floor(((slice + 1) * values.length) / slices);
    const window = values.slice(start, Math.max(start + 1, end));
    const energy = window.reduce((sum, value) => sum + Math.abs(value), 0);
    energies.push(energy);
  }
  const total = energies.reduce((sum, value) => sum + value, 0);
  if (total < EPSILON) {
    return energies.map(() => 1 / energies.length);
  }
  return energies.map((value) => value / total);
}

export function scoreCandidate(queryPrices: number[], candidatePrices: number[]): MatchBreakdown & { score: number } {
  const queryReturns = buildNormalizedReturns(queryPrices);
  const candidateReturns = buildNormalizedReturns(candidatePrices);
  const sampleSize = Math.min(queryReturns.length, candidateReturns.length);
  if (sampleSize === 0) {
    return { shape: 0, correlation: 0, slope: 0, energy: 0, score: 0 };
  }

  const q = queryReturns.slice(0, sampleSize);
  const c = candidateReturns.slice(0, sampleSize);

  const meanAbsDiff = q.reduce((sum, value, index) => sum + Math.abs(value - c[index]), 0) / sampleSize;
  const shape = 1 / (1 + meanAbsDiff);

  const corr = correlation(q, c);
  const correlationScore = clamp01((corr + 1) / 2);

  const queryTrend = totalReturn(queryPrices);
  const candidateTrend = totalReturn(candidatePrices);
  const slopeDenominator = Math.max(Math.abs(queryTrend), Math.abs(candidateTrend), 0.02);
  const slope = clamp01(1 - Math.abs(queryTrend - candidateTrend) / slopeDenominator);

  const queryEnergy = energyProfile(q);
  const candidateEnergy = energyProfile(c);
  const l1Distance = queryEnergy.reduce(
    (sum, value, index) => sum + Math.abs(value - candidateEnergy[index]),
    0,
  );
  const energy = clamp01(1 - l1Distance / 2);

  const score = clamp01(shape * 0.4 + correlationScore * 0.3 + slope * 0.15 + energy * 0.15) * 100;
  return { shape, correlation: correlationScore, slope, energy, score };
}

function projectedReturns(closes: number[], anchorIndex: number, forecastBars: number): number[] {
  if (anchorIndex < 0 || anchorIndex >= closes.length) {
    return [];
  }
  const anchor = Math.max(closes[anchorIndex], EPSILON);
  const maxEnd = Math.min(closes.length, anchorIndex + 1 + forecastBars);
  const output: number[] = [];
  for (let index = anchorIndex + 1; index < maxEnd; index += 1) {
    output.push(closes[index] / anchor - 1);
  }
  return output;
}

function percentile(values: number[], p: number): number {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 1) {
    return sorted[0];
  }
  const position = (sorted.length - 1) * p;
  const left = Math.floor(position);
  const right = Math.ceil(position);
  if (left === right) {
    return sorted[left];
  }
  const weight = position - left;
  return sorted[left] * (1 - weight) + sorted[right] * weight;
}

function aggregateQuantiles(matches: MatchResult[], forecastBars: number): SearchResult["quantiles"] {
  const lower: number[] = [];
  const median: number[] = [];
  const upper: number[] = [];

  for (let bar = 0; bar < forecastBars; bar += 1) {
    const column = matches
      .map((match) => match.projectedReturns[bar])
      .filter((value): value is number => Number.isFinite(value));
    lower.push(percentile(column, 0.2));
    median.push(percentile(column, 0.5));
    upper.push(percentile(column, 0.8));
  }

  return { lower, median, upper };
}

export function searchPattern(closes: number[], options: SearchOptions): SearchResult {
  const { queryLength, forecastBars, lookbackBars, stride, scales, topMatches } = options;
  if (closes.length < queryLength + forecastBars + 5) {
    return {
      matches: [],
      bestMatch: null,
      quantiles: {
        lower: Array.from({ length: forecastBars }, () => 0),
        median: Array.from({ length: forecastBars }, () => 0),
        upper: Array.from({ length: forecastBars }, () => 0),
      },
    };
  }

  const queryStart = closes.length - queryLength;
  const queryPrices = closes.slice(queryStart);
  const earliestStart = Math.max(0, queryStart - lookbackBars);
  const matches: MatchResult[] = [];

  for (const scale of scales) {
    const candidateLength = Math.max(6, Math.round(queryLength * scale));
    const latestStart = queryStart - candidateLength - forecastBars;
    if (latestStart < earliestStart) {
      continue;
    }

    for (let start = earliestStart; start <= latestStart; start += Math.max(1, stride)) {
      const rawCandidate = closes.slice(start, start + candidateLength);
      const candidatePrices = resampleSeries(rawCandidate, queryLength);
      const breakdown = scoreCandidate(queryPrices, candidatePrices);
      const match: MatchResult = {
        startIndex: start,
        length: candidateLength,
        scale,
        score: breakdown.score,
        breakdown,
        projectedReturns: projectedReturns(closes, start + candidateLength - 1, forecastBars),
      };

      matches.push(match);
    }
  }

  matches.sort((left, right) => right.score - left.score);
  const top = matches.slice(0, Math.max(1, topMatches));
  return {
    matches: top,
    bestMatch: top[0] ?? null,
    quantiles: aggregateQuantiles(top, forecastBars),
  };
}

export function deriveTradeSignal(result: SearchResult, minConfidence: number, threshold: number): TradeSignal {
  const bestMatch = result.bestMatch;
  const projectedReturn = result.quantiles.median[result.quantiles.median.length - 1] ?? 0;
  const confidence = bestMatch?.score ?? 0;

  if (confidence < minConfidence) {
    return { direction: "flat", confidence, projectedReturn };
  }
  if (projectedReturn > threshold) {
    return { direction: "long", confidence, projectedReturn };
  }
  if (projectedReturn < -threshold) {
    return { direction: "short", confidence, projectedReturn };
  }
  return { direction: "flat", confidence, projectedReturn };
}
