import type { DashboardData } from "../../lib/types";
import { SectionHeader } from "../ui/section-header";

export function PipelinePanel({ data }: { data: DashboardData }) {
  return (
    <section className="section-block">
      <SectionHeader title="Pipeline Readout" detail="The app surfaces the same sequence described in the architecture document." />
      <div className="card pipeline-card">
        {data.pipelineSteps.map((step, index) => (
          <div className="pipeline-step" key={step}>
            <span className="pipeline-index">{String(index + 1).padStart(2, "0")}</span>
            <span className="pipeline-text">{step}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
