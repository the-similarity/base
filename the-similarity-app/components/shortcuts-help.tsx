"use client";

/**
 * Keyboard-shortcuts help modal.
 *
 * Triggered by `?` (Shift+/ on US keyboards) from the root page. Shows a
 * two-column "key -> description" reference, grouped into sections
 * (Navigation, Workstation, Chart).
 *
 * Dismissal rules (all three must work — consistent with command palette):
 *   1. Escape key                     — handled by the parent page's global
 *                                       onKey effect, which calls onClose
 *   2. Click on the translucent backdrop
 *   3. Click on the "Close" button in the card's corner
 *
 * Rendering / lifecycle:
 *   - This component is purely presentational. All keyboard wiring lives in
 *     app/page.tsx so there is a single source of truth for keybindings and
 *     overlay priority (Esc closes cmdk OR help OR tweaks, not all three).
 *   - Returning null when `open` is false keeps the overlay fully unmounted
 *     (no z-index fighting, no trapped focus, no stale aria state).
 *   - Styling is controlled entirely via globals.css classes prefixed with
 *     `.shortcuts-help` so parallel agents can safely edit workstation /
 *     chart styles without cross-contamination.
 *
 * Feature flag awareness:
 *   - When SHOW_PREVIEW is false, only the `g r` jump chord works; listing
 *     the other 5 chords (g e, g s, …) would advertise features the user
 *     cannot reach. The parent passes `showPreviewChords` to gate them.
 *
 * Accessibility:
 *   - role="dialog" + aria-modal + aria-labelledby hooks a screen reader
 *     into the modal title.
 *   - Backdrop click uses a stop-propagation sibling pattern so clicks on
 *     the card itself never bubble up to the backdrop's onClick.
 */

import React from "react";

interface ShortcutsHelpProps {
  /** Whether the modal is mounted and visible. */
  open: boolean;
  /** Callback fired when the user dismisses via backdrop or Close button. */
  onClose: () => void;
  /**
   * When true, the `g` chord map lists all 6 surface letters
   * (r/e/s/v/n/d); when false only `g r` is advertised. Mirrors the
   * SHOW_PREVIEW gate in app/page.tsx.
   */
  showPreviewChords: boolean;
}

// ── Shortcut catalogue ───────────────────────────────────────────────
// Declared as data so the layout is rendered from a single list. Each
// row is rendered as (keys | description) inside a section.
//
// Invariant: the strings here must match the actual bindings in
// app/page.tsx. If a binding is renamed, update both.
interface Row {
  /** Key chips to display. Multiple strings = multi-key chord. */
  keys: string[];
  /** Human-readable description of what the key does. */
  desc: string;
}
interface Section {
  /** Section header (small-caps serif in the modal). */
  title: string;
  rows: Row[];
}

/**
 * Builds the section list. Accepts `showPreviewChords` so we can
 * dynamically include/exclude preview-only chords without re-rendering
 * the entire modal.
 */
function buildSections(showPreviewChords: boolean): Section[] {
  const navRows: Row[] = [
    { keys: ["/"], desc: "Open command palette" },
    { keys: ["Cmd", "K"], desc: "Open command palette" },
    { keys: ["?"], desc: "Show this help" },
    { keys: ["Esc"], desc: "Close any overlay" },
    { keys: ["g", "r"], desc: "Jump to Retrieve surface" },
  ];
  if (showPreviewChords) {
    // Preview surfaces: each chord jumps to one of the 5 editorial mocks.
    // Mirrors jumpMap in app/page.tsx.
    navRows.push({ keys: ["g", "e"], desc: "Jump to Represent" });
    navRows.push({ keys: ["g", "s"], desc: "Jump to Simulate" });
    navRows.push({ keys: ["g", "v"], desc: "Jump to Evaluate" });
    navRows.push({ keys: ["g", "n"], desc: "Jump to Render" });
    navRows.push({ keys: ["g", "d"], desc: "Jump to Decide" });
  }

  const workstationRows: Row[] = [
    { keys: ["Enter"], desc: "Run search" },
    { keys: ["r"], desc: "Run search (alternate)" },
    { keys: ["Shift", "T"], desc: "Toggle tweaks panel" },
    { keys: ["t"], desc: "Toggle light / dark theme" },
  ];

  const chartRows: Row[] = [
    { keys: ["Fast", "Pro"], desc: "Top-right chart-mode toggle" },
    { keys: ["mouse"], desc: "Drag query window in Fast mode" },
  ];

  return [
    { title: "Navigation", rows: navRows },
    { title: "Workstation", rows: workstationRows },
    { title: "Chart", rows: chartRows },
  ];
}

/**
 * Modal component. Returns null when closed to keep the DOM clean.
 *
 * Event flow:
 *   - Click on `.shortcuts-help__overlay` (the backdrop) -> onClose.
 *   - Click on `.shortcuts-help__card` -> stopPropagation keeps it open.
 *   - Click on `.shortcuts-help__close` -> onClose.
 */
export function ShortcutsHelp({ open, onClose, showPreviewChords }: ShortcutsHelpProps) {
  if (!open) return null;

  const sections = buildSections(showPreviewChords);

  return (
    <div
      className="shortcuts-help__overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="shortcuts-help-title"
    >
      <div
        className="shortcuts-help__card"
        // Stop clicks inside the card from reaching the backdrop's handler.
        // Without this, every click inside would dismiss the modal.
        onClick={(e) => e.stopPropagation()}
      >
        <div className="shortcuts-help__header">
          <h2 id="shortcuts-help-title" className="shortcuts-help__title serif">
            Keyboard shortcuts
          </h2>
          <button
            type="button"
            className="shortcuts-help__close"
            aria-label="Close shortcuts help"
            onClick={onClose}
          >
            {/*
             * Minimal X glyph — matches the ~12x12 svg idiom used elsewhere
             * (nav__search, tweaks toggle). Stroke uses currentColor so it
             * tracks the close button's text color across light/dark.
             */}
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.3">
              <line x1="2" y1="2" x2="10" y2="10" />
              <line x1="10" y1="2" x2="2" y2="10" />
            </svg>
          </button>
        </div>

        <div className="shortcuts-help__body">
          {sections.map((section) => (
            <section key={section.title} className="shortcuts-help__section">
              <div className="shortcuts-help__section-title label">{section.title}</div>
              <dl className="shortcuts-help__rows">
                {section.rows.map((row, idx) => (
                  <div key={idx} className="shortcuts-help__row">
                    <dt className="shortcuts-help__keys">
                      {row.keys.map((k, ki) => (
                        <React.Fragment key={ki}>
                          {/*
                           * Every key chip reuses the shared `.kbd` class
                           * defined in globals.css so kbd styling stays
                           * consistent with status-bar hints.
                           */}
                          <span className="kbd">{k}</span>
                          {ki < row.keys.length - 1 && (
                            <span className="shortcuts-help__plus"> </span>
                          )}
                        </React.Fragment>
                      ))}
                    </dt>
                    <dd className="shortcuts-help__desc">{row.desc}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>

        <div className="shortcuts-help__footer label">
          press <span className="kbd">Esc</span> to close
        </div>
      </div>
    </div>
  );
}
