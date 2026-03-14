import type { DashboardData } from "../../lib/types";
import { SectionHeader } from "../ui/section-header";

export function ArchitecturePanel({ data }: { data: DashboardData }) {
  return (
    <section className="section-block">
      <SectionHeader title="Module Layout" detail="Direct translation of the architecture doc into a frontend operator map." />
      <div className="module-grid">
        {data.architectureCards.map((card) => (
          <article className="card module-card" key={card.module}>
            <p className="card-label">{card.module}</p>
            <p className="module-copy">{card.responsibility}</p>
            <p className="module-scale">{card.scale}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
