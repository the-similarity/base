"use client";

/**
 * AnalogCard — single-analog tile for the public /try widget.
 *
 * Renders one historical match as a self-contained card: date range, a
 * thumbnail SVG combining the query-shape window with its continuation,
 * the composite similarity score, and the "what happened next" return.
 * Style is research-tool descriptive, not advisory — no buy/sell
 * language, no entry/stop/target prices.
 *
 * SVG sizing is fixed-width (260) so the card grid lays out predictably
 * across breakpoints; the parent `.try-grid` is a CSS grid that flows
 * 1-up on mobile and 2-up on tablet/desktop.
 */

import type { AnalogMatch } from "../../lib/data";

type Props = {
  match: AnalogMatch;
};

const FMT_DATE: Intl.DateTimeFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  year: "numeric",
});

function fmtPct(x: number, digits = 1): string {
  const sign = x >= 0 ? "+" : "";
  return `${sign}${(x * 100).toFixed(digits)}%`;
}

export function AnalogCard({ match }: Props) {
  // Build a tiny thumbnail by stitching the query window (left) and its
  // continuation (right). We normalise to the query window's start so
  // the y-axis is in "percent change from window-start" — invariant to
  // the absolute price level of the historical regime.
  const qp = match.priceWindow;
  const after = match.after;
  if (!qp.length) return null;

  const base = qp[0];
  const allRel = [...qp, ...after].map((p) => (p / base - 1) * 100);
  const minY = Math.min(...allRel);
  const maxY = Math.max(...allRel);
  const span = Math.max(0.5, maxY - minY); // floor span so flat windows still render
  const W = 260;
  const H = 60;
  const PAD_Y = 4;
  const innerH = H - 2 * PAD_Y;
  const xStep = W / (allRel.length - 1 || 1);

  const path = allRel
    .map((y, i) => {
      const py = PAD_Y + (1 - (y - minY) / span) * innerH;
      const px = i * xStep;
      return `${i === 0 ? "M" : "L"}${px.toFixed(1)} ${py.toFixed(1)}`;
    })
    .join(" ");

  // Vertical divider between the query window and its continuation —
  // the "today" line of the historical analog. Helps the reader see at
  // a glance where the match window ended and the future began.
  const dividerX = (qp.length - 1) * xStep;

  const directionClass =
    match.afterReturn > 0.005
      ? "is-up"
      : match.afterReturn < -0.005
      ? "is-down"
      : "is-flat";

  return (
    <article className={`try-card ${directionClass}`}>
      <header className="try-card__head">
        <span className="try-card__rank">#{match.rank}</span>
        <span className="try-card__dates">
          {FMT_DATE.format(match.date)} – {FMT_DATE.format(match.endDate)}
        </span>
      </header>

      <svg
        className="try-card__spark"
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        aria-label={`Price-shape thumbnail for analog from ${FMT_DATE.format(match.date)}`}
      >
        {/* "today" divider for the historical analog — left side is the
            matched window, right side is what happened next. */}
        <line
          x1={dividerX}
          x2={dividerX}
          y1={0}
          y2={H}
          stroke="var(--rule)"
          strokeWidth={1}
          strokeDasharray="2 3"
        />
        <path
          d={path}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.4}
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <dl className="try-card__metrics">
        <div className="try-card__metric">
          <dt>Similarity</dt>
          <dd>{(match.composite * 100).toFixed(0)}</dd>
        </div>
        <div className="try-card__metric">
          <dt>What happened next</dt>
          <dd className={`try-card__return ${directionClass}`}>
            {fmtPct(match.afterReturn)}
          </dd>
        </div>
      </dl>

      <p className="try-card__note">{match.note}</p>
    </article>
  );
}
