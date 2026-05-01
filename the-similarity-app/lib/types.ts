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

/**
 * Calibration grade — discrete quality band for quick at-a-glance judgment.
 *
 * Mapping (derived downstream from coverage + crps + hit_rate):
 *   A → coverage within 5pp of target, crps <= 0.05, hit_rate >= 0.58
 *   B → coverage within 10pp, crps <= 0.08, hit_rate >= 0.54
 *   C → coverage within 15pp, crps <= 0.12, hit_rate >= 0.52
 *   D → coverage within 20pp OR crps <= 0.20
 *   F → worse than the D thresholds
 *   "unknown" → not enough eval history to grade
 */
export type CalibrationGrade = "A" | "B" | "C" | "D" | "F" | "unknown";

/**
 * Regime drift signal — how unstable the matched regime looks vs its
 * historical baseline. "unknown" when the backend has no comparable
 * baseline for the active symbol.
 */
export type RegimeDrift = "low" | "elevated" | "high" | "unknown";

/**
 * A single reliability-diagram bucket: for a predicted probability bin,
 * what fraction of observations fell below the corresponding forecast level.
 * predicted=observed is perfect calibration (the identity line).
 */
export type ReliabilityBucket = {
  /** Predicted probability / nominal CDF level in [0, 1]. */
  predicted: number;
  /** Observed frequency in [0, 1]. */
  observed: number;
};

/**
 * Trust + calibration metrics attached to every search response.
 *
 * All numeric fields MUST be finite — NaN/Infinity are serialized as 0
 * on the wire and the UI renders "—" when `grade === "unknown"`.
 *
 * Numeric conventions:
 *   coverage   — fraction of realized moves inside the P10-P90 cone. Target 0.80.
 *   crps       — average CRPS across analog forward windows (lower is better).
 *   hit_rate   — direction accuracy at horizon. Chance baseline is 0.50.
 */
export type CalibrationMetrics = {
  coverage: number;
  crps: number;
  hitRate: number;
  grade: CalibrationGrade;
  regimeDrift: RegimeDrift;
  reliability: ReliabilityBucket[];
  /** Number of analog forward windows used to compute these metrics. */
  nAnalogs: number;
};

export type SearchResponse = {
  queryValues: number[];
  matches: MatchResult[];
  forecast: ForecastResult | null;
  metrics: CalibrationMetrics | null;
};

/**
 * A single dataset entry as returned by the backend `/catalog` endpoint.
 *
 * Metadata fields (`source`, `rowCount`, `startTimestamp`, `endTimestamp`,
 * `lastUpdatedAt`, `frequency`) are surfaced to the workstation dataset
 * dropdown so each item can render a rich card (source badge, date
 * range, bar count, staleness indicator). They are all TREATED AS
 * OPTIONAL by the UI: a freshly-ingested dataset whose manifest entry
 * hasn't been rewritten yet may arrive without them, and the dropdown
 * must degrade gracefully (render the core "SYMBOL · TIMEFRAME"
 * identifier and omit the sub-lines) rather than erroring.
 *
 * `frequency` is a server-derived human-readable label (e.g. "1 hour"
 * for timeframe "1h"). The frontend must NEVER re-parse `timeframe`
 * locally — if the backend doesn't supply `frequency`, the raw short
 * code is acceptable fallback.
 */
export type CatalogItem = {
  assetClass: string;
  symbol: string;
  timeframe: string;
  source: string;
  rowCount: number;
  startTimestamp: string | null;
  endTimestamp: string | null;
  lastUpdatedAt: string | null;
  frequency: string | null;
};

export type DatasetSeries = {
  datasetId: string;
  column: string;
  values: number[];
  dates: string[];
  rowCount: number;
};

export type OhlcData = {
  datasetId: string;
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  volume: number[];
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
  /**
   * Cross-timeframe pattern matching. When non-empty the backend
   * runs `cross_timeframe_search`: history is resampled to each
   * pandas frequency code (e.g. "5min", "15min", "1h", "4h") and the
   * query window is rescaled per-timeframe so it covers the same
   * temporal duration at every resolution. Matches across all
   * resolutions are merged + deduped.
   *
   * Leave empty (or omit) for the default single-timeframe path.
   */
  timeframes?: string[];
  /**
   * ISO-8601 timestamps paired 1:1 with `historyValues`. REQUIRED
   * when `timeframes` is non-empty — the backend cannot build a
   * DatetimeIndex for resampling without these.
   */
  historyDates?: string[];
};
