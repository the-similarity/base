export const METHODS = [
  "dtw", "pearson_warped", "bempedelis_r2", "bempedelis_smoothness",
  "koopman", "wavelet_spectrum", "emd", "tda", "transfer_entropy",
] as const;

export type MethodName = (typeof METHODS)[number];

export const METHOD_COLORS: Record<string, string> = {
  dtw: "#4ade80",
  pearson_warped: "#60a5fa",
  bempedelis_r2: "#f472b6",
  bempedelis_smoothness: "#fb923c",
  koopman: "#a78bfa",
  wavelet_spectrum: "#2dd4bf",
  emd: "#fbbf24",
  tda: "#f87171",
  transfer_entropy: "#94a3b8",
};

export const METHOD_LABELS: Record<string, string> = {
  dtw: "DTW",
  pearson_warped: "Pearson",
  bempedelis_r2: "Bemp R²",
  bempedelis_smoothness: "Bemp Smooth",
  koopman: "Koopman",
  wavelet_spectrum: "Wavelet",
  emd: "EMD",
  tda: "TDA",
  transfer_entropy: "TE",
};

// Camel-case keyed version for use with ScoreBreakdown fields
const snakeToCamel = (s: string) =>
  s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

export const METHOD_LABELS_CAMEL: Record<string, string> =
  Object.fromEntries(
    Object.entries(METHOD_LABELS).map(([k, v]) => [snakeToCamel(k), v]),
  );
