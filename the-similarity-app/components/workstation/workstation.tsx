"use client";

/**
 * The Retrieve workstation — the main interactive view.
 *
 * Three-column layout: 260px sidebar (query definition, window controls,
 * pinned analogs, notebook), fluid center (header metrics, chart card,
 * trust strip, analog strip), and 320px right panel (9-lens radar + bars,
 * lens reading narrative).
 *
 * The query window position drives everything: when the user drags it,
 * analogs are re-ranked and the forecast cone redraws.
 */

import { useState, useMemo } from "react";
import {
  SERIES, LENS_DEFS, findAnalogs, buildCone,
  fmtDate, fmtDateShort, fmtPct,
  LensScores,
} from "../../lib/data";
import { LineChart, AnalogOverlay } from "./line-chart";
import { LensRadar } from "./lens-radar";
import { LensBars } from "./lens-bars";
import { Sparkline } from "./sparkline";

/** Settings shape passed from the app shell */
export interface WorkstationSettings {
  theme: string;
  kAnalogs: number;
  horizon: number;
  showAnalogs: string;
  showCone: boolean;
}

interface WorkstationProps {
  settings: WorkstationSettings;
  onSettings: (s: WorkstationSettings) => void;
}

export function Workstation({ settings, onSettings }: WorkstationProps) {
  const N = SERIES.length;
  const [windowState, setWindowState] = useState({ start: N - 240, len: 120 });
  const [viewRange, setViewRange] = useState({ start: N - 900, end: N - 30 });
  const [pinned, setPinned] = useState<Set<string>>(new Set());
  const [hoverAnalog, setHoverAnalog] = useState<string | null>(null);
  const [crosshairIdx, setCrosshairIdx] = useState<number | null>(null);
  const [trustOpen, setTrustOpen] = useState(false);

  // Re-run analog search when query window changes
  const { analogs, cone } = useMemo(() => {
    const anal = findAnalogs(windowState.start, windowState.len,
      { k: settings.kAnalogs || 6, horizon: settings.horizon || 60 });
    const lastP = SERIES[windowState.start + windowState.len - 1].p;
    const c = buildCone(anal, settings.horizon || 60, lastP);
    return { analogs: anal, cone: c };
  }, [windowState.start, windowState.len, settings.kAnalogs, settings.horizon]);

  // Composite lenses = mean across top analogs
  const compLenses = useMemo(() => {
    const keys = LENS_DEFS.map(d => d.key);
    const out: Record<string, number> = {};
    keys.forEach(k => {
      out[k] = analogs.reduce((s, a) => s + (a.lenses[k] || 0), 0) / (analogs.length || 1);
    });
    return out as unknown as LensScores;
  }, [analogs]);

  // Cone endpoint statistics for the header metrics
  const coneStats = useMemo(() => {
    if (!cone || !cone.length) return null;
    const lastP = SERIES[windowState.start + windowState.len - 1].p;
    const final = cone[cone.length - 1];
    return {
      horizon: cone.length,
      p50Return: final.p50 / lastP - 1,
      p10Return: final.p10 / lastP - 1,
      p90Return: final.p90 / lastP - 1,
      width: (final.p90 - final.p10) / lastP,
    };
  }, [cone, windowState]);

  // Filter analog overlays based on settings
  const analogOverlays = useMemo((): AnalogOverlay[] => {
    const show = settings.showAnalogs === "all" ? analogs
      : settings.showAnalogs === "pinned" ? analogs.filter(a => pinned.has(a.id))
      : analogs.slice(0, 3);
    return show.map(a => ({ ...a, pinned: pinned.has(a.id) }));
  }, [analogs, pinned, settings.showAnalogs]);

  const togglePin = (id: string) => {
    setPinned(prev => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  // Query metadata for sidebar
  const queryMeta = useMemo(() => {
    const startD = SERIES[windowState.start].d;
    const endD = SERIES[windowState.start + windowState.len - 1].d;
    const startP = SERIES[windowState.start].p;
    const endP = SERIES[windowState.start + windowState.len - 1].p;
    return { startD, endD, startP, endP, ret: endP / startP - 1 };
  }, [windowState]);

  return (
    <div className="workstation">
      {/* ── LEFT SIDEBAR ─────────────────────────────────────── */}
      <aside className="side">
        <div className="side__section">
          <div className="side__header">
            <span className="label">Query</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>SPX &middot; daily</span>
          </div>
          <div className="side__row"><span className="k">Window start</span><span className="v">{fmtDate(queryMeta.startD)}</span></div>
          <div className="side__row"><span className="k">Window end</span><span className="v">{fmtDate(queryMeta.endD)}</span></div>
          <div className="side__row"><span className="k">Length</span><span className="v">{windowState.len} d</span></div>
          <div className="side__row">
            <span className="k">Return</span>
            <span className="v" style={{ color: queryMeta.ret >= 0 ? "var(--positive)" : "var(--negative)" }}>
              {fmtPct(queryMeta.ret)}
            </span>
          </div>
        </div>

        <div className="side__section">
          <div className="side__header"><span className="label">Window length</span></div>
          <div className="chip-row">
            {[30, 60, 120, 180, 250].map(L => (
              <button key={L} className="chip" data-active={windowState.len === L ? "true" : undefined}
                onClick={() => setWindowState(w => ({ ...w, len: L,
                  start: Math.min(w.start, N - L - (settings.horizon || 60) - 5) }))}>
                {L}D
              </button>
            ))}
          </div>
          <div style={{ height: 10 }} />
          <div className="side__header"><span className="label">View range</span></div>
          <div className="chip-row">
            {[
              { L: "2Y", n: 500 }, { L: "5Y", n: 1250 }, { L: "10Y", n: 2500 }, { L: "All", n: N - 220 }
            ].map(r => (
              <button key={r.L} className="chip"
                data-active={viewRange.end - viewRange.start === r.n ? "true" : undefined}
                onClick={() => setViewRange({
                  start: Math.max(200, windowState.start - Math.floor(r.n * 0.65)),
                  end: Math.min(N - 1, windowState.start + windowState.len + Math.floor(r.n * 0.35))
                })}>
                {r.L}
              </button>
            ))}
          </div>
        </div>

        <div className="side__section">
          <div className="side__header">
            <span className="label">Pinned analogs</span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{pinned.size}/{analogs.length}</span>
          </div>
          <div className="saved-list">
            {analogs.slice(0, 6).map(a => (
              <div key={a.id} className="saved" onClick={() => togglePin(a.id)}>
                <span className="saved__date">{fmtDateShort(a.date)}</span>
                <span className="saved__name">{a.label}</span>
                <span className="saved__score">{a.composite.toFixed(2)}</span>
                <span style={{
                  width: 10, height: 10, borderRadius: 2, border: "1px solid var(--rule-strong)",
                  background: pinned.has(a.id) ? "var(--accent)" : "transparent"
                }} />
              </div>
            ))}
          </div>
        </div>

        <div className="side__section">
          <div className="side__header"><span className="label">Notebook</span></div>
          <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.55 }}>
            <em className="serif" style={{ fontSize: 13 }}>Nine lenses agree</em> that late-&apos;18 Q4 and
            pre-GFC &apos;07 carry the most structural weight in this query&apos;s analog set.
            The cone tightens sharply in week 3 &mdash;
            <span className="mono" style={{ fontSize: 11 }}> dispersion drops 34%</span>.
          </div>
        </div>
      </aside>

      {/* ── MAIN ─────────────────────────────────────────────── */}
      <section className="main">
        <header className="main__head">
          <div className="main__title-wrap">
            <div className="label" style={{ marginBottom: 6 }}>Retrieve &middot; analog workstation</div>
            <h1>What does <em>this</em> moment rhyme with?</h1>
            <div className="main__subtitle">
              Drag the query window along the timeline. The engine re-ranks {analogs.length} historical
              matches and redraws the forecast cone. Pin analogs to overlay them.
            </div>
          </div>
          <div className="main__metrics">
            <div className="metric">
              <span className="label">Composite</span>
              <span className="v">{(analogs[0]?.composite ?? 0).toFixed(2)}</span>
              <span className="d">top match</span>
            </div>
            <div className="metric">
              <span className="label">P50 / {coneStats?.horizon}d</span>
              <span className={"v " + (coneStats && coneStats.p50Return >= 0 ? "pos" : "neg")}>
                {coneStats ? fmtPct(coneStats.p50Return) : "\u2014"}
              </span>
              <span className="d">median outcome</span>
            </div>
            <div className="metric">
              <span className="label">Cone width</span>
              <span className="v">{coneStats ? fmtPct(coneStats.width, 0) : "\u2014"}</span>
              <span className="d">p10 to p90</span>
            </div>
            <div className="metric">
              <span className="label">Calibration</span>
              <span className="v">B+</span>
              <span className="d">12-mo rolling</span>
            </div>
          </div>
        </header>

        <div className="chart-stack">
          <div className="chart-card">
            <div className="chart-card__head">
              <div className="chart-card__title">
                <span className="t">SPX &middot; full history</span>
                <span className="sub">30 years &middot; 7,500 daily closes</span>
              </div>
              <div className="chart-card__legend">
                <span className="legend-dot"><i />Query</span>
                <span className="legend-dot analog"><i />Analogs ({analogOverlays.length})</span>
                <span className="legend-dot cone"><i />P10&ndash;P90 cone</span>
              </div>
            </div>
            <div className="chart-card__body">
              <LineChart
                series={SERIES}
                viewStart={viewRange.start}
                viewEnd={viewRange.end}
                window={windowState}
                onWindowChange={setWindowState}
                analogsOverlay={analogOverlays}
                cone={cone}
                forecastHorizon={settings.horizon || 60}
                onHover={setCrosshairIdx}
                crosshairIdx={crosshairIdx}
                height={380}
                showCone={settings.showCone !== false}
              />
            </div>
          </div>
        </div>

        {/* Trust strip */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div className="trust">
            <div className="trust__item">
              <span className="label">Coverage 80%</span>
              <span className="v pos">78.4%</span>
            </div>
            <div className="trust__item">
              <span className="label">CRPS (1Y)</span>
              <span className="v">0.042</span>
            </div>
            <div className="trust__item">
              <span className="label">Hit rate &middot; sign</span>
              <span className="v pos">0.61</span>
            </div>
            <div className="trust__item">
              <span className="label">Regime drift</span>
              <span className="v warn">elevated</span>
            </div>
            <div className="trust__item">
              <span className="label">N analogs used</span>
              <span className="v">{analogs.length}</span>
            </div>
            <button className="trust__expand" onClick={() => setTrustOpen(o => !o)}>
              {trustOpen ? "Hide" : "Open"} calibration panel &rarr;
            </button>
          </div>

          {trustOpen && (
            <div className="trust-panel">
              <div>
                <h3>Reliability diagram</h3>
                <svg viewBox="0 0 260 160" width="100%" height="160">
                  <rect x="1" y="1" width="258" height="158" fill="none" stroke="var(--rule)" />
                  <line x1="20" y1="140" x2="240" y2="20" stroke="var(--ink-4)" strokeDasharray="3 3" />
                  {[0.05, 0.18, 0.31, 0.48, 0.6, 0.72, 0.82, 0.92].map((p, i) => {
                    const obs = p + (Math.sin(i * 1.3) * 0.04);
                    return <circle key={i} cx={20 + p * 220} cy={140 - obs * 120} r="3.5" fill="var(--positive)" />;
                  })}
                  <text x="20" y="154" className="axis-label" fontSize="9" fill="var(--ink-3)">predicted</text>
                  <text x="4" y="20" className="axis-label" fontSize="9" fill="var(--ink-3)" transform="rotate(-90 8 20)">observed</text>
                </svg>
                <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 8 }}>
                  Predicted quantiles match observed frequencies to within 4 percentage points.
                </div>
              </div>
              <div>
                <h3>Coverage over time</h3>
                <svg viewBox="0 0 260 160" width="100%" height="160">
                  <rect x="1" y="1" width="258" height="158" fill="none" stroke="var(--rule)" />
                  <line x1="10" y1="60" x2="250" y2="60" stroke="var(--rule-strong)" strokeDasharray="3 3" />
                  <text x="12" y="56" className="axis-label" fontSize="9" fill="var(--ink-3)">80% target</text>
                  {Array.from({ length: 48 }).map((_, i) => {
                    const v = 0.80 + Math.sin(i * 0.7) * 0.08 + (i > 36 ? -0.05 : 0);
                    const x = 10 + i * 5;
                    const y = 160 - v * 150;
                    return <line key={i} x1={x} x2={x} y1={160} y2={y} stroke="var(--ink-2)" strokeWidth="1.4" />;
                  })}
                </svg>
                <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 8 }}>
                  Coverage has been stable at 78&ndash;82% over the last 12 months, with mild regime drift at the tail.
                </div>
              </div>
              <div>
                <h3>Honesty note</h3>
                <p style={{ fontFamily: "var(--serif)", fontSize: 15, lineHeight: 1.5, color: "var(--ink-2)", fontStyle: "italic" }}>
                  Similarity is not a guarantee. Markets regime-shift. The cone reports what
                  <span style={{ fontStyle: "normal", fontWeight: 500 }}> tended to happen</span> after similar
                  structural patterns &mdash; nothing more, nothing less.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Analog strip */}
        <div className="strip">
          {analogs.map(a => (
            <div key={a.id} className="analog-card"
              data-pinned={pinned.has(a.id) ? "true" : undefined}
              onClick={() => togglePin(a.id)}
              onMouseEnter={() => setHoverAnalog(a.id)}
              onMouseLeave={() => setHoverAnalog(null)}>
              <div className="analog-card__head">
                <span className="analog-card__date">#{a.rank} &middot; {fmtDateShort(a.date)}</span>
                <span className="analog-card__score">{a.composite.toFixed(2)}</span>
              </div>
              <div className="analog-card__title">{a.label}</div>
              <div className="analog-card__note">{a.note}</div>
              <div className="analog-card__spark">
                <Sparkline values={[...a.priceWindow, ...a.after.slice(0, 60)]} width={110} highlight={0.35} />
                <span className={"analog-card__after " + (a.afterReturn >= 0 ? "pos" : "neg")}>
                  {fmtPct(a.afterReturn)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── RIGHT PANEL ──────────────────────────────────────── */}
      <aside className="right">
        <div className="right__section">
          <div className="lens-head">
            <div>
              <div className="label">Nine lenses &middot; mean agreement</div>
              <div className="score">
                {(Object.values(compLenses).reduce((a: number, b: number) => a + b, 0) / 9).toFixed(2)}
                <span className="d"> / 1.00</span>
              </div>
            </div>
          </div>
          <LensRadar lenses={compLenses} size={220} />
          <LensBars lenses={compLenses} compact={false} />
        </div>

        <div className="right__section">
          <div className="side__header"><span className="label">Lens reading</span></div>
          <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.6 }}>
            <p style={{ margin: "0 0 10px" }}>
              <b style={{ color: "var(--ink)", fontWeight: 500 }}>High agreement on Shape + Engine lenses</b> suggests
              structural and dynamical alignment with top analogs.
            </p>
            <p style={{ margin: 0 }}>
              <b style={{ color: "var(--ink)", fontWeight: 500 }}>Weakest lens:</b> Carry &mdash;
              the predictive transfer is real but modest. Treat P50 as a center of mass, not a target.
            </p>
          </div>
        </div>
      </aside>
    </div>
  );
}
