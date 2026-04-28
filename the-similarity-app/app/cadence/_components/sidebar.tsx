/**
 * Cadence sidebar — left rail with brand mark, flat 5-item nav, and user footer.
 *
 * The slop cut collapsed Cadence from 9 screens to 5. With only five items
 * remaining (Today / Rhymes / Log / Sources / Labs), the original 4 group
 * labels (Today / Patterns / Plan / System) added more visual noise than
 * navigation help — so the rail renders as a single ungrouped list.
 *
 * The "Rhymes" item carries a "NEW" pill to highlight the hero feature on
 * first visit.
 *
 * Class names are all `cadence-` prefixed — the page-scoped stylesheet
 * (styles.tsx) only matches `.cadence-app .cadence-foo` selectors. Any
 * un-prefixed class on this rail will be styled by `app/globals.css`
 * (which has `.brand`, `.sidebar`, etc.) and break the layout.
 */
import type { ScreenId } from "./screen-types";
import { Icon } from "./icons";

export interface SidebarProps {
  current: ScreenId;
  onNavigate: (id: ScreenId) => void;
}

interface NavItem {
  id: ScreenId;
  name: string;
  icon: string;
  badge?: string | number;
}

// Flat nav — no groups. Order intentionally matches Cmd+K palette so users
// who learn the keyboard shortcut find the same vertical scan order in the
// rail.
const NAV: NavItem[] = [
  { id: "today", name: "Today", icon: "heartPulse" },
  { id: "rhymes", name: "Rhymes", icon: "echoRings", badge: "NEW" },
  { id: "log", name: "Log", icon: "ledger" },
  { id: "sources", name: "Sources", icon: "plug" },
  { id: "labs", name: "Labs", icon: "beaker" },
];

export function Sidebar({ current, onNavigate }: SidebarProps) {
  return (
    <aside className="cadence-sidebar">
      <div className="cadence-brand">
        <div className="cadence-brand-mark">C</div>
        <div className="cadence-brand-name">Cadence</div>
        <div className="cadence-brand-sub">v1</div>
      </div>

      {NAV.map((it) => (
        <button
          key={it.id}
          className={`cadence-nav-item ${current === it.id ? "is-active" : ""}`}
          onClick={() => onNavigate(it.id)}
        >
          <Icon name={it.icon} />
          <span>{it.name}</span>
          {it.badge !== undefined &&
            (typeof it.badge === "string" ? (
              // Text badge ("NEW") gets the sage-green pill style.
              <span
                className="cadence-pill cadence-pill-pos"
                style={{
                  marginLeft: "auto",
                  height: 17,
                  padding: "0 6px",
                  fontSize: 10,
                }}
              >
                {it.badge}
              </span>
            ) : (
              // Numeric badge (count) gets the neutral pill.
              <span className="cadence-badge">{it.badge}</span>
            ))}
        </button>
      ))}

      <div className="cadence-sidebar-foot">
        <div className="cadence-avatar">B</div>
        <div className="cadence-col" style={{ minWidth: 0 }}>
          <div className="cadence-who">Buba</div>
          <div className="cadence-plan">Cadence</div>
        </div>
        <button
          className="cadence-icon-btn"
          style={{ marginLeft: "auto" }}
          onClick={() => onNavigate("today")}
          title="Settings"
        >
          <Icon name="settings" />
        </button>
      </div>
    </aside>
  );
}
