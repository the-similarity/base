/**
 * Lumen sidebar — left rail with brand mark, 3 nav groups, and user footer.
 *
 * Three groups (Overview / Money / Plan) span 9 items total — one per
 * screen in the workstation. The "Insights" item carries an "AI" pill
 * badge, "Transactions" carries a numeric badge (12); both badge styles
 * are spelled out below rather than abstracted because the styling differs.
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
    label: "Overview",
    items: [
      { id: "dashboard", name: "Dashboard", icon: "home" },
      { id: "cashflow", name: "Cash Flow", icon: "flow" },
      { id: "insights", name: "Insights", icon: "sparkle", badge: "AI" },
    ],
  },
  {
    label: "Money",
    items: [
      { id: "accounts", name: "Accounts", icon: "bank" },
      { id: "transactions", name: "Transactions", icon: "list", badge: 12 },
      { id: "recurring", name: "Recurring", icon: "repeat" },
    ],
  },
  {
    label: "Plan",
    items: [
      { id: "budgets", name: "Budgets", icon: "pie" },
      { id: "goals", name: "Goals", icon: "target" },
      { id: "investments", name: "Investments", icon: "trend" },
    ],
  },
];

export function Sidebar({ current, onNavigate }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">L</div>
        <div className="brand-name">Lumen</div>
        <div className="brand-sub">v3</div>
      </div>

      {GROUPS.map((g) => (
        <div className="nav-group" key={g.label}>
          <div className="nav-label">{g.label}</div>
          {g.items.map((it) => (
            <button
              key={it.id}
              className={`nav-item ${current === it.id ? "active" : ""}`}
              onClick={() => onNavigate(it.id)}
            >
              <Icon name={it.icon} />
              <span>{it.name}</span>
              {it.badge !== undefined &&
                (typeof it.badge === "string" ? (
                  // Text badge ("AI") gets a green pill style.
                  <span
                    className="pill pos"
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
                  <span className="badge">{it.badge}</span>
                ))}
            </button>
          ))}
        </div>
      ))}

      <div className="sidebar-foot">
        <div className="avatar">AC</div>
        <div className="col" style={{ minWidth: 0 }}>
          <div className="who">Alex Chen</div>
          <div className="plan">Lumen Plus</div>
        </div>
        <button
          className="icon-btn"
          style={{ marginLeft: "auto" }}
          onClick={() => onNavigate("dashboard")}
          title="Settings"
        >
          <Icon name="settings" />
        </button>
      </div>
    </aside>
  );
}
