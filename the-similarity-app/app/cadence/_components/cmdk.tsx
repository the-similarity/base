/**
 * Cadence command palette — Cmd+K modal with grouped results + arrow nav.
 *
 * Items are grouped under "Navigate", "Actions", and "Ask Cadence". The
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
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "./icons";
import type { ScreenId } from "./screen-types";

interface PaletteItem {
  g: string;
  label: string;
  icon: string;
  // Caller decides what running the item does (typically navigate).
  run: () => void;
  kbd?: string;
}

export interface CmdKProps {
  open: boolean;
  onClose: () => void;
  onNavigate: (id: ScreenId) => void;
}

export function CmdK({ open, onClose, onNavigate }: CmdKProps) {
  // Early-return when closed so React unmounts the body and its state
  // disappears. The next open() will mount a fresh CmdKBody, giving us a
  // pristine query/active state without any explicit reset.
  if (!open) return null;
  return <CmdKBody onClose={onClose} onNavigate={onNavigate} />;
}

interface CmdKBodyProps {
  onClose: () => void;
  onNavigate: (id: ScreenId) => void;
}

function CmdKBody({ onClose, onNavigate }: CmdKBodyProps) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Mount-once focus pass. Using setTimeout(0) defers focus past the React
  // event loop turn that opened the palette, otherwise the original
  // keypress that triggered the open might steal focus back.
  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(t);
  }, []);

  // Items reflect the 9-screen nav plus a few action stubs and example
  // rhyme/health-domain natural-language queries. The "Ask Cadence" group
  // routes to /rhymes by default since the rhyme-finder is the primary
  // surface for any narrative question about the user's body.
  const items: PaletteItem[] = [
    { g: "Navigate", label: "Today", icon: "heartPulse", run: () => onNavigate("today"), kbd: "G T" },
    { g: "Navigate", label: "Rhymes", icon: "echoRings", run: () => onNavigate("rhymes"), kbd: "G R" },
    { g: "Navigate", label: "Log", icon: "ledger", run: () => onNavigate("log"), kbd: "G L" },
    { g: "Navigate", label: "Goals", icon: "flag", run: () => onNavigate("goals"), kbd: "G G" },
    { g: "Navigate", label: "Sources", icon: "plug", run: () => onNavigate("sources"), kbd: "G S" },
    { g: "Navigate", label: "Labs", icon: "beaker", run: () => onNavigate("labs"), kbd: "G B" },
    { g: "Actions", label: "Log a workout", icon: "run", run: () => onNavigate("log") },
    { g: "Actions", label: "Log a meal", icon: "fork", run: () => onNavigate("log") },
    { g: "Actions", label: "Log a supplement", icon: "pill", run: () => onNavigate("log") },
    { g: "Actions", label: "Log mood / energy", icon: "zap", run: () => onNavigate("log") },
    { g: "Actions", label: "Connect new wearable", icon: "link", run: () => onNavigate("sources") },
    { g: "Actions", label: "Upload lab results", icon: "download", run: () => onNavigate("labs") },
    { g: "Ask Cadence", label: "When did I last feel this tired?", icon: "sparkle", run: () => onNavigate("rhymes") },
    { g: "Ask Cadence", label: "What pattern preceded my last cold?", icon: "sparkle", run: () => onNavigate("rhymes") },
    { g: "Ask Cadence", label: "How does this week compare to last month?", icon: "sparkle", run: () => onNavigate("rhymes") },
    { g: "Ask Cadence", label: "Am I overtraining?", icon: "sparkle", run: () => onNavigate("rhymes") },
  ];

  const filtered = items.filter((i) =>
    i.label.toLowerCase().includes(q.toLowerCase())
  );
  // Re-bucket the filtered list into its original groups (preserving insertion order).
  const groups: Record<string, PaletteItem[]> = {};
  filtered.forEach((i) => {
    (groups[i.g] = groups[i.g] || []).push(i);
  });

  return (
    <div className="cadence-cmdk-back" onClick={onClose}>
      <div className="cadence-cmdk" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="cadence-cmdk-input"
          placeholder="Type a command, search a metric, or ask Cadence…"
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
        <div className="cadence-cmdk-list">
          {Object.entries(groups).map(([g, arr]) => (
            <div key={g}>
              <div className="cadence-cmdk-group">{g}</div>
              {arr.map((it) => {
                const idx = filtered.indexOf(it);
                return (
                  <div
                    key={it.label}
                    className={`cadence-cmdk-item ${idx === active ? "is-active" : ""}`}
                    onMouseEnter={() => setActive(idx)}
                    onClick={() => {
                      it.run();
                      onClose();
                    }}
                  >
                    <Icon name={it.icon} />
                    <span>{it.label}</span>
                    {it.kbd && <span className="cadence-kbd">{it.kbd}</span>}
                  </div>
                );
              })}
            </div>
          ))}
          {filtered.length === 0 && (
            <div
              className="cadence-cmdk-item cadence-text-3"
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
