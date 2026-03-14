import { getMockDashboardData } from "./mock-data";
import type { DashboardData } from "./types";

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
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`Dashboard request failed with status ${response.status}`);
    }

    return (await response.json()) as DashboardData;
  } catch (error) {
    console.warn("Falling back to mock dashboard payload.", error);
    return getMockDashboardData("mock");
  }
}
