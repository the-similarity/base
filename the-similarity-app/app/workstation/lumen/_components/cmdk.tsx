/**
 * Lumen command palette — Cmd+K modal with grouped results + arrow nav.
 *
 * The Lumen route is single-screen so the palette is intentionally
 * sparse: a "Workspace" group with a theme toggle and an
 * escape hatch into the standalone /workstation route. There is no
 * "Navigate" group anymore — there is nowhere to navigate to within
 * /workstation/lumen.
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
  setDark?: Dispatch<SetStateAction<boolean>>;
}

export function CmdK({ open, onClose, setDark }: CmdKProps) {
  // Early-return when closed so React unmounts the body and its state
  // disappears. The next open() will mount a fresh CmdKBody, giving us a
  // pristine query/active state without any explicit reset.
  if (!open) return null;
  return <CmdKBody onClose={onClose} setDark={setDark} />;
}

interface CmdKBodyProps {
  onClose: () => void;
  setDark?: Dispatch<SetStateAction<boolean>>;
}

function CmdKBody({ onClose, setDark }: CmdKBodyProps) {
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

  // Theme control is optional so the palette still works if the parent
  // renders it without a route-level dark-mode setter.
  const toggleTheme = () => {
    if (setDark) setDark((value) => !value);
  };

  // Open the standalone Workstation route (the non-Lumen view) in the
  // current tab. This is the escape hatch from the Lumen chrome —
  // useful when a power user wants the full keyboard-shortcut surface
  // that the standalone view exposes.
  const openStandaloneWorkstation = () => {
    if (typeof window !== "undefined") {
      window.open("/workstation", "_self");
    }
  };

  const items: PaletteItem[] = [
    {
      g: "Workspace",
      label: "Toggle theme",
      icon: "sparkle",
      run: toggleTheme,
    },
    {
      g: "Workspace",
      label: "Open full workstation in standalone view",
      icon: "link",
      run: openStandaloneWorkstation,
    },
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
          placeholder="Type a command…"
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
