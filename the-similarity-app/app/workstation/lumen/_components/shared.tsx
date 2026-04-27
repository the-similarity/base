/**
 * Lumen — small layout/atom components shared across screens.
 *
 * Pill / Chip / SectionHead / Topbar / MerchantBadge / CategoryChip /
 * SegControl / PropRow.
 *
 * These are intentionally thin wrappers around the page-scoped CSS classes
 * (.pill, .chip, .topbar, .merch, etc.) — they do not own visual logic
 * beyond what the stylesheet defines. The only visual logic in here is the
 * MerchantBadge fallback (when an unknown merchant name lands in TX, we
 * derive a 2-letter mark from the first two characters).
 */
import type { ReactNode, CSSProperties } from "react";
import { Icon } from "./icons";
import { CATEGORIES, MERCHANTS } from "./data";

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
// Chip — filter chip used in the transactions filter bar.
// =====================================================================

export interface ChipProps {
  active?: boolean;
  children: ReactNode;
  onClick?: () => void;
  removable?: boolean;
}

export function Chip({ active, children, onClick, removable }: ChipProps) {
  return (
    <button className={`chip ${active ? "active" : ""}`} onClick={onClick}>
      {children}
      {active && removable && (
        <span className="x">
          <Icon name="x" />
        </span>
      )}
    </button>
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
// MerchantBadge — colored tile with the merchant's 2-letter mark.
// =====================================================================

export interface MerchantBadgeProps {
  name: string;
  size?: number;
  withMark?: boolean;
}

export function MerchantBadge({ name, size = 26, withMark = true }: MerchantBadgeProps) {
  // Unknown merchants get a neutral grey tile + first-two-letter fallback
  // rather than crashing with `undefined.color`.
  const m = MERCHANTS[name] || { color: "#7a7a75", mark: name.slice(0, 2).toUpperCase() };
  return (
    <div
      className="merch"
      style={{
        background: m.color,
        width: size,
        height: size,
        fontSize: size * 0.42,
        flex: `0 0 ${size}px`,
        borderRadius: size * 0.27,
      }}
    >
      {withMark && (m.mark || name.slice(0, 1))}
    </div>
  );
}

// =====================================================================
// CategoryChip — pill colored by the category's signature hue.
// =====================================================================

export interface CategoryChipProps {
  cat: string;
}

export function CategoryChip({ cat }: CategoryChipProps) {
  const c = CATEGORIES[cat];
  if (!c) return null;
  return (
    // Inline style here because the tint mixes per-category color + 15%
    // alpha, which can't be expressed cleanly as a static class.
    <span className="pill" style={{ background: c.color + "15", color: c.color }}>
      <Icon name={c.icon} style={{ width: 11, height: 11 }} />
      {c.label}
    </span>
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
// PropRow — two-column key/value row used in the transaction detail panel.
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
