/**
 * Lumen command palette — Cmd+K modal with grouped results + arrow nav.
 *
 * Items are grouped under "Navigate" (one entry per Lumen screen) and
 * "Actions" (open external app routes, theme/tweaks toggles). The
 * filter is a case-insensitive substring match on the item label only.
 *
 * Keyboard:
 *   - Esc closes
 *   - Up/Down move the active highlight within the visible filtered list
 *   - Enter runs the highlighted item then closes
 *
 * Architecture note: the modal is split into two pieces — a top-level
 * `CmdK` that early-returns when closed, and an inner `CmdKBody` that
 * holds the query + highlight state. Splitting it this way means each
 * "open" event freshly mounts the body so the state is reset to defaults
 * naturally without an `useEffect(() => setQ('')...)` (which would trip
 * the React Compiler's set-state-in-effect rule). It also keeps the
 * input.focus() call colocated with the input that gets focused.
 *
 * All className strings here use `lumen-` prefixed names so the modal
 * can never be accidentally styled by `app/globals.css`.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { Icon } from "./icons";
import type { ScreenId } from "./screen-types";
import type { TweakState } from "./tweaks";

interface PaletteItem {
  g: string;
  label: string;
  icon: string;
  // Caller decides what running the item does (typically navigate or
  // open an external link).
  run: () => void;
  kbd?: string;
}

export interface CmdKProps {
  open: boolean;
  onClose: () => void;
  onNavigate: (id: ScreenId) => void;
  setTweaks?: Dispatch<SetStateAction<TweakState>>;
}

export function CmdK({ open, onClose, onNavigate, setTweaks }: CmdKProps) {
  // Early-return when closed so React unmounts the body and its state
  // disappears. The next open() will mount a fresh CmdKBody, giving us a
  // pristine query/active state without any explicit reset.
  if (!open) return null;
  return <CmdKBody onClose={onClose} onNavigate={onNavigate} setTweaks={setTweaks} />;
}

interface CmdKBodyProps {
  onClose: () => void;
  onNavigate: (id: ScreenId) => void;
  setTweaks?: Dispatch<SetStateAction<TweakState>>;
}

function CmdKBody({ onClose, onNavigate, setTweaks }: CmdKBodyProps) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Mount-once focus pass. setTimeout(0) defers focus past the React
  // event loop turn that opened the palette, otherwise the original
  // keypress that triggered the open might steal focus back.
  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(t);
  }, []);

  // Open an absolute URL in a new tab. Used by the "Actions" group for
  // routes that live outside /workstation/lumen.
  const openExternal = (href: string) => {
    if (typeof window !== "undefined") {
      window.open(href, "_blank", "noopener,noreferrer");
    }
  };

  // Tweaks are optional — defensive default so the palette still works
  // if the parent forgets to pass `setTweaks`.
  const toggleTheme = () => {
    if (setTweaks) setTweaks((t) => ({ ...t, dark: !t.dark }));
  };

  const items: PaletteItem[] = [
    { g: "Navigate", label: "Retrieve", icon: "target", run: () => onNavigate("retrieve"), kbd: "G R" },
    { g: "Navigate", label: "Runs", icon: "list", run: () => onNavigate("runs"), kbd: "G N" },
    { g: "Navigate", label: "Compare", icon: "grid", run: () => onNavigate("compare"), kbd: "G C" },
    { g: "Navigate", label: "Reviews", icon: "note", run: () => onNavigate("reviews"), kbd: "G V" },
    { g: "Navigate", label: "Dashboard", icon: "pie", run: () => onNavigate("dashboard"), kbd: "G D" },
    { g: "Navigate", label: "Strategy", icon: "trend", run: () => onNavigate("strategy"), kbd: "G S" },
    { g: "Navigate", label: "Cadence", icon: "flow", run: () => onNavigate("cadence"), kbd: "G F" },
    { g: "Navigate", label: "Case Studies", icon: "book", run: () => onNavigate("case-studies"), kbd: "G K" },
    { g: "Navigate", label: "Reports", icon: "receipt", run: () => onNavigate("reports"), kbd: "G P" },
    { g: "Actions", label: "Open full workstation", icon: "link", run: () => openExternal("/workstation") },
    { g: "Actions", label: "View runs in finance app", icon: "list", run: () => openExternal("/finance") },
    { g: "Actions", label: "Toggle theme", icon: "sparkle", run: toggleTheme },
    { g: "Actions", label: "Toggle tweaks panel", icon: "settings", run: () => {
      // Tweaks panel collapse/expand is owned by the panel itself —
      // surface this entry as a discoverability hint. Clicking the
      // panel's own button is still the primary affordance.
    } },
  ];

  const filtered = items.filter((i) =>
    i.label.toLowerCase().includes(q.toLowerCase())
  );
  // Re-bucket the filtered list into its original groups (preserving
  // insertion order).
  const groups: Record<string, PaletteItem[]> = {};
  filtered.forEach((i) => {
    (groups[i.g] = groups[i.g] || []).push(i);
  });

  return (
    <div className="lumen-cmdk-back" onClick={onClose}>
      <div className="lumen-cmdk" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="lumen-cmdk-input"
          placeholder="Type a command, search a screen, or jump to a route…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(filtered.length - 1, a + 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(0, a - 1));
            }
            if (e.key === "Enter" && filtered[active]) {
              filtered[active].run();
              onClose();
            }
          }}
        />
        <div className="lumen-cmdk-list">
          {Object.entries(groups).map(([g, arr]) => (
            <div key={g}>
              <div className="lumen-cmdk-group">{g}</div>
              {arr.map((it) => {
                const idx = filtered.indexOf(it);
                return (
                  <div
                    key={it.label}
                    className={`lumen-cmdk-item ${idx === active ? "is-active" : ""}`}
                    onMouseEnter={() => setActive(idx)}
                    onClick={() => {
                      it.run();
                      onClose();
                    }}
                  >
                    <Icon name={it.icon} />
                    <span>{it.label}</span>
                    {it.kbd && <span className="lumen-kbd">{it.kbd}</span>}
                  </div>
                );
              })}
            </div>
          ))}
          {filtered.length === 0 && (
            <div
              className="lumen-cmdk-item lumen-text-3"
              style={{ justifyContent: "center" }}
            >
              No results
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
