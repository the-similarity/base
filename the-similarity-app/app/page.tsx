"use client";

import { TerminalProvider } from "../lib/terminal-context";
import { TerminalShell } from "../components/terminal/terminal-shell";
import { DataLoader } from "../components/terminal/data-loader";

export default function Page() {
  return (
    <TerminalProvider>
      <DataLoader />
      <TerminalShell />
    </TerminalProvider>
  );
}
