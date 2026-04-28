/**
 * Lumen sidebar — left rail with The Similarity wordmark, a single
 * "Workstation" nav group, and a small workspace footer.
 *
 * History note: this file used to render three groups (Workstation /
 * Finance / Reports) wired to nine inert mockup screens. The Lumen
 * route now embeds the real Workstation component, so the rail
 * collapses to one always-active "Retrieve" entry plus an
 * informational "Catalog" row. The `current` and `onNavigate` props
 * are kept as inert pass-throughs so the page-level type contract
 * (`ScreenId`) doesn't need to change shape just because navigation
 * has nowhere to go right now.
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
  // When `inert` is true the row is rendered as decorative — it still
  // calls onNavigate (which is a no-op for non-`retrieve` ids in the
  // current page contract) but never appears active. Used for the
  // Catalog row, which is informational only.
  inert?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

/**
 * Single-group nav. The Lumen route is a contained workstation page —
 * there is exactly one screen (Retrieve, the embedded Workstation
 * component). Catalog is included as a second row purely so the rail
 * doesn't feel empty; clicking it is a no-op for now.
 */
const GROUPS: NavGroup[] = [
  {
    label: "Workstation",
    items: [
      { id: "retrieve", name: "Retrieve", icon: "target" },
      // Catalog is decorative — there's no second screen to route to.
      // Marked inert so the row never shows the active state.
      { id: "retrieve", name: "Catalog", icon: "bank", inert: true },
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
          {g.items.map((it, idx) => {
            // Active when the row's id matches AND it isn't marked
            // decorative. Without the `inert` guard the Catalog row
            // (which shares the `retrieve` id) would always paint as
            // active alongside Retrieve.
            const isActive = !it.inert && current === it.id;
            return (
              <button
                key={`${it.id}-${idx}`}
                className={`lumen-nav-item ${isActive ? "is-active" : ""}`}
                onClick={() => onNavigate(it.id)}
              >
                <Icon name={it.icon} />
                <span>{it.name}</span>
              </button>
            );
          })}
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
