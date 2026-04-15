import Link from "next/link";
import type { ReportEntry } from "../../lib/reports-catalogue";

/**
 * Single card for a published HTML report, styled to match the
 * published decks themselves. Clicking opens the report in a new
 * tab — these are full-page decks with their own print-to-PDF
 * layout, so routing them inline would be hostile.
 */
export function ReportCard({ report }: { report: ReportEntry }) {
  const href = `/reports/${report.file}`;
  return (
    <Link href={href} target="_blank" rel="noopener" className="deck-report">
      <div className="deck-report__meta">
        <span className={`deck-report__tag deck-report__tag--${report.kind}`}>
          {report.tag}
        </span>
        <span className="deck-report__date">{report.date}</span>
      </div>
      <h3 className="deck-report__title">{report.title}</h3>
      <p className="deck-report__summary">{report.summary}</p>
      <span className="deck-report__open">Open deck →</span>
    </Link>
  );
}
