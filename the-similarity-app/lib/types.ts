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
