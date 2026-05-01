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
import { normalizeApiBaseUrl, resolveApiBaseUrl } from "./api-base";
import type { LensScores, AnalogMatch, ConePoint } from "./data";
import type { CatalogItem, DatasetSeries, OhlcData, DashboardData, SearchRequest, SearchResponse, ScoreBreakdown, ForecastResult } from "./types";

/**
 * Check if the API backend is reachable. Used by the workstation to decide
 * whether to use real data or the synthetic fallback.
 * Timeout: 2 seconds to avoid blocking the UI on slow/dead backends.
 */
export async function isApiAvailable(): Promise<boolean> {
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) return false;
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(`${normalizeApiBaseUrl(apiBaseUrl)}/healthz`, {
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

    // Extract price window from matched series or from the loaded series.
    const priceWindow = m.matchedSeries ?? seriesValues.slice(m.startIdx, m.endIdx);
    const lastMatchPrice = priceWindow.length > 0 ? priceWindow[priceWindow.length - 1] : 1;

    /*
     * Unit contract (must stay aligned with `the_similarity/core/projector.py`):
     *   backend `forward_window` is a list of CENTERED CUMULATIVE RETURNS,
     *   i.e. `(future_price - anchor) / anchor` where `anchor` is the last
     *   price of the matched window. A value of `0.05` means "5% above the
     *   match's end price" — NOT an absolute price.
     *
     * Downstream consumers (workstation LineChart, analog cards, the
     * trust strip) work in the SAME price-scale as `priceWindow`. We
     * convert here so `after` is a drop-in continuation of priceWindow
     * rather than requiring every consumer to know about the mixed
     * unit situation.
     *
     * afterReturn (used by the ranked-analog cards and summary text) is
     * just the last centered return — NOT the previous buggy
     * `after[-1] / lastMatchPrice - 1`, which treated `after` as prices
     * and produced nonsense values like −99.999%.
     */
    const rawReturns = m.forwardWindow ?? [];
    const after = rawReturns.map(r => (1 + r) * lastMatchPrice);
    const afterReturn = rawReturns.length > 0 ? rawReturns[rawReturns.length - 1] : 0;

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
      // Preserve raw math-name scores for features that need the
      // engine-native breakdown (e.g. "Save to goodrun" in the
      // AnalogDetailDrawer). These are the pre-mapping fields — the UI
      // moat (`lens1..9`) is enforced by only READING these in
      // opt-in consumers, not by their absence.
      scoreBreakdown: {
        dtw: m.scoreBreakdown.dtw,
        pearsonWarped: m.scoreBreakdown.pearsonWarped,
        bempedelisR2: m.scoreBreakdown.bempedelisR2,
        bempedelisSmoothness: m.scoreBreakdown.bempedelisSmoothness,
        koopman: m.scoreBreakdown.koopman,
        waveletSpectrum: m.scoreBreakdown.waveletSpectrum,
        emd: m.scoreBreakdown.emd,
        tda: m.scoreBreakdown.tda,
        transferEntropy: m.scoreBreakdown.transferEntropy,
      },
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
 *
 * Unit contract: the backend `/search` endpoint returns percentile curves
 * expressed as *centered cumulative returns* — i.e. `(future_price - anchor)
 * / anchor`. A value of `0.05` means "5% above the anchor price", not
 * "5 percent of the anchor price". See `the_similarity/core/projector.py`
 * (function `project`, line `returns = (future - anchor) / anchor`).
 *
 * LineChart / ConePoint expects *absolute price levels* on the same scale
 * as the main series, so we convert with `(1 + return) * anchor`. The
 * previous implementation used `return * anchor`, which treated the curves
 * as fractions of anchor rather than deltas — the cone rendered near zero
 * on the raw-price axis (the 'cone drawn at the bottom' bug) and the
 * derived `p50Return` metric printed impossible values like −104.8%.
 *
 * Default sentinel is 0 (no move from anchor), not 1: if the backend drops
 * a bar, the cone stays pinned at the anchor instead of jumping to 2×.
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

  // Convert centered returns to absolute prices: price = (1 + r) * anchor.
  const toPrice = (r: number | undefined) => (1 + (r ?? 0)) * queryLastPrice;

  const cone: ConePoint[] = [];
  for (let t = 0; t < bars; t++) {
    cone.push({
      t,
      p10: toPrice(p10[t]),
      p25: toPrice(p25[t]),
      p50: toPrice(p50[t]),
      p75: toPrice(p75[t]),
      p90: toPrice(p90[t]),
    });
  }
  return cone;
}

export async function getDashboardData(): Promise<DashboardData> {
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) {
    return getMockDashboardData("mock");
  }

  try {
    const response = await fetch(`${normalizeApiBaseUrl(apiBaseUrl)}/dashboard`, {
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

/**
 * Fetch the dataset catalog from the backend.
 *
 * The response includes the rich metadata used by the workstation's
 * dataset dropdown: source, date range, row count, last-updated
 * timestamp, and human-readable frequency label. Every field except the
 * identifier triple (assetClass / symbol / timeframe) is treated as
 * optional on the wire — older backends that don't yet ship the
 * metadata simply leave the corresponding TS fields `null` / `0` and
 * the UI renders a minimal card.
 *
 * Returns an empty array when the API is not configured (the offline /
 * demo-mode path uses a static synthetic entry instead of hitting this
 * function).
 */
export async function fetchCatalog(): Promise<CatalogItem[]> {
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) return [];
  const response = await fetch(`${normalizeApiBaseUrl(apiBaseUrl)}/catalog`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Catalog request failed (${response.status})`);
  const json = await response.json();
  return (json.datasets ?? []).map((d: Record<string, unknown>) => ({
    assetClass: d.asset_class as string,
    symbol: d.symbol as string,
    timeframe: d.timeframe as string,
    // Source may legitimately be absent on legacy manifests; preserve
    // "unknown" as a stable display string rather than letting `null`
    // trickle into the UI and force every consumer to null-check it.
    source: (d.source as string | undefined) ?? "unknown",
    rowCount: (d.row_count as number | undefined) ?? 0,
    startTimestamp: (d.start_timestamp as string | null | undefined) ?? null,
    endTimestamp: (d.end_timestamp as string | null | undefined) ?? null,
    lastUpdatedAt: (d.last_updated_at as string | null | undefined) ?? null,
    // Frequency is derived server-side; fall back to the raw timeframe
    // code if an older backend omits it so the dropdown still shows
    // *something* readable.
    frequency: (d.frequency as string | null | undefined) ?? (d.timeframe as string),
  }));
}

export async function fetchSeries(
  assetClass: string,
  symbol: string,
  timeframe: string,
  column = "close",
): Promise<DatasetSeries> {
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) throw new Error("API not configured");
  const url = `${normalizeApiBaseUrl(apiBaseUrl)}/datasets/${assetClass}/${symbol}/${timeframe}/series?column=${column}`;
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
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) throw new Error("API not configured");
  const url = `${normalizeApiBaseUrl(apiBaseUrl)}/datasets/${assetClass}/${symbol}/${timeframe}/ohlc`;
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
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) throw new Error("API not configured");
  const response = await fetch(`${normalizeApiBaseUrl(apiBaseUrl)}/search`, {
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
