/**
 * Lumen tweaks panel — floating bottom-right panel with theme controls.
 *
 * Three sections:
 *   - Accent: 5 color swatches (Forest / Sapphire / Sienna / Plum / Ink)
 *   - Background: Painterly / Dusk / Char / Paper radio
 *   - Theme: dark mode toggle
 *
 * The host-protocol postMessage stuff in the original design (used to
 * sync edit mode with claude.ai/design's host iframe) is intentionally
 * removed — we're a normal page on our own domain so there's no host to
 * announce to.
 *
 * Visibility: the panel is collapsed by default (just shows a small button
 * in the corner). Clicking the button expands the panel; clicking the X
 * collapses it again. State is local to this component so the page-level
 * tweak values persist across open/close.
 */
"use client";

import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";

export interface TweakState {
  accent: string;
  background: "painterly" | "dusk" | "charcoal" | "paper";
  dark: boolean;
}

export interface TweaksPanelProps {
  tweaks: TweakState;
  setTweaks: Dispatch<SetStateAction<TweakState>>;
}

const ACCENTS: Array<{ v: string; l: string }> = [
  { v: "#0a6b48", l: "Forest" },
  { v: "#1f5fd6", l: "Sapphire" },
  { v: "#c2410c", l: "Sienna" },
  { v: "#7d3aa9", l: "Plum" },
  { v: "#1a1a1a", l: "Ink" },
];

const BG_OPTIONS: Array<{ value: TweakState["background"]; label: string }> = [
  { value: "painterly", label: "Painterly" },
  { value: "dusk", label: "Dusk" },
  { value: "charcoal", label: "Char" },
  { value: "paper", label: "Paper" },
];

export function TweaksPanel({ tweaks, setTweaks }: TweaksPanelProps) {
  const [open, setOpen] = useState(false);

  // Closed state: a small painterly chip in the corner that opens the panel.
  // Kept very small so it doesn't compete with the main UI when collapsed.
  if (!open) {
    return (
      <button
        className="lumen-tweaks-tab"
        onClick={() => setOpen(true)}
        title="Open tweaks panel"
        aria-label="Open tweaks panel"
      >
        Tweaks
      </button>
    );
  }

  return (
    <div className="lumen-tweaks-panel" role="dialog" aria-label="Tweaks">
      <div className="lumen-tweaks-head">
        <b>Tweaks</b>
        <button
          className="lumen-tweaks-x"
          onClick={() => setOpen(false)}
          aria-label="Close tweaks"
        >
          ×
        </button>
      </div>
      <div className="lumen-tweaks-body">
        {/* Accent section — 5 brand-friendly swatches */}
        <div className="lumen-tweaks-sect">Accent</div>
        <div className="lumen-tweak-swatch-row">
          {ACCENTS.map((a) => (
            <button
              key={a.v}
              className={`lumen-tweak-swatch ${tweaks.accent === a.v ? "is-active" : ""}`}
              style={{ background: a.v }}
              title={a.l}
              aria-label={`Accent ${a.l}`}
              onClick={() => setTweaks((t) => ({ ...t, accent: a.v }))}
            />
          ))}
        </div>

        {/* Background section */}
        <div className="lumen-tweaks-sect">Background</div>
        <div className="lumen-tweaks-radio">
          {BG_OPTIONS.map((o) => (
            <button
              key={o.value}
              className={tweaks.background === o.value ? "is-active" : ""}
              onClick={() =>
                setTweaks((t) => ({ ...t, background: o.value }))
              }
            >
              {o.label}
            </button>
          ))}
        </div>

        {/* Theme section */}
        <div className="lumen-tweaks-sect">Theme</div>
        <div className="lumen-tweaks-toggle-row">
          <span>Dark mode</span>
          <button
            type="button"
            className="lumen-tweaks-toggle"
            data-on={tweaks.dark ? "1" : "0"}
            role="switch"
            aria-checked={tweaks.dark}
            onClick={() => setTweaks((t) => ({ ...t, dark: !t.dark }))}
          >
            <i />
          </button>
        </div>
      </div>
    </div>
  );
}
