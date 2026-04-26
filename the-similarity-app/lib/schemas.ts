import { z } from "zod";

export const ForecastBandsSchema = z.object({
  p10: z.array(z.number()),
  p50: z.array(z.number()),
  p90: z.array(z.number()),
});

export const RangeViewSchema = z.object({
  label: z.string(),
  query: z.array(z.number()),
  bestMatch: z.array(z.number()),
  forecast: ForecastBandsSchema,
});

export const MatchCardSchema = z.object({
  label: z.string(),
  window: z.string(),
  score: z.number(),
  delta: z.number(),
  method: z.string(),
  regime: z.string(),
});

export const ModuleCardSchema = z.object({
  module: z.string(),
  responsibility: z.string(),
  scale: z.string(),
});

export const ConfidenceBreakdownItemSchema = z.object({
  label: z.string(),
  value: z.number(),
});

export const HeroContentSchema = z.object({
  eyebrow: z.string(),
  title: z.string(),
  description: z.string(),
  badges: z.array(z.string()),
});

const RangeKeySchema = z.enum(["1D", "1W", "1M", "3M", "1Y", "ALL"]);

export const DashboardDataSchema = z.object({
  dataSource: z.enum(["mock", "api"]),
  hero: HeroContentSchema,
  ranges: z.array(RangeKeySchema),
  defaultRange: RangeKeySchema,
  views: z.record(RangeKeySchema, RangeViewSchema),
  topMatches: z.array(MatchCardSchema),
  architectureCards: z.array(ModuleCardSchema),
  pipelineSteps: z.array(z.string()),
  baseBreakdown: z.array(ConfidenceBreakdownItemSchema),
});

export const ScoreBreakdownSchema = z.object({
  bempedelisR2: z.number().default(0),
  bempedelisSmoothness: z.number().default(0),
  koopman: z.number().default(0),
  waveletSpectrum: z.number().default(0),
  emd: z.number().default(0),
  tda: z.number().default(0),
  dtw: z.number().default(0),
  pearsonWarped: z.number().default(0),
  transferEntropy: z.number().default(0),
});

export const MatchResultSchema = z.object({
  startIdx: z.number(),
  endIdx: z.number(),
  startDate: z.string().nullable().default(null),
  endDate: z.string().nullable().default(null),
  confidenceScore: z.number(),
  scoreBreakdown: ScoreBreakdownSchema,
  matchedSeries: z.array(z.number()).nullable().default(null),
  transformAlpha: z.array(z.number()).nullable().default(null),
  transformBeta: z.array(z.number()).nullable().default(null),
  transformR2: z.number().default(0),
  koopmanEigenvalues: z.array(z.number()).nullable().default(null),
  fractalSpectrum: z.array(z.number()).nullable().default(null),
  persistenceDiagram: z.array(z.array(z.number())).nullable().default(null),
  forwardWindow: z.array(z.number()).nullable().default(null),
});

export const ForecastResponseSchema = z.object({
  bars: z.number(),
  percentiles: z.array(z.number()),
  curves: z.record(z.string(), z.array(z.number())),
  allPaths: z.array(z.array(z.number())),
  weights: z.array(z.number()),
});

/**
 * Reliability diagram bucket: (predicted_level, observed_frequency) pair.
 * Both fields are clamped to [0, 1] by downstream rendering, but the schema
 * itself is permissive (z.number()) so the backend can return slight
 * over/under-shoots (e.g. 1.02) without rejecting the payload.
 */
export const ReliabilityBucketSchema = z.object({
  predicted: z.number(),
  observed: z.number(),
});

/**
 * Calibration metrics schema. `grade` and `regimeDrift` default to
 * "unknown" so older backends that don't return a `metrics` block still
 * produce a valid (but non-graded) payload when forward-compat wrapping
 * synthesizes an empty metrics object. All numeric fields default to 0
 * to keep coerce-from-JSON trivial for the UI.
 */
export const CalibrationMetricsSchema = z.object({
  coverage: z.number().default(0),
  crps: z.number().default(0),
  hitRate: z.number().default(0),
  grade: z.enum(["A", "B", "C", "D", "F", "unknown"]).default("unknown"),
  regimeDrift: z.enum(["low", "elevated", "high", "unknown"]).default("unknown"),
  reliability: z.array(ReliabilityBucketSchema).default([]),
  nAnalogs: z.number().default(0),
});

export const SearchResponseSchema = z.object({
  queryValues: z.array(z.number()),
  matches: z.array(MatchResultSchema),
  forecast: ForecastResponseSchema.nullable().default(null),
  // metrics is optional+nullable so older backends without the field still
  // parse cleanly — the UI falls back to a client-computed metrics block
  // when the server returns null.
  metrics: CalibrationMetricsSchema.nullable().optional().default(null),
});
