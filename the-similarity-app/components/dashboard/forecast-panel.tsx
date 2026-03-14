import type { RangeView } from "../../lib/types";
import { formatSigned } from "../../lib/chart-utils";
import { SectionHeader } from "../ui/section-header";

export function ForecastPanel({ view }: { view: RangeView }) {
  const terminalLow = view.forecast.p10[view.forecast.p10.length - 1];
  const terminalMid = view.forecast.p50[view.forecast.p50.length - 1];
  const terminalHigh = view.forecast.p90[view.forecast.p90.length - 1];
  const anchor = view.query[view.query.length - 1];
  const rows = [
    { label: "Bear band", value: terminalLow, delta: ((terminalLow - anchor) / anchor) * 100 },
    { label: "Median path", value: terminalMid, delta: ((terminalMid - anchor) / anchor) * 100 },
    { label: "Bull band", value: terminalHigh, delta: ((terminalHigh - anchor) / anchor) * 100 },
  ];

  return (
    <section className="section-block">
      <SectionHeader title="Forecast Cone" detail="Weighted percentile projection from forward paths that followed each historical analog." />
      <div className="forecast-grid">
        {rows.map((row) => (
          <article className="card forecast-card" key={row.label}>
            <p className="card-label">{row.label}</p>
            <div className="metric-value-row">
              <span className="card-value">{row.value.toFixed(1)}</span>
              <span className="card-unit">terminal</span>
            </div>
            <p className={`card-delta ${row.delta >= 0 ? "positive" : "negative"}`}>{formatSigned(row.delta)}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
