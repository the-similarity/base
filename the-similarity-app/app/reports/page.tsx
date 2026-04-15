import Link from "next/link";
import { ChangesFeed } from "../../components/reports/changes-feed";
import { ReportCard } from "../../components/reports/report-card";
import { REPORTS } from "../../lib/reports-catalogue";

/**
 * /reports — project activity surface for finance stakeholders.
 *
 * Purpose:
 *   Single page that collects every HTML deck / findings report and a
 *   live feed of project activity (recent commits + PRs). Think of it
 *   as the "what changed this week" tab for someone who doesn't open
 *   GitHub. The HTML reports live under `public/reports/` and are
 *   served as static assets; the feed is dynamic via `/api/changes`.
 *
 * Invariants:
 *   - The catalogue of reports is defined in `lib/reports-catalogue.ts`.
 *     Adding a new HTML deck means (a) drop the file under
 *     `public/reports/`, (b) prepend an entry to REPORTS.
 *   - The feed falls back silently if `git`/`gh` aren't on the PATH;
 *     in that case only the reports cards render.
 */
export default function ReportsPage() {
  return (
    <div className="portfolio-page">
      <header className="portfolio-header">
        <div className="portfolio-header__breadcrumb">
          <Link href="/" className="portfolio-header__breadcrumb-link">
            Terminal
          </Link>
          <span className="portfolio-header__breadcrumb-sep">/</span>
          <span className="portfolio-header__breadcrumb-current">Reports</span>
        </div>
        <h1 className="portfolio-header__title">Project Reports</h1>
        <p className="portfolio-header__subtitle">
          Published decks, findings, and a live feed of commits and pull requests as the engine evolves.
        </p>
      </header>

      {/* Published reports — static HTML decks under public/reports/ */}
      <section className="portfolio-section">
        <div className="portfolio-section__header">
          <h2 className="portfolio-section__title">Published Decks</h2>
          <span className="portfolio-section__count">{REPORTS.length} reports</span>
        </div>
        <div className="reports-grid">
          {REPORTS.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </div>
      </section>

      {/* Changes feed — fetched from /api/changes at runtime */}
      <section className="portfolio-section">
        <div className="portfolio-section__header">
          <h2 className="portfolio-section__title">Activity Feed</h2>
          <span className="portfolio-section__count">live</span>
        </div>
        <ChangesFeed />
      </section>
    </div>
  );
}
