"use client";

/**
 * Prudent shell — Sidebar, TopBar, PageHeader, and the small presentation
 * helpers (Chip, NavGlyph, SectionLabel, DateRangeChip) shared across every
 * /prudent route page.
 *
 * Historical context:
 *   These components used to live inline in dashboard.tsx, where the
 *   "nav" was a local useState in <Dashboard/>. With the App Router
 *   refactor we derive the active nav from `usePathname()` and render
 *   sidebar items as <Link href> elements so clicking "Thread" actually
 *   navigates to /prudent/thread instead of toggling a state variable.
 *
 * Invariants:
 *   - The shell is shared — every /prudent/* page renders inside the same
 *     layout so the sidebar/top-bar don't flash when the user moves
 *     between pages.
 *   - Each sidebar Link owns its own href; the active state is a pure
 *     function of `usePathname()`.
 *   - DateRangeChip persists its preset to localStorage under the
 *     `prudent:daterange:v1` key (unchanged from dashboard.tsx).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, Fragment } from "react";
import { useEngine } from "./engine-context";
import type { ReactNode } from "react";

// ═══════════════════════════════════════════════════════════════════════
// Date helpers — shared string shapes for the breadcrumb + date range
// chip. Duplicated here (and in today-view.tsx) so each module can stand
// on its own; we keep them tiny because they have no state.
// ═══════════════════════════════════════════════════════════════════════

export function fmtShortDate(d: Date): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
export function fmtLongDate(d: Date): string {
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}
export function fmtClockTime(d: Date): string {
  return d
    .toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    })
    .toLowerCase();
}

// ═══════════════════════════════════════════════════════════════════════
// Sidebar
// ═══════════════════════════════════════════════════════════════════════

/**
 * Map between pathname prefixes and sidebar nav ids. The App Router rewrites
 * "/prudent" → id "today" so the top-level route is the spiritual landing
 * page; every other id matches its sub-route.
 */
export function navIdForPathname(pathname: string): string {
  if (!pathname.startsWith("/prudent")) return "today";
  const rest = pathname.slice("/prudent".length);
  if (rest === "" || rest === "/") return "today";
  // Strip leading slash; take the first segment (so /prudent/thread/123
  // still resolves to "thread"). This keeps the sidebar highlight stable
  // as Wave 2 agents add deeper per-page routing.
  return rest.replace(/^\//, "").split("/")[0];
}

// Map a nav id back to its href. "today" is the parent route, everything
// else is `/prudent/<id>`. Wave 2 agents will create the corresponding
// page.tsx files; until then clicking a link will 404, which is fine
// because this PR's only job is the foundation.
function hrefForNavId(id: string): string {
  return id === "today" ? "/prudent" : `/prudent/${id}`;
}

export function Sidebar() {
  const pathname = usePathname() ?? "/prudent";
  const nav = navIdForPathname(pathname);
  const { openComposer, exportEntries, entries } = useEngine();

  // Today hint — short month+day derived from `new Date()` so the sidebar
  // never drifts out of sync with the wall clock.
  const todayHint = fmtShortDate(new Date());
  const items: { id: string; label: string; hint?: string }[] = [
    { id: "today", label: "Today", hint: todayHint },
    { id: "thread", label: "Thread", hint: "30d" },
    { id: "rhymes", label: "Rhymes" },
    { id: "tags", label: "Tags" },
    { id: "patterns", label: "Patterns" },
    {
      id: "entries",
      label: "Entries",
      hint: entries.length > 0 ? String(entries.length) : undefined,
    },
  ];

  return (
    <aside
      style={{
        display: "flex",
        height: "100vh",
        position: "sticky",
        top: 0,
        background: "var(--sidebar)",
        borderRight: "1px solid var(--line)",
      }}
    >
      {/* Icon rail — dark column hosting the brand mark, a help glyph, and
          the user avatar. Pure presence elements; no dead nav glyphs. */}
      <div
        style={{
          width: 56,
          background: "var(--rail)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "14px 0 14px 0",
          gap: 4,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            background: "var(--accent)",
            borderRadius: 7,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontWeight: 700,
            fontSize: 12,
            fontFamily: "var(--mono)",
            marginBottom: 10,
          }}
        >
          {"//"}
        </div>
        <div style={{ flex: 1 }} />
        <button
          style={{
            width: 28,
            height: 28,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--rail-ink)",
            borderRadius: 6,
          }}
          title="Help"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="5.5" />
            <path d="M6.5 7a1.5 1.5 0 113 0c0 1-1.5 1-1.5 2M8 11.2v.1" />
          </svg>
        </button>
        <div
          style={{
            width: 26,
            height: 26,
            background: "linear-gradient(135deg, #F97316, #3B82F6)",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: 11,
            fontWeight: 700,
            marginTop: 4,
            border: "1px solid rgba(255,255,255,0.12)",
          }}
        >
          K
        </div>
      </div>
      <div style={{ width: 280, padding: "16px 14px", display: "flex", flexDirection: "column" }}>
        <button
          onClick={openComposer}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--ink)",
            color: "var(--app-bg)",
            padding: "10px 13px",
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 500,
            marginBottom: 18,
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 14, lineHeight: 1 }}>＋</span> New entry
          </span>
          <span style={{ fontSize: 10, opacity: 0.55, fontFamily: "var(--mono)" }}>⌘N</span>
        </button>

        <SectionLabel>Spaces</SectionLabel>
        {items.map((it) => {
          const active = nav === it.id;
          return (
            <Link
              key={it.id}
              href={hrefForNavId(it.id)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "9px 10px",
                borderRadius: 7,
                fontSize: 13,
                background: active ? "var(--hover)" : "transparent",
                color: active ? "var(--ink)" : "var(--muted)",
                fontWeight: active ? 600 : 450,
                textAlign: "left",
                marginBottom: 1,
                textDecoration: "none",
                transition: "background 100ms ease, color 100ms ease",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <NavGlyph id={it.id} active={active} />
                {it.label}
              </span>
              {it.hint ? (
                <span className="mono" style={{ fontSize: 10, color: "var(--faint)" }}>
                  {it.hint}
                </span>
              ) : null}
            </Link>
          );
        })}

        <SectionLabel top={18}>Self services</SectionLabel>
        <NavLink label="Favourites" hint="4" />
        <NavLink label="Bookmarks" hint="12" />
        <NavLink label="Drafts" fresh />

        <SectionLabel top={18}>External</SectionLabel>
        {/* Engine logs is a route navigation (Wave 2 will add the page);
            Export fires a direct download via the context callback. */}
        <Link
          href="/prudent/engine"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            padding: "9px 10px",
            fontSize: 13,
            color: nav === "engine" ? "var(--ink)" : "var(--muted)",
            background: nav === "engine" ? "var(--hover)" : "transparent",
            borderRadius: 7,
            textAlign: "left",
            fontWeight: nav === "engine" ? 600 : 450,
            textDecoration: "none",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <NavGlyph id="engine" />
            Engine logs
          </span>
        </Link>
        <button
          onClick={exportEntries}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            padding: "9px 10px",
            fontSize: 13,
            color: "var(--muted)",
            background: "transparent",
            borderRadius: 7,
            textAlign: "left",
            fontWeight: 450,
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <NavGlyph id="export" />
            Export
          </span>
          <span
            className="mono"
            style={{ fontSize: 10, color: "var(--faint)" }}
            aria-hidden
          >
            ↓
          </span>
        </button>

        <div style={{ flex: 1 }} />
        <div
          style={{
            padding: "8px 0 2px 0",
            borderTop: "1px solid var(--line)",
            display: "flex",
            flexDirection: "column",
            gap: 2,
            marginTop: 10,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 10px",
              fontSize: 13,
              color: "var(--faint)",
              textAlign: "left",
              fontWeight: 450,
              cursor: "default",
              userSelect: "none",
            }}
            aria-disabled="true"
          >
            <NavGlyph id="support" /> Support
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 10px",
              fontSize: 13,
              color: "var(--faint)",
              textAlign: "left",
              fontWeight: 450,
              cursor: "default",
              userSelect: "none",
            }}
            aria-disabled="true"
          >
            <NavGlyph id="settings" /> Settings
          </div>
        </div>
      </div>
    </aside>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Section helpers
// ═══════════════════════════════════════════════════════════════════════

function SectionLabel({ children, top = 10 }: { children: ReactNode; top?: number }) {
  return (
    <div
      className="mono"
      style={{
        fontSize: 10,
        color: "var(--faint)",
        letterSpacing: "0.08em",
        padding: `${top}px 10px 8px 10px`,
        textTransform: "uppercase",
        fontWeight: 600,
      }}
    >
      {children}
    </div>
  );
}

function NavLink({ label, hint, fresh }: { label: string; hint?: string; fresh?: boolean }) {
  return (
    <button
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "9px 10px",
        borderRadius: 7,
        fontSize: 13,
        color: "var(--muted)",
        textAlign: "left",
        fontWeight: 450,
      }}
    >
      <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <NavGlyph id={label.toLowerCase()} />
        {label}
      </span>
      {fresh ? (
        <span
          style={{
            fontSize: 9,
            background: "var(--warm)",
            color: "#fff",
            padding: "2px 7px",
            borderRadius: 10,
            fontWeight: 600,
            letterSpacing: "0.02em",
          }}
        >
          New
        </span>
      ) : hint ? (
        <span className="mono" style={{ fontSize: 10, color: "var(--faint)" }}>
          {hint}
        </span>
      ) : null}
    </button>
  );
}

export function NavGlyph({ id, active }: { id: string; active?: boolean }) {
  const color = active ? "var(--ink)" : "var(--muted)";
  const common = { width: 14, height: 14, color };
  const m: Record<string, React.ReactElement> = {
    today: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="8" cy="8" r="5.5" />
        <path d="M8 4.5v3.5l2.2 1.5" />
      </svg>
    ),
    thread: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M2 11l3-2 3 2 3-4 3 3" />
      </svg>
    ),
    rhymes: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 6c1.5-2 4-2 5 0s3.5 2 5 0M3 11c1.5-2 4-2 5 0s3.5 2 5 0" />
      </svg>
    ),
    tags: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 3h5l5 5-5 5-5-5V3z" />
        <circle cx="5.5" cy="5.5" r="0.8" fill="currentColor" />
      </svg>
    ),
    patterns: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="2.5" y="2.5" width="4" height="4" />
        <rect x="9.5" y="2.5" width="4" height="4" />
        <rect x="2.5" y="9.5" width="4" height="4" />
        <rect x="9.5" y="9.5" width="4" height="4" />
      </svg>
    ),
    entries: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 2.5h8l2 2v9H3z" />
        <path d="M5.5 7h5M5.5 10h5M5.5 4.5h3" />
      </svg>
    ),
    engine: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="8" cy="8" r="2" />
        <path d="M8 2.5v2M8 11.5v2M13.5 8h-2M4.5 8h-2" />
      </svg>
    ),
    export: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M8 10V2m0 0l-3 3m3-3l3 3M3 12v2h10v-2" />
      </svg>
    ),
    support: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="8" cy="8" r="5.5" />
        <path d="M6.5 7a1.5 1.5 0 113 0c0 1-1.5 1-1.5 2M8 11.2v.1" />
      </svg>
    ),
    settings: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="8" cy="8" r="2" />
        <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2" />
      </svg>
    ),
  };
  return m[id] || <span style={{ width: 14 }} />;
}

// ═══════════════════════════════════════════════════════════════════════
// Top bar
// ═══════════════════════════════════════════════════════════════════════

export function TopBar() {
  // Breadcrumb derived from `new Date()` — the back/forward arrows, search,
  // bell, and avatar from the reference screenshot were dead controls and
  // have been dropped. Only the functional "Analytics › Today · <date>"
  // chip remains.
  const today = new Date();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: 13,
        paddingBottom: 2,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--muted)" }}>
        <span
          style={{
            padding: "4px 10px",
            borderRadius: 6,
            background: "var(--hover)",
            color: "var(--muted)",
            fontWeight: 500,
          }}
        >
          Analytics
        </span>
        <span style={{ color: "var(--faint)", fontSize: 14, lineHeight: 1 }}>›</span>
        <span
          style={{
            color: "var(--ink)",
            fontWeight: 500,
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            padding: "4px 10px 4px 8px",
            borderRadius: 6,
            background: "var(--hover)",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              background: "var(--accent)",
              borderRadius: 2,
            }}
          />
          Today · {fmtLongDate(today)}
        </span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Page header (title + filters row)
// ═══════════════════════════════════════════════════════════════════════

/**
 * Title + subtitle derived from the current pathname. Each /prudent/* route
 * gets a sensible page title even when its `page.tsx` is a stub — Wave 2
 * agents can keep this map authoritative or override locally by rendering
 * their own header above the route body.
 */
export function PageHeader() {
  const pathname = usePathname() ?? "/prudent";
  const nav = navIdForPathname(pathname);
  const { entries } = useEngine();

  const titleMap: Record<string, { title: string; subtitle: ReactNode }> = {
    today: {
      title: "Today",
      subtitle: "Narrative parsed live · events extracted on the fly",
    },
    thread: {
      title: "Thread",
      subtitle: (
        <>
          <span className="tnum" style={{ color: "var(--ink)", fontWeight: 500 }}>
            {entries.length}
          </span>{" "}
          entries saved · newest first · click any card to read
        </>
      ),
    },
    rhymes: {
      title: "Rhymes",
      subtitle: "Days whose shape most resembles today.",
    },
    entries: {
      title: "Entries",
      subtitle: (
        <>
          <span className="tnum" style={{ color: "var(--ink)", fontWeight: 500 }}>
            {entries.length}
          </span>{" "}
          logged · export or remove individual entries
        </>
      ),
    },
    tags: { title: "Tags", subtitle: "Coming soon." },
    patterns: { title: "Patterns", subtitle: "Coming soon." },
    engine: { title: "Engine logs", subtitle: "Live view of the parse pipeline." },
  };
  const { title, subtitle } = titleMap[nav] ?? titleMap.today;
  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          marginBottom: 16,
          gap: 12,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h1
            style={{
              fontSize: 30,
              fontWeight: 600,
              letterSpacing: "-0.02em",
              color: "var(--ink)",
              margin: 0,
              lineHeight: 1.1,
            }}
          >
            {title}
          </h1>
          <div
            style={{
              fontSize: 13,
              color: "var(--muted)",
              marginTop: 6,
              fontWeight: 400,
            }}
          >
            {subtitle}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <DateRangeChip />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Chip — small filter/control pill used in a few places
// ═══════════════════════════════════════════════════════════════════════

export function Chip({ label, caret, active }: { label: string; caret?: boolean; active?: boolean }) {
  return (
    <button
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 11px",
        fontSize: 12,
        background: active ? "var(--hover)" : "var(--panel)",
        border: "1px solid var(--line-mid)",
        borderRadius: 7,
        color: active ? "var(--ink)" : "var(--muted)",
        fontWeight: 500,
        lineHeight: 1.2,
      }}
    >
      {label}
      {caret && (
        <svg width="9" height="9" viewBox="0 0 9 9" fill="none" stroke="currentColor" strokeWidth="1.3" style={{ opacity: 0.7 }}>
          <path d="M2 3.5L4.5 6 7 3.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// DateRangeChip — functional date-range preset control
// ═══════════════════════════════════════════════════════════════════════

/**
 * DateRangeChip — click opens a small popover with three presets. Persists
 * the chosen preset to localStorage so a reload keeps the chip consistent.
 * The actual data-window is NOT wired here yet; the chip's only contract is
 * "clicks are observable and preserve state." Wave 2 agents can pipe the
 * preset into chart scales when they take over today-view.
 */
export function DateRangeChip() {
  type Preset = "today" | "7d" | "30d";
  const [preset, setPreset] = useState<Preset>(() => {
    if (typeof window === "undefined") return "today";
    const v = window.localStorage.getItem("prudent:daterange:v1");
    return v === "today" || v === "7d" || v === "30d" ? v : "today";
  });
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem("prudent:daterange:v1", preset);
    } catch {
      /* swallow */
    }
  }, [preset]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!anchorRef.current) return;
      if (!anchorRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const labelFor = (p: Preset): { from: string; to: string } => {
    const now = new Date();
    if (p === "today") {
      return { from: fmtLongDate(now), to: fmtClockTime(now) };
    }
    if (p === "7d") {
      const earlier = new Date(now);
      earlier.setDate(earlier.getDate() - 7);
      return { from: fmtShortDate(earlier), to: fmtShortDate(now) };
    }
    const earlier = new Date(now);
    earlier.setDate(earlier.getDate() - 30);
    return { from: fmtShortDate(earlier), to: fmtShortDate(now) };
  };
  const { from, to } = labelFor(preset);

  return (
    <div ref={anchorRef} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 11px",
          fontSize: 12,
          background: "var(--panel)",
          border: "1px solid var(--line-mid)",
          borderRadius: 7,
          color: "var(--ink)",
          fontWeight: 500,
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <svg
          width="13"
          height="13"
          viewBox="0 0 15 15"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
        >
          <rect x="2" y="3" width="11" height="10" rx="1" />
          <path d="M2 6h11M5 1.5v3M10 1.5v3" />
        </svg>
        <span>{from}</span>
        <span style={{ color: "var(--faint)" }}>→</span>
        <span>{to}</span>
        <svg
          width="9"
          height="9"
          viewBox="0 0 9 9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          style={{
            opacity: 0.55,
            marginLeft: 2,
            transition: "transform 120ms ease",
            transform: open ? "rotate(180deg)" : "rotate(0)",
          }}
        >
          <path d="M2 3.5L4.5 6 7 3.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div
          role="listbox"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            zIndex: 40,
            background: "var(--panel)",
            border: "1px solid var(--line-mid)",
            borderRadius: 8,
            padding: 4,
            boxShadow: "0 12px 24px -10px rgba(20,22,26,0.25)",
            minWidth: 160,
          }}
        >
          {(
            [
              { id: "today" as const, label: "Today" },
              { id: "7d" as const, label: "Last 7 days" },
              { id: "30d" as const, label: "Last 30 days" },
            ]
          ).map((opt) => (
            <button
              key={opt.id}
              onClick={() => {
                setPreset(opt.id);
                setOpen(false);
              }}
              role="option"
              aria-selected={preset === opt.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                width: "100%",
                padding: "7px 10px",
                fontSize: 12.5,
                color: preset === opt.id ? "var(--ink)" : "var(--muted)",
                background: preset === opt.id ? "var(--hover)" : "transparent",
                borderRadius: 6,
                fontWeight: preset === opt.id ? 600 : 500,
                textAlign: "left",
              }}
            >
              <span>{opt.label}</span>
              {preset === opt.id && (
                <svg
                  width="11"
                  height="11"
                  viewBox="0 0 11 11"
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M2 5.5L4.5 8l4.5-5" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Footer — shared across every prudent page so the layout stays visually
// anchored at the bottom even on short pages.
// ═══════════════════════════════════════════════════════════════════════

export function Footer() {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "14px 2px 0 2px",
        borderTop: "1px solid var(--line)",
        fontSize: 11,
        color: "var(--faint)",
        marginTop: 4,
      }}
    >
      <div style={{ display: "flex", gap: 18 }}>
        <span>Privacy</span>
        <span>Terms</span>
        <span>Help Center</span>
        <span>Feedback</span>
      </div>
      <div className="mono" style={{ letterSpacing: "0.02em" }}>
        © 2026 The Similarity · engine v0.3
      </div>
    </div>
  );
}

// Re-export Fragment for route pages that need a keyed Fragment without
// pulling the React namespace. Keeps the shell's public surface flat.
export { Fragment };
