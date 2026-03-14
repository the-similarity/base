import type { DashboardData, RangeKey } from "../../lib/types";
import { SectionHeader } from "../ui/section-header";

export function ConfidencePanel({
  activeRange,
  data,
}: {
  activeRange: RangeKey;
  data: DashboardData;
}) {
  const rangeModifier = activeRange === "ALL" ? 0.04 : activeRange === "1D" ? -0.06 : 0;

  return (
    <section className="section-block">
      <SectionHeader title="Confidence Stack" detail="Composite method contribution for the current top analog." />
      <div className="card breakdown-card">
        {data.baseBreakdown.map((item) => {
          const value = Math.max(0.12, Math.min(0.98, item.value + rangeModifier));

          return (
            <div className="breakdown-row" key={item.label}>
              <div className="breakdown-meta">
                <span className="breakdown-label">{item.label}</span>
                <span className="breakdown-value">{Math.round(value * 100)}</span>
              </div>
              <div className="breakdown-track">
                <div className="breakdown-fill" style={{ width: `${value * 100}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
