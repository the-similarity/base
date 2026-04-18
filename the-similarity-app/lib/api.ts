/**
 * API client for the-similarity-api backend.
 *
 * All API functions fall back gracefully when the backend is unreachable.
 * The `isApiAvailable()` check lets the workstation decide whether to use
 * real data or the synthetic fallback engine.
 *
 * Score breakdown mapping: the API returns engine-internal field names
 * (dtw, koopman, etc.) which are mapped to opaque lens identifiers
 * (lens1..lens9) via `mapScoreBreakdownToLenses()` before reaching the UI.
 */

import { DashboardDataSchema, SearchResponseSchema } from "./schemas";
import { getMockDashboardData } from "./mock-data";
import type { LensScores, AnalogMatch, ConePoint } from "./data";
import type { CatalogItem, DatasetSeries, OhlcData, DashboardData, SearchRequest, SearchResponse, ScoreBreakdown, ForecastResult } from "./types";

const apiBaseUrl = process.env.NEXT_PUBLIC_THE_SIMILARITY_API_URL ?? process.env.THE_SIMILARITY_API_URL ?? "";

/**
 * Check if the API backend is reachable. Used by the workstation to decide
 * whether to use real data or the synthetic fallback.
 * Timeout: 2 seconds to avoid blocking the UI on slow/dead backends.
 */
export async function isApiAvailable(): Promise<boolean> {
  if (!apiBaseUrl) return false;
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(`${normalizeBaseUrl(apiBaseUrl)}/healthz`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Map the API's ScoreBreakdown (engine-internal names) to the UI's LensScores
 * (opaque lens1..lens9 identifiers). This is the moat-protection boundary —
 * no engine method names cross this function into the UI layer.
 *
 * Mapping:
 *   dtw              → lens1 (Shape)
 *   pearsonWarped     → lens2 (Dynamics)
 *   bempedelisR2      → lens3 (Scaling) — uses mean of R2 and smoothness
 *   waveletSpectrum   → lens4 (Rhythm)
 *   koopman           → lens5 (Engine)
 *   emd               → lens6 (Decomposition)
 *   tda               → lens7 (Topology)
 *   transferEntropy   → lens8 (Carry)
 *   computed consensus→ lens9 (Consensus)
 */
export function mapScoreBreakdownToLenses(bd: ScoreBreakdown): LensScores {
  const lens1 = bd.dtw;
  const lens2 = bd.pearsonWarped;
  // Scaling: average of R2 and smoothness sub-scores
  const lens3 = (bd.bempedelisR2 + bd.bempedelisSmoothness) / 2;
  const lens4 = bd.waveletSpectrum;
  const lens5 = bd.koopman;
  const lens6 = bd.emd;
  const lens7 = bd.tda;
  const lens8 = bd.transferEntropy;

  // Consensus: mean - 0.35 * std of the other 8 lenses
  const arr = [lens1, lens2, lens3, lens4, lens5, lens6, lens7, lens8];
  const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
  const variance = arr.reduce((a, b) => a + (b - mean) ** 2, 0) / arr.length;
  const lens9 = Math.max(0, Math.min(1, mean - 0.35 * Math.sqrt(variance)));

  return { lens1, lens2, lens3, lens4, lens5, lens6, lens7, lens8, lens9 };
}

/**
 * Map the API's SearchResponse matches to the workstation's AnalogMatch format.
 * Handles score mapping, date formatting, and forward window extraction.
 *
 * @param response - Raw search response from the API
 * @param seriesDates - Date strings for the loaded series (for labeling)
 * @param seriesValues - Price values for the loaded series
 * @param windowLen - Length of the query window
 */
export function mapMatchesToAnalogs(
  response: SearchResponse,
  seriesDates: string[],
  seriesValues: number[],
  windowLen: number,
): AnalogMatch[] {
  return response.matches.map((m, idx) => {
    const lenses = mapScoreBreakdownToLenses(m.scoreBreakdown);
    const composite = Object.values(lenses).reduce((a, b) => a + b, 0) / 9;

    // Extract price window from matched series or from the loaded series
    const priceWindow = m.matchedSeries ?? seriesValues.slice(m.startIdx, m.endIdx);
    const after = m.forwardWindow ?? [];
    const lastMatchPrice = priceWindow.length > 0 ? priceWindow[priceWindow.length - 1] : 1;
    const afterReturn = after.length > 0 ? (after[after.length - 1] / lastMatchPrice - 1) : 0;

    // Build date label from API dates or series dates
    const startDateStr = m.startDate ?? seriesDates[m.startIdx] ?? "";
    const endDateStr = m.endDate ?? seriesDates[m.endIdx] ?? "";
    const startDate = startDateStr ? new Date(startDateStr) : new Date();
    const endDate = endDateStr ? new Date(endDateStr) : new Date();

    // Generate a descriptive label from the date
    const year = startDate.getFullYear();
    const label = `Match from ${year}`;

    return {
      id: `API-${m.startIdx}`,
      rank: idx + 1,
      startIdx: m.startIdx,
      date: startDate,
      endDate,
      label,
      composite,
      lenses,
      priceWindow,
      after,
      afterReturn,
      note: generateLensNote(lenses),
    };
  });
}

/** Generate a short narrative note from lens scores (same logic as analogNote). */
function generateLensNote(l: LensScores): string {
  const parts: string[] = [];
  if (l.lens1 > 0.7) parts.push("strong shape alignment");
  if (l.lens2 > 0.75) parts.push("temporal co-movement");
  if (l.lens5 > 0.7) parts.push("dynamical signature match");
  if (l.lens7 > 0.7) parts.push("geometric persistence");
  if (l.lens8 > 0.5) parts.push("predictive carry");
  if (!parts.length) parts.push("mixed-quality match");
  return parts.slice(0, 2).join(" \u00B7 ");
}

/**
 * Map the API's ForecastResponse to the workstation's ConePoint[] format.
 * The API returns percentile curves keyed by percentile number (10, 25, 50, 75, 90).
 * We convert these to absolute price levels relative to queryLastPrice.
 */
export function mapForecastToCone(
  forecast: ForecastResult,
  queryLastPrice: number,
): ConePoint[] {
  const bars = forecast.bars;
  const p10 = forecast.curves["10"] ?? [];
  const p25 = forecast.curves["25"] ?? [];
  const p50 = forecast.curves["50"] ?? [];
  const p75 = forecast.curves["75"] ?? [];
  const p90 = forecast.curves["90"] ?? [];

  const cone: ConePoint[] = [];
  for (let t = 0; t < bars; t++) {
    // API curves are cumulative return ratios — multiply by last price
    // to get absolute price levels. If curves are already absolute, the
    // queryLastPrice factor acts as a scaling anchor.
    cone.push({
      t,
      p10: (p10[t] ?? 1) * queryLastPrice,
      p25: (p25[t] ?? 1) * queryLastPrice,
      p50: (p50[t] ?? 1) * queryLastPrice,
      p75: (p75[t] ?? 1) * queryLastPrice,
      p90: (p90[t] ?? 1) * queryLastPrice,
    });
  }
  return cone;
}

function normalizeBaseUrl(value: string) {
  return value.replace(/\/+$/, "");
}

export async function getDashboardData(): Promise<DashboardData> {
  if (!apiBaseUrl) {
    return getMockDashboardData("mock");
  }

  try {
    const response = await fetch(`${normalizeBaseUrl(apiBaseUrl)}/dashboard`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`Dashboard request failed with status ${response.status}`);
    }

    const json = await response.json();
    return DashboardDataSchema.parse(json);
  } catch (error) {
    console.warn("Falling back to mock dashboard payload.", error);
    return getMockDashboardData("mock");
  }
}

export async function fetchCatalog(): Promise<CatalogItem[]> {
  if (!apiBaseUrl) return [];
  const response = await fetch(`${normalizeBaseUrl(apiBaseUrl)}/catalog`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Catalog request failed (${response.status})`);
  const json = await response.json();
  return (json.datasets ?? []).map((d: Record<string, unknown>) => ({
    assetClass: d.asset_class,
    symbol: d.symbol,
    timeframe: d.timeframe,
    source: d.source,
    rowCount: d.row_count,
    startTimestamp: d.start_timestamp ?? null,
    endTimestamp: d.end_timestamp ?? null,
  }));
}

export async function fetchSeries(
  assetClass: string,
  symbol: string,
  timeframe: string,
  column = "close",
): Promise<DatasetSeries> {
  if (!apiBaseUrl) throw new Error("API not configured");
  const url = `${normalizeBaseUrl(apiBaseUrl)}/datasets/${assetClass}/${symbol}/${timeframe}/series?column=${column}`;
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Series request failed (${response.status})`);
  const json = await response.json();
  return {
    datasetId: json.dataset_id,
    column: json.column,
    values: json.values,
    dates: json.dates ?? [],
    rowCount: json.row_count,
  };
}

export async function fetchOhlc(
  assetClass: string,
  symbol: string,
  timeframe: string,
): Promise<OhlcData> {
  if (!apiBaseUrl) throw new Error("API not configured");
  const url = `${normalizeBaseUrl(apiBaseUrl)}/datasets/${assetClass}/${symbol}/${timeframe}/ohlc`;
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`OHLC request failed (${response.status})`);
  const json = await response.json();
  return {
    datasetId: json.dataset_id,
    open: json.open,
    high: json.high,
    low: json.low,
    close: json.close,
    volume: json.volume ?? [],
    dates: json.dates ?? [],
    rowCount: json.row_count,
  };
}

export async function searchApi(
  request: SearchRequest,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const response = await fetch(`${normalizeBaseUrl(apiBaseUrl)}/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Search failed (${response.status}): ${text}`);
  }

  const json = await response.json();
  return SearchResponseSchema.parse(json);
}
