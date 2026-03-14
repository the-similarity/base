import type { DashboardData } from "../../lib/types";
import { formatSigned } from "../../lib/chart-utils";
import { SectionHeader } from "../ui/section-header";

export function MatchesPanel({ data }: { data: DashboardData }) {
  return (
    <section className="section-block">
      <SectionHeader title="Top Matches" detail="Ranked windows returned by the search pipeline." />
      <div className="card-row">
        {data.topMatches.map((match) => (
          <article className="card match-card" key={match.label}>
            <p className="card-label">{match.label}</p>
            <div className="metric-value-row">
              <span className="card-value">{match.score.toFixed(1)}</span>
              <span className="card-unit">score</span>
            </div>
            <p className={`card-delta ${match.delta >= 0 ? "positive" : "negative"}`}>{formatSigned(match.delta)}</p>
            <div className="match-meta">
              <span>{match.window}</span>
              <span>{match.method}</span>
              <span>{match.regime}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
