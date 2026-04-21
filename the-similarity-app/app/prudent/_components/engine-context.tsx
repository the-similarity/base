"use client";

/**
 * EngineContext — shared journal + composer + tweaks state for the prudent
 * route tree.
 *
 * Why a context:
 *   With the App Router refactor the sidebar, top bar, page header, and each
 *   route page all need access to the same journal entries and the same
 *   composer open/close callbacks. Passing 8 props through the layout into
 *   every child page would be noisy and brittle. A single context provider
 *   mounted at `app/prudent/layout.tsx` keeps the wiring to one place.
 *
 * What lives here:
 *   - `entries` — the persisted StoredEntry[] loaded from localStorage.
 *   - `reloadEntries` — re-read storage; call after save or delete.
 *   - `openComposer` — opens the composer modal with an empty draft.
 *   - `openReadOnly` — opens the composer as a viewer for a past entry.
 *   - `exportEntries` — download every stored entry as a JSON blob.
 *   - `removeEntry` — delete a single entry by id and reload storage.
 *   - `text` / `setText` — the current composer draft (shared so sub-pages
 *     can display live-parsed state without re-hosting the textarea).
 *   - `tweaks` / `setTweak` — the persisted UI tweak bag (accent/theme/compare).
 *
 * Invariants:
 *   - The provider mounts EXACTLY once (`app/prudent/layout.tsx`). Nested
 *     providers would fork the storage read and cause drift.
 *   - All storage writes go through the provider so `entries` in state is
 *     always the source of truth for the next render.
 *   - SSR-safe: the provider guards every localStorage access with
 *     `typeof window !== "undefined"` so Next can render the first frame
 *     on the server without crashing.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  loadEntries,
  saveEntry,
  exportEntriesAsJSON,
  type StoredEntry,
} from "../storage";

// Tweaks shape — mirrored from the dashboard; we keep the palette here so the
// context can persist + emit accent variables to the root element.
export type Accent = "blue" | "ember" | "teal" | "plum";
export type Theme = "light" | "dark";
export type CompareMode = "rhyme" | "yesterday" | "none";

export interface Tweaks {
  accent: Accent;
  density: "comfortable" | "compact";
  theme: Theme;
  compare: CompareMode;
}

const TWEAK_DEFAULTS: Tweaks = {
  accent: "blue",
  density: "comfortable",
  theme: "light",
  compare: "rhyme",
};

const TWEAKS_KEY = "prudent:tweaks:v1";

// Lazy initializer for tweaks. Mirrors the original dashboard helper so a
// cross-session polished layout is preserved through the refactor.
function loadTweaks(): Tweaks {
  if (typeof window === "undefined") return TWEAK_DEFAULTS;
  try {
    const raw = window.localStorage.getItem(TWEAKS_KEY);
    if (!raw) return TWEAK_DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Tweaks>;
    return {
      accent: (["blue", "ember", "teal", "plum"] as const).includes(
        parsed.accent as Accent,
      )
        ? (parsed.accent as Accent)
        : TWEAK_DEFAULTS.accent,
      density:
        parsed.density === "comfortable" || parsed.density === "compact"
          ? parsed.density
          : TWEAK_DEFAULTS.density,
      theme:
        parsed.theme === "light" || parsed.theme === "dark"
          ? parsed.theme
          : TWEAK_DEFAULTS.theme,
      compare:
        parsed.compare === "rhyme" ||
        parsed.compare === "yesterday" ||
        parsed.compare === "none"
          ? parsed.compare
          : TWEAK_DEFAULTS.compare,
    };
  } catch {
    return TWEAK_DEFAULTS;
  }
}

// Accent + soft companion palette, re-exported so the layout and the today
// view can paint the prudent-root CSS variables without importing from the
// old dashboard module.
export const ACCENT_HEX: Record<Accent, string> = {
  blue: "#3B82F6",
  ember: "#EA580C",
  teal: "#0E7490",
  plum: "#7C3AED",
};
export const ACCENT_SOFT_HEX: Record<Accent, string> = {
  blue: "#93C5FD",
  ember: "#FDBA74",
  teal: "#67E8F9",
  plum: "#C4B5FD",
};

export interface EngineContextValue {
  // Journal
  entries: StoredEntry[];
  reloadEntries: () => void;
  removeEntry: (id: string) => void;
  // Composer
  composerOpen: boolean;
  readOnlyEntry: StoredEntry | null;
  openComposer: () => void;
  openReadOnly: (entry: StoredEntry) => void;
  closeComposer: () => void;
  persistEntry: (draft: {
    text: string;
    events: StoredEntry["events"];
    series: StoredEntry["series"];
    avg: number;
  }) => void;
  // Draft text shared between route pages (so sub-pages can peek at the
  // composer's parsed state without hosting the textarea).
  text: string;
  setText: (t: string) => void;
  // Export
  exportEntries: () => void;
  // Tweaks
  tweaks: Tweaks;
  setTweak: <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => void;
}

// Intentionally `null` so consumers crash loudly when used outside the
// provider — we'd rather fail fast than silently return default state.
const EngineContext = createContext<EngineContextValue | null>(null);

export function useEngine(): EngineContextValue {
  const ctx = useContext(EngineContext);
  if (!ctx) {
    throw new Error(
      "useEngine must be used inside <EngineProvider> — mount it from app/prudent/layout.tsx",
    );
  }
  return ctx;
}

export function EngineProvider({
  children,
  rootRef,
}: {
  children: ReactNode;
  // The provider pushes accent/theme CSS variables onto the prudent-root
  // element. Layout owns the ref so styles stay scoped to /prudent and
  // never pollute the workstation theme.
  rootRef: React.RefObject<HTMLDivElement | null>;
}) {
  const [tweaks, setTweaks] = useState<Tweaks>(() => loadTweaks());
  const [entries, setEntries] = useState<StoredEntry[]>(() => loadEntries());
  const [composerOpen, setComposerOpen] = useState(false);
  const [readOnlyEntry, setReadOnlyEntry] = useState<StoredEntry | null>(null);
  const [text, setText] = useState("");

  // Paint the accent / theme onto the root element as CSS variables. We
  // mutate the DOM directly rather than rendering inline style props because
  // the variables need to cascade to every child SVG/chart, and inline
  // style props would not propagate through <style> blocks.
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    el.style.setProperty("--accent", ACCENT_HEX[tweaks.accent]);
    el.style.setProperty("--accent-mid", ACCENT_SOFT_HEX[tweaks.accent]);
    el.classList.toggle("prudent-dark", tweaks.theme === "dark");
  }, [rootRef, tweaks.accent, tweaks.theme]);

  // Persist tweaks whenever they change (best-effort — quota errors swallowed).
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(TWEAKS_KEY, JSON.stringify(tweaks));
    } catch {
      /* swallow */
    }
  }, [tweaks]);

  const setTweak = useCallback(
    <K extends keyof Tweaks>(k: K, v: Tweaks[K]) => {
      setTweaks((prev) => ({ ...prev, [k]: v }));
    },
    [],
  );

  const reloadEntries = useCallback(() => {
    setEntries(loadEntries());
  }, []);

  const removeEntry = useCallback((id: string) => {
    if (typeof window === "undefined") return;
    try {
      const next = loadEntries().filter((e) => e.id !== id);
      window.localStorage.setItem("prudent:entries:v1", JSON.stringify(next));
      setEntries(next);
    } catch {
      /* swallow */
    }
  }, []);

  const openComposer = useCallback(() => {
    setReadOnlyEntry(null);
    setText("");
    setComposerOpen(true);
  }, []);

  const openReadOnly = useCallback((entry: StoredEntry) => {
    setReadOnlyEntry(entry);
    setComposerOpen(true);
  }, []);

  const closeComposer = useCallback(() => {
    setComposerOpen(false);
    setReadOnlyEntry(null);
  }, []);

  const persistEntry: EngineContextValue["persistEntry"] = useCallback(
    ({ text: t, events, series, avg }) => {
      if (!t.trim()) {
        setComposerOpen(false);
        return;
      }
      const entry: StoredEntry = {
        id: `entry-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        createdAt: new Date().toISOString(),
        day: 0,
        text: t,
        events,
        series,
        avg,
      };
      saveEntry(entry);
      setEntries(loadEntries());
      setText("");
      setComposerOpen(false);
      setReadOnlyEntry(null);
    },
    [],
  );

  const exportEntries = useCallback(() => {
    if (typeof window === "undefined") return;
    const json = exportEntriesAsJSON();
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const today = new Date().toISOString().slice(0, 10);
    const a = document.createElement("a");
    a.href = url;
    a.download = `prudent-entries-${today}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, []);

  // Keyboard shortcut: ⌘/Ctrl+N opens the composer; Escape closes. We mount
  // one global listener at the provider so pages don't need to re-install it.
  // Use a ref to keep the callbacks stable — the listener never re-binds.
  const openRef = useRef(openComposer);
  const closeRef = useRef(closeComposer);
  openRef.current = openComposer;
  closeRef.current = closeComposer;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isNew = (e.metaKey || e.ctrlKey) && (e.key === "n" || e.key === "N");
      if (isNew) {
        e.preventDefault();
        openRef.current();
      }
      if (e.key === "Escape") {
        closeRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo<EngineContextValue>(
    () => ({
      entries,
      reloadEntries,
      removeEntry,
      composerOpen,
      readOnlyEntry,
      openComposer,
      openReadOnly,
      closeComposer,
      persistEntry,
      text,
      setText,
      exportEntries,
      tweaks,
      setTweak,
    }),
    [
      entries,
      reloadEntries,
      removeEntry,
      composerOpen,
      readOnlyEntry,
      openComposer,
      openReadOnly,
      closeComposer,
      persistEntry,
      text,
      exportEntries,
      tweaks,
      setTweak,
    ],
  );

  return (
    <EngineContext.Provider value={value}>{children}</EngineContext.Provider>
  );
}
