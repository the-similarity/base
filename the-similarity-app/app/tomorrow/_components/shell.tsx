"use client";

/**
 * Tomorrow shell — Sidebar, TopBar, PageHeader, and the small presentation
 * helpers (Chip, NavGlyph, DateRangeChip) shared across every
 * /tomorrow route page.
 *
 * Historical context:
 *   These components used to live inline in dashboard.tsx, where the
 *   "nav" was a local useState in <Dashboard/>. With the App Router
 *   refactor we derive the active nav from `usePathname()` so route chrome
 *   is a pure function of the URL.
 *
 * Invariants:
 *   - The shell is shared — every /tomorrow/* page renders inside the same
 *     layout so the sidebar/top-bar don't flash when the user moves
 *     between pages.
 *   - DateRangeChip persists its preset to localStorage under the
 *     `tomorrow:daterange:v1` key (unchanged from dashboard.tsx).
 */

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
// Route helpers
// ═══════════════════════════════════════════════════════════════════════

/**
 * Map between pathname prefixes and sidebar nav ids. The App Router rewrites
 * "/tomorrow" → id "today" so the top-level route is the spiritual landing
 * page; every other id matches its sub-route.
 */
export function navIdForPathname(pathname: string): string {
  if (!pathname.startsWith("/tomorrow")) return "today";
  const rest = pathname.slice("/tomorrow".length);
  if (rest === "" || rest === "/") return "today";
  // Strip leading slash; take the first segment (so /tomorrow/thread/123
  // still resolves to "thread"). This keeps the sidebar highlight stable
  // as Wave 2 agents add deeper per-page routing.
  return rest.replace(/^\//, "").split("/")[0];
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
    experiment: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M4.5 2.5h7M6 2.5v3.2L3.5 12a1.2 1.2 0 001.1 1.6h6.8a1.2 1.2 0 001.1-1.6L10 5.7V2.5" />
        <path d="M5.2 10h5.6" />
      </svg>
    ),
    subscribe: (
      <svg {...common} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 4.5h10v7H3z" />
        <path d="M4.7 7h6.6M5.2 9.5h2.5" />
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
 * Title + subtitle derived from the current pathname. Each /tomorrow/* route
 * gets a sensible page title even when its `page.tsx` is a stub — Wave 2
 * agents can keep this map authoritative or override locally by rendering
 * their own header above the route body.
 */
export function PageHeader() {
  const pathname = usePathname() ?? "/tomorrow";
  const nav = navIdForPathname(pathname);
  const { entries } = useEngine();

  const titleMap: Record<string, { title: string; subtitle: ReactNode }> = {
    today: {
      title: "Today",
      subtitle: "Write what is happening. Tomorrow helps you decide what to do next.",
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
      title: "Similar days",
      subtitle: "Past days that can help explain what today may do next.",
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
    tags: { title: "Themes", subtitle: "The people, work, body, and stress that keep showing up." },
    patterns: { title: "Repeats", subtitle: "What keeps showing up in your saved days." },
    experiment: { title: "Daily read", subtitle: "A short read for today, with clear limits." },
    subscribe: { title: "Tomorrow Pro", subtitle: "$29.99/mo for daily reads, voice notes, and saved-day reminders." },
    engine: { title: "How it works", subtitle: "How Tomorrow turns your writing into a read." },
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
    const v = window.localStorage.getItem("tomorrow:daterange:v1");
    return v === "today" || v === "7d" || v === "30d" ? v : "today";
  });
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem("tomorrow:daterange:v1", preset);
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
// Footer — shared across every tomorrow page so the layout stays visually
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
        © 2026 The Similarity · Tomorrow local preview
      </div>
    </div>
  );
}

// Re-export Fragment for route pages that need a keyed Fragment without
// pulling the React namespace. Keeps the shell's public surface flat.
export { Fragment };
