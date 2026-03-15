"use client";
import { TerminalProvider } from "../lib/terminal-context";
import { TerminalShell } from "../components/terminal/terminal-shell";
import { TerminalDataLoader } from "../components/terminal/data-loader";

export default function Page() {
  return (
    <TerminalProvider>
      <TerminalDataLoader />
      <TerminalShell />
    </TerminalProvider>
  );
}
