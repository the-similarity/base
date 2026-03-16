import { DashboardDataSchema, SearchResponseSchema } from "./schemas";
import { getMockDashboardData } from "./mock-data";
import type { CatalogItem, DatasetSeries, OhlcData, DashboardData, SearchRequest, SearchResponse } from "./types";

const apiBaseUrl = process.env.NEXT_PUBLIC_THE_SIMILARITY_API_URL ?? process.env.THE_SIMILARITY_API_URL ?? "";

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
