/**
 * Scoring method identifiers and display metadata.
 *
 * The engine uses internal method names (dtw, koopman, etc.) in its API
 * responses. These are mapped to opaque "lens" identifiers for the UI so
 * that the engine's method names are never visible to end users.
 */

export const METHODS = [
  "dtw", "pearson_warped", "bempedelis_r2", "bempedelis_smoothness",
  "koopman", "wavelet_spectrum", "emd", "tda", "transfer_entropy",
] as const;

export type MethodName = (typeof METHODS)[number];

// Editorial deck palette: monochrome ink ramp from near-black to light gray.
// No hue; methods are distinguished only by shade, matching the
// "single ink hierarchy" established in globals.css.
export const METHOD_COLORS: Record<string, string> = {
  dtw: "#1a1a1a",
  pearson_warped: "#2d2d2d",
  bempedelis_r2: "#3d3d3d",
  bempedelis_smoothness: "#4a4a4a",
  koopman: "#5a5a5a",
  wavelet_spectrum: "#6b6b6b",
  emd: "#808080",
  tda: "#9a9a9a",
  transfer_entropy: "#b5b5b5",
};

// User-facing labels: obscured names that describe the *kind* of similarity
// without revealing the algorithm. Used in score breakdown bars, detail panels,
// and anywhere a method name is shown to the user.
export const METHOD_LABELS: Record<string, string> = {
  dtw: "Shape",
  pearson_warped: "Dynamics",
  bempedelis_r2: "Scaling R\u00B2",
  bempedelis_smoothness: "Scaling Smooth",
  koopman: "Engine",
  wavelet_spectrum: "Rhythm",
  emd: "Decomposition",
  tda: "Topology",
  transfer_entropy: "Carry",
};

// Camel-case keyed version for use with ScoreBreakdown fields
const snakeToCamel = (s: string) =>
  s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

export const METHOD_LABELS_CAMEL: Record<string, string> =
  Object.fromEntries(
    Object.entries(METHOD_LABELS).map(([k, v]) => [snakeToCamel(k), v]),
  );
