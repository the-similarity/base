/**
 * Lumen — small layout/atom components shared across screens.
 *
 * Pill / Chip / SectionHead / Topbar / SegControl / PropRow.
 *
 * Every JSX class name in this file uses the `lumen-` prefix. The page
 * stylesheet (styles.tsx) only knows about `.lumen-app .lumen-foo`
 * selectors — anything un-prefixed will collide with `app/globals.css`
 * (which defines its own `.pill`, `.chip`, `.kbd`, `.row`, `.right`,
 * `.label`, `.mono` etc.). Treat the prefix as load-bearing.
 *
 * MerchantBadge / CategoryChip from the previous personal-finance
 * design were removed — they referenced demo `MERCHANTS` and
 * `CATEGORIES` lookup tables that no longer exist.
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

/**
 * Pill — `lumen-pill` colored chip. Tones map to `is-*` modifier
 * classes defined in styles.tsx (is-pos, is-neg, is-warn, is-info,
 * is-outline). Default tone leaves the modifier off and uses the
 * neutral grey background.
 */
export function Pill({ tone = "default", children, dot = false, style }: PillProps) {
  const toneClass = tone === "default" ? "" : `is-${tone}`;
  return (
    <span className={`lumen-pill ${toneClass}`.trim()} style={style}>
      {dot && <span className="lumen-dot" />}
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
    <div className="lumen-section-head">
      <div className="lumen-title">{title}</div>
      {sub && <div className="lumen-sub">{sub}</div>}
      {actions && <div className="lumen-actions">{actions}</div>}
    </div>
  );
}

// =====================================================================
// Topbar — breadcrumbs + search button + per-screen actions.
// =====================================================================

export interface TopbarProps {
  crumbs?: string[];
  actions?: ReactNode;
  onCmdK?: () => void;
}

/**
 * Topbar — fixed-height row at the top of the main panel.
 *
 * Visual layout:
 *   [crumbs]                        [search button]  [actions]
 *
 * The search button is a styled `lumen-btn is-ghost` that triggers the
 * Cmd+K palette. The optional `actions` slot is the place each screen
 * stuffs its own primary action (e.g. "Open workstation").
 */
export function Topbar({ crumbs = [], actions, onCmdK }: TopbarProps) {
  return (
    <div className="lumen-topbar">
      <div className="lumen-crumbs">
        {crumbs.map((c, i) => (
          // Index-as-key is fine because crumbs are stable per screen.
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {i > 0 && <span className="lumen-sep">/</span>}
            <span className={i === crumbs.length - 1 ? "lumen-here" : ""}>{c}</span>
          </span>
        ))}
      </div>
      <div className="lumen-top-actions">
        <button
          className="lumen-btn is-ghost"
          onClick={onCmdK}
          style={{ height: 28, paddingRight: 6 }}
        >
          <Icon name="search" /> Search <span className="lumen-kbd">⌘K</span>
        </button>
        {actions}
      </div>
    </div>
  );
}

// =====================================================================
// SegControl — tiny segmented switch (1M / 3M / 1Y / ALL etc).
// =====================================================================

export type SegOption = string | { value: string; label: string };

export interface SegControlProps {
  value: string;
  options: SegOption[];
  onChange: (v: string) => void;
}

export function SegControl({ value, options, onChange }: SegControlProps) {
  return (
    <div className="lumen-seg">
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
  return (
    <div className="lumen-prop-row">
      <div className="lumen-k">
        {icon && <Icon name={icon} />}
        {label}
      </div>
      <div className="lumen-v">{children}</div>
    </div>
  );
}
