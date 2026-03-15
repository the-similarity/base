"use client";
import { useTerminal } from "../../lib/terminal-context";
import { Sparkline } from "./sparkline";


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

export function DetailPanel() {
  const { state, dispatch } = useTerminal();

  if (state.selectedIdx === null) return null;
  const match = state.matches[state.selectedIdx];
  if (!match) return null;

  const breakdownEntries = Object.entries(match.scoreBreakdown).filter(
    ([, v]) => typeof v === "number" && v > 0,
  );

  // Mini overlay chart: query vs match (normalized)
  const dashData = state.dashboardData;
  const queryValues = dashData
    ? dashData.views[dashData.defaultRange].query
    : [];
  const matchValues = match.matchedSeries || [];

  return (
    <div className="detail-panel">
      <div className="terminal-panel-header">
        <span>
          Match #{state.selectedIdx + 1} &middot;{" "}
          {match.confidenceScore.toFixed(1)}
        </span>
        <button
          onClick={() => dispatch({ type: "SELECT", idx: null })}
          style={{
            marginLeft: "auto",
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
          }}
        >
          [esc]
        </button>
      </div>

      <div style={{ padding: "var(--space-sm)" }}>
        {/* Overlay mini chart */}
        {queryValues.length > 1 && matchValues.length > 1 && (
          <div style={{ marginBottom: "var(--space-md)" }}>
            <div
              style={{
                fontSize: 10,
                color: "var(--text-muted)",
                fontFamily: "var(--font-mono)",
                marginBottom: "var(--space-xs)",
              }}
            >
              OVERLAY
            </div>
            <OverlayMiniChart query={queryValues} matched={matchValues} />
          </div>
        )}

        {/* Window info */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "var(--space-sm)",
            marginBottom: "var(--space-md)",
          }}
        >
          <InfoCell label="Start" value={match.startDate || `idx ${match.startIdx}`} />
          <InfoCell label="End" value={match.endDate || `idx ${match.endIdx}`} />
          <InfoCell
            label="Transform R\u00B2"
            value={match.transformR2.toFixed(4)}
          />
          <InfoCell
            label="Span"
            value={`${match.endIdx - match.startIdx} bars`}
          />
        </div>

        {/* Transform params */}
        {match.transformAlpha && match.transformAlpha.length > 0 && (
          <div style={{ marginBottom: "var(--space-md)" }}>
            <div
              style={{
                fontSize: 10,
                color: "var(--text-muted)",
                fontFamily: "var(--font-mono)",
                marginBottom: "var(--space-xs)",
              }}
            >
              TRANSFORM
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                color: "var(--text-secondary)",
                display: "flex",
                gap: "var(--space-md)",
                flexWrap: "wrap",
              }}
            >
              <span>
                &alpha;=[
                {match.transformAlpha.slice(0, 3).map((a) => a.toFixed(3)).join(", ")}
                {match.transformAlpha.length > 3 ? ", ..." : ""}]
              </span>
              {match.transformBeta && (
                <span>
                  &beta;=[
                  {match.transformBeta.slice(0, 3).map((b) => b.toFixed(3)).join(", ")}
                  {match.transformBeta.length > 3 ? ", ..." : ""}]
                </span>
              )}
            </div>
          </div>
        )}

        {/* Score breakdown */}
        <div>
          <div
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              fontFamily: "var(--font-mono)",
              marginBottom: "var(--space-xs)",
            }}
          >
            SCORE BREAKDOWN
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            {breakdownEntries.map(([method, value]) => (
              <div
                key={method}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-sm)",
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                }}
              >
                <span
                  style={{
                    color: "var(--text-secondary)",
                    width: 90,
                    flexShrink: 0,
                  }}
                >
                  {METHOD_LABELS[method] || method}
                </span>
                <div
                  style={{
                    flex: 1,
                    height: 4,
                    borderRadius: 2,
                    background: "var(--bg-hover)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(value * 100, 100)}%`,
                      height: "100%",
                      background: "var(--accent)",
                      borderRadius: 2,
                    }}
                  />
                </div>
                <span style={{ color: "var(--text-muted)", width: 36, textAlign: "right" }}>
                  {(value * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Forward window sparkline */}
        {match.forwardWindow && match.forwardWindow.length > 1 && (
          <div style={{ marginTop: "var(--space-md)" }}>
            <div
              style={{
                fontSize: 10,
                color: "var(--text-muted)",
                fontFamily: "var(--font-mono)",
                marginBottom: "var(--space-xs)",
              }}
            >
              FORWARD PATH
            </div>
            <Sparkline
              data={match.forwardWindow}
              width={240}
              height={32}
              color="var(--chart-forecast)"
            />
          </div>
        )}
      </div>
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: 9,
          color: "var(--text-muted)",
          fontFamily: "var(--font-mono)",
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 12,
          color: "var(--text-primary)",
          fontFamily: "var(--font-mono)",
        }}
      >
        {value}
      </div>
    </div>
  );
}

function OverlayMiniChart({
  query,
  matched,
}: {
  query: number[];
  matched: number[];
}) {
  const width = 240;
  const height = 60;
  const padY = 4;
  const innerH = height - padY * 2;

  function normalize(values: number[]) {
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (max === min) return values.map(() => 0.5);
    return values.map((v) => (v - min) / (max - min));
  }

  const nq = normalize(query);
  const nm = normalize(matched);
  const maxLen = Math.max(nq.length, nm.length);
  const denom = Math.max(maxLen - 1, 1);

  function toPath(values: number[]) {
    return values
      .map((v, i) => {
        const x = (i / denom) * width;
        const y = padY + innerH - v * innerH;
        return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ display: "block" }}
    >
      <path
        d={toPath(nm)}
        fill="none"
        stroke="var(--chart-match)"
        strokeWidth="1"
        opacity="0.6"
      />
      <path
        d={toPath(nq)}
        fill="none"
        stroke="var(--chart-query)"
        strokeWidth="1.2"
      />
    </svg>
  );
}
