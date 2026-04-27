/**
 * Lumen sidebar — left rail with The Similarity wordmark, three nav
 * groups (WORKSTATION / FINANCE / REPORTS), and a small workspace
 * footer.
 *
 * The brand mark is a 22x22 SVG of three nested circles (the
 * self-similarity primitive) drawn with `currentColor` so it inherits
 * the foreground ink color and follows dark-mode automatically.
 *
 * Class names are all `lumen-` prefixed — the page-scoped stylesheet
 * (styles.tsx) only matches `.lumen-app .lumen-foo` selectors. Any
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
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

/**
 * Three-group nav. Order:
 *   WORKSTATION → the headline analog-retrieval entry point
 *   FINANCE     → run-management surfaces (Runs / Compare / Reviews / Dashboard)
 *   REPORTS     → narrative + portfolio surfaces (Strategy / Cadence / Case Studies / Reports)
 *
 * Adding a new screen requires extending `ScreenId` and the page
 * switch in `page.tsx` — see screen-types.ts for the contract.
 */
const GROUPS: NavGroup[] = [
  {
    label: "Workstation",
    items: [
      { id: "retrieve", name: "Retrieve", icon: "target" },
    ],
  },
  {
    label: "Finance",
    items: [
      { id: "runs", name: "Runs", icon: "list" },
      { id: "compare", name: "Compare", icon: "grid" },
      { id: "reviews", name: "Reviews", icon: "note" },
      { id: "dashboard", name: "Dashboard", icon: "pie" },
    ],
  },
  {
    label: "Reports",
    items: [
      { id: "strategy", name: "Strategy", icon: "trend" },
      { id: "cadence", name: "Cadence", icon: "flow" },
      { id: "case-studies", name: "Case Studies", icon: "book" },
      { id: "reports", name: "Reports", icon: "receipt" },
    ],
  },
];

/**
 * Brand mark SVG — three nested circles, the self-similarity primitive.
 * Inlined (not imported as a file) so the entire Lumen tree is
 * self-contained: lifting it into another project requires no asset
 * pipeline. Stroke is `currentColor` so it inherits the page's ink
 * color in both light and dark modes.
 */
function BrandMark() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 26 26"
      style={{ color: "var(--ink)" }}
      aria-hidden="true"
    >
      <circle cx="13" cy="13" r="11" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="13" cy="13" r="6" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="13" cy="13" r="1.8" fill="currentColor" />
    </svg>
  );
}

export function Sidebar({ current, onNavigate }: SidebarProps) {
  return (
    <aside className="lumen-sidebar">
      <div className="lumen-brand">
        <div className="lumen-brand-mark">
          <BrandMark />
        </div>
        {/* Wordmark: roman "The" + italic "Similarity" — Instrument Serif
            handles both weights via the same family. */}
        <div className="lumen-brand-name">
          The <em>Similarity</em>
        </div>
      </div>

      {GROUPS.map((g) => (
        <div className="lumen-nav-group" key={g.label}>
          <div className="lumen-nav-label">{g.label}</div>
          {g.items.map((it) => (
            <button
              key={it.id}
              className={`lumen-nav-item ${current === it.id ? "is-active" : ""}`}
              onClick={() => onNavigate(it.id)}
            >
              <Icon name={it.icon} />
              <span>{it.name}</span>
            </button>
          ))}
        </div>
      ))}

      {/* Footer: small workspace label + settings icon. The label
          mirrors the "WORKSTATION → Quant" routing reality of the
          product instead of the previous "Alex Chen / Lumen Plus" demo. */}
      <div className="lumen-sidebar-foot">
        <div className="lumen-col" style={{ minWidth: 0 }}>
          <div className="lumen-who">Workspace</div>
          <div className="lumen-plan">Quant</div>
        </div>
        <button
          className="lumen-icon-btn"
          style={{ marginLeft: "auto" }}
          onClick={() => onNavigate("retrieve")}
          title="Settings"
          aria-label="Settings"
        >
          <Icon name="settings" />
        </button>
      </div>
    </aside>
  );
}
