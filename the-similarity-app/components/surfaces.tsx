"use client";

/**
 * Non-Retrieve surfaces: Represent, Simulate, Evaluate, Render, Decide.
 *
 * Each surface is a self-contained page with editorial typography,
 * eyebrow labels, and specialized content layouts (grid, table, cards,
 * dot cloud, ledger). These are statically composed — no server data
 * fetching; all content is inline.
 */

import { useState, useMemo } from "react";

// ── Represent surface ───────────────────────────────────────────────────

function PlatformMap({ active, onChoose }: { active: number; onChoose: (i: number) => void }) {
  const pillars = [
    { n: "I", name: "Finance", desc: "The proving ground. Fast feedback, dense data, buyers who pay for edge.", status: "live", runs: "1,204" },
    { n: "II", name: "Synthetic Copies", desc: "Realism-first synthetic datasets for training, testing, and privacy-audited sharing.", status: "beta", runs: "318" },
    { n: "III", name: "Synthetic Worlds", desc: "Headless control environments for simulation, stress-test, and agent evaluation.", status: "alpha", runs: "42" },
    { n: "IV", name: "3D Data Space", desc: "A navigable surface over latent state. Walk regimes, transitions, and clusters.", status: "alpha", runs: "19" },
    { n: "V", name: "World Event", desc: "Multimodal forecasting combining event history, markets, and text context.", status: "r&d", runs: "\u2014" },
    { n: "VI", name: "NL \u2192 Time Series", desc: "Translate narrative and intent into analyzable, editable temporal structures.", status: "r&d", runs: "\u2014" },
  ];
  return (
    <div className="pillar-grid">
      {pillars.map((p, i) => (
        <div key={p.name} className={"pillar" + (active === i ? " pillar--active" : "")}
          onClick={() => onChoose(i)}>
          <div className="pillar__num">Surface {p.n}</div>
          <div className="pillar__name">{p.name}</div>
          <div className="pillar__desc">{p.desc}</div>
          <div className="pillar__meta">
            <span>Status &middot; <b>{p.status}</b></span>
            <span>Runs &middot; <b>{p.runs}</b></span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function RepresentSurface() {
  const [active, setActive] = useState(0);
  return (
    <div className="surface">
      <div className="surface__eyebrow">
        <span className="label label-ink">02 &middot; Represent</span>
        <span className="label">One engine &middot; six surfaces</span>
      </div>
      <h1 className="surface__title">A single engine, expressed through <em>six products</em>.</h1>
      <p className="surface__lede">
        Retrieval, latent dynamics, context, and calibrated uncertainty &mdash; the same four layers
        power finance, synthetic data, world-event forecasting, and narrative-to-time-series.
        Click a surface to pivot the workstation.
      </p>
      <PlatformMap active={active} onChoose={setActive} />

      <div className="rule" />

      <div className="surface__eyebrow">
        <span className="label label-ink">Engine stack</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 0,
        borderTop: "1px solid var(--rule)", borderLeft: "1px solid var(--rule)" }}>
        {[
          { k: "Analogue", q: "What rhymes with this?" },
          { k: "Latent", q: "How does this state evolve?" },
          { k: "Context", q: "What outside signals matter?" },
          { k: "Uncertainty", q: "What should be trusted, how much?" },
        ].map(l => (
          <div key={l.k} style={{ padding: "20px 20px 24px", borderRight: "1px solid var(--rule)",
            borderBottom: "1px solid var(--rule)", background: "var(--bg-card)" }}>
            <div className="label" style={{ marginBottom: 6 }}>Layer</div>
            <div className="serif" style={{ fontSize: 22, fontWeight: 500, marginBottom: 4 }}>{l.k}</div>
            <div style={{ color: "var(--ink-3)", fontSize: 12.5, fontStyle: "italic" }}>{l.q}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Simulate surface ────────────────────────────────────────────────────

export function SimulateSurface() {
  const scenarios = [
    { name: "2008-analog stress", kind: "Retrieved", body: "Project the next 60 days under the 5 highest-scoring pre-GFC analogs. P50 drawdown \u22128.4%, P10 \u221217.2%.", horizon: "60d", analogs: 5, cone: "\u221217.2% / \u22128.4% / +2.1%" },
    { name: "Vol-regime shift", kind: "Latent", body: "Engine modes forced into high-vol basin. Evaluate holdings over 250 days with conditional cone.", horizon: "250d", analogs: 18, cone: "\u221222.8% / +3.1% / +19.4%" },
    { name: "Narrative: soft-landing", kind: "NL\u2192TS", body: "Translate editorial prose into temporal structure, then match analogs. Used for scenario briefing.", horizon: "120d", analogs: 11, cone: "\u22123.1% / +5.7% / +12.3%" },
    { name: "Synthetic counterfactual", kind: "Worlds", body: "Replay Q4 2018 under 12 controlled parameter sweeps. Compare policy impact envelopes.", horizon: "90d", analogs: 12, cone: "\u221211.9% / \u22122.4% / +6.8%" },
  ];
  return (
    <div className="surface">
      <div className="surface__eyebrow">
        <span className="label label-ink">03 &middot; Simulate</span>
        <span className="label">Calibrated futures</span>
      </div>
      <h1 className="surface__title">Project forward under <em>honest uncertainty</em>.</h1>
      <p className="surface__lede">
        Scenarios are composable. Retrieve analogs, force a latent basin, translate narrative into
        initial conditions, and run cones against holdings &mdash; side-by-side.
      </p>
      <div className="scenario-grid">
        {scenarios.map(s => (
          <div key={s.name} className="scenario">
            <div className="scenario__meta">{s.kind} &middot; {s.horizon} &middot; n={s.analogs}</div>
            <div className="scenario__name">{s.name}</div>
            <div className="scenario__body">{s.body}</div>
            <div className="scenario__foot">
              <span>P10 / P50 / P90</span>
              <span style={{ color: "var(--ink)" }}>{s.cone}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Evaluate surface ────────────────────────────────────────────────────

export function EvaluateSurface() {
  const runs = [
    ["0f19a4e2", "Mar 14, 2026", "SPX", "0.612", "0.81", "B+", "complete"],
    ["1d88c710", "Mar 09, 2026", "NDX", "0.587", "0.73", "B", "complete"],
    ["8a34e001", "Mar 02, 2026", "USDJPY", "0.543", "0.68", "B-", "complete"],
    ["7bcc9213", "Feb 22, 2026", "HG=F", "0.624", "0.77", "B+", "complete"],
    ["4ee8112f", "Feb 14, 2026", "BTCUSD", "0.501", "0.55", "C", "complete"],
    ["2aa10007", "Feb 05, 2026", "SPX", "0.598", "0.79", "B+", "complete"],
  ];
  return (
    <div className="surface">
      <div className="surface__eyebrow">
        <span className="label label-ink">04 &middot; Evaluate</span>
        <span className="label">Walk-forward calibration</span>
      </div>
      <h1 className="surface__title">Did the cone actually <em>hold</em>?</h1>
      <p className="surface__lede">
        Every run is backtested walk-forward. Trust, calibration grade, and hit rate are reported
        alongside raw point-estimate metrics &mdash; because one number lies.
      </p>

      <div className="eval-grid">
        <div className="eval-card">
          <div className="label" style={{ marginBottom: 8 }}>Recent runs</div>
          <table className="tab">
            <thead>
              <tr>
                <th>Run</th><th>Date</th><th>Symbol</th>
                <th className="num">Hit rate</th>
                <th className="num">Trust</th>
                <th>Cal.</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r[0]}>
                  <td className="mono">{r[0]}</td>
                  <td className="mono" style={{ color: "var(--ink-3)" }}>{r[1]}</td>
                  <td style={{ fontWeight: 500 }}>{r[2]}</td>
                  <td className="num">{r[3]}</td>
                  <td className="num">{r[4]}</td>
                  <td><span className="pill pill--ink">{r[5]}</span></td>
                  <td><span className="pill pill--pos">{r[6]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="eval-card">
          <div className="label" style={{ marginBottom: 8 }}>Aggregate (last 90 days)</div>
          <div className="eval-grid-3">
            <div className="eval-stat"><span className="label">Mean coverage</span><div className="v">78.9%</div><div className="d">target 80%</div></div>
            <div className="eval-stat"><span className="label">Mean trust</span><div className="v">0.74</div><div className="d">0&ndash;1 score</div></div>
            <div className="eval-stat"><span className="label">Sign hit rate</span><div className="v">0.60</div><div className="d">random = 0.50</div></div>
            <div className="eval-stat"><span className="label">CRPS</span><div className="v">0.042</div><div className="d">lower better</div></div>
            <div className="eval-stat"><span className="label">Calibration grade</span><div className="v">B+</div><div className="d">A / B / C scale</div></div>
            <div className="eval-stat"><span className="label">Analogs / run</span><div className="v">6.8</div><div className="d">avg retained</div></div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Render surface ──────────────────────────────────────────────────────

export function RenderSurface() {
  // Latent space dot cloud with seeded positions
  const dots = useMemo(() => {
    const out: { x: number; y: number; color: string; size: number; opacity: number }[] = [];
    let s = 7;
    const rand = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    const clusters = [
      { cx: 0.3, cy: 0.4, color: "var(--ink)", n: 80, label: "Expansion" },
      { cx: 0.7, cy: 0.35, color: "var(--positive)", n: 65, label: "Recovery" },
      { cx: 0.55, cy: 0.72, color: "var(--negative)", n: 55, label: "Crash" },
      { cx: 0.22, cy: 0.78, color: "var(--warn)", n: 40, label: "Topping" },
    ];
    clusters.forEach(c => {
      for (let i = 0; i < c.n; i++) {
        const a = rand() * Math.PI * 2;
        const r = Math.pow(rand(), 0.6) * 0.12;
        out.push({
          x: (c.cx + Math.cos(a) * r) * 100,
          y: (c.cy + Math.sin(a) * r) * 100,
          color: c.color,
          size: 3 + rand() * 4,
          opacity: 0.5 + rand() * 0.5,
        });
      }
    });
    return { dots: out, clusters };
  }, []);

  return (
    <div className="surface">
      <div className="surface__eyebrow">
        <span className="label label-ink">05 &middot; Render</span>
        <span className="label">3D latent space</span>
      </div>
      <h1 className="surface__title">Walk the space of <em>possible states</em>.</h1>
      <p className="surface__lede">
        Each dot is a 60-day window projected into latent space. Clusters are regimes. Arrows between
        clusters are transitions we&apos;ve observed.
      </p>
      <div className="latent-card">
        <div className="latent-scene">
          {dots.dots.map((d, i) => (
            <div key={i} className="latent-dot"
              style={{ left: d.x + "%", top: d.y + "%", background: d.color,
                width: d.size, height: d.size, opacity: d.opacity }} />
          ))}
          {dots.clusters.map((c, i) => (
            <div key={i} style={{
              position: "absolute", left: c.cx * 100 + "%", top: c.cy * 100 + "%",
              transform: "translate(-50%, -50%)",
              fontFamily: "var(--mono)", fontSize: 10, letterSpacing: ".14em",
              textTransform: "uppercase", color: "var(--ink)",
              background: "var(--bg-elevated)", padding: "3px 8px",
              border: "1px solid var(--rule-strong)", borderRadius: 2,
              pointerEvents: "none",
            }}>{c.label}</div>
          ))}
          {/* Axis indicators */}
          <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
            <line x1="30" y1="410" x2="80" y2="410" stroke="var(--ink-3)" strokeWidth="1" />
            <line x1="30" y1="410" x2="30" y2="360" stroke="var(--ink-3)" strokeWidth="1" />
            <text x="82" y="413" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-3)">DIM-1</text>
            <text x="28" y="356" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-3)" textAnchor="end" transform="rotate(-90 28 356)">DIM-2</text>
          </svg>
        </div>
        <div className="latent-legend">
          <span>Projection &middot; UMAP &middot; 9-lens embedding</span>
          <span>&bull;</span>
          <span>240 windows &middot; 4 regimes</span>
          <span style={{ marginLeft: "auto" }}>Rotate &middot; pan &middot; pin to workstation &#8599;</span>
        </div>
      </div>
    </div>
  );
}

// ── Decide surface ──────────────────────────────────────────────────────

export function DecideSurface() {
  const signals = [
    ["Apr 17 2026", "Reduce SPX delta", "From analog set dominated by late-\u201818 and \u201807", "60d", "0.82", "open", "pos"],
    ["Apr 14 2026", "Hedge credit / long vol", "Cone widens past 3\u03C3 in week 2; Topology flags regime pivot", "120d", "0.71", "open", "warn"],
    ["Apr 09 2026", "Rotate into commodities", "Engine mode alignment with 2005-era HG", "180d", "0.64", "open", "pos"],
    ["Apr 02 2026", "Trim BTC exposure", "Low trust score; Rhythm disagrees w/ Shape", "45d", "0.51", "closed", "neg"],
    ["Mar 28 2026", "Enter JPY long", "Carry lens strong across 4 analogs", "90d", "0.76", "realized", "pos"],
  ];
  return (
    <div className="surface">
      <div className="surface__eyebrow">
        <span className="label label-ink">06 &middot; Decide</span>
        <span className="label">Signal ledger</span>
      </div>
      <h1 className="surface__title">From <em>analog</em> to action &mdash; with a receipt.</h1>
      <p className="surface__lede">
        Every signal is bound to the query, the analog set, and the lens readings that produced it.
        A receipt you can show a PM, a CIO, or a regulator.
      </p>
      <div className="ledger">
        <div className="ledger__head">
          <span>Date</span><span>Signal</span><span>Horizon</span><span>Trust</span><span>Return</span><span>Status</span>
        </div>
        {signals.map(s => (
          <div key={s[1]} className="ledger__row">
            <span className="ledger__date">{s[0]}</span>
            <span className="ledger__title">{s[1]}<span className="sub">{s[2]}</span></span>
            <span className="mono" style={{ color: "var(--ink-2)" }}>{s[3]}</span>
            <span className="mono">{s[4]}</span>
            <span><span className={"pill " + (s[6] === "pos" ? "pill--pos" : s[6] === "neg" ? "pill--neg" : "pill--warn")}>
              {s[6] === "pos" ? "+" : s[6] === "neg" ? "\u2212" : "\u00B1"} tracked
            </span></span>
            <span><span className={"pill " + (s[5] === "open" ? "pill--ink" : s[5] === "realized" ? "pill--pos" : "")}>{s[5]}</span></span>
          </div>
        ))}
      </div>
    </div>
  );
}
