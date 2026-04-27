/**
 * Lumen command palette — Cmd+K modal with grouped results + arrow nav.
 *
 * Items are grouped under "Navigate", "Actions", and "Ask Lumen". The
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

  const items: PaletteItem[] = [
    { g: "Navigate", label: "Dashboard", icon: "home", run: () => onNavigate("dashboard"), kbd: "G D" },
    { g: "Navigate", label: "Cash Flow", icon: "flow", run: () => onNavigate("cashflow"), kbd: "G F" },
    { g: "Navigate", label: "Insights", icon: "sparkle", run: () => onNavigate("insights"), kbd: "G I" },
    { g: "Navigate", label: "Accounts", icon: "bank", run: () => onNavigate("accounts"), kbd: "G A" },
    { g: "Navigate", label: "Transactions", icon: "list", run: () => onNavigate("transactions"), kbd: "G T" },
    { g: "Navigate", label: "Recurring", icon: "repeat", run: () => onNavigate("recurring"), kbd: "G R" },
    { g: "Navigate", label: "Budgets", icon: "pie", run: () => onNavigate("budgets"), kbd: "G B" },
    { g: "Navigate", label: "Goals", icon: "target", run: () => onNavigate("goals"), kbd: "G G" },
    { g: "Navigate", label: "Investments", icon: "trend", run: () => onNavigate("investments"), kbd: "G V" },
    { g: "Actions", label: "Add transaction", icon: "plus", run: () => {} },
    { g: "Actions", label: "Transfer money", icon: "flow", run: () => {} },
    { g: "Actions", label: "Connect new account", icon: "link", run: () => {} },
    { g: "Actions", label: "New goal", icon: "target", run: () => onNavigate("goals") },
    { g: "Actions", label: "Export CSV", icon: "download", run: () => {} },
    { g: "Ask Lumen", label: "How much did I spend on dining last month?", icon: "sparkle", run: () => onNavigate("insights") },
    { g: "Ask Lumen", label: "When will I hit my house down payment goal?", icon: "sparkle", run: () => onNavigate("insights") },
    { g: "Ask Lumen", label: "Find duplicate subscriptions", icon: "sparkle", run: () => onNavigate("recurring") },
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
    <div className="cmdk-back" onClick={onClose}>
      <div className="cmdk" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="cmdk-input"
          placeholder="Type a command, search a transaction, or ask Lumen…"
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
        <div className="cmdk-list">
          {Object.entries(groups).map(([g, arr]) => (
            <div key={g}>
              <div className="cmdk-group">{g}</div>
              {arr.map((it) => {
                const idx = filtered.indexOf(it);
                return (
                  <div
                    key={it.label}
                    className={`cmdk-item ${idx === active ? "active" : ""}`}
                    onMouseEnter={() => setActive(idx)}
                    onClick={() => {
                      it.run();
                      onClose();
                    }}
                  >
                    <Icon name={it.icon} />
                    <span>{it.label}</span>
                    {it.kbd && <span className="kbd">{it.kbd}</span>}
                  </div>
                );
              })}
            </div>
          ))}
          {filtered.length === 0 && (
            <div
              className="cmdk-item text-3"
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
