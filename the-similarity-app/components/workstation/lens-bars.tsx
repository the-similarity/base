"use client";

/**
 * Lens score bar list — shows all 9 lenses with a name, horizontal
 * fill bar, and numeric value. Bars below 0.55 get the "weak" style
 * (dimmed fill). Optional compact mode omits the description text.
 */

import { LENS_DEFS, LensScores } from "../../lib/data";

interface LensBarsProps {
  /** Per-lens scores (0..1) */
  lenses: LensScores;
  /** Callback when a lens row is hovered */
  onHover?: (key: string | null) => void;
  /** If true, omit the description text after the lens name */
  compact?: boolean;
}

export function LensBars({ lenses, onHover, compact = false }: LensBarsProps) {
  return (
    <div className="lens-bars">
      {LENS_DEFS.map(def => {
        const v = lenses[def.key] ?? 0;
        return (
          <div key={def.key} className="lens-bar"
            onMouseEnter={() => onHover && onHover(def.key)}
            onMouseLeave={() => onHover && onHover(null)}>
            <div>
              <div className="lens-bar__name">
                <span style={{ fontWeight: 500 }}>{def.name}</span>
                {!compact && <span style={{ color: "var(--ink-3)", fontSize: 11 }}>&mdash; {def.q}</span>}
              </div>
              <div className="lens-bar__track">
                <div className={"lens-bar__fill" + (v < 0.55 ? " weak" : "")} style={{ width: `${v * 100}%` }} />
              </div>
            </div>
            <div className="lens-bar__val">{v.toFixed(2)}</div>
          </div>
        );
      })}
    </div>
  );
}
