"use client";

/**
 * Command palette (Cmd+K / slash) — quick navigation between surfaces
 * and toggling theme/tweaks. Filters items as you type, supports
 * arrow-key navigation and Enter to select.
 *
 * Uses a key-based remount pattern to reset state on open, avoiding
 * setState-in-effect and ref-during-render lint issues.
 */

import { useState } from "react";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onNav: (v: string) => void;
  /**
   * Optional callback for the "Open shortcuts help" palette action
   * (added in a following commit). Keeping it optional preserves
   * backward compatibility with any caller that mounts the palette
   * without wiring help — the item is simply hidden in that case.
   */
  onOpenHelp?: () => void;
}

const items = [
  { k: "Go to Retrieve", v: "retrieve", hint: "G R" },
  { k: "Go to Represent", v: "represent", hint: "G E" },
  { k: "Go to Simulate", v: "simulate", hint: "G S" },
  { k: "Go to Evaluate", v: "evaluate", hint: "G V" },
  { k: "Go to Render", v: "render", hint: "G N" },
  { k: "Go to Decide", v: "decide", hint: "G D" },
  { k: "Toggle theme", v: "theme", hint: "T" },
  { k: "Toggle Tweaks", v: "tweaks", hint: "Shift T" },
];

/** Wrapper that controls mounting via open prop */
export function CommandPalette({ open, onClose, onNav }: CommandPaletteProps) {
  if (!open) return null;
  return <CommandPaletteInner onClose={onClose} onNav={onNav} />;
}

/** Inner component — always starts fresh (no stale state from prev open) */
function CommandPaletteInner({ onClose, onNav }: Omit<CommandPaletteProps, "open">) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);

  const filtered = items.filter(i => i.k.toLowerCase().includes(q.toLowerCase()));

  const choose = (v: string) => { onNav(v); onClose(); };

  return (
    <div className="cmdk-overlay" onClick={onClose}>
      <div className="cmdk" onClick={e => e.stopPropagation()}>
        <input className="cmdk__input" autoFocus placeholder="Type a command or surface\u2026"
          value={q} onChange={e => { setQ(e.target.value); setIdx(0); }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && filtered[idx]) choose(filtered[idx].v);
            if (e.key === "ArrowDown") { e.preventDefault(); setIdx(i => Math.min(filtered.length - 1, i + 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setIdx(i => Math.max(0, i - 1)); }
            if (e.key === "Escape") onClose();
          }} />
        <div className="cmdk__list">
          {filtered.map((it, i) => (
            <div key={it.v} className="cmdk__item" data-active={i === idx ? "true" : undefined}
              onMouseEnter={() => setIdx(i)} onClick={() => choose(it.v)}>
              <span>{it.k}</span>
              <span className="label">{it.hint}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
