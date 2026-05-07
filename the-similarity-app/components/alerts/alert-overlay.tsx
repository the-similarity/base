"use client";

import { FeedbackControl } from "./feedback-control";
import type { ScannerAlert, SetupBar } from "../setup/types";
import styles from "./alert-overlay.module.css";

function normalize(values: number[]): number[] {
  const first = values[0] || 1;
  return values.map(v => ((v / first) - 1) * 100);
}

function pathFor(values: number[], width: number, height: number): string {
  if (values.length === 0) return "";
  return values.map((value, i) => {
    const x = values.length === 1 ? 0 : (i / (values.length - 1)) * width;
    const y = height - value;
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function closes(bars: SetupBar[]): number[] {
  return bars.map(bar => bar.close).filter(Number.isFinite);
}

type AlertOverlayProps = {
  alert: ScannerAlert;
};

export function AlertOverlay({ alert }: AlertOverlayProps) {
  const width = 420;
  const height = 136;
  const current = normalize(closes(alert.currentBars));
  const analog = normalize(closes(alert.analog.analogBars));
  const all = [...current, ...analog];
  const min = Math.min(...all, -1);
  const max = Math.max(...all, 1);
  const project = (values: number[]) => {
    const span = Math.max(0.01, max - min);
    return values.map(v => ((v - min) / span) * height);
  };

  return (
    <article className={styles.overlay}>
      <div className={styles.head}>
        <div>
          <div className={styles.meta}>
            {alert.symbol} · {alert.timeframe} · score {alert.score.toFixed(2)}
          </div>
          <h3 className={styles.title}>Setup active against #{alert.analog.rank} historical analog</h3>
        </div>
        <FeedbackControl targetType="alert" targetId={alert.id} compact />
      </div>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Current price overlaid with historical analog"
      >
        {[0.25, 0.5, 0.75].map(t => (
          <line
            key={t}
            x1="0"
            x2={width}
            y1={height * t}
            y2={height * t}
            stroke="var(--rule)"
            strokeWidth="1"
          />
        ))}
        <path
          d={pathFor(project(analog), width, height)}
          fill="none"
          stroke="var(--positive)"
          strokeWidth="2"
          strokeDasharray="4 4"
        />
        <path
          d={pathFor(project(current), width, height)}
          fill="none"
          stroke="var(--ink)"
          strokeWidth="2.4"
        />
      </svg>
      <div className={styles.legend}>
        <span className={styles.current}><i />Current</span>
        <span className={styles.analog}><i />Historical analog</span>
      </div>
    </article>
  );
}

export function EmptyAlertsState() {
  return (
    <div className={styles.empty} role="status">
      <p className={styles.emptyTitle}>Zero alerts yet</p>
      <p className={styles.emptyBody}>
        Scanning ~36 instruments. We&apos;ll ping you the moment your setup hits.
      </p>
    </div>
  );
}
