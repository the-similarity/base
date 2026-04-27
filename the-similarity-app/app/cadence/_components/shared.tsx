/**
 * Cadence — small layout/atom components shared across screens.
 *
 * Pill / SectionHead / Topbar / SegControl / PropRow / SourceLogo.
 *
 * These are intentionally thin wrappers around the page-scoped CSS classes
 * (.pill, .topbar, .section-head, etc.) — they do not own visual logic
 * beyond what the stylesheet defines.
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
  return (
    <span className={`pill ${tone === "default" ? "" : tone}`} style={style}>
      {dot && <span className="dot" />}
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
    <div className="section-head">
      <div className="title">{title}</div>
      {sub && <div className="sub">{sub}</div>}
      {actions && <div className="actions">{actions}</div>}
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
    <div className="topbar">
      <div className="crumbs">
        {crumbs.map((c, i) => (
          // Using index-as-key is fine here because crumbs are stable per screen.
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {i > 0 && <span className="sep">/</span>}
            <span className={i === crumbs.length - 1 ? "here" : ""}>{c}</span>
          </span>
        ))}
      </div>
      <div className="top-actions">
        <button
          className="btn ghost"
          onClick={onCmdK}
          style={{ height: 28, paddingRight: 6 }}
        >
          <Icon name="search" /> Search <span className="kbd">⌘K</span>
        </button>
        <button className="icon-btn" title="Notifications">
          <Icon name="bell" />
        </button>
        <button className="icon-btn" title="Refresh">
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
    <div className="seg">
      {options.map((o) => {
        const v = typeof o === "object" ? o.value : o;
        const l = typeof o === "object" ? o.label : o;
        return (
          <button
            key={v}
            className={value === v ? "active" : ""}
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
  return (
    <div className="prop-row">
      <div className="k">
        {icon && <Icon name={icon} />}
        {label}
      </div>
      <div className="v">{children}</div>
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
      className="source-logo"
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
