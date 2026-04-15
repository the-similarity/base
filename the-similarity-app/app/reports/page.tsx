import { ChangesFeed } from "../../components/reports/changes-feed";
import { ReportCard } from "../../components/reports/report-card";
import { REPORTS } from "../../lib/reports-catalogue";

/**
 * /reports — project activity surface for finance stakeholders.
 *
 * Visual language intentionally mirrors the published HTML decks
 * (`vision/pitch_deck_414.html`, `vision/findings_deck_414.html`):
 * off-white background, mono accents, editorial column. Scoped via
 * `.deck-page` so the dark terminal chrome used by other pages is
 * not affected by this route.
 *
 * Invariants:
 *   - Report catalogue in `lib/reports-catalogue.ts` is the single
 *     source of truth for what appears under "Published Decks".
 *   - Activity feed is fetched from `/api/changes`; falls back
 *     silently if git/gh are unavailable.
 */
export default function ReportsPage() {
  return (
    <div className="deck-page">
      <div className="deck-page__inner">
        <div className="deck-page__label">The Similarity / Reports</div>
        <p className="deck-page__intro">
          Published decks, findings, and a live feed of commits and pull
          requests as the engine evolves. The design intentionally matches the
          HTML decks themselves — this is the same surface, wired live.
        </p>

        <h1 className="deck-page__title">Project reports.</h1>

        <section className="deck-section">
          <div className="deck-section__meta">
            <span className="deck-section__tag">Published Decks</span>
            <span className="deck-section__count">
              {REPORTS.length} reports
            </span>
          </div>
          <h2 className="deck-section__heading">Decks you can open.</h2>
          <div className="deck-reports">
            {REPORTS.map((report) => (
              <ReportCard key={report.id} report={report} />
            ))}
          </div>
        </section>

        <section className="deck-section">
          <div className="deck-section__meta">
            <span className="deck-section__tag">Activity Feed</span>
            <span className="deck-section__count">live</span>
          </div>
          <h2 className="deck-section__heading">Recent changes.</h2>
          <p className="deck-callout">
            Commits and pull requests merged as the engine gets sharper. Newest
            first. Click a PR title to jump to the discussion on GitHub.
          </p>
          <ChangesFeed />
        </section>
      </div>
    </div>
  );
}
