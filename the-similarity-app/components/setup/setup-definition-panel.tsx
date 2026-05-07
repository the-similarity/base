"use client";

import { useMemo, useState } from "react";
import {
  buildSetupTemplate,
  saveSetupTemplate,
} from "./setup-scanner-client";
import type { SetupBar, SetupTemplate } from "./types";
import styles from "./setup-definition-panel.module.css";

type SetupDefinitionPanelProps = {
  symbol: string;
  timeframe: string;
  regionBars: SetupBar[];
  liveBars: SetupBar[];
  onTemplate?: (template: SetupTemplate) => void;
};

function fmtPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function describeBars(bars: SetupBar[]): { count: number; ret: number } {
  if (bars.length < 2) return { count: bars.length, ret: 0 };
  const first = bars[0].close || 1;
  const last = bars[bars.length - 1].close || first;
  return { count: bars.length, ret: ((last - first) / first) * 100 };
}

export function SetupDefinitionPanel({
  symbol,
  timeframe,
  regionBars,
  liveBars,
  onTemplate,
}: SetupDefinitionPanelProps) {
  const [name, setName] = useState("My setup");
  const [liveCount, setLiveCount] = useState(60);
  const [status, setStatus] = useState("");

  const visibleLiveBars = useMemo(
    () => liveBars.slice(Math.max(0, liveBars.length - liveCount)),
    [liveBars, liveCount],
  );
  const regionMeta = describeBars(regionBars);
  const liveMeta = describeBars(visibleLiveBars);

  async function capture(source: "chart_region" | "live_capture"): Promise<void> {
    const bars = source === "chart_region" ? regionBars : visibleLiveBars;
    if (bars.length < 8) {
      setStatus("Need at least 8 bars to define a setup.");
      return;
    }
    const template = buildSetupTemplate({
      name,
      symbol,
      timeframe,
      source,
      bars,
    });
    await saveSetupTemplate(template);
    setStatus(`${source === "chart_region" ? "Chart region" : "Live"} setup captured.`);
    onTemplate?.(template);
  }

  return (
    <div className={styles.panel}>
      <div className={styles.controls}>
        <label className={styles.field}>
          <span className="label">Setup name</span>
          <input
            className={styles.input}
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Setup name"
          />
        </label>
        <label className={styles.field}>
          <span className="label">Live bars</span>
          <select
            className={styles.select}
            value={liveCount}
            onChange={e => setLiveCount(Number(e.target.value))}
          >
            {[30, 60, 120, 180, 250].map(n => (
              <option key={n} value={n}>{n} bars</option>
            ))}
          </select>
        </label>
      </div>
      <div className={styles.summary}>
        <div><strong>Region:</strong> {regionMeta.count} bars · {fmtPct(regionMeta.ret)}</div>
        <div><strong>Live:</strong> {liveMeta.count} bars · {fmtPct(liveMeta.ret)}</div>
      </div>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.button}
          onClick={() => void capture("chart_region")}
        >
          <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M2.5 3.5h11v8.5h-11zM5 2v3M11 2v3M5 10h6" fill="none" stroke="currentColor" strokeWidth="1.4" />
          </svg>
          Region
        </button>
        <button
          type="button"
          className={`${styles.button} ${styles.buttonPrimary}`}
          onClick={() => void capture("live_capture")}
        >
          <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          Live capture
        </button>
      </div>
      <div className={styles.status} aria-live="polite">{status}</div>
    </div>
  );
}

