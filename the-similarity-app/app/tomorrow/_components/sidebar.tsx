"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "./button";
import { Avatar } from "./avatar";
import { StatusBadge } from "./status-badge";
import { useEngine } from "./engine-context";
import { NavGlyph, fmtShortDate, navIdForPathname } from "./shell";
import { TOMORROW_TOKENS } from "./tokens";

export function Sidebar() {
  const pathname = usePathname() ?? "/tomorrow";
  const nav = navIdForPathname(pathname);
  const { openComposer, exportEntries, entries } = useEngine();
  const todayHint = fmtShortDate(new Date());

  return (
    <aside className="tomorrow-sidebar">
      <div className="tomorrow-sidebar__brand">
        <div className="tomorrow-brand-mark">T</div>
        <div>
          <div className="tomorrow-brand-name">Tomorrow</div>
          <div className="tomorrow-brand-sub">Lumen journal</div>
        </div>
      </div>

      <div className="tomorrow-sidebar__body">
        <Button
          variant="primary"
          onClick={openComposer}
          className="tomorrow-compose-button"
          title="New entry"
          aria-label="New entry"
        >
          <span aria-hidden="true" className="tomorrow-compose-icon">+</span>
          <span className="tomorrow-compose-label">New entry</span>
        </Button>

        <nav className="tomorrow-sidebar__nav" aria-label="Tomorrow sections">
          {TOMORROW_TOKENS.routes.map((item) => {
            const active = nav === item.id;
            const hint =
              item.id === "today"
                ? todayHint
                : item.id === "thread"
                  ? "30d"
                  : item.id === "entries" && entries.length > 0
                    ? String(entries.length)
                    : undefined;
            return (
              <Link
                key={item.id}
                href={item.href}
                className="tomorrow-nav-item"
                data-active={active}
              >
                <span className="tomorrow-nav-main">
                  <NavGlyph id={item.id} active={active} />
                  <span className="tomorrow-nav-label">{item.label}</span>
                </span>
                {hint ? (
                  <span className="mono tomorrow-nav-hint" style={{ fontSize: 10, color: "var(--faint)" }}>
                    {hint}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="tomorrow-sidebar__footer" style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: "auto" }}>
          <StatusBadge>{entries.length} entries</StatusBadge>
          <Button variant="ghost" onClick={exportEntries} className="tomorrow-export-button" style={{ justifyContent: "flex-start" }}>
            <NavGlyph id="export" />
            <span className="tomorrow-export-label">Export journal</span>
          </Button>
          <div className="tomorrow-local-row" style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--muted)", fontSize: 12 }}>
            <Avatar />
            <span>Local only</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
