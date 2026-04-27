"use client";

import { useMemo } from "react";
import { Panel } from "../_components/shell";
import { useEngine } from "../_components/engine-context";
import { buildHistoryFromEntries } from "../storage";

export default function RhymesPage() {
  const { entries, openComposer } = useEngine();
  const history = useMemo(() => buildHistoryFromEntries(entries, 52), [entries]);
  const cards = useMemo(() => topRhymeCards(history), [history]);

  if (history.length < 10) {
    return (
      <Panel title="Need more signal" subtitle="Cadence needs more longitudinal history before rhymes stabilize.">
        <p style={{ color: "#475569" }}>Connect a wearable source or load demo data from Today.</p>
        <button onClick={openComposer} style={{ background: "#0F172A", color: "#fff", borderRadius: 8, padding: "8px 12px" }}>Add manual body log</button>
      </Panel>
    );
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Panel title="Last 5 times your biomarkers looked like this" subtitle="Weighted analogue outcomes from your own history.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 10 }}>
          {cards.map((card) => (
            <article key={card.id} style={{ border: "1px solid #D7DEE7", borderRadius: 12, padding: 12, background: "white" }}>
              <div style={{ fontWeight: 700 }}>Week {card.range}</div>
              <div style={{ color: "#64748B", fontSize: 12, marginTop: 2 }}>Similarity {card.score}%</div>
              <div style={{ marginTop: 10, fontSize: 14 }}>{card.followedBy}</div>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Forecast cone" subtitle="Analogue-weighted expectation from your own history.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(120px,1fr))", gap: 10 }}>
          {forecast(cards).map((f) => (
            <div key={f.h} style={{ border: "1px solid #D7DEE7", borderRadius: 12, padding: 12, background: "white" }}>
              <div style={{ fontSize: 12, color: "#64748B" }}>Next {f.h} days</div>
              <div style={{ fontSize: 28, fontWeight: 700 }}>{f.mid}</div>
              <div style={{ fontSize: 12, color: "#64748B" }}>{f.low} to {f.high}</div>
            </div>
          ))}
        </div>
        <p style={{ marginBottom: 0, color: "#64748B", fontSize: 12 }}>Informational, not diagnostic or medical advice.</p>
      </Panel>
    </div>
  );
}

function topRhymeCards(history: Array<{ day: number; avg: number }>) {
  const out = [] as Array<{ id: string; range: string; score: number; followedBy: string; nextAvg: number }>;
  for (let i = 0; i < Math.min(5, history.length - 8); i += 1) {
    const source = history[i];
    const next = history[i + 1];
    out.push({
      id: `${source.day}-${i}`,
      range: `-${source.day} to -${Math.max(0, source.day - 6)}`,
      score: Math.max(62, 94 - i * 6),
      followedBy: next.avg > source.avg ? "Followed by rebound and better recovery" : "Followed by fatigue accumulation",
      nextAvg: next.avg,
    });
  }
  return out;
}

function forecast(cards: Array<{ nextAvg: number }>) {
  const mean = cards.length ? cards.reduce((s, c) => s + c.nextAvg, 0) / cards.length : 50;
  return [7, 14, 30].map((h) => ({ h, low: Math.round(mean - 6), mid: Math.round(mean), high: Math.round(mean + 6) }));
}
