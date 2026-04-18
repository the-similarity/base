"use client";

/**
 * Tweaks floating panel — fixed-position settings panel for live
 * adjustment of theme, analog count (k), forecast horizon, overlay
 * mode, and cone visibility. Toggled via Shift+T or the gear icon.
 */

import { WorkstationSettings } from "./workstation/workstation";

interface TweaksPanelProps {
  settings: WorkstationSettings;
  onSettings: (s: WorkstationSettings) => void;
  visible: boolean;
}

export function TweaksPanel({ settings, onSettings, visible }: TweaksPanelProps) {
  if (!visible) return null;

  const set = (k: keyof WorkstationSettings, v: WorkstationSettings[keyof WorkstationSettings]) =>
    onSettings({ ...settings, [k]: v });

  return (
    <div className="tweaks">
      <div className="tweaks__head">
        <span>Tweaks</span>
        <span style={{ color: "var(--ink-4)", fontSize: 10 }}>live</span>
      </div>
      <div className="tweaks__body">
        <div className="tweaks__row">
          <label>Theme</label>
          <div className="tweaks__segmented">
            {(["light", "dark"] as const).map(t => (
              <button key={t} data-active={settings.theme === t ? "true" : undefined}
                onClick={() => set("theme", t)}>{t}</button>
            ))}
          </div>
        </div>
        <div className="tweaks__row">
          <label>Analogs returned (k)</label>
          <input type="range" min="3" max="10" step="1" value={settings.kAnalogs}
            onChange={e => set("kAnalogs", +e.target.value)} className="tweaks__slider" />
          <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>k = {settings.kAnalogs}</div>
        </div>
        <div className="tweaks__row">
          <label>Forecast horizon (days)</label>
          <input type="range" min="20" max="180" step="5" value={settings.horizon}
            onChange={e => set("horizon", +e.target.value)} className="tweaks__slider" />
          <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>h = {settings.horizon}d</div>
        </div>
        <div className="tweaks__row">
          <label>Overlay</label>
          <div className="tweaks__segmented">
            {([["top3", "Top 3"], ["all", "All"], ["pinned", "Pinned only"]] as const).map(([v, l]) => (
              <button key={v} data-active={settings.showAnalogs === v ? "true" : undefined}
                onClick={() => set("showAnalogs", v)}>{l}</button>
            ))}
          </div>
        </div>
        <div className="tweaks__row">
          <label>Forecast cone</label>
          <div className="tweaks__segmented">
            {([["on", "Show"], ["off", "Hide"]] as const).map(([v, l]) => (
              <button key={v} data-active={(settings.showCone !== false) === (v === "on") ? "true" : undefined}
                onClick={() => set("showCone", v === "on")}>{l}</button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
