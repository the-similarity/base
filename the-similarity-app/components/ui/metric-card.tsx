import { formatSigned } from "../../lib/chart-utils";

export function MetricCard({
  label,
  value,
  unit,
  delta,
}: {
  label: string;
  value: string;
  unit?: string;
  delta?: number;
}) {
  return (
    <article className="card stat-card">
      <div className="metric-dot" aria-hidden="true" />
      <p className="card-label">{label}</p>
      <div className="metric-value-row">
        <span className="card-value">{value}</span>
        {unit ? <span className="card-unit">{unit}</span> : null}
      </div>
      {delta !== undefined ? (
        <p className={`card-delta ${delta >= 0 ? "positive" : "negative"}`}>{formatSigned(delta)}</p>
      ) : (
        <p className="card-delta neutral">Stable run</p>
      )}
    </article>
  );
}
