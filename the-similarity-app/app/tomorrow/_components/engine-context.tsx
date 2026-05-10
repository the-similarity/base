"use client";

/**
 * EngineContext — shared journal + composer state for the tomorrow
 * route tree.
 *
 * Why a context:
 *   With the App Router refactor the sidebar, top bar, page header, and each
 *   route page all need access to the same journal entries and the same
 *   composer open/close callbacks. Passing 8 props through the layout into
 *   every child page would be noisy and brittle. A single context provider
 *   mounted at `app/tomorrow/layout.tsx` keeps the wiring to one place.
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
 *   - `compareMode` / `setCompareMode` — the Today chart comparison mode.
 *
 * Invariants:
 *   - The provider mounts EXACTLY once (`app/tomorrow/layout.tsx`). Nested
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

export type CompareMode = "rhyme" | "yesterday" | "none";
const ENTRIES_KEY = "prudent:entries:v1";

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
  // Today chart compare mode
  compareMode: CompareMode;
  setCompareMode: (mode: CompareMode) => void;
}

// Intentionally `null` so consumers crash loudly when used outside the
// provider — we'd rather fail fast than silently return default state.
const EngineContext = createContext<EngineContextValue | null>(null);

export function useEngine(): EngineContextValue {
  const ctx = useContext(EngineContext);
  if (!ctx) {
    throw new Error(
      "useEngine must be used inside <EngineProvider> — mount it from app/tomorrow/layout.tsx",
    );
  }
  return ctx;
}

export function EngineProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [compareMode, setCompareMode] = useState<CompareMode>("rhyme");
  const [entries, setEntries] = useState<StoredEntry[]>(() => loadEntries());
  const [composerOpen, setComposerOpen] = useState(false);
  const [readOnlyEntry, setReadOnlyEntry] = useState<StoredEntry | null>(null);
  const [text, setText] = useState("");

  const reloadEntries = useCallback(() => {
    setEntries(loadEntries());
  }, []);

  const removeEntry = useCallback((id: string) => {
    if (typeof window === "undefined") return;
    try {
      const next = loadEntries().filter((e) => e.id !== id);
      window.localStorage.setItem(ENTRIES_KEY, JSON.stringify(next));
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
    a.download = `tomorrow-entries-${today}.json`;
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
      compareMode,
      setCompareMode,
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
      compareMode,
    ],
  );

  return (
    <EngineContext.Provider value={value}>{children}</EngineContext.Provider>
  );
}
