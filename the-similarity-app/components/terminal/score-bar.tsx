"use client";
import type { ScoreBreakdown } from "@/lib/types";

const METHOD_COLORS: Record<string, string> = {
  bempedelisR2: "#f472b6",
  bempedelisSmoothness: "#fb923c",
  koopman: "#a78bfa",
  waveletSpectrum: "#2dd4bf",
  emd: "#fbbf24",
  tda: "#f87171",
  dtw: "#4ade80",
  pearsonWarped: "#60a5fa",
  transferEntropy: "#94a3b8",
};

const METHOD_LABELS: Record<string, string> = {
  bempedelisR2: "Bemp R\u00B2",
  bempedelisSmoothness: "Bemp Smooth",
  koopman: "Koopman",
  waveletSpectrum: "Wavelet",
  emd: "EMD",
  tda: "TDA",
  dtw: "DTW",
  pearsonWarped: "Pearson",
  transferEntropy: "TE",
};

export function ScoreBar({ breakdown }: { breakdown: ScoreBreakdown }) {
  const entries = Object.entries(breakdown).filter(
    ([, v]) => typeof v === "number" && v > 0,
  );
  const total = entries.reduce((s, [, v]) => s + v, 0) || 1;

  return (
    <div
      className="score-bar-track"
      title={entries
        .map(
          ([k, v]) =>
            `${METHOD_LABELS[k] || k}: ${(v * 100).toFixed(0)}%`,
        )
        .join(", ")}
    >
      <div style={{ display: "flex", height: "100%", width: "100%" }}>
        {entries.map(([method, value]) => (
          <div
            key={method}
            className="score-bar-fill"
            style={{
              width: `${(value / total) * 100}%`,
              background: METHOD_COLORS[method] || "var(--text-muted)",
            }}
          />
        ))}
      </div>
    </div>
  );
}
