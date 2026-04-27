/**
 * Rhymes screen — THE HERO SCREEN.
 *
 * The product's mission framing is "world's first general prediction"
 * applied to personal health: find rhymes in YOUR OWN past biomarker
 * data and project what's likely to come next. This screen makes that
 * mechanic visible end-to-end:
 *
 *   1. Hero — date range + "5 rhymes found" headline + p50 forecast
 *      summary ("HRV likely 60-72ms over next 14 days")
 *   2. Forecast cone — top-of-page big chart with the weighted-quantile
 *      projection over 14 days, anchored at today's HRV
 *   3. Rhyme cards (5) — each card shows:
 *      - source date range from user's own past
 *      - similarity % score
 *      - mini multivariate biomarker overlay (5 channels: then vs now)
 *      - "what came next" outcome label (illness / overtraining /
 *         breakthrough / recovery / fatigue cycle / steady)
 *      - optional context tag (training / travel / illness / etc.)
 *
 * Local state:
 *   - `selected`: which rhyme card is the "active" one (drives the cone
 *      to spotlight that single rhyme's outcome). Default: 0 (top rhyme).
 *
 * Why this is the soul of the product:
 *   Cadence's pitch is "your body has rhymed before — here's what came
 *   next." This screen IS that pitch. Prudent does the analogous thing
 *   for trader narratives; Cadence does it for biomarkers. Both are
 *   downstream of the same Similarity primitive (analogue retrieval +
 *   projection + calibrated uncertainty).
 */
"use client";

import { useMemo, useState } from "react";
import { Icon } from "../icons";
import { Pill, Topbar, SectionHead } from "../shared";
import { ForecastCone, Sparkline } from "../charts";
import { DAYS, FMT, TAG_META, BASELINE } from "../data";
import type { DaySummary } from "../data";
import { findRhymes, OUTCOME_META, projectFromRhymes, RHYME_CHANNELS } from "../../engine";
import type { RhymeWindow } from "../../engine";
import type { ScreenProps } from "../screen-types";

export function ScreenRhymes({ onCmdK }: ScreenProps) {
  const [selected, setSelected] = useState(0);

  const last7 = DAYS.slice(0, 7);
  const today = DAYS[0];

  // Run the rhyme finder. K=5 surfaces enough analogues that the cone
  // shows real disagreement between historical outcomes (the cone width
  // IS the calibrated uncertainty story we're trying to tell).
  const rhymes = useMemo(() => findRhymes(DAYS, last7, { k: 5 }), [last7]);

  // The cone uses ALL rhymes for the weighted-quantile blend. The
  // selected rhyme drives the highlighted card UI but doesn't subset
  // the cone — that would be statistically dishonest (k=1 has no
  // uncertainty to express).
  const cone = useMemo(() => projectFromRhymes(rhymes, 14), [rhymes]);

  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Rhymes"]}
        onCmdK={onCmdK}
        actions={
          <button className="btn">
            <Icon name="download" /> Export
          </button>
        }
      />

      <div className="scroll">
        <div className="scroll-pad">
          {/* Hero */}
          <div className="h-eyebrow mb-8">
            Self-similarity over your own data · last 7 days
          </div>
          <div className="h-display num" style={{ fontSize: 44 }}>
            {rhymes.length} rhymes found
          </div>
          <div className="row gap-12 mt-12 mb-20">
            <Pill tone="pos" dot>
              best match {rhymes[0]?.score ?? 0}% similar
            </Pill>
            {cone.length > 0 && (
              <Pill tone="info">
                14-day HRV projection {Math.round(cone[cone.length - 1].p10)}–{Math.round(cone[cone.length - 1].p90)}ms
              </Pill>
            )}
            <span className="text-3 fz-12">
              5 channels · z-normalized RMSE · weighted-quantile cone
            </span>
          </div>

          {/* Forecast cone */}
          <div className="card mt-8" style={{ padding: "16px 20px 12px 12px" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, padding: "0 0 4px 12px" }}>
              <div className="title fz-13 fw-6">14-day HRV projection</div>
              <span className="text-3 fz-12">p10 / p50 / p90 across {rhymes.length} rhymes</span>
            </div>
            <ForecastCone
              cone={cone}
              anchor={today.hrv}
              color="var(--accent)"
              yMin={Math.max(20, BASELINE.hrv - 30)}
              yMax={BASELINE.hrv + 30}
            />
            <div className="row gap-16 mt-8 fz-11 text-3" style={{ paddingLeft: 38 }}>
              <span>
                <span style={{ display: "inline-block", width: 14, borderTop: "2px solid var(--accent)", verticalAlign: "middle", marginRight: 4 }} />
                p50 (median outcome)
              </span>
              <span>
                <span style={{ display: "inline-block", width: 14, borderTop: "2px dashed var(--accent)", opacity: 0.5, verticalAlign: "middle", marginRight: 4 }} />
                p10 / p90 (uncertainty band)
              </span>
            </div>
          </div>

          {/* Rhyme cards */}
          <div className="section-head mt-24">
            <div className="title">Rhymes</div>
            <div className="sub">Click to select · the cone uses all 5 weighted by similarity</div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 12 }}>
            {rhymes.map((r, i) => (
              <RhymeCard
                key={`${r.startIdx}-${r.endIdx}`}
                r={r}
                today={last7}
                featured={i === selected}
                onClick={() => setSelected(i)}
                rank={i + 1}
              />
            ))}
          </div>

          {/* Methodology note */}
          <div className="card tinted card-pad mt-24">
            <SectionHead title="How rhymes are found" sub="Methodology" />
            <div className="text-2 fz-13" style={{ lineHeight: 1.6 }}>
              For each candidate 7-day window in your own history, Cadence
              z-normalizes 5 channels (HRV, RHR, sleep, energy, glucose),
              computes per-channel L2 distance to today's window, averages
              across channels, then maps to a similarity score
              <span className="mono"> 100·exp(−distance)</span>. The 14 days
              that followed each rhyming window become the projection set,
              blended by similarity into the forecast cone above.
              <br />
              <br />
              No cohort. No HIPAA. No &ldquo;is this stranger like me.&rdquo;
              Just your body&rsquo;s own rhymes.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────── helpers ───────────

interface RhymeCardProps {
  r: RhymeWindow;
  today: DaySummary[];
  featured?: boolean;
  onClick: () => void;
  rank: number;
}

function RhymeCard({ r, today, featured, onClick, rank }: RhymeCardProps) {
  const om = OUTCOME_META[r.outcomeLabel];
  return (
    <button
      onClick={onClick}
      className={`rhyme-card ${featured ? "featured" : ""}`}
      style={{ textAlign: "left", width: "100%", cursor: "pointer" }}
    >
      <div className="rh-head">
        <span className="text-3 fz-11 mono">#{rank}</span>
        <span className="rh-date">
          {FMT.shortDate(r.window[r.window.length - 1].date)} – {FMT.shortDate(r.window[0].date)}
        </span>
        <span className="rh-score">{r.score}% match</span>
        {r.contextTag && (
          <Pill tone="default" style={{ background: TAG_META[r.contextTag].color + "22", color: TAG_META[r.contextTag].color }}>
            {TAG_META[r.contextTag].label}
          </Pill>
        )}
        <span className="right text-3 fz-12" style={{ marginLeft: "auto", color: om.color, fontWeight: 600 }}>
          {om.label}
        </span>
      </div>

      {/* Multivariate biomarker overlay — 5 mini sparklines side-by-side */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
        {RHYME_CHANNELS.map((c) => {
          const thenSeries = r.window.map((d) => d[c] as number).reverse();
          const nowSeries = today.map((d) => d[c] as number).reverse();
          const cur = today[0][c] as number;
          return (
            <div key={c}>
              <div className="text-3 fz-11" style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 2 }}>
                <span style={{ textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 550 }}>{c}</span>
                <span className="mono">{cur}</span>
              </div>
              <div style={{ position: "relative", height: 36 }}>
                <div style={{ position: "absolute", inset: 0, opacity: 0.45 }}>
                  <Sparkline data={thenSeries} stroke="var(--ink-3)" width={140} height={36} fill={false} dot={false} smooth={false} />
                </div>
                <div style={{ position: "absolute", inset: 0 }}>
                  <Sparkline data={nowSeries} stroke="var(--accent)" width={140} height={36} fill={false} dot smooth />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </button>
  );
}
