/**
 * Cadence tweaks panel — floating bottom-right panel with theme controls.
 *
 * Three sections:
 *   - Accent: 5 color swatches (Sage / Coral / Indigo / Plum / Ink)
 *     The default is sage, picking up the sage→coral biofeedback look.
 *   - Background: Bloom / Dawn / Paper / Slate radio
 *   - Theme: dark mode toggle
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
  background: "bloom" | "dawn" | "paper" | "slate";
  dark: boolean;
}

export interface TweaksPanelProps {
  tweaks: TweakState;
  setTweaks: Dispatch<SetStateAction<TweakState>>;
}

// Accent palette tuned to health/bio: sage default, warm coral, cool
// indigo, deep plum, neutral ink. Each maps to the page-scoped --accent
// CSS variable (and accent-2 mirrors it for compatibility with anything
// that still reads --accent-2 from the Lumen-style stylesheet).
const ACCENTS: Array<{ v: string; l: string }> = [
  { v: "#5b8a72", l: "Sage" },
  { v: "#c2655c", l: "Coral" },
  { v: "#5a7d9c", l: "Indigo" },
  { v: "#7d3aa9", l: "Plum" },
  { v: "#1a1a1a", l: "Ink" },
];

const BG_OPTIONS: Array<{ value: TweakState["background"]; label: string }> = [
  { value: "bloom", label: "Bloom" },
  { value: "dawn", label: "Dawn" },
  { value: "paper", label: "Paper" },
  { value: "slate", label: "Slate" },
];

export function TweaksPanel({ tweaks, setTweaks }: TweaksPanelProps) {
  const [open, setOpen] = useState(false);

  // Closed state: a small painterly chip in the corner that opens the panel.
  // Kept very small so it doesn't compete with the main UI when collapsed.
  if (!open) {
    return (
      <button
        className="cadence-tweaks-tab"
        onClick={() => setOpen(true)}
        title="Open tweaks panel"
        aria-label="Open tweaks panel"
      >
        Tweaks
      </button>
    );
  }

  return (
    <div className="cadence-tweaks-panel" role="dialog" aria-label="Tweaks">
      <div className="cadence-tweaks-head">
        <b>Tweaks</b>
        <button
          className="cadence-tweaks-x"
          onClick={() => setOpen(false)}
          aria-label="Close tweaks"
        >
          ×
        </button>
      </div>
      <div className="cadence-tweaks-body">
        {/* Accent section — 5 brand-friendly swatches */}
        <div className="cadence-tweaks-sect">Accent</div>
        <div className="tweak-swatch-row">
          {ACCENTS.map((a) => (
            <button
              key={a.v}
              className={`tweak-swatch ${tweaks.accent === a.v ? "active" : ""}`}
              style={{ background: a.v }}
              title={a.l}
              aria-label={`Accent ${a.l}`}
              onClick={() => setTweaks((t) => ({ ...t, accent: a.v }))}
            />
          ))}
        </div>

        {/* Background section */}
        <div className="cadence-tweaks-sect">Background</div>
        <div className="cadence-tweaks-radio">
          {BG_OPTIONS.map((o) => (
            <button
              key={o.value}
              className={tweaks.background === o.value ? "active" : ""}
              onClick={() =>
                setTweaks((t) => ({ ...t, background: o.value }))
              }
            >
              {o.label}
            </button>
          ))}
        </div>

        {/* Theme section */}
        <div className="cadence-tweaks-sect">Theme</div>
        <div className="cadence-tweaks-toggle-row">
          <span>Dark mode</span>
          <button
            type="button"
            className="cadence-tweaks-toggle"
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
