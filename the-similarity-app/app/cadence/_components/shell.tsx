"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useEngine } from "./engine-context";

export interface NavItem {
  id: string;
  label: string;
  hint?: string;
}

export function navIdForPathname(pathname: string): string {
  if (!pathname.startsWith("/cadence")) return "today";
  const rest = pathname.slice("/cadence".length);
  if (!rest || rest === "/") return "today";
  return rest.replace(/^\//, "").split("/")[0];
}

function hrefFor(id: string): string {
  return id === "today" ? "/cadence" : `/cadence/${id}`;
}

export function CadenceSidebar() {
  const pathname = usePathname() ?? "/cadence";
  const active = navIdForPathname(pathname);
  const { entries, openComposer } = useEngine();

  const nav: NavItem[] = [
    { id: "today", label: "Today", hint: "Now" },
    { id: "rhymes", label: "Rhymes" },
    { id: "patterns", label: "Patterns" },
    { id: "tags", label: "Contexts" },
    { id: "thread", label: "Thread", hint: "30d" },
    { id: "entries", label: "Ingestion", hint: String(entries.length || "") || undefined },
  ];

  return (
    <aside style={{ width: 250, borderRight: "1px solid var(--cad-line)", padding: 16, background: "#F4F6F8" }}>
      <div style={{ fontSize: 12, color: "var(--cad-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
        Cadence
      </div>
      <h2 style={{ margin: "6px 0 18px", fontSize: 20 }}>Body intelligence</h2>

      <button
        onClick={openComposer}
        style={{ width: "100%", textAlign: "left", padding: "10px 12px", borderRadius: 10, background: "#0F172A", color: "#F8FAFC", fontWeight: 600, marginBottom: 14 }}
      >
        + New health log
      </button>

      <nav style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {nav.map((item) => (
          <Link
            key={item.id}
            href={hrefFor(item.id)}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderRadius: 10,
              padding: "9px 10px",
              textDecoration: "none",
              color: active === item.id ? "#0F172A" : "#374151",
              background: active === item.id ? "#E2E8F0" : "transparent",
              fontWeight: active === item.id ? 600 : 500,
            }}
          >
            <span>{item.label}</span>
            {item.hint ? <span style={{ fontSize: 11, color: "#6B7280" }}>{item.hint}</span> : null}
          </Link>
        ))}
      </nav>
    </aside>
  );
}

export function CadenceTopBar() {
  const now = new Date();
  return (
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
      <div style={{ color: "var(--cad-muted)", fontSize: 13 }}>Health / Rhythm / Personal baseline</div>
      <div style={{ fontSize: 13, color: "var(--cad-muted)" }}>
        {now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
      </div>
    </header>
  );
}

export function CadencePageIntro() {
  const pathname = usePathname() ?? "/cadence";
  const page = navIdForPathname(pathname);

  const copy: Record<string, { title: string; subtitle: string }> = {
    today: {
      title: "Today",
      subtitle: "Understand how your body is trending right now, vs your own baseline.",
    },
    rhymes: {
      title: "Rhymes",
      subtitle: "Find prior periods in your history that look like this week.",
    },
    patterns: {
      title: "Patterns",
      subtitle: "Detect recurring rhythms and slow drifts across your biomarkers.",
    },
    tags: {
      title: "Contexts",
      subtitle: "Track contexts you tag: travel, illness, hard training, fasting, jet lag.",
    },
    thread: {
      title: "Thread",
      subtitle: "Longitudinal timeline for all body signals and logs.",
    },
    entries: {
      title: "Ingestion",
      subtitle: "Connector status, source logs, and manual body-entry composer.",
    },
  };

  const current = copy[page] ?? copy.today;
  return (
    <section style={{ marginBottom: 16 }}>
      <h1 style={{ fontSize: 34, margin: 0, letterSpacing: "-0.02em" }}>{current.title}</h1>
      <p style={{ margin: "8px 0 0", color: "var(--cad-muted)", fontSize: 18 }}>{current.subtitle}</p>
    </section>
  );
}

export function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section style={{ border: "1px solid var(--cad-line)", borderRadius: 16, background: "#F8FAFC", padding: 16 }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 16, fontWeight: 700 }}>{title}</div>
        {subtitle ? <div style={{ fontSize: 12, color: "var(--cad-muted)", marginTop: 3 }}>{subtitle}</div> : null}
      </div>
      {children}
    </section>
  );
}
