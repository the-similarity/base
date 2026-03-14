import { DashboardDataSchema, SearchResponseSchema } from "./schemas";
import { getMockDashboardData } from "./mock-data";
import type { DashboardData, SearchRequest, SearchResponse } from "./types";

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
