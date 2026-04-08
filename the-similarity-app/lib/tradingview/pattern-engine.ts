export type TradeBias = "both" | "long" | "short";
export type SignalDirection = "long" | "short" | "flat";

export type MatchScoreBreakdown = {
  correlation: number;
  rmse: number;
  directional: number;
  volatility: number;
};

export type SearchOptions = {
  patternLength: number;
  searchDepth: number;
  searchStep: number;
  forecastBars: number;
  scaleFactors?: number[];
};

export type BestMatch = {
  candidateStart: number;
  candidateLength: number;
  candidateEnd: number;
  scaleFactor: number;
  score: number;
  confidence: number;
  breakdown: MatchScoreBreakdown;
  queryWindow: number[];
  matchedWindow: number[];
  projectedPath: number[];
  projectedReturn: number;
};

export type TradeDecision = {
  direction: SignalDirection;
  confidence: number;
  projectedReturn: number;
  reason: string;
};

const EPSILON = 1e-9;
const DEFAULT_SCALE_FACTORS = [0.75, 1, 1.25];

function mean(values: number[]): number {
  if (values.length === 0) return 0;

  return values.reduce((total, value) => total + value, 0) / values.length;
}

function standardDeviation(values: number[]): number {
  if (values.length === 0) return 0;

  const avg = mean(values);
  const variance = values.reduce((total, value) => total + (value - avg) ** 2, 0) / values.length;

  return Math.sqrt(variance);
}

export function linearResample(values: number[], targetLength: number): number[] {
  if (targetLength <= 0) return [];
  if (values.length === 0) return Array.from({ length: targetLength }, () => 0);
  if (values.length === 1) return Array.from({ length: targetLength }, () => values[0]);
  if (values.length === targetLength) return [...values];

  return Array.from({ length: targetLength }, (_, index) => {
    const position = (index * (values.length - 1)) / Math.max(targetLength - 1, 1);
    const leftIndex = Math.floor(position);
    const rightIndex = Math.min(values.length - 1, Math.ceil(position));
    const fraction = position - leftIndex;
    const leftValue = values[leftIndex];
    const rightValue = values[rightIndex];

    return leftValue + (rightValue - leftValue) * fraction;
  });
}

export function percentReturns(values: number[]): number[] {
  if (values.length < 2) return [];

  return values.slice(1).map((value, index) => {
    const previous = values[index];
    if (Math.abs(previous) < EPSILON) return 0;

    return (value - previous) / previous;
  });
}

export function zScore(values: number[]): number[] {
  if (values.length === 0) return [];

  const avg = mean(values);
  const stdev = standardDeviation(values);
  if (stdev < EPSILON) return Array.from({ length: values.length }, () => 0);

  return values.map((value) => (value - avg) / stdev);
}

export function normalizePattern(values: number[]): number[] {
  return zScore(percentReturns(values));
}

export function correlationScore(a: number[], b: number[]): number {
  const length = Math.min(a.length, b.length);
  if (length === 0) return 0;

  let dot = 0;
  let aNorm = 0;
  let bNorm = 0;
  for (let index = 0; index < length; index += 1) {
    dot += a[index] * b[index];
    aNorm += a[index] * a[index];
    bNorm += b[index] * b[index];
  }

  if (aNorm < EPSILON || bNorm < EPSILON) return 0;

  const correlation = dot / Math.sqrt(aNorm * bNorm);
  return Math.max(0, Math.min(1, (correlation + 1) / 2));
}

export function rmseScore(a: number[], b: number[]): number {
  const length = Math.min(a.length, b.length);
  if (length === 0) return 0;

  let squaredError = 0;
  for (let index = 0; index < length; index += 1) {
    squaredError += (a[index] - b[index]) ** 2;
  }

  const rmse = Math.sqrt(squaredError / length);
  return 1 / (1 + rmse);
}

export function directionalAgreement(a: number[], b: number[]): number {
  const length = Math.min(a.length, b.length);
  if (length === 0) return 0;

  let agreement = 0;
  for (let index = 0; index < length; index += 1) {
    const signA = Math.sign(a[index]);
    const signB = Math.sign(b[index]);
    if (signA === signB) {
      agreement += 1;
    }
  }

  return agreement / length;
}

export function volatilitySimilarity(aReturns: number[], bReturns: number[]): number {
  const volA = standardDeviation(aReturns);
  const volB = standardDeviation(bReturns);
  const maxVol = Math.max(volA, volB);
  if (maxVol < EPSILON) return 1;

  const minVol = Math.min(volA, volB);
  return minVol / maxVol;
}

export function scorePatternMatch(queryWindow: number[], candidateWindow: number[]) {
  const normalizedQuery = normalizePattern(queryWindow);
  const normalizedCandidate = normalizePattern(candidateWindow);
  const queryReturns = percentReturns(queryWindow);
  const candidateReturns = percentReturns(candidateWindow);

  const breakdown: MatchScoreBreakdown = {
    correlation: correlationScore(normalizedQuery, normalizedCandidate),
    rmse: rmseScore(normalizedQuery, normalizedCandidate),
    directional: directionalAgreement(queryReturns, candidateReturns),
    volatility: volatilitySimilarity(queryReturns, candidateReturns),
  };

  const score =
    breakdown.correlation * 0.4 +
    breakdown.rmse * 0.25 +
    breakdown.directional * 0.2 +
    breakdown.volatility * 0.15;

  return {
    score,
    confidence: score * 100,
    breakdown,
  };
}

export function scalePathToAnchor(path: number[], candidateAnchor: number, currentAnchor: number): number[] {
  if (path.length === 0 || Math.abs(candidateAnchor) < EPSILON) return [];

  return path.map((value) => {
    const relativeReturn = (value - candidateAnchor) / candidateAnchor;
    return currentAnchor * (1 + relativeReturn);
  });
}

export function findBestPatternMatch(series: number[], options: SearchOptions): BestMatch | null {
  const { patternLength, searchDepth, searchStep, forecastBars } = options;
  const scaleFactors = options.scaleFactors?.length ? options.scaleFactors : DEFAULT_SCALE_FACTORS;

  if (patternLength < 4 || series.length < patternLength * 2 + forecastBars + 1) {
    return null;
  }

  const queryStart = series.length - patternLength;
  const queryWindow = series.slice(queryStart);
  const currentAnchor = queryWindow.at(-1) ?? queryWindow[queryWindow.length - 1];
  let bestMatch: BestMatch | null = null;

  for (const scaleFactor of scaleFactors) {
    const candidateLength = Math.max(4, Math.round(patternLength * scaleFactor));
    const searchStart = Math.max(0, queryStart - searchDepth);
    const searchEnd = queryStart - forecastBars - candidateLength;

    if (searchEnd < searchStart) {
      continue;
    }

    for (let candidateStart = searchStart; candidateStart <= searchEnd; candidateStart += searchStep) {
      const candidateEnd = candidateStart + candidateLength;
      const candidateRaw = series.slice(candidateStart, candidateEnd);
      const candidateWindow = linearResample(candidateRaw, patternLength);
      const projectionSource = series.slice(candidateEnd, candidateEnd + forecastBars);
      if (projectionSource.length !== forecastBars) {
        continue;
      }

      const { score, confidence, breakdown } = scorePatternMatch(queryWindow, candidateWindow);
      const candidateAnchor = candidateRaw.at(-1) ?? candidateRaw[candidateRaw.length - 1];
      const projectedPath = scalePathToAnchor(projectionSource, candidateAnchor, currentAnchor);
      const projectedReturn = Math.abs(currentAnchor) < EPSILON
        ? 0
        : (projectedPath.at(-1)! - currentAnchor) / currentAnchor;

      if (!bestMatch || score > bestMatch.score) {
        bestMatch = {
          candidateStart,
          candidateLength,
          candidateEnd,
          scaleFactor,
          score,
          confidence,
          breakdown,
          queryWindow,
          matchedWindow: scalePathToAnchor(candidateWindow, candidateAnchor, currentAnchor),
          projectedPath,
          projectedReturn,
        };
      }
    }
  }

  return bestMatch;
}

export function decideTradeSignal(params: {
  confidence: number;
  projectedReturn: number;
  minConfidence: number;
  minProjectedMove: number;
  bias?: TradeBias;
}): TradeDecision {
  const { confidence, projectedReturn, minConfidence, minProjectedMove, bias = "both" } = params;

  if (confidence < minConfidence) {
    return {
      direction: "flat",
      confidence,
      projectedReturn,
      reason: "confidence below threshold",
    };
  }

  if (projectedReturn >= minProjectedMove && bias !== "short") {
    return {
      direction: "long",
      confidence,
      projectedReturn,
      reason: "bullish analog projection",
    };
  }

  if (projectedReturn <= -minProjectedMove && bias !== "long") {
    return {
      direction: "short",
      confidence,
      projectedReturn,
      reason: "bearish analog projection",
    };
  }

  return {
    direction: "flat",
    confidence,
    projectedReturn,
    reason: "projected move below threshold or blocked by bias",
  };
}
