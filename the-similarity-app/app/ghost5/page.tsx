"use client";

import { useEffect, useState } from "react";

import { LUMEN_CSS } from "../workstation/lumen/_components/styles";
import { CmdK } from "../workstation/lumen/_components/cmdk";
import { Topbar } from "../workstation/lumen/_components/shared";
import {
  Workstation,
  type WorkstationSettings,
} from "../../components/workstation/workstation";

const GHOST5_DEFAULTS: WorkstationSettings = {
  theme: "light",
  kAnalogs: 20,
  horizon: 40,
  showAnalogs: "all",
  showCone: false,
  chartMode: "candle",
};

export default function Ghost5Page() {
  const [cmdOpen, setCmdOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const [settings, setSettings] = useState<WorkstationSettings>(GHOST5_DEFAULTS);

  const desiredTheme: "dark" | "light" = dark ? "dark" : "light";
  const effectiveSettings: WorkstationSettings =
    settings.theme === desiredTheme
      ? settings
      : { ...settings, theme: desiredTheme };

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCmdOpen((open) => !open);
      }
      if (event.key === "Escape") setCmdOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: LUMEN_CSS }} />
      <div className={`lumen-app${dark ? " dark" : ""}`}>
        <div className="lumen-shell">
          <div className="lumen-main">
            <Topbar
              crumbs={["Workspace", "Ghost5"]}
              actions={<span className="lumen-pill is-pos">$39 / month</span>}
              onCmdK={() => setCmdOpen(true)}
            />
            <div
              className="lumen-workstation-host"
              style={{
                display: "flex",
                flex: 1,
                minHeight: 0,
                overflow: "hidden",
              }}
            >
              <Workstation
                settings={effectiveSettings}
                onSettings={setSettings}
                productMode="ghost5"
              />
            </div>
          </div>
        </div>

        <CmdK
          open={cmdOpen}
          onClose={() => setCmdOpen(false)}
          setDark={setDark}
        />
      </div>
    </>
  );
}
