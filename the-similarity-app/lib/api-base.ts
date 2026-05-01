const configuredApiBaseUrl =
  process.env.NEXT_PUBLIC_THE_SIMILARITY_API_URL ??
  process.env.THE_SIMILARITY_API_URL ??
  "";

export function normalizeApiBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

export function resolveApiBaseUrl(): string {
  if (configuredApiBaseUrl) return normalizeApiBaseUrl(configuredApiBaseUrl);

  if (typeof window === "undefined") return "";

  const { hostname, port } = window.location;
  const frontendPort = Number(port);
  const isLocalHost = hostname === "localhost" || hostname === "127.0.0.1";

  if (isLocalHost && Number.isInteger(frontendPort) && frontendPort >= 3000 && frontendPort <= 3004) {
    return `http://127.0.0.1:${8000 + (frontendPort - 3000)}`;
  }

  return "";
}
