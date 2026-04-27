"use client";

import { useMemo } from "react";
import { useEngine } from "../_components/engine-context";
import { Panel } from "../_components/shell";

export default function PatternsPage() {
  const { entries } = useEngine();
  const signals = useMemo(() => {
    const avgs = entries.map((e) => e.avg);
    const mean = avgs.length ? avgs.reduce((a, b) => a + b, 0) / avgs.length : 50;
    const spread = avgs.length ? Math.sqrt(avgs.reduce((a, b) => a + (b - mean) ** 2, 0) / avgs.length) : 0;
    return { mean: Math.round(mean), spread: Math.round(spread), count: entries.length };
  }, [entries]);

  return (
    <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))" }}>
      <Panel title="Weekly rhythm" subtitle="Recurring cycle detection">
        <h3 style={{ margin: 0 }}>{signals.mean}/100</h3>
        <p style={{ color: "#64748B" }}>Baseline weekly state around this recovery zone.</p>
      </Panel>
      <Panel title="Training plateau marker" subtitle="Volatility over recent logs">
        <h3 style={{ margin: 0 }}>σ {signals.spread}</h3>
        <p style={{ color: "#64748B" }}>Lower spread can indicate stable adaptation; spikes may signal overreach.</p>
      </Panel>
      <Panel title="Illness onset signature" subtitle="Context + downturn clustering">
        <h3 style={{ margin: 0 }}>{Math.max(0, Math.round((55 - signals.mean) / 3))} flags</h3>
        <p style={{ color: "#64748B" }}>Use context tags to improve this pattern classifier.</p>
      </Panel>
      <Panel title="Data confidence" subtitle="How much history Cadence can learn from">
        <h3 style={{ margin: 0 }}>{signals.count} logs</h3>
        <p style={{ color: "#64748B" }}>3+ months gives much stronger self-similarity quality.</p>
      </Panel>
    </div>
  );
}
