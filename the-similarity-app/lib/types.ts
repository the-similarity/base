export type TabKey = "overview" | "matches" | "forecast" | "architecture";
export type RangeKey = "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL";
export type DataSource = "mock" | "api";

export type ForecastBands = {
  p10: number[];
  p50: number[];
  p90: number[];
};

export type RangeView = {
  label: string;
  query: number[];
  bestMatch: number[];
  forecast: ForecastBands;
};

export type MatchCard = {
  label: string;
  window: string;
  score: number;
  delta: number;
  method: string;
  regime: string;
};

export type ModuleCard = {
  module: string;
  responsibility: string;
  scale: string;
};

export type ConfidenceBreakdownItem = {
  label: string;
  value: number;
};

export type HeroContent = {
  eyebrow: string;
  title: string;
  description: string;
  badges: string[];
};

export type DashboardData = {
  dataSource: DataSource;
  hero: HeroContent;
  ranges: RangeKey[];
  defaultRange: RangeKey;
  views: Record<RangeKey, RangeView>;
  topMatches: MatchCard[];
  architectureCards: ModuleCard[];
  pipelineSteps: string[];
  baseBreakdown: ConfidenceBreakdownItem[];
};

export type ScoreBreakdown = {
  bempedelisR2: number;
  bempedelisSmoothness: number;
  koopman: number;
  waveletSpectrum: number;
  emd: number;
  tda: number;
  dtw: number;
  pearsonWarped: number;
  transferEntropy: number;
};

export type MatchResult = {
  startIdx: number;
  endIdx: number;
  startDate: string | null;
  endDate: string | null;
  confidenceScore: number;
  scoreBreakdown: ScoreBreakdown;
  matchedSeries: number[] | null;
  transformAlpha: number[] | null;
  transformBeta: number[] | null;
  transformR2: number;
  koopmanEigenvalues: number[] | null;
  fractalSpectrum: number[] | null;
  persistenceDiagram: number[][] | null;
  forwardWindow: number[] | null;
};

export type ForecastResult = {
  bars: number;
  percentiles: number[];
  curves: Record<string, number[]>;
  allPaths: number[][];
  weights: number[];
};

export type SearchResponse = {
  queryValues: number[];
  matches: MatchResult[];
  forecast: ForecastResult | null;
};

export type CatalogItem = {
  assetClass: string;
  symbol: string;
  timeframe: string;
  source: string;
  rowCount: number;
  startTimestamp: string | null;
  endTimestamp: string | null;
};

export type DatasetSeries = {
  datasetId: string;
  column: string;
  values: number[];
  dates: string[];
  rowCount: number;
};

export type SearchRequest = {
  queryValues: number[];
  historyValues: number[];
  topK?: number;
  forwardBars?: number;
  excludeSelf?: boolean;
  normalization?: string;
  stride?: number;
  tier1Candidates?: number;
  tier2Candidates?: number;
  activeMethods?: string[];
  percentiles?: number[];
  weights?: Record<string, number>;
};
