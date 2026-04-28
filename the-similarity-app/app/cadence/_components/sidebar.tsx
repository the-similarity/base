/**
 * Cadence sidebar — left rail with brand mark, 3 nav groups, and user footer.
 *
 * Three groups (Today / Patterns / Plan) span 9 items total — one per
 * screen in the workstation. Mirrors Lumen's structure exactly so the
 * two routes feel like sibling products from the same family.
 *
 * Group rationale:
 *   - Today    — everything anchored to the current moment (today / flow / log)
 *   - Patterns — analogue retrieval over user's own past (rhymes / cycles)
 *   - Plan     — forward-looking commitments (targets / goals)
 *   - System   — connectivity + lab inputs (sources / labs)
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

interface NavGroup {
  label: string;
  items: NavItem[];
}

const GROUPS: NavGroup[] = [
  {
    label: "Today",
    items: [
      { id: "today", name: "Today", icon: "heartPulse" },
      { id: "log", name: "Log", icon: "ledger" },
    ],
  },
  {
    label: "Patterns",
    items: [
      { id: "rhymes", name: "Rhymes", icon: "echoRings", badge: "NEW" },
    ],
  },
  {
    label: "Plan",
    items: [
      { id: "targets", name: "Targets", icon: "target" },
      { id: "goals", name: "Goals", icon: "flag" },
    ],
  },
  {
    label: "System",
    items: [
      { id: "sources", name: "Sources", icon: "plug" },
      { id: "labs", name: "Labs", icon: "beaker" },
    ],
  },
];

export function Sidebar({ current, onNavigate }: SidebarProps) {
  return (
    <aside className="cadence-sidebar">
      <div className="cadence-brand">
        <div className="cadence-brand-mark">C</div>
        <div className="cadence-brand-name">Cadence</div>
        <div className="cadence-brand-sub">v1</div>
      </div>

      {GROUPS.map((g) => (
        <div className="cadence-nav-group" key={g.label}>
          <div className="cadence-nav-label">{g.label}</div>
          {g.items.map((it) => (
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
        </div>
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
