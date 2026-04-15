import Link from "next/link";
import type { ReportEntry } from "../../lib/reports-catalogue";

/**
 * Single card for a published HTML report. Clicking the card opens
 * the report in a new tab (they are full-page HTML decks with their
 * own print-to-PDF layout, so routing them inline would be hostile).
 */
export function ReportCard({ report }: { report: ReportEntry }) {
  const href = `/reports/${report.file}`;
  return (
    <Link href={href} target="_blank" rel="noopener" className="reports-card">
      <div className="reports-card__meta">
        <span className={`reports-card__tag reports-card__tag--${report.kind}`}>
          {report.tag}
        </span>
        <span className="reports-card__date">{report.date}</span>
      </div>
      <h3 className="reports-card__title">{report.title}</h3>
      <p className="reports-card__summary">{report.summary}</p>
      <span className="reports-card__open">Open deck →</span>
    </Link>
  );
}
