import type {
  ConfidenceBreakdownItem,
  DashboardData,
  DataSource,
  MatchCard,
  ModuleCard,
  RangeKey,
  RangeView,
} from "./types";

const ranges: RangeKey[] = ["1D", "1W", "1M", "3M", "1Y", "ALL"];

const topMatches: MatchCard[] = [
  {
    label: "Primary analog",
    window: "2019-05-03 -> 2019-08-14",
    score: 86.4,
    delta: 5.8,
    method: "DTW + Pearson",
    regime: "trending_up",
  },
  {
    label: "Volatility twin",
    window: "2020-10-19 -> 2021-01-28",
    score: 82.1,
    delta: 3.2,
    method: "Wavelet",
    regime: "high_vol",
  },
  {
    label: "Compression setup",
    window: "2018-02-12 -> 2018-05-25",
    score: 78.7,
    delta: -1.4,
    method: "Bempedelis",
    regime: "mean_reverting",
  },
  {
    label: "Late cycle echo",
    window: "2023-03-11 -> 2023-06-20",
    score: 74.2,
    delta: 6.9,
    method: "Koopman",
    regime: "trending_up",
  },
];

const architectureCards: ModuleCard[] = [
  {
    module: "io/loader.py",
    responsibility: "Data ingestion from CSV, parquet, DataFrame, dict, and array inputs.",
    scale: "Swap for streaming loader later",
  },
  {
    module: "core/windower.py",
    responsibility: "Sliding window generation and multi-scale candidate indexing.",
    scale: "Chunkable and memory-bound",
  },
  {
    module: "core/matcher.py",
    responsibility: "Pipeline orchestration from query normalization to ranked candidates.",
    scale: "Delegates to independent methods",
  },
  {
    module: "core/scorer.py",
    responsibility: "Confidence aggregation and method score normalization into a 0-100 rank.",
    scale: "Pure math, easy to parallelize",
  },
  {
    module: "core/projector.py",
    responsibility: "Weighted percentile forecast cone from post-match forward paths.",
    scale: "Stateless projection surface",
  },
  {
    module: "methods/",
    responsibility: "Independent scoring engines like DTW, Bempedelis, Wavelet, and Koopman.",
    scale: "Worker-friendly extraction path",
  },
];

const pipelineSteps = [
  "load() -> TimeSeries",
  "normalize(query)",
  "sliding_windows(history)",
  "tier 1 pre-filters",
  "tier 2 method scoring",
  "compute_confidence()",
  "project(matches, history)",
];

const baseBreakdown: ConfidenceBreakdownItem[] = [
  { label: "DTW", value: 0.91 },
  { label: "Pearson", value: 0.84 },
  { label: "Bempedelis", value: 0.71 },
  { label: "Wavelet", value: 0.66 },
  { label: "Koopman", value: 0.58 },
  { label: "EMD", value: 0.42 },
];

function createSeries(
  length: number,
  start: number,
  slope: number,
  amplitude: number,
  frequency: number,
  phase: number,
) {
  return Array.from({ length }, (_, index) => {
    const wave = Math.sin(index * frequency + phase) * amplitude;
    const harmonic = Math.cos(index * frequency * 0.55 + phase * 0.5) * amplitude * 0.32;

    return Number((start + index * slope + wave + harmonic).toFixed(2));
  });
}

function buildForecast(
  anchor: number,
  length: number,
  slope: number,
  amplitude: number,
  phase: number,
) {
  const median = Array.from({ length }, (_, index) => {
    const point = index + 1;

    return Number(
      (
        anchor +
        point * slope +
        Math.sin(point * 0.48 + phase) * amplitude +
        Math.cos(point * 0.24 + phase) * amplitude * 0.35
      ).toFixed(2),
    );
  });

  const p10 = median.map((value, index) => Number((value - 2.4 - index * 0.18).toFixed(2)));
  const p90 = median.map((value, index) => Number((value + 2.4 + index * 0.22).toFixed(2)));

  return { p10, p50: median, p90 };
}

function buildRangeView(
  label: string,
  queryConfig: Parameters<typeof createSeries>,
  matchConfig: Parameters<typeof createSeries>,
  forecastConfig: { length: number; slope: number; amplitude: number; phase: number },
): RangeView {
  const query = createSeries(...queryConfig);
  const bestMatch = createSeries(...matchConfig);
  const anchor = query.at(-1) ?? query[query.length - 1];

  return {
    label,
    query,
    bestMatch,
    forecast: buildForecast(
      anchor,
      forecastConfig.length,
      forecastConfig.slope,
      forecastConfig.amplitude,
      forecastConfig.phase,
    ),
  };
}

const views: Record<RangeKey, RangeView> = {
  "1D": buildRangeView("Intraday scan", [24, 101.6, 0.28, 1.25, 0.54, 0.6], [24, 100.9, 0.26, 1.1, 0.56, 0.75], {
    length: 8,
    slope: 0.21,
    amplitude: 0.7,
    phase: 0.8,
  }),
  "1W": buildRangeView("Weekly shape", [26, 98.8, 0.42, 1.6, 0.42, 0.25], [26, 98.1, 0.39, 1.44, 0.44, 0.36], {
    length: 8,
    slope: 0.34,
    amplitude: 0.86,
    phase: 0.55,
  }),
  "1M": buildRangeView("Monthly analog", [28, 96.3, 0.55, 2.1, 0.33, 0.2], [28, 95.6, 0.5, 1.9, 0.34, 0.28], {
    length: 10,
    slope: 0.46,
    amplitude: 1.05,
    phase: 0.45,
  }),
  "3M": buildRangeView("Quarterly setup", [30, 92.4, 0.66, 2.45, 0.26, 0.18], [30, 91.7, 0.62, 2.2, 0.25, 0.26], {
    length: 12,
    slope: 0.59,
    amplitude: 1.18,
    phase: 0.38,
  }),
  "1Y": buildRangeView("Annual structure", [32, 84.2, 0.94, 3.3, 0.19, 0.18], [32, 83.5, 0.9, 2.95, 0.18, 0.26], {
    length: 12,
    slope: 0.84,
    amplitude: 1.45,
    phase: 0.34,
  }),
  ALL: buildRangeView("Full history", [34, 76.8, 1.12, 4.2, 0.14, 0.16], [34, 75.9, 1.08, 3.8, 0.13, 0.24], {
    length: 14,
    slope: 1.06,
    amplitude: 1.72,
    phase: 0.28,
  }),
};

export function getMockDashboardData(source: DataSource = "mock"): DashboardData {
  return {
    dataSource: source,
    hero: {
      eyebrow: "The Similarity dashboard",
      title: "Pattern search, confidence scoring, and forecast cones in one research desk.",
      description:
        "This Next.js frontend translates the architecture and design docs into a compact operator UI for historical analog discovery.",
      badges: ["Next.js", "TypeScript", "Pydantic contract"],
    },
    ranges,
    defaultRange: "3M",
    views,
    topMatches,
    architectureCards,
    pipelineSteps,
    baseBreakdown,
  };
}
