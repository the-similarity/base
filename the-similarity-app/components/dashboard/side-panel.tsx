import type { DashboardData, RangeView } from "../../lib/types";
import { formatSigned } from "../../lib/chart-utils";

export function SidePanel({
  view,
  dataSource,
}: {
  view: RangeView;
  dataSource: DashboardData["dataSource"];
}) {
  const lastMedian = view.forecast.p50[view.forecast.p50.length - 1];
  const lastLow = view.forecast.p10[view.forecast.p10.length - 1];
  const lastHigh = view.forecast.p90[view.forecast.p90.length - 1];
  const coneSpread = lastHigh - lastLow;

  return (
    <aside className="card panel-card">
      <div className="panel-block">
        <p className="card-label">Current configuration</p>
        <div className="kv-list">
          <div className="kv-row">
            <span>Normalization</span>
            <strong>logreturn_zscore</strong>
          </div>
          <div className="kv-row">
            <span>Window stride</span>
            <strong>5 bars</strong>
          </div>
          <div className="kv-row">
            <span>Tier 1 survivors</span>
            <strong>124</strong>
          </div>
          <div className="kv-row">
            <span>Tier 2 methods</span>
            <strong>DTW, Pearson, Bempedelis</strong>
          </div>
        </div>
      </div>
      <div className="panel-block">
        <p className="card-label">Cone at horizon</p>
        <div className="metric-value-row">
          <span className="card-value">{lastMedian.toFixed(1)}</span>
          <span className="card-unit">P50</span>
        </div>
        <p className="card-delta positive">{formatSigned(5.8)}</p>
        <div className="mini-grid">
          <div>
            <span className="mini-label">P10</span>
            <strong>{lastLow.toFixed(1)}</strong>
          </div>
          <div>
            <span className="mini-label">P90</span>
            <strong>{lastHigh.toFixed(1)}</strong>
          </div>
          <div>
            <span className="mini-label">Spread</span>
            <strong>{coneSpread.toFixed(1)}</strong>
          </div>
          <div>
            <span className="mini-label">Matches</span>
            <strong>20</strong>
          </div>
        </div>
      </div>
      <div className="panel-block">
        <p className="card-label">Notes</p>
        <p className="panel-note">
          {dataSource === "api"
            ? "This frontend is reading a real dashboard payload from the configured API repository."
            : "This frontend is currently using its mock adapter fallback, but it now targets an HTTP payload instead of local Python modules."}
        </p>
      </div>
    </aside>
  );
}
