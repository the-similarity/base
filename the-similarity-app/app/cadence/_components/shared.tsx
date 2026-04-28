/**
 * Cadence — small layout/atom components shared across screens.
 *
 * Pill / SectionHead / Topbar / SegControl / PropRow / SourceLogo.
 *
 * These are intentionally thin wrappers around the page-scoped CSS classes
 * (.cadence-pill, .cadence-topbar, .cadence-section-head, etc.) — they do
 * not own visual logic beyond what the stylesheet defines.
 *
 * All className strings here are `cadence-` prefixed. Anything un-prefixed
 * would collide with rules in `app/globals.css` and break the layout (see
 * styles.tsx for the full collision rationale).
 */
import type { ReactNode, CSSProperties } from "react";
import { Icon } from "./icons";

// =====================================================================
// Pill — small rounded label with optional dot + tone variant.
// =====================================================================

export type PillTone = "default" | "pos" | "neg" | "warn" | "info" | "outline";

export interface PillProps {
  tone?: PillTone;
  children: ReactNode;
  dot?: boolean;
  style?: CSSProperties;
}

export function Pill({ tone = "default", children, dot = false, style }: PillProps) {
  // The default tone is the bare `.cadence-pill` rule; any other tone gets
  // a `cadence-pill-<tone>` modifier that overrides background/color.
  const toneClass = tone === "default" ? "" : `cadence-pill-${tone}`;
  return (
    <span className={`cadence-pill ${toneClass}`} style={style}>
      {dot && <span className="cadence-dot" />}
      {children}
    </span>
  );
}

// =====================================================================
// SectionHead — title + sub + optional actions row above a card grid.
// =====================================================================

export interface SectionHeadProps {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
}

export function SectionHead({ title, sub, actions }: SectionHeadProps) {
  return (
    <div className="cadence-section-head">
      <div className="cadence-title">{title}</div>
      {sub && <div className="cadence-sub">{sub}</div>}
      {actions && <div className="cadence-actions">{actions}</div>}
    </div>
  );
}

// =====================================================================
// Topbar — breadcrumbs + search button + bell/refresh + per-screen actions.
// =====================================================================

export interface TopbarProps {
  crumbs?: string[];
  actions?: ReactNode;
  onCmdK?: () => void;
}

export function Topbar({ crumbs = [], actions, onCmdK }: TopbarProps) {
  return (
    <div className="cadence-topbar">
      <div className="cadence-crumbs">
        {crumbs.map((c, i) => (
          // Using index-as-key is fine here because crumbs are stable per screen.
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {i > 0 && <span className="cadence-sep">/</span>}
            <span className={i === crumbs.length - 1 ? "cadence-here" : ""}>{c}</span>
          </span>
        ))}
      </div>
      <div className="cadence-top-actions">
        <button
          className="cadence-btn cadence-btn-ghost"
          onClick={onCmdK}
          style={{ height: 28, paddingRight: 6 }}
        >
          <Icon name="search" /> Search <span className="cadence-kbd">⌘K</span>
        </button>
        <button className="cadence-icon-btn" title="Notifications">
          <Icon name="bell" />
        </button>
        <button className="cadence-icon-btn" title="Refresh">
          <Icon name="refresh" />
        </button>
        {actions}
      </div>
    </div>
  );
}

// =====================================================================
// SegControl — tiny segmented switch (1D / 1W / 1M / 1Y etc).
// =====================================================================

export type SegOption = string | { value: string; label: string };

export interface SegControlProps {
  value: string;
  options: SegOption[];
  onChange: (v: string) => void;
}

export function SegControl({ value, options, onChange }: SegControlProps) {
  return (
    <div className="cadence-seg">
      {options.map((o) => {
        const v = typeof o === "object" ? o.value : o;
        const l = typeof o === "object" ? o.label : o;
        return (
          <button
            key={v}
            className={value === v ? "is-active" : ""}
            onClick={() => onChange(v)}
          >
            {l}
          </button>
        );
      })}
    </div>
  );
}

// =====================================================================
// PropRow — two-column key/value row used in detail panels.
// =====================================================================

export interface PropRowProps {
  icon?: string;
  label: ReactNode;
  children: ReactNode;
}

export function PropRow({ icon, label, children }: PropRowProps) {
  // NOTE: .cadence-prop-row / .cadence-k / .cadence-v are not currently
  // styled in styles.tsx — this component is presently unused but kept as
  // the styled equivalent so future detail panels can drop it in. Class
  // names are still cadence-* prefixed to prevent collisions if/when
  // styles.tsx grows rules for them.
  return (
    <div className="cadence-prop-row">
      <div className="cadence-k">
        {icon && <Icon name={icon} />}
        {label}
      </div>
      <div className="cadence-v">{children}</div>
    </div>
  );
}

// =====================================================================
// SourceLogo — colored tile used by the Sources screen for wearable cards.
// =====================================================================

export interface SourceLogoProps {
  color: string;
  mark: string;
  size?: number;
}

export function SourceLogo({ color, mark, size = 36 }: SourceLogoProps) {
  return (
    <div
      className="cadence-source-logo"
      style={{
        background: color,
        width: size,
        height: size,
        flex: `0 0 ${size}px`,
        fontSize: size * 0.36,
      }}
    >
      {mark}
    </div>
  );
}
