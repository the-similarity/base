"use client";

/**
 * Command palette (Cmd+K / slash) — quick navigation between surfaces
 * and triggering workstation actions (run search, pin management,
 * horizon / chart-mode selection) + theme/tweaks/help toggles.
 *
 * Architecture:
 *   - Surface-navigation and theme/tweaks/help toggles are handled by the
 *     parent via the `onNav` and `onOpenHelp` callbacks. The palette does
 *     not know about React state — it only sends intents up.
 *   - Workstation-facing actions (Run search, Pin all top-K, Clear pins,
 *     Set horizon, Chart mode) dispatch DOM CustomEvents on `window`.
 *     This is a deliberate loose-coupling choice: the workstation is not
 *     a direct child of this component, and wiring props down through
 *     page.tsx would couple the palette to the workstation API.
 *   - Event-listener wire-up on the workstation side is deferred to a
 *     later PR (the wave-2 URL-state / workflow PR). Until then the
 *     palette actions fire harmless no-op events.
 *
 * Event contract (see workstation for listener wiring — deferred):
 *   - "ts:run-search"       — no detail. Trigger the Run Search action.
 *   - "ts:pin-all"          — no detail. Pin all current top-K results.
 *   - "ts:clear-pins"       — no detail. Clear the pin set.
 *   - "ts:set-horizon"      — detail: { bars: number }
 *   - "ts:set-chart-mode"   — detail: { mode: "fast" | "pro" }
 *
 * Sections:
 *   Items are grouped under section headers (Navigation / Workstation /
 *   Settings) when the filter is empty or matches multiple sections.
 *   When a filter query is active and only one section has matches, the
 *   header for that section is still shown (keeps context visible as
 *   the user types).
 *
 * Uses a key-based remount pattern (via the wrapper component) to reset
 * internal state on open — avoids setState-in-effect and ref-during-render
 * lint issues.
 */

import { useMemo, useState } from "react";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onNav: (v: string) => void;
  /**
   * Optional callback for the "Open shortcuts help" palette action.
   * Keeping it optional preserves backward compatibility with any caller
   * that mounts the palette without wiring help — the item is simply
   * hidden in that case.
   */
  onOpenHelp?: () => void;
}

/**
 * Item shape:
 *   - k     display label (e.g. "Go to Retrieve")
 *   - hint  right-aligned key hint (e.g. "G R")
 *   - kind  discriminator for how `choose` dispatches:
 *             "nav"    — call onNav(v)
 *             "event"  — dispatch a window CustomEvent named `event`
 *             "help"   — call onOpenHelp (if provided)
 *   - v      value passed to onNav (only meaningful for "nav")
 *   - event  custom-event name (only meaningful for "event")
 *   - detail optional CustomEvent.detail payload
 *   - section section-header label this item belongs to
 */
interface Item {
  k: string;
  hint: string;
  kind: "nav" | "event" | "help";
  v?: string;
  event?: string;
  detail?: Record<string, unknown>;
  section: "Navigation" | "Workstation" | "Settings";
}

// ── Item catalogue ──────────────────────────────────────────────────
// Declared once at module scope so filter runs don't rebuild this on
// every keystroke. The ordering here IS the display order: sections
// are implicit — we render a header whenever the section changes.
const items: Item[] = [
  // Navigation — jump between surfaces. `g <letter>` chord hint echoes
  // the keyboard bindings defined in app/page.tsx.
  { k: "Go to Retrieve",  v: "retrieve",  hint: "G R", kind: "nav", section: "Navigation" },
  { k: "Go to Represent", v: "represent", hint: "G E", kind: "nav", section: "Navigation" },
  { k: "Go to Simulate",  v: "simulate",  hint: "G S", kind: "nav", section: "Navigation" },
  { k: "Go to Evaluate",  v: "evaluate",  hint: "G V", kind: "nav", section: "Navigation" },
  { k: "Go to Render",    v: "render",    hint: "G N", kind: "nav", section: "Navigation" },
  { k: "Go to Decide",    v: "decide",    hint: "G D", kind: "nav", section: "Navigation" },

  // Workstation — operate on the analogue search surface.
  //
  // Run search mirrors the `r` / Enter shortcuts inside the workstation
  // (PR #225). Dispatching an event keeps the palette surface-agnostic —
  // the listener on the workstation side is added in a later PR.
  { k: "Run search",        hint: "Enter", kind: "event", event: "ts:run-search",  section: "Workstation" },
  { k: "Pin all top-K",     hint: "",      kind: "event", event: "ts:pin-all",     section: "Workstation" },
  { k: "Clear pins",        hint: "",      kind: "event", event: "ts:clear-pins",  section: "Workstation" },

  // Horizon presets — mirror the values exposed by the visible horizon
  // selector (PR #226). detail.bars is the forecast-horizon bar count.
  { k: "Set horizon · 60d",  hint: "",  kind: "event", event: "ts:set-horizon", detail: { bars: 60  }, section: "Workstation" },
  { k: "Set horizon · 120d", hint: "",  kind: "event", event: "ts:set-horizon", detail: { bars: 120 }, section: "Workstation" },
  { k: "Set horizon · 180d", hint: "",  kind: "event", event: "ts:set-horizon", detail: { bars: 180 }, section: "Workstation" },
  { k: "Set horizon · 250d", hint: "",  kind: "event", event: "ts:set-horizon", detail: { bars: 250 }, section: "Workstation" },
  { k: "Set horizon · 365d", hint: "",  kind: "event", event: "ts:set-horizon", detail: { bars: 365 }, section: "Workstation" },

  // Chart-mode toggle — fast (canvas) vs pro (lightweight-charts, PR #227).
  { k: "Chart mode · Fast", hint: "", kind: "event", event: "ts:set-chart-mode", detail: { mode: "fast" }, section: "Workstation" },
  { k: "Chart mode · Pro",  hint: "", kind: "event", event: "ts:set-chart-mode", detail: { mode: "pro"  }, section: "Workstation" },

  // Settings — theme / tweaks / help.
  { k: "Toggle theme",         v: "theme",  hint: "T",       kind: "nav",  section: "Settings" },
  { k: "Toggle Tweaks",        v: "tweaks", hint: "Shift T", kind: "nav",  section: "Settings" },
  { k: "Open shortcuts help",               hint: "?",       kind: "help", section: "Settings" },
];

/** Wrapper that controls mounting via open prop. */
export function CommandPalette({ open, onClose, onNav, onOpenHelp }: CommandPaletteProps) {
  if (!open) return null;
  return <CommandPaletteInner onClose={onClose} onNav={onNav} onOpenHelp={onOpenHelp} />;
}

/** Inner component — always starts fresh (no stale state from previous open). */
function CommandPaletteInner({ onClose, onNav, onOpenHelp }: Omit<CommandPaletteProps, "open">) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);

  /*
   * Filter pipeline:
   *   1. Case-insensitive substring match against the display label.
   *   2. Drop the "Open shortcuts help" row if onOpenHelp is not wired —
   *      invoking a missing handler would be a silent no-op, which is
   *      worse than never showing the option.
   *
   * useMemo keeps the filtered list stable across keystrokes that don't
   * change q or the handler, which matters for the idx-based selection
   * highlight (no flicker on repeated renders).
   */
  const filtered = useMemo(() => {
    const needle = q.toLowerCase();
    return items
      .filter(i => i.kind !== "help" || !!onOpenHelp)
      .filter(i => i.k.toLowerCase().includes(needle));
  }, [q, onOpenHelp]);

  /**
   * Dispatch the effect of selecting an item. Centralized so keyboard
   * (Enter) and mouse (click) paths share identical behavior.
   */
  const choose = (item: Item) => {
    if (item.kind === "nav" && item.v) {
      onNav(item.v);
    } else if (item.kind === "event" && item.event) {
      /*
       * Dispatch on window so any listener (workstation, tests, future
       * telemetry) can subscribe. CustomEvent is safe in all modern
       * browsers and Next's SSR env (we only dispatch from onClick /
       * onKeyDown, which never runs on the server).
       */
      window.dispatchEvent(new CustomEvent(item.event, { detail: item.detail }));
    } else if (item.kind === "help" && onOpenHelp) {
      onOpenHelp();
    }
    onClose();
  };

  return (
    <div className="cmdk-overlay" onClick={onClose}>
      <div className="cmdk" onClick={e => e.stopPropagation()}>
        <input className="cmdk__input" autoFocus placeholder="Type a command or surface\u2026"
          value={q} onChange={e => { setQ(e.target.value); setIdx(0); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && filtered[idx]) choose(filtered[idx]);
            if (e.key === "ArrowDown") { e.preventDefault(); setIdx(i => Math.min(filtered.length - 1, i + 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setIdx(i => Math.max(0, i - 1)); }
            if (e.key === "Escape") onClose();
          }} />
        <div className="cmdk__list">
          {/*
           * Render pass with section headers.
           *
           * We walk the filtered list in order; whenever the section
           * changes from the previous item we emit a header row. This
           * preserves the declared ordering in `items` without a
           * secondary group-by pass and without stable-sort worries.
           */}
          {filtered.map((it, i) => {
            const prev = filtered[i - 1];
            const showHeader = !prev || prev.section !== it.section;
            return (
              <div key={`${it.section}:${it.k}`}>
                {showHeader && (
                  <div className="cmdk__section label">{it.section}</div>
                )}
                <div className="cmdk__item" data-active={i === idx ? "true" : undefined}
                  onMouseEnter={() => setIdx(i)} onClick={() => choose(it)}>
                  <span>{it.k}</span>
                  {it.hint && <span className="label">{it.hint}</span>}
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && (
            <div className="cmdk__empty label">No matches</div>
          )}
        </div>
      </div>
    </div>
  );
}
